"""Schwab V1.2: one process, RAM snapshots, Keychain credentials, no write retries."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import re
import secrets
import sys
import time
import webbrowser
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

# 01 Configuration ------------------------------------------------------------
HOST, PORT = "127.0.0.1", 5678
CLIENT_ID = "v9AsFvKCeMiA1J2yiG60jAtBAvKsSjLLOIkpUr1zthIusYGJ"  # 填入 Schwab App Key
CALLBACK_URL = "https://127.0.0.1"
ACCOUNT_HASH = ""  # 单账户留空；多个账户时填固定 hash
MAX_ORDER_AMOUNT_USD = Decimal("45000")  # 仅限制买入
MAX_LOSS_PER_TRADE_USD = Decimal("2000")
MAX_STOP_LOSS_RATIO = Decimal("0.15")
BREAKOUT_OFFSET = Decimal("0.01")
ALLOWED_ORIGINS = {"http://127.0.0.1:3000", "http://127.0.0.1:5678"}
API = "https://api.schwabapi.com"
TOKEN_URL = f"{API}/v1/oauth/token"
AUTHORIZE_URL = f"{API}/v1/oauth/authorize"
TOKEN_REFRESH_MARGIN_SECONDS = 60
INIT_RETRY_SECONDS = 5
KEYCHAIN_SERVICE = "schwab-minimum-trader"
LOG = logging.getLogger("schwab_backend")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def decimal_value(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def decimal_text(value: Any) -> str | None:
    parsed = decimal_value(value)
    return format(parsed, "f") if parsed is not None else None


def positive(value: Any) -> Decimal | None:
    parsed = decimal_value(value)
    return parsed if parsed is not None and parsed > 0 else None


def symbol_value(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9./-]*", value):
        raise ValueError("Symbol 格式无效")
    return value


# 02 Data Models --------------------------------------------------------------
class BackendError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        self.status, self.code, self.message, self.details = status, code, message, details
        super().__init__(code)

    def body(self) -> dict:
        return {
            "result": "unknown" if self.code == "ORDER_RESULT_UNKNOWN" else "error",
            "error": {"code": self.code, "message": self.message, "details": self.details},
        }


def unknown() -> BackendError:
    return BackendError(504, "ORDER_RESULT_UNKNOWN", "订单结果未确认，请人工核对；禁止自动重发")


def conflict(message: str = "订单操作冲突，请核对当前订单") -> BackendError:
    return BackendError(409, "ORDER_CONFLICT", message)


def unavailable() -> BackendError:
    return BackendError(503, "SCHWAB_UNAVAILABLE", "Schwab 暂时不可用")


def auth_required() -> BackendError:
    return BackendError(503, "AUTH_REQUIRED", "请运行 auth 完成 Schwab 授权")


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketRequest(StrictRequest):
    symbol: str
    qty: Annotated[StrictInt, Field(gt=0)]

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return symbol_value(value)


class BreakoutRequest(MarketRequest):
    buy_stop: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    sell_stop: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]

    @field_validator("buy_stop", "sell_stop", mode="before")
    @classmethod
    def decimal_input(cls, value: Any) -> Any:
        if not isinstance(value, (str, Decimal)):
            raise ValueError("价格必须是十进制字符串")
        return value


class ReplaceRequest(StrictRequest):
    new_stop: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]

    @field_validator("new_stop", mode="before")
    @classmethod
    def decimal_input(cls, value: Any) -> Any:
        return BreakoutRequest.decimal_input(value)


def order_id_value(value: str | int) -> str:
    value = str(value)
    if not re.fullmatch(r"[0-9]+", value) or int(value) <= 0:
        raise BackendError(422, "VALIDATION_FAILED", "Order ID 必须是正整数字符串")
    return str(int(value))


def decode_response(response: httpx.Response) -> Any:
    try:
        return json.loads(response.content, parse_float=Decimal)
    except (ValueError, UnicodeError):
        raise unavailable() from None


# 03 Keychain & OAuth ---------------------------------------------------------
@dataclass(repr=False)
class Credentials:
    access_token: str
    refresh_token: str
    expiration: float


class KeychainStore:
    """Explicit native backend: never fall back to a plaintext keyring."""

    @staticmethod
    def backend():
        if sys.platform != "darwin":
            raise RuntimeError("凭据存储要求 macOS Keychain")
        from keyring.backends.macOS import Keyring

        return Keyring()

    def secret(self) -> str | None:
        return self.backend().get_password(KEYCHAIN_SERVICE, "client_secret")

    def set_secret(self, value: str) -> None:
        self.backend().set_password(KEYCHAIN_SERVICE, "client_secret", value)

    def load(self) -> Credentials | None:
        value = self.backend().get_password(KEYCHAIN_SERVICE, "oauth_tokens")
        return Credentials(**json.loads(value)) if value else None

    def save(self, credentials: Credentials) -> None:
        self.backend().set_password(KEYCHAIN_SERVICE, "oauth_tokens", json.dumps(vars(credentials)))

    def clear(self) -> None:
        self.backend().delete_password(KEYCHAIN_SERVICE, "oauth_tokens")


class TokenManager:
    def __init__(self, store: KeychainStore, http: httpx.AsyncClient):
        self.store, self.http = store, http
        self.token_refresh_lock = asyncio.Lock()
        self.credentials: Credentials | None = None
        self.status = "auth_required"

    def valid(self) -> bool:
        return (
            self.credentials is not None
            and self.credentials.expiration > time.time() + TOKEN_REFRESH_MARGIN_SECONDS
        )

    async def token(self) -> str:
        if self.valid():
            self.status = "valid"
            return self.credentials.access_token
        async with self.token_refresh_lock:
            try:
                if self.credentials is None:
                    self.credentials = await asyncio.to_thread(self.store.load)
                if self.valid():
                    self.status = "valid"
                    return self.credentials.access_token
                if self.credentials is None or not CLIENT_ID:
                    raise auth_required()
                self.status = "refreshing"
                secret = await asyncio.to_thread(self.store.secret)
                if not secret:
                    raise auth_required()
                response = await self.http.post(
                    TOKEN_URL,
                    auth=(CLIENT_ID, secret),
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self.credentials.refresh_token,
                    },
                )
                if response.status_code in {400, 401, 403}:
                    await asyncio.to_thread(self.store.clear)
                    raise auth_required()
                if response.status_code != 200:
                    raise unavailable()
                credentials = self.parse_tokens(response, self.credentials.refresh_token)
                await asyncio.to_thread(self.store.save, credentials)
                self.credentials = credentials
                self.status = "valid"
                return credentials.access_token
            except BackendError as error:
                if error.code == "AUTH_REQUIRED":
                    self.credentials = None
                    self.status = "auth_required"
                else:
                    self.status = "valid"
                raise
            except httpx.HTTPError:
                self.status = "valid"
                raise unavailable() from None
            except Exception as error:
                LOG.warning("Keychain 访问失败 (%s): %s", type(error).__name__, error)
                self.credentials = None
                self.status = "auth_required"
                raise auth_required() from None

    @staticmethod
    def parse_tokens(response: httpx.Response, previous_refresh: str = "") -> Credentials:
        data = decode_response(response)
        expires = positive(data.get("expires_in"))
        if (
            not expires
            or not data.get("access_token")
            or not data.get("refresh_token", previous_refresh)
        ):
            raise unavailable()
        return Credentials(
            data["access_token"],
            data.get("refresh_token", previous_refresh),
            time.time() + float(expires),
        )

    def invalidate(self, access_token: str) -> None:
        if self.credentials and self.credentials.access_token == access_token:
            self.credentials.expiration = 0


def authorization_url(state: str) -> str:
    return (
        AUTHORIZE_URL
        + "?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": CLIENT_ID,
                "redirect_uri": CALLBACK_URL,
                "state": state,
            }
        )
    )


def callback_code(callback: str, expected_state: str) -> str:
    parsed, expected = urlsplit(callback.strip()), urlsplit(CALLBACK_URL)
    # Browsers serialize an empty HTTPS path as '/'; both identify the root.
    if (parsed.scheme, parsed.netloc, parsed.path or "/") != (
        expected.scheme,
        expected.netloc,
        expected.path or "/",
    ):
        raise ValueError("Callback URL 与配置不匹配")
    query = parse_qs(parsed.query)
    states, codes = query.get("state", []), query.get("code", [])
    if (
        len(states) != 1
        or not secrets.compare_digest(states[0], expected_state)
        or len(codes) != 1
        or "error" in query
    ):
        raise ValueError("OAuth state 或 Authorization Code 无效")
    return codes[0]


# 04 Schwab REST Client -------------------------------------------------------
class SchwabREST:
    def __init__(self, tokens: TokenManager, http: httpx.AsyncClient):
        self.tokens, self.http = tokens, http
        self.account_hash: str | None = None
        self.account_number: str | None = None
        self.failures: set[str] = set()

    @property
    def status(self) -> str:
        return "unavailable" if self.failures else "connected"

    def account_path(self, suffix: str = "") -> str:
        if not self.account_hash:
            raise unavailable()
        return f"/trader/v1/accounts/{self.account_hash}{suffix}"

    async def request(self, method: str, path: str, *, params=None, payload=None) -> httpx.Response:
        writing = method != "GET"
        access = await self.tokens.token()
        try:
            headers = {"Authorization": f"Bearer {access}"}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            response = await self.http.request(
                method,
                API + path,
                params=params,
                content=json.dumps(payload, default=decimal_text) if payload is not None else None,
                headers=headers,
            )
            # Only reads may refresh-and-retry after an explicit 401.
            if response.status_code == 401:
                self.tokens.invalidate(access)
                if not writing:
                    access = await self.tokens.token()
                    response = await self.http.request(
                        method,
                        API + path,
                        params=params,
                        headers={"Authorization": f"Bearer {access}"},
                    )
            if response.status_code == 401:
                self.tokens.invalidate(access)
                raise auth_required()
            if response.status_code >= 500 or response.status_code in {408, 429}:
                if writing and response.status_code != 429:
                    raise unknown()
                raise unavailable()
            if response.status_code == 404:
                raise BackendError(404, "NOT_FOUND", "Schwab 资源不存在")
            if not 200 <= response.status_code < 300:
                details = {"http_status": response.status_code}
                # Error-body parsing must not mask the original HTTP rejection.
                with suppress(ValueError):
                    body = response.json()
                    if isinstance(body, dict):
                        broker_error = {
                            key: body[key] for key in ("message", "errors") if key in body
                        }
                        if broker_error:
                            details["broker_error"] = broker_error
                raise BackendError(502, "SCHWAB_REJECTED", "Schwab 拒绝请求", details)
            self.failures.discard(path)
            return response
        except httpx.HTTPError:
            self.failures.add(path)
            raise (unknown() if writing else unavailable()) from None
        except asyncio.CancelledError:
            if writing:
                # Cancellation after dispatch cannot prove that Schwab didn't accept it.
                self.failures.add(path)
                raise unknown() from None
            raise
        except BackendError as error:
            if error.code in {"SCHWAB_UNAVAILABLE", "ORDER_RESULT_UNKNOWN"}:
                self.failures.add(path)
            raise

    async def get(self, path: str, params=None) -> Any:
        return decode_response(await self.request("GET", path, params=params))

    async def initialize_account(self) -> None:
        accounts = await self.get("/trader/v1/accounts/accountNumbers")
        if not accounts:
            raise unavailable()
        matches = [a for a in accounts if a.get("hashValue") == ACCOUNT_HASH]
        if ACCOUNT_HASH:
            if len(matches) != 1:
                raise BackendError(400, "BAD_REQUEST", "ACCOUNT_HASH 不在当前授权账户中")
            selected = matches[0]
        elif len(accounts) == 1:
            selected = accounts[0]
        else:
            raise BackendError(400, "BAD_REQUEST", "多个账户：请在代码顶部固定 ACCOUNT_HASH")
        self.account_hash = selected["hashValue"]
        self.account_number = str(selected["accountNumber"])

    async def quote(self, symbol: str) -> dict:
        data = await self.get("/marketdata/v1/quotes", {"symbols": symbol, "fields": "quote"})
        if symbol not in data:
            raise BackendError(404, "NOT_FOUND", "Schwab 未返回此 Symbol 的报价")
        return data[symbol]

    async def orders(self) -> list:
        now = datetime.now(UTC)
        return await self.get(
            self.account_path("/orders"),
            {
                "fromEnteredTime": (now - timedelta(days=59)).isoformat(),
                "toEnteredTime": now.isoformat(),
            },
        )

    async def order(self, order_id: str) -> dict:
        return await self.get(self.account_path(f"/orders/{order_id}"))


# 05 Schwab Streaming Client --------------------------------------------------
class StreamFailure(Exception):
    pass


class SchwabStream:
    def __init__(self, runtime: Runtime):
        self.runtime = runtime
        self.socket = None
        self.info: dict = {}
        self.pending: dict[str, asyncio.Future] = {}
        self.request_id = 0
        self.subscription_lock = asyncio.Lock()
        self.active_symbols: set[str] = set()
        self.logged_in = False
        self.connected_at = 0.0

    async def command(self, service: str, command: str, parameters: dict) -> None:
        self.request_id += 1
        request_id = str(self.request_id)
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.socket.send(
                json.dumps(
                    {
                        "requests": [
                            {
                                "service": service,
                                "command": command,
                                "requestid": request_id,
                                "SchwabClientCustomerId": self.info["schwabClientCustomerId"],
                                "SchwabClientCorrelId": self.info["schwabClientCorrelId"],
                                "parameters": parameters,
                            }
                        ]
                    }
                )
            )
            await asyncio.wait_for(future, timeout=15)
        finally:
            self.pending.pop(request_id, None)

    async def subscribe_symbols(self) -> None:
        async with self.subscription_lock:
            if not self.logged_in:
                return
            missing = self.runtime.state.subscribed_symbols - self.active_symbols
            if not missing:
                return
            await self.command(
                "LEVELONE_EQUITIES",
                "ADD" if self.active_symbols else "SUBS",
                {"keys": ",".join(sorted(missing)), "fields": "0,1,2"},
            )
            self.active_symbols.update(missing)

    async def receive(self) -> None:
        try:
            async for raw in self.socket:
                try:
                    message = json.loads(raw, parse_float=Decimal)
                except ValueError:
                    raise StreamFailure() from None
                for response in message.get("response", []):
                    future = self.pending.get(str(response.get("requestid")))
                    if future is not None and not future.done():
                        if response.get("content", {}).get("code") == 0:
                            future.set_result(None)
                        else:
                            future.set_exception(StreamFailure())
                for data in message.get("data", []):
                    await self.runtime.handle_stream_data(data, self.connected_at)
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(StreamFailure())

    async def session(self, socket) -> None:
        self.socket = socket
        self.runtime.set_stream_status("connecting")
        self.connected_at = time.time()
        self.active_symbols.clear()
        self.runtime.state.stream_quotes.clear()
        receiver = asyncio.create_task(self.receive())
        try:
            access = await self.runtime.tokens.token()
            try:
                await self.command(
                    "ADMIN",
                    "LOGIN",
                    {
                        "Authorization": access,
                        "SchwabClientChannel": self.info["schwabClientChannel"],
                        "SchwabClientFunctionId": self.info["schwabClientFunctionId"],
                    },
                )
            except StreamFailure:
                self.runtime.tokens.invalidate(access)
                raise
            await self.command(
                "ACCT_ACTIVITY", "SUBS", {"keys": "Account Activity", "fields": "0,1,2,3"}
            )
            self.logged_in = True
            await self.subscribe_symbols()
            self.runtime.set_stream_status("connected")
            self.runtime.refresh_requested.set()
            await receiver
        finally:
            self.logged_in = False
            receiver.cancel()
            with suppress(asyncio.CancelledError, ConnectionClosed, StreamFailure):
                await receiver
            self.socket = None
            self.runtime.state.stream_quotes.clear()
            self.runtime.set_stream_status("disconnected")

    async def run(self) -> None:
        while True:
            try:
                await self.runtime.tokens.token()
                preferences = await self.runtime.rest.get("/trader/v1/userPreference")
                self.info = preferences["streamerInfo"][0]
                self.runtime.set_stream_status("connecting")
                # The library handles handshake failures and exponential backoff.
                async for socket in connect(
                    self.info["streamerSocketUrl"],
                    ping_interval=20,
                    ping_timeout=20,
                    open_timeout=15,
                    close_timeout=5,
                ):
                    try:
                        await self.session(socket)
                    except (ConnectionClosed, StreamFailure, TimeoutError):
                        pass
                    if self.runtime.tokens.status == "auth_required":
                        break
                    await asyncio.sleep(INIT_RETRY_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                # No frames, credentials or broker payloads are logged.
                self.runtime.set_stream_status("disconnected")
            await asyncio.sleep(INIT_RETRY_SECONDS)


# 06 Runtime Cache ------------------------------------------------------------
ACCOUNT_FIELDS = {
    "liquidation_value": "liquidationValue",
    "long_market_value": "longMarketValue",
    "cash_balance": "cashBalance",
    "available_funds": "availableFunds",
    "buying_power": "buyingPower",
    "intraday_buying_power": "intradayBuyingPowerAmount",
    "day_trading_buying_power": "dayTradingBuyingPower",
    "margin_balance": "marginBalance",
    "maintenance_requirement": "maintenanceRequirement",
}


def map_account(raw: dict, updated_at: str) -> tuple[dict, list]:
    account = raw["securitiesAccount"]
    balances = account.get("currentBalances", {})
    mapped = {key: decimal_text(balances.get(source)) for key, source in ACCOUNT_FIELDS.items()}
    mapped["stock_buying_power"] = decimal_text(
        account.get("projectedBalances", {}).get("stockBuyingPower")
    )
    mapped["updated_at"] = updated_at
    positions = []
    for position in account.get("positions", []):
        instrument = position.get("instrument", {})
        if instrument.get("assetType") != "EQUITY":
            continue
        long_qty = decimal_value(position.get("longQuantity", 0)) or Decimal(0)
        short_qty = decimal_value(position.get("shortQuantity", 0)) or Decimal(0)
        positions.append(
            {
                "symbol": instrument.get("symbol"),
                "asset_type": "EQUITY",
                "quantity": decimal_text(long_qty - short_qty),
                "average_price": decimal_text(position.get("averagePrice")),
                "market_value": decimal_text(position.get("marketValue")),
                "day_profit_loss": decimal_text(position.get("currentDayProfitLoss")),
                "open_profit_loss": decimal_text(position.get("longOpenProfitLoss")),
                "day_profit_loss_percent": decimal_text(
                    position.get("currentDayProfitLossPercentage")
                ),
            }
        )
    return mapped, positions


def map_order(raw: dict, parent_id: str | None = None) -> dict:
    legs = raw.get("orderLegCollection", [])
    leg = legs[0] if legs else {}
    order_id = str(raw["orderId"]) if raw.get("orderId") is not None else None
    executions = []
    if leg.get("instrument", {}).get("assetType") == "EQUITY":
        for activity in raw.get("orderActivityCollection", []):
            if (
                activity.get("activityType") != "EXECUTION"
                or activity.get("executionType") != "FILL"
            ):
                continue
            for execution in activity.get("executionLegs", []):
                executions.append(
                    {
                        "activity_id": str(activity["activityId"]),
                        "leg_id": str(execution["legId"]),
                        "quantity": decimal_text(execution["quantity"]),
                        "price": decimal_text(execution["price"]),
                        "time": datetime.fromisoformat(execution["time"])
                        .astimezone(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                    }
                )
    return {
        "order_id": order_id,
        "parent_order_id": parent_id,
        "symbol": leg.get("instrument", {}).get("symbol"),
        "instruction": leg.get("instruction"),
        "asset_type": leg.get("instrument", {}).get("assetType"),
        "editable": raw.get("editable"),
        "order_type": raw.get("orderType"),
        "strategy_type": raw.get("orderStrategyType"),
        "quantity": decimal_text(raw.get("quantity", leg.get("quantity"))),
        "filled_quantity": decimal_text(raw.get("filledQuantity")),
        "stop_price": decimal_text(raw.get("stopPrice")),
        "duration": raw.get("duration"),
        "session": raw.get("session"),
        "status": raw.get("status"),
        "cancelable": raw.get("cancelable"),
        "entered_at": raw.get("enteredTime"),
        "executions": executions,
        "child_orders": [
            map_order(child, order_id) for child in raw.get("childOrderStrategies", [])
        ],
    }


def flatten_orders(orders: list[dict]):
    for order in orders:
        yield order
        yield from flatten_orders(order["child_orders"])


@dataclass
class RuntimeState:
    account: dict | None = None
    positions: list = field(default_factory=list)
    orders: list = field(default_factory=list)
    quotes: dict = field(default_factory=dict)
    stream_quotes: dict = field(default_factory=dict)
    subscribed_symbols: set = field(default_factory=set)
    notified_fills: set = field(default_factory=set)
    stream_status: str = "disconnected"
    account_updated_at: str | None = None
    orders_updated_at: str | None = None


class Runtime:
    def __init__(self, *, store=None, http=None):
        self.http = http or httpx.AsyncClient(
            timeout=15, follow_redirects=False, transport=httpx.AsyncHTTPTransport(retries=0)
        )
        self.tokens = TokenManager(store or KeychainStore(), self.http)
        self.rest = SchwabREST(self.tokens, self.http)
        self.state = RuntimeState()
        self.events = Broadcaster()
        self.stream = SchwabStream(self)
        self.trading = TradingGateway(self)
        self.refreshes: dict[str, asyncio.Task] = {}
        self.refresh_requested = asyncio.Event()
        self.tasks: set[asyncio.Task] = set()
        self.stream_task: asyncio.Task | None = None
        self.initialization_error: str | None = None

    def background(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(self._consume_task)
        return task

    @staticmethod
    def _consume_task(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception() is not None:
            LOG.warning("后台任务暂时失败：%s", type(task.exception()).__name__)

    def snapshot(self) -> dict:
        return {
            "account": self.state.account,
            "positions": self.state.positions,
            "orders": self.state.orders,
            "updated_at": utc_now(),
        }

    def set_stream_status(self, status: str) -> None:
        if self.state.stream_status != status:
            self.state.stream_status = status
            self.events.publish(
                "stream_status", {"connected": status == "connected", "timestamp": utc_now()}
            )

    async def refresh(self, kind: str) -> None:
        # Share the same in-flight GET with pollers, events and manual refreshes.
        current = self.refreshes.get(kind)
        if current is None or current.done():
            current = asyncio.create_task(self._refresh(kind))
            self.refreshes[kind] = current
        await asyncio.shield(current)

    async def _refresh(self, kind: str) -> None:
        if kind == "account":
            raw = await self.rest.get(self.rest.account_path(), {"fields": "positions"})
            updated = utc_now()
            try:
                account, positions = map_account(raw, updated)
            except (KeyError, TypeError, ValueError):
                raise unavailable() from None
            self.state.account, self.state.positions = account, positions
            self.state.account_updated_at = updated
        else:
            orders = await self.rest.orders()
            self.state.orders = [map_order(order) for order in orders]
            self.state.orders_updated_at = utc_now()
        self.events.publish("snapshot_updated", self.snapshot())

    async def refresh_both(self) -> None:
        results = await asyncio.gather(
            self.refresh("account"), self.refresh("orders"), return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                raise result

    async def maintain(self) -> None:
        while True:
            try:
                await self.tokens.token()
                if not self.rest.account_hash:
                    await self.rest.initialize_account()
                await self.refresh_both()
                self.initialization_error = None
                if self.stream_task is None or self.stream_task.done():
                    self.stream_task = self.background(self.stream.run())
            except BackendError as error:
                self.initialization_error = error.code
                if (
                    error.code == "AUTH_REQUIRED"
                    and self.stream_task
                    and not self.stream_task.done()
                ):
                    self.stream_task.cancel()
            except Exception:
                self.initialization_error = "SCHWAB_UNAVAILABLE"
            # Events wake the poller, including events received during the last refresh.
            with suppress(TimeoutError):
                await asyncio.wait_for(self.refresh_requested.wait(), timeout=INIT_RETRY_SECONDS)
            self.refresh_requested.clear()

    async def start(self) -> None:
        self.background(self.maintain())

    async def close(self) -> None:
        tasks = set(self.tasks) | set(self.refreshes.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.http.aclose()

    def health(self) -> dict:
        return {
            "service": "running",
            "auth_status": self.tokens.status,
            "schwab_rest": self.rest.status
            if self.state.account_updated_at
            and self.state.orders_updated_at
            and self.initialization_error is None
            else "unavailable",
            "schwab_stream": self.state.stream_status,
            "account_initialized": self.state.account_updated_at is not None,
            "orders_initialized": self.state.orders_updated_at is not None,
            "last_account_update": self.state.account_updated_at,
            "last_orders_update": self.state.orders_updated_at,
        }

    async def get_quote(self, symbol: str, refresh: bool = False) -> dict:
        if refresh or symbol not in self.state.quotes:
            raw = await self.rest.quote(symbol)
            values = raw.get("quote", {})
            self.state.quotes[symbol] = {
                "bid": decimal_text(values.get("bidPrice")),
                "ask": decimal_text(values.get("askPrice")),
                "day_high": decimal_text(values.get("highPrice")),
                "day_low": decimal_text(values.get("lowPrice")),
                "last_price": decimal_text(values.get("lastPrice")),
                "close_price": decimal_text(values.get("closePrice")),
                "updated_at": utc_now(),
            }
        self.state.subscribed_symbols.add(symbol)
        if self.stream.logged_in:
            try:
                await self.stream.subscribe_symbols()
            except (ConnectionClosed, StreamFailure, TimeoutError):
                if self.stream.socket is not None:
                    await self.stream.socket.close()
        quote = self.state.quotes[symbol]
        stream = (
            self.state.stream_quotes.get(symbol, {})
            if self.state.stream_status == "connected"
            else {}
        )
        high, low = positive(quote["day_high"]), positive(quote["day_low"])
        return {
            "symbol": symbol,
            "bid": stream.get("bid", quote["bid"]),
            "ask": stream.get("ask", quote["ask"]),
            "day_high": quote["day_high"],
            "day_low": quote["day_low"],
            "last_price": quote["last_price"],
            "close_price": quote["close_price"],
            "suggested_buy_stop": decimal_text(high + BREAKOUT_OFFSET) if high else None,
            "suggested_sell_stop": decimal_text(low),
            "updated_at": stream.get("updated_at", quote["updated_at"]),
        }

    async def handle_stream_data(self, data: dict, connected_at: float) -> None:
        service = data.get("service")
        for content in data.get("content", []):
            if service == "LEVELONE_EQUITIES":
                symbol = content.get("key", content.get("0"))
                if symbol not in self.state.subscribed_symbols:
                    continue
                quote = self.state.stream_quotes.setdefault(symbol, {})
                changed = False
                for key, name in (("1", "bid"), ("2", "ask")):
                    if key in content:
                        quote[name] = decimal_text(content[key])
                        changed = True
                if changed:
                    quote["updated_at"] = utc_now()
                    fallback = self.state.quotes.get(symbol, {})
                    self.events.publish(
                        "quote_updated",
                        {
                            "symbol": symbol,
                            "bid": quote.get("bid", fallback.get("bid")),
                            "ask": quote.get("ask", fallback.get("ask")),
                            "updated_at": quote["updated_at"],
                        },
                    )
            elif service == "ACCT_ACTIVITY":
                account = content.get("1")
                if account and str(account) != self.rest.account_number:
                    continue
                self.refresh_requested.set()
                if content.get("2") == "OrderFillCompleted":
                    await self.handle_fill(content, data.get("timestamp"), connected_at)

    async def handle_fill(self, content: dict, timestamp: Any, connected_at: float) -> None:
        try:
            payload = content.get("3", {})
            if isinstance(payload, str):
                payload = json.loads(payload)
            order_id = str(payload["SchwabOrderID"])
            occurred = float(timestamp) / 1000
            if occurred < connected_at:
                return  # No sound replay of events from before this connection.
        except (KeyError, TypeError, ValueError):
            return
        if order_id in self.state.notified_fills:
            return
        self.state.notified_fills.add(order_id)
        symbol = find_nested(payload, "Symbol")
        if not symbol:
            symbol = next(
                (
                    o["symbol"]
                    for o in flatten_orders(self.state.orders)
                    if o["order_id"] == order_id
                ),
                None,
            )
        self.events.publish(
            "order_filled",
            {
                "order_id": order_id,
                "symbol": symbol,
                "occurred_at": datetime.fromtimestamp(occurred, UTC)
                .isoformat()
                .replace("+00:00", "Z"),
            },
        )
        self.background(play_fill_sound())


def find_nested(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = find_nested(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_nested(child, key)
            if found is not None:
                return found
    return None


# 07 Trading Gateway ----------------------------------------------------------
def order_payload(
    symbol: str,
    qty: int,
    instruction: str,
    order_type: str,
    duration: str = "DAY",
    stop: Decimal | None = None,
) -> dict:
    order = {
        "session": "NORMAL",
        "duration": duration,
        "orderType": order_type,
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": instruction,
                "quantity": qty,
                "instrument": {"symbol": symbol, "assetType": "EQUITY"},
            }
        ],
    }
    if stop is not None:
        order["stopPrice"] = decimal_text(stop)
    return order


def location_order_id(response: httpx.Response) -> str:
    path = urlsplit(response.headers.get("Location", "")).path
    match = re.search(r"/orders/([0-9]+)/?$", path)
    if not match or int(match[1]) <= 0:
        raise unknown()
    return match[1]


class TradingGateway:
    """Internal gateway: request types are validated once by the HTTP routes."""

    def __init__(self, runtime: Runtime):
        self.runtime = runtime
        self.active: set[tuple] = set()

    @asynccontextmanager
    async def operation(self, key: tuple):
        # There is no await between checking and adding: atomic within this event loop.
        if key in self.active:
            raise conflict("相同操作正在执行，请等待本次请求完成")
        self.active.add(key)
        try:
            yield
        finally:
            self.active.discard(key)

    def amount(self, qty: int | Decimal, price: Decimal) -> None:
        if qty * price > MAX_ORDER_AMOUNT_USD:
            raise BackendError(422, "RISK_LIMIT_EXCEEDED", "单笔买入金额超过限制")

    async def trade_quote(self, symbol: str) -> dict:
        raw = await self.runtime.rest.quote(symbol)
        if raw.get("assetMainType") != "EQUITY":
            raise BackendError(422, "VALIDATION_FAILED", "仅支持股票或 ETF")
        return raw.get("quote", {})

    @staticmethod
    def require_price(quote: dict, key: str) -> Decimal:
        price = positive(quote.get(key))
        if price is None:
            raise BackendError(422, "VALIDATION_FAILED", "Schwab 未返回有效的 Bid/Ask")
        return price

    async def submit(self, payload: dict) -> dict:
        response = await self.runtime.rest.request(
            "POST", self.runtime.rest.account_path("/orders"), payload=payload
        )
        if response.status_code != 201:
            raise unknown()
        order_id = location_order_id(response)
        self.runtime.refresh_requested.set()
        return {"result": "accepted", "order_id": order_id, "verified": False}

    async def buy_market(self, symbol: str, qty: int) -> dict:
        async with self.operation(("buy_market", symbol, qty)):
            quote = await self.trade_quote(symbol)
            self.amount(qty, self.require_price(quote, "askPrice"))
            return await self.submit(order_payload(symbol, qty, "BUY", "MARKET"))

    async def sell_market(self, symbol: str, qty: int) -> dict:
        async with self.operation(("sell_market", symbol, qty)):
            await self.runtime.refresh("account")
            held = sum(
                (
                    Decimal(p["quantity"])
                    for p in self.runtime.state.positions
                    if p["symbol"] == symbol
                ),
                Decimal(0),
            )
            if held < qty:
                raise BackendError(422, "RISK_LIMIT_EXCEEDED", "卖出数量超过当前多头持仓")
            return await self.submit(order_payload(symbol, qty, "SELL", "MARKET"))

    async def buy_breakout(
        self, symbol: str, qty: int, buy_stop: Decimal, sell_stop: Decimal
    ) -> dict:
        async with self.operation(("buy_breakout", symbol, qty, buy_stop, sell_stop)):
            if sell_stop >= buy_stop:
                raise BackendError(422, "RISK_LIMIT_EXCEEDED", "必须满足 0 < sell_stop < buy_stop")
            # Multiplication avoids a rounded division at the risk boundary.
            if buy_stop - sell_stop > MAX_STOP_LOSS_RATIO * buy_stop:
                raise BackendError(422, "RISK_LIMIT_EXCEEDED", "止损比例超过限制")
            self.amount(qty, buy_stop)
            if qty * (buy_stop - sell_stop) > MAX_LOSS_PER_TRADE_USD:
                raise BackendError(422, "RISK_LIMIT_EXCEEDED", "估算价差风险超过限制")
            quote = await self.trade_quote(symbol)
            if buy_stop <= self.require_price(quote, "askPrice") or sell_stop >= self.require_price(
                quote, "bidPrice"
            ):
                raise BackendError(
                    422, "RISK_LIMIT_EXCEEDED", "Buy Stop 必须高于 Ask，Sell Stop 必须低于 Bid"
                )
            parent = order_payload(symbol, qty, "BUY", "STOP", stop=buy_stop)
            parent["orderStrategyType"] = "TRIGGER"
            parent["childOrderStrategies"] = [
                order_payload(symbol, qty, "SELL", "STOP", "GOOD_TILL_CANCEL", sell_stop)
            ]
            return await self.submit(parent)

    async def replace_stop(self, order_id: str | int, new_stop: Decimal) -> dict:
        order_id = order_id_value(order_id)
        async with self.operation(("order", order_id)):
            raw = await self.runtime.rest.order(order_id)
            legs = raw.get("orderLegCollection", [])
            if (
                raw.get("orderType") != "STOP"
                or raw.get("orderStrategyType") != "SINGLE"
                or raw.get("session") != "NORMAL"
                or raw.get("editable") is not True
                or raw.get("status")
                not in {"WORKING", "AWAITING_STOP_CONDITION", "QUEUED", "ACCEPTED"}
                or raw.get("childOrderStrategies")
                or len(legs) != 1
                or legs[0].get("instruction") != "SELL"
                or legs[0].get("instrument", {}).get("assetType") != "EQUITY"
            ):
                raise conflict("只能修改已独立激活且可编辑的股票 Sell Stop")
            leg = legs[0]
            quantity = positive(
                leg.get("quantity") if leg.get("quantity") is not None else raw.get("quantity")
            )
            if (
                quantity is None
                or quantity != quantity.to_integral_value()
                or leg.get("quantityType") not in (None, "", "SHARES")
            ):
                raise conflict("原订单数量必须是有限正整数股数，不能截断或推测改单数量")
            duration = raw.get("duration")
            if not duration:
                raise conflict("原订单缺少有效期，无法保持原单设置")
            if (
                raw.get("stopType") not in (None, "", "STANDARD")
                or raw.get("stopPriceLinkBasis") not in (None, "", "MANUAL")
                or raw.get("stopPriceLinkType") not in (None, "", "VALUE")
                or any(
                    decimal_value(raw[key]) != 0
                    for key in ("stopPriceOffset", "activationPrice")
                    if raw.get(key) not in (None, "")
                )
            ):
                raise conflict("仅支持固定价格、标准触发的股票 Sell Stop，不能自动更改原触发设置")
            payload = order_payload(
                leg["instrument"]["symbol"],
                int(quantity),
                "SELL",
                "STOP",
                duration=duration,
                stop=new_stop,
            )
            # Preserve explicit tax/execution instructions, including FIFO, without GET metadata.
            for key in ("taxLotMethod", "specialInstruction"):
                if raw.get(key) not in (None, ""):
                    payload[key] = raw[key]
            response = await self.runtime.rest.request(
                "PUT", self.runtime.rest.account_path(f"/orders/{order_id}"), payload=payload
            )
            if response.status_code != 201:
                raise unknown()
            new_id = location_order_id(response)
            self.runtime.refresh_requested.set()
            return {
                "result": "accepted",
                "old_order_id": order_id,
                "new_order_id": new_id,
                "verified": False,
            }

    async def cancel_order(self, order_id: str | int) -> dict:
        order_id = order_id_value(order_id)
        async with self.operation(("order", order_id)):
            response = await self.runtime.rest.request(
                "DELETE", self.runtime.rest.account_path(f"/orders/{order_id}")
            )
            if response.status_code != 200:
                raise unknown()
            self.runtime.refresh_requested.set()
            return {"result": "accepted", "order_id": order_id, "verified": False}


# 08 SSE & Notifications ------------------------------------------------------
class Broadcaster:
    def __init__(self):
        self.clients: set[asyncio.Queue] = set()

    @staticmethod
    def encode(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"

    def publish(self, event: str, data: dict) -> None:
        encoded = self.encode(event, data)
        for queue in tuple(self.clients):
            if queue.full():
                # Disconnect a slow client; do not block reception or silently lose fills.
                self.clients.discard(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
            else:
                queue.put_nowait(encoded)

    async def listen(self, snapshot: dict):
        queue = asyncio.Queue(maxsize=256)
        self.clients.add(queue)
        try:
            yield self.encode("snapshot_updated", snapshot)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    if event is None:
                        return
                    yield event
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            self.clients.discard(queue)


async def play_fill_sound() -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "afplay",
            "/System/Library/Sounds/Glass.aiff",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await proc.wait()
        finally:
            if proc.returncode is None:
                proc.terminate()
                await proc.wait()
    except OSError:
        LOG.warning("成交声音暂时不可用")


# 09 Local API Routes ---------------------------------------------------------
def create_app(*, runtime: Runtime | None = None) -> FastAPI:
    runtime = runtime or Runtime()

    @asynccontextmanager
    async def lifespan(app):
        await runtime.start()
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(
        title="Schwab Local Trading Backend",
        version="1.2",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.runtime = runtime

    @app.exception_handler(BackendError)
    async def backend_error(request, error):
        return JSONResponse(error.body(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        details = [
            {"location": list(item["loc"]), "message": item["msg"]} for item in error.errors()
        ]
        failure = BackendError(422, "VALIDATION_FAILED", "请求参数无效", details)
        return JSONResponse(failure.body(), status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        failure = BackendError(
            error.status_code,
            "NOT_FOUND" if error.status_code == 404 else "BAD_REQUEST",
            "请求不合法",
        )
        return JSONResponse(failure.body(), status_code=error.status_code)

    @app.middleware("http")
    async def local_access(request: Request, call_next):
        host = request.headers.get("host", "").lower()
        if host not in {f"127.0.0.1:{PORT}", f"localhost:{PORT}", "127.0.0.1", "localhost"}:
            failure = BackendError(400, "BAD_REQUEST", "Host 必须为本机地址")
            return JSONResponse(failure.body(), status_code=400)
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "DELETE"}:
            if origin is not None and origin not in ALLOWED_ORIGINS:
                failure = BackendError(400, "BAD_REQUEST", "Origin 不在允许列表中")
                return JSONResponse(failure.body(), status_code=400)
        if request.method in {"POST", "PUT"}:
            if (
                request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                failure = BackendError(400, "BAD_REQUEST", "POST/PUT 必须使用 application/json")
                return JSONResponse(failure.body(), status_code=400)
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(ALLOWED_ORIGINS),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

    def require_snapshot(value):
        if value is None:
            raise auth_required() if runtime.tokens.status == "auth_required" else unavailable()

    def parsed_symbol(value: str) -> str:
        try:
            return symbol_value(value)
        except ValueError:
            raise BackendError(422, "VALIDATION_FAILED", "Symbol 格式无效") from None

    @app.get("/api/v1/health")
    async def health():
        return runtime.health()

    @app.get("/api/v1/account")
    async def account():
        require_snapshot(runtime.state.account_updated_at)
        return runtime.state.account

    @app.get("/api/v1/positions")
    async def positions():
        require_snapshot(runtime.state.account_updated_at)
        return {
            "positions": runtime.state.positions,
            "updated_at": runtime.state.account_updated_at,
        }

    @app.get("/api/v1/orders")
    async def orders(symbol: str | None = None, refresh: bool = False):
        selected = parsed_symbol(symbol) if symbol is not None else None
        if refresh:
            await runtime.refresh("orders")
        require_snapshot(runtime.state.orders_updated_at)
        result = runtime.state.orders
        if selected:
            result = [
                o
                for o in result
                if any(child["symbol"] == selected for child in flatten_orders([o]))
            ]
        return {"orders": result, "updated_at": runtime.state.orders_updated_at}

    @app.post("/api/v1/orders/market-buy", status_code=201)
    async def market_buy(request: MarketRequest):
        return await runtime.trading.buy_market(request.symbol, request.qty)

    @app.post("/api/v1/orders/market-sell", status_code=201)
    async def market_sell(request: MarketRequest):
        return await runtime.trading.sell_market(request.symbol, request.qty)

    @app.post("/api/v1/orders/breakout-buy", status_code=201)
    async def breakout_buy(request: BreakoutRequest):
        return await runtime.trading.buy_breakout(
            request.symbol, request.qty, request.buy_stop, request.sell_stop
        )

    @app.get("/api/v1/orders/{order_id}")
    async def single_order(order_id: str):
        order_id = order_id_value(order_id)
        raw = await runtime.rest.order(order_id)
        parent = next(
            (
                o["parent_order_id"]
                for o in flatten_orders(runtime.state.orders)
                if o["order_id"] == order_id
            ),
            None,
        )
        return map_order(raw, parent)

    @app.put("/api/v1/orders/{order_id}/stop")
    async def replace_stop(order_id: str, request: ReplaceRequest):
        return await runtime.trading.replace_stop(order_id, request.new_stop)

    @app.delete("/api/v1/orders/{order_id}", status_code=202)
    async def cancel_order(order_id: str):
        return await runtime.trading.cancel_order(order_id)

    @app.get("/api/v1/quotes/{symbol:path}")
    async def quote(symbol: str, refresh: bool = False):
        return await runtime.get_quote(parsed_symbol(symbol), refresh)

    @app.get("/api/v1/events")
    async def events():
        return StreamingResponse(
            runtime.events.listen(runtime.snapshot()),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


# 10 Startup & CLI ------------------------------------------------------------
async def authorize() -> None:
    if not CLIENT_ID:
        raise ValueError("请先在代码顶部填写 CLIENT_ID")
    store = KeychainStore()
    secret = await asyncio.to_thread(store.secret)
    if not secret:
        secret = getpass.getpass("Schwab client_secret（仅存入 Keychain）: ")
        if not secret:
            raise ValueError("client_secret 不能为空")
        await asyncio.to_thread(store.set_secret, secret)
    state = secrets.token_urlsafe(32)
    url = authorization_url(state)
    print("在浏览器中授权；Callback 页面无法打开属于预期，请复制完整地址。\n" + url)
    webbrowser.open(url)
    callback = input("请粘贴完整 Callback URL: ")
    code = callback_code(callback, state)
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as http:
        response = await http.post(
            TOKEN_URL,
            auth=(CLIENT_ID, secret),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": CALLBACK_URL,
            },
        )
        if response.status_code != 200:
            raise ValueError("授权失败，请重新运行 auth；不自动重用 Authorization Code")
        await asyncio.to_thread(store.save, TokenManager.parse_tokens(response))
    print("授权已保存至 Keychain；运行中的 Backend 将自动恢复。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["serve", "auth"], nargs="?", default="serve")
    args = parser.parse_args()
    try:
        if args.command == "auth":
            asyncio.run(authorize())
        else:
            import uvicorn

            # Fixed binding and worker count are intentional parts of the contract.
            uvicorn.run(create_app(), host=HOST, port=PORT, workers=1, access_log=False)
    except Exception as error:
        detail = error.message if isinstance(error, BackendError) else str(error)
        print(f"启动或授权失败 ({type(error).__name__}): {detail}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

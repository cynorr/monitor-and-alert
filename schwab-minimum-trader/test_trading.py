"""Protocol and safety tests use fake credentials and httpx.MockTransport only."""

import asyncio
import copy
import json
import time
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

import schwab_backend as backend


class MemoryStore:
    def __init__(self, credentials=None):
        self.credentials = credentials
        self.saved = 0
        self.locked = False

    def load(self):
        if self.locked:
            raise RuntimeError("locked")
        return copy.copy(self.credentials)

    def clear(self):
        self.credentials = None

    def secret(self):
        return "fake-secret"

    def save(self, credentials):
        if self.locked:
            raise RuntimeError("locked")
        self.saved += 1
        self.credentials = copy.copy(credentials)


def credentials(expiration=None):
    return backend.Credentials("fake-access", "fake-refresh", expiration or time.time() + 1800)


def raw_order(order_id=123, **overrides):
    result = {
        "orderId": order_id,
        "orderType": "STOP",
        "orderStrategyType": "SINGLE",
        "session": "NORMAL",
        "duration": "GOOD_TILL_CANCEL",
        "stopPrice": "90.00",
        "quantity": 10,
        "filledQuantity": 0,
        "status": "AWAITING_STOP_CONDITION",
        "editable": True,
        "cancelable": True,
        "enteredTime": "2026-10-15T14:30:00Z",
        "orderLegCollection": [
            {
                "instruction": "SELL",
                "quantity": 10,
                "legId": 1,
                "positionEffect": "CLOSING",
                "instrument": {"symbol": "NVDA", "assetType": "EQUITY"},
            }
        ],
    }
    result.update(overrides)
    return result


def service_error(status):
    # ServiceError schema: message + errors[]. Text is synthetic, not a live capture.
    # https://github.com/Patch-Code-Prosperity/Schwab-API-Sandbox/blob/main/account_orders_openapi.yaml
    return httpx.Response(status, json={"message": httpx.codes(status).phrase, "errors": []})


class Broker:
    def __init__(self):
        self.requests = []
        self.quote = {
            "NVDA": {
                "assetMainType": "EQUITY",
                "quote": {
                    "bidPrice": "99.90",
                    "askPrice": "100.00",
                    "highPrice": "101.00",
                    "lowPrice": "95.00",
                },
            }
        }
        self.account = {
            "securitiesAccount": {
                "currentBalances": {
                    "liquidationValue": "125000.00",
                    "buyingPower": "54000.00",
                    "marginBalance": "15000.00",
                },
                "positions": [
                    {
                        "instrument": {"symbol": "NVDA", "assetType": "EQUITY"},
                        "longQuantity": "10.5",
                        "shortQuantity": 0,
                        "averagePrice": "90.12",
                    }
                ],
            }
        }
        self.order_list = [raw_order()]
        self.read_failure = False
        self.order_read_status = 200
        self.write_status = None
        self.write_exception = None
        self.location = "/trader/v1/accounts/hash/orders/456"
        self.accounts = [{"accountNumber": "1234", "hashValue": "hash"}]
        self.token_status = 200
        self.block_write = None
        self.started_write = asyncio.Event()

    async def __call__(self, request):
        self.requests.append(request)
        path = request.url.path
        if path == "/v1/oauth/token":
            await asyncio.sleep(0.01)
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            return httpx.Response(
                self.token_status,
                json={
                    "access_token": "renewed-access",
                    "refresh_token": "renewed-refresh",
                    "expires_in": 1800,
                },
            )
        if request.method != "GET":
            self.started_write.set()
            if self.block_write:
                await self.block_write.wait()
            if self.write_exception:
                raise self.write_exception("unknown", request=request)
            status = self.write_status or (200 if request.method == "DELETE" else 201)
            if status >= 400:
                return service_error(status)
            return httpx.Response(
                status, headers={"Location": self.location} if self.location else {}
            )
        if self.read_failure:
            return service_error(503)
        if path.endswith("/accountNumbers"):
            return httpx.Response(200, json=self.accounts)
        if path == "/marketdata/v1/quotes":
            return httpx.Response(200, json=self.quote)
        if path.endswith("/userPreference"):
            return service_error(503)
        if "/orders" in path and self.order_read_status != 200:
            return service_error(self.order_read_status)
        if path.endswith("/orders/456"):
            return httpx.Response(200, json=raw_order(456, stopPrice="92.00"))
        if "/orders/" in path:
            return httpx.Response(200, json=self.order_list[0])
        if path.endswith("/orders"):
            return httpx.Response(200, json=self.order_list)
        return httpx.Response(200, json=self.account)

    def writes(self):
        return [
            r
            for r in self.requests
            if r.method in {"POST", "PUT", "DELETE"} and r.url.path != "/v1/oauth/token"
        ]


@pytest.fixture
async def setup(monkeypatch):
    broker = Broker()
    monkeypatch.setattr(backend, "CLIENT_ID", "fake-id")
    monkeypatch.setattr(backend, "MAX_ORDER_AMOUNT_USD", Decimal("10000"))
    monkeypatch.setattr(backend, "MAX_LOSS_PER_TRADE_USD", Decimal("1000"))
    http = httpx.AsyncClient(transport=httpx.MockTransport(broker))
    store = MemoryStore(credentials())
    runtime = backend.Runtime(http=http, store=store)
    await runtime.tokens.token()
    await runtime.rest.initialize_account()
    yield runtime, broker, store
    await runtime.close()


@pytest.fixture
async def api(setup):
    runtime, broker, store = setup
    app = backend.create_app(runtime=runtime)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:5678"
    ) as client:
        yield client, runtime, broker


@pytest.mark.parametrize("qty", [0, -1, True, 1.0, "1", None])
async def test_quantity_is_strict_positive_integer(api, qty):
    client, _, broker = api
    response = await client.post("/api/v1/orders/market-buy", json={"symbol": "NVDA", "qty": qty})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert not broker.writes()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "0", "-1", 101.0, True])
async def test_stop_prices_must_be_positive_decimal_strings(api, value):
    client, _, broker = api
    response = await client.post(
        "/api/v1/orders/breakout-buy",
        json={"symbol": "NVDA", "qty": 1, "buy_stop": value, "sell_stop": "95"},
    )
    assert response.status_code == 422
    assert not broker.writes()
    response = await client.put("/api/v1/orders/123/stop", json={"new_stop": value})
    assert response.status_code == 422
    assert not broker.writes()


async def test_extra_order_fields_rejected(api):
    client, _, broker = api
    response = await client.post(
        "/api/v1/orders/market-buy", json={"symbol": "NVDA", "qty": 1, "session": "SEAMLESS"}
    )
    assert response.status_code == 422
    assert not broker.writes()


async def test_market_buy_fixed_payload_and_amount_boundary(api):
    client, _, broker = api
    response = await client.post("/api/v1/orders/market-buy", json={"symbol": "nvda", "qty": 100})
    assert response.status_code == 201
    assert response.json() == {"result": "accepted", "order_id": "456", "verified": False}
    payload = json.loads(broker.writes()[0].content)
    assert payload == {
        "session": "NORMAL",
        "duration": "DAY",
        "orderType": "MARKET",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": [
            {
                "instruction": "BUY",
                "quantity": 100,
                "instrument": {"symbol": "NVDA", "assetType": "EQUITY"},
            }
        ],
    }
    response = await client.post("/api/v1/orders/market-buy", json={"symbol": "NVDA", "qty": 101})
    assert response.json()["error"]["code"] == "RISK_LIMIT_EXCEEDED"
    assert len(broker.writes()) == 1


async def test_market_sell_uses_fresh_fractional_position_and_no_cancel(setup):
    runtime, broker, _ = setup
    await runtime.trading.sell_market("NVDA", 10)
    payload = json.loads(broker.writes()[0].content)
    assert payload["orderLegCollection"][0]["instruction"] == "SELL"
    with pytest.raises(backend.BackendError, match="RISK_LIMIT_EXCEEDED"):
        await runtime.trading.sell_market("NVDA", 11)
    assert [r.method for r in broker.writes()] == ["POST"]


async def test_large_market_sell_does_not_depend_on_quote_or_buy_limit(setup):
    runtime, broker, _ = setup
    position = broker.account["securitiesAccount"]["positions"][0]
    position.update(longQuantity="1000", marketValue="100000")
    broker.quote = {}  # Quote is unavailable; closing the held shares must still work.
    result = await runtime.trading.sell_market("NVDA", 1000)
    assert result["result"] == "accepted"
    assert len(broker.writes()) == 1
    assert not any(r.url.path.startswith("/marketdata/") for r in broker.requests)
    assert json.loads(broker.writes()[0].content)["orderLegCollection"][0]["quantity"] == 1000


async def test_raise_stop_above_buy_amount_limit_is_allowed(setup):
    runtime, broker, _ = setup
    broker.order_list = [raw_order(quantity=1000)]
    broker.order_list[0]["orderLegCollection"][0]["quantity"] = 1000
    result = await runtime.trading.replace_stop(123, Decimal("200"))
    assert result["result"] == "accepted" and result["verified"] is False
    assert json.loads(broker.writes()[0].content)["stopPrice"] == "200"
    assert len(broker.writes()) == 1


async def test_short_position_cannot_be_sold(setup):
    runtime, broker, _ = setup
    broker.account["securitiesAccount"]["positions"][0].update(longQuantity=0, shortQuantity=5)
    with pytest.raises(backend.BackendError, match="RISK_LIMIT_EXCEEDED"):
        await runtime.trading.sell_market("NVDA", 1)
    assert not broker.writes()


async def test_breakout_native_oto_one_post(setup):
    runtime, broker, _ = setup
    result = await runtime.trading.buy_breakout("NVDA", 10, Decimal("101"), Decimal("95"))
    assert result["order_id"] == "456"
    payload = json.loads(broker.writes()[0].content)
    assert payload["orderType"] == "STOP" and payload["orderStrategyType"] == "TRIGGER"
    assert payload["duration"] == "DAY" and payload["stopPrice"] == "101"
    child = payload["childOrderStrategies"][0]
    assert child["duration"] == "GOOD_TILL_CANCEL" and child["stopPrice"] == "95"
    assert child["orderLegCollection"][0]["quantity"] == 10
    assert child["orderLegCollection"][0]["instruction"] == "SELL"
    assert child["orderType"] == "STOP" and child["session"] == "NORMAL"
    assert len(broker.writes()) == 1


@pytest.mark.parametrize(
    "qty,buy,sell",
    [
        (1, "101", "101"),
        (1, "101", "102"),
        (1, "101", "85"),
        (100, "101", "95"),
        (1, "100", "95"),
        (1, "101", "100"),
    ],
)
async def test_breakout_risk_rejections(setup, qty, buy, sell):
    runtime, broker, _ = setup
    with pytest.raises(backend.BackendError, match="RISK_LIMIT_EXCEEDED"):
        await runtime.trading.buy_breakout("NVDA", qty, Decimal(buy), Decimal(sell))
    assert not broker.writes()


async def test_loss_limit_and_exact_ratio_boundary(setup, monkeypatch):
    runtime, broker, _ = setup
    monkeypatch.setattr(backend, "MAX_LOSS_PER_TRADE_USD", Decimal("9.99"))
    with pytest.raises(backend.BackendError, match="RISK_LIMIT_EXCEEDED"):
        await runtime.trading.buy_breakout("NVDA", 1, Decimal("110"), Decimal("99"))
    monkeypatch.setattr(backend, "MAX_LOSS_PER_TRADE_USD", Decimal("11"))
    await runtime.trading.buy_breakout("NVDA", 1, Decimal("110"), Decimal("99"))
    assert len(broker.writes()) == 1


def test_default_trading_limits():
    assert backend.MAX_ORDER_AMOUNT_USD == Decimal("45000")
    assert backend.MAX_LOSS_PER_TRADE_USD == Decimal("2000")
    assert backend.MAX_STOP_LOSS_RATIO == Decimal("0.15")


@pytest.mark.parametrize(
    "qty,buy,sell,accepted",
    [
        (100, "450", "440", True),
        (100, "450.0001", "440", False),
        (100, "300", "280", True),
        (100, "300", "279.9999", False),
        (10, "200", "170", True),
        (10, "200", "169.9999", False),
    ],
)
async def test_updated_breakout_limit_boundaries(setup, monkeypatch, qty, buy, sell, accepted):
    runtime, broker, _ = setup
    monkeypatch.setattr(backend, "MAX_ORDER_AMOUNT_USD", Decimal("45000"))
    monkeypatch.setattr(backend, "MAX_LOSS_PER_TRADE_USD", Decimal("2000"))
    broker.quote["NVDA"]["quote"].update(
        askPrice=str(Decimal(buy) - Decimal("0.4")),
        bidPrice=str(Decimal(buy) - Decimal("0.5")),
    )
    if accepted:
        await runtime.trading.buy_breakout("NVDA", qty, Decimal(buy), Decimal(sell))
        assert len(broker.writes()) == 1
    else:
        with pytest.raises(backend.BackendError, match="RISK_LIMIT_EXCEEDED"):
            await runtime.trading.buy_breakout("NVDA", qty, Decimal(buy), Decimal(sell))
        assert not broker.writes()


async def test_updated_market_buy_limit(setup, monkeypatch):
    runtime, broker, _ = setup
    monkeypatch.setattr(backend, "MAX_ORDER_AMOUNT_USD", Decimal("45000"))
    broker.quote["NVDA"]["quote"]["askPrice"] = "450"
    await runtime.trading.buy_market("NVDA", 100)
    broker.quote["NVDA"]["quote"]["askPrice"] = "450.0001"
    with pytest.raises(backend.BackendError, match="RISK_LIMIT_EXCEEDED"):
        await runtime.trading.buy_market("NVDA", 100)
    assert len(broker.writes()) == 1


async def test_no_low_price_or_breakout_deviation_rule(setup):
    runtime, broker, _ = setup
    broker.quote["NVDA"]["quote"].update(bidPrice="0.20", askPrice="0.21")
    await runtime.trading.buy_breakout("NVDA", 1, Decimal("0.22"), Decimal("0.199"))
    broker.quote["NVDA"]["quote"].update(bidPrice="999", askPrice="1000")
    await runtime.trading.buy_breakout("NVDA", 1, Decimal("1001"), Decimal("950"))
    assert len(broker.writes()) == 2


@pytest.mark.parametrize("key,value", [("askPrice", None), ("askPrice", "NaN"), ("askPrice", 0)])
async def test_invalid_quote_rejects_market_buy(setup, key, value):
    runtime, broker, _ = setup
    broker.quote["NVDA"]["quote"][key] = value
    with pytest.raises(backend.BackendError, match="VALIDATION_FAILED"):
        await runtime.trading.buy_market("NVDA", 1)
    assert not broker.writes()


async def test_options_rejected(setup):
    runtime, broker, _ = setup
    broker.quote["NVDA"]["assetMainType"] = "OPTION"
    with pytest.raises(backend.BackendError, match="VALIDATION_FAILED"):
        await runtime.trading.buy_market("NVDA", 1)
    assert not broker.writes()


async def test_replace_minimal_payload_preserves_tax_settings_and_original_order(api):
    client, _, broker = api
    broker.order_list[0].update(
        taxLotMethod="LIFO",
        specialInstruction="DO_NOT_REDUCE",
        stopType="STANDARD",
        complexOrderStrategyType="NONE",
        requestedDestination="AUTO",
        destinationLinkName="SOHO",
        price=0.0,
        stopPriceOffset=0.0,
        activationPrice=0.0,
    )
    original = copy.deepcopy(broker.order_list[0])
    response = await client.put("/api/v1/orders/123/stop", json={"new_stop": "92.00"})
    assert response.status_code == 200
    assert response.json() == {
        "result": "accepted",
        "old_order_id": "123",
        "new_order_id": "456",
        "verified": False,
    }
    writes = broker.writes()
    assert len(writes) == 1 and writes[0].method == "PUT"
    payload = json.loads(writes[0].content)
    assert payload["stopPrice"] == "92.00" and payload["duration"] == "GOOD_TILL_CANCEL"
    assert "status" not in payload and "orderId" not in payload and "editable" not in payload
    assert payload["orderLegCollection"][0] == {
        "instruction": "SELL",
        "quantity": 10,
        "instrument": {"symbol": "NVDA", "assetType": "EQUITY"},
    }
    assert payload["taxLotMethod"] == "LIFO"
    assert payload["specialInstruction"] == "DO_NOT_REDUCE"
    assert set(payload) == {
        "session",
        "duration",
        "orderType",
        "orderStrategyType",
        "stopPrice",
        "orderLegCollection",
        "taxLotMethod",
        "specialInstruction",
    }
    assert broker.order_list[0] == original


@pytest.mark.parametrize(
    "change",
    [
        {"status": "AWAITING_PARENT_ORDER"},
        {"status": "FILLED"},
        {"status": "PENDING_CANCEL"},
        {"status": "REPLACED"},
        {"orderType": "LIMIT"},
        {"editable": False},
        {"orderStrategyType": "TRIGGER"},
        {"session": "SEAMLESS"},
    ],
)
async def test_replace_refuses_inactive_or_unsupported_targets(setup, change):
    runtime, broker, _ = setup
    broker.order_list = [raw_order(**change)]
    with pytest.raises(backend.BackendError, match="ORDER_CONFLICT"):
        await runtime.trading.replace_stop(123, Decimal("92"))
    assert not broker.writes()


async def test_replace_returns_without_followup_get_or_cache_mutation(setup):
    runtime, broker, _ = setup
    before = copy.deepcopy(runtime.state.orders)
    response = await runtime.trading.replace_stop(123, Decimal("92"))
    assert response["result"] == "accepted" and response["verified"] is False
    assert [(r.method, r.url.path) for r in broker.requests if "/orders" in r.url.path] == [
        ("GET", "/trader/v1/accounts/hash/orders/123"),
        ("PUT", "/trader/v1/accounts/hash/orders/123"),
    ]
    assert runtime.state.orders == before
    assert runtime.refresh_requested.is_set()


async def test_cancel_only_target_and_status_202(api):
    client, _, broker = api
    response = await client.delete("/api/v1/orders/123")
    assert response.status_code == 202
    assert response.json()["order_id"] == "123"
    assert len(broker.writes()) == 1 and broker.writes()[0].url.path.endswith("/orders/123")


@pytest.mark.parametrize("method", ["buy", "replace", "cancel"])
async def test_write_timeout_never_retried_but_allows_new_manual_submission(setup, method):
    runtime, broker, _ = setup
    broker.write_exception = httpx.ReadTimeout

    async def execute():
        if method == "buy":
            return await runtime.trading.buy_market("NVDA", 1)
        if method == "replace":
            return await runtime.trading.replace_stop(123, Decimal("92"))
        return await runtime.trading.cancel_order(123)

    with pytest.raises(backend.BackendError, match="ORDER_RESULT_UNKNOWN") as error:
        await execute()
    assert error.value.body()["result"] == "unknown"
    assert len(broker.writes()) == 1
    broker.write_exception = None
    assert (await execute())["result"] == "accepted"
    assert len(broker.writes()) == 2


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "SCHWAB_REJECTED"),
        (401, "AUTH_REQUIRED"),
        (403, "SCHWAB_REJECTED"),
        (404, "NOT_FOUND"),
        (500, "ORDER_RESULT_UNKNOWN"),
        (503, "ORDER_RESULT_UNKNOWN"),
        (429, "SCHWAB_UNAVAILABLE"),
    ],
)
async def test_write_error_mapping_without_retry(setup, status, code):
    runtime, broker, _ = setup
    broker.write_status = status
    with pytest.raises(backend.BackendError, match=code):
        await runtime.trading.buy_market("NVDA", 1)
    assert len(broker.writes()) == 1


async def test_replace_broker_rejection_is_not_replaced_with_local_tick_rules(api):
    client, _, broker = api
    broker.write_status = 400
    response = await client.put("/api/v1/orders/123/stop", json={"new_stop": "92.123"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "SCHWAB_REJECTED"
    assert response.json()["error"]["details"] == {
        "http_status": 400,
        "broker_error": {"message": "Bad Request", "errors": []},
    }
    writes = broker.writes()
    assert len(writes) == 1 and writes[0].method == "PUT"
    assert json.loads(writes[0].content)["stopPrice"] == "92.123"


@pytest.mark.parametrize(
    "content,broker_error",
    [
        (
            b'{"message":"Synthetic rejection","errors":["Synthetic detail"]}',
            {"message": "Synthetic rejection", "errors": ["Synthetic detail"]},
        ),
        (b'{"errors":["Synthetic detail"]}', {"errors": ["Synthetic detail"]}),
        (b"", None),
        (b"<html>Request rejected by gateway</html>", None),
    ],
)
async def test_broker_rejection_details_survive_error_body_parsing(api, content, broker_error):
    client, runtime, broker = api
    original = broker.__call__

    async def handler(request):
        if request.method == "PUT":
            broker.requests.append(request)
            return httpx.Response(400, content=content)
        return await original(request)

    runtime.http._transport = httpx.MockTransport(handler)
    response = await client.put("/api/v1/orders/123/stop", json={"new_stop": "92"})
    expected = {"http_status": 400}
    if broker_error is not None:
        expected["broker_error"] = broker_error
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "SCHWAB_REJECTED"
    assert response.json()["error"]["details"] == expected
    assert len(broker.writes()) == 1


async def test_cancel_missing_order_uses_broker_404_without_preflight_get(api):
    client, _, broker = api
    broker.requests.clear()
    broker.write_status = 404
    response = await client.delete("/api/v1/orders/123")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert [r.method for r in broker.requests] == ["DELETE"]


async def test_accepted_order_can_later_be_rejected_by_broker(api):
    client, _, broker = api
    response = await client.post("/api/v1/orders/market-buy", json={"symbol": "NVDA", "qty": 1})
    assert response.status_code == 201 and response.json()["verified"] is False
    broker.order_list = [raw_order(456, status="REJECTED", editable=False, cancelable=False)]
    response = await client.get("/api/v1/orders?refresh=true")
    assert response.json()["orders"][0]["status"] == "REJECTED"
    assert len(broker.writes()) == 1


@pytest.mark.parametrize("location", ["", "/orders/", "/orders/abc", "/orders/0"])
async def test_missing_location_is_unknown(setup, location):
    runtime, broker, _ = setup
    broker.location = location
    with pytest.raises(backend.BackendError, match="ORDER_RESULT_UNKNOWN"):
        await runtime.trading.buy_market("NVDA", 1)
    assert len(broker.writes()) == 1


def test_absolute_location_and_decimal_serialization():
    assert (
        backend.location_order_id(
            httpx.Response(
                201,
                headers={
                    "Location": "https://api.schwabapi.com/trader/v1/accounts/hash/orders/12345"
                },
            )
        )
        == "12345"
    )
    response = httpx.Response(200, content=b'{"price":0.1234567890123456789012345678}')
    assert (
        backend.decimal_text(backend.decode_response(response)["price"])
        == "0.1234567890123456789012345678"
    )


async def test_concurrent_duplicate_trade_rejected(setup):
    runtime, broker, _ = setup
    broker.block_write = asyncio.Event()
    first = asyncio.create_task(runtime.trading.buy_market("NVDA", 1))
    await broker.started_write.wait()
    with pytest.raises(backend.BackendError, match="ORDER_CONFLICT"):
        await runtime.trading.buy_market("NVDA", 1)
    broker.block_write.set()
    await first
    assert len(broker.writes()) == 1


async def test_replace_cancel_share_order_lock(setup):
    runtime, broker, _ = setup
    broker.block_write = asyncio.Event()
    first = asyncio.create_task(runtime.trading.replace_stop(123, Decimal("92")))
    await broker.started_write.wait()
    with pytest.raises(backend.BackendError, match="ORDER_CONFLICT"):
        await runtime.trading.cancel_order("00123")
    broker.block_write.set()
    await first
    assert len(broker.writes()) == 1


async def test_concurrent_token_refresh_is_single_request(setup):
    runtime, broker, store = setup
    runtime.tokens.credentials.expiration = 0
    tokens = await asyncio.gather(*(runtime.tokens.token() for _ in range(30)))
    assert set(tokens) == {"renewed-access"}
    assert len([r for r in broker.requests if r.url.path == "/v1/oauth/token"]) == 1
    assert store.saved == 1
    assert store.credentials.refresh_token == "renewed-refresh"


async def test_invalid_grant_waits_for_new_keychain_tokens(setup):
    runtime, broker, store = setup
    runtime.tokens.credentials.expiration = 0
    broker.token_status = 400
    with pytest.raises(backend.BackendError, match="AUTH_REQUIRED"):
        await runtime.tokens.token()
    with pytest.raises(backend.BackendError, match="AUTH_REQUIRED"):
        await runtime.tokens.token()
    store.credentials = backend.Credentials(
        "manual-new-access", "manual-new-refresh", time.time() + 1800
    )
    assert await runtime.tokens.token() == "manual-new-access"
    assert runtime.tokens.status == "valid"
    assert len([r for r in broker.requests if r.url.path == "/v1/oauth/token"]) == 1


async def test_keychain_temporarily_locked_then_recovers(setup):
    runtime, _, store = setup
    runtime.tokens.credentials = None
    store.locked = True
    with pytest.raises(backend.BackendError, match="AUTH_REQUIRED"):
        await runtime.tokens.token()
    store.locked = False
    assert await runtime.tokens.token() == "fake-access"


async def test_keychain_save_failure_requires_auth_and_accepts_new_tokens(setup):
    runtime, _, store = setup
    store.locked = True
    runtime.tokens.credentials.expiration = 0
    with pytest.raises(backend.BackendError, match="AUTH_REQUIRED"):
        await runtime.tokens.token()
    assert runtime.tokens.status == "auth_required"
    store.locked = False
    store.credentials = backend.Credentials("manual-new", "manual-refresh", time.time() + 1800)
    assert await runtime.tokens.token() == "manual-new"


async def test_read_401_refreshes_once_without_retrying_writes(setup):
    runtime, broker, _ = setup
    original = broker.__call__
    count = 0

    async def handler(request):
        nonlocal count
        if request.url.path == "/marketdata/v1/quotes":
            count += 1
            if count == 1:
                return httpx.Response(401)
        return await original(request)

    runtime.http._transport = httpx.MockTransport(handler)
    await runtime.rest.quote("NVDA")
    assert count == 2 and runtime.tokens.credentials.access_token == "renewed-access"


def test_oauth_callback_validates_state_url_and_decodes_once():
    assert backend.callback_code("https://127.0.0.1?code=a%2Bb%40&state=ok", "ok") == "a+b@"
    url = backend.authorization_url("random")
    assert parse_qs(urlsplit(url).query)["state"] == ["random"]
    for callback in (
        "https://127.0.0.1?code=x&state=wrong",
        "https://evil.test?code=x&state=ok",
        "http://127.0.0.1/?code=x&state=ok",
        "https://127.0.0.1:5678/?code=x&state=ok",
        "https://127.0.0.1/callback?code=x&state=ok",
        "https://127.0.0.1?code=x&state=ok&state=ok",
        "https://127.0.0.1?state=ok",
    ):
        with pytest.raises(ValueError):
            backend.callback_code(callback, "ok")


@pytest.mark.parametrize("configured_path", ["", "/"])
@pytest.mark.parametrize("browser_path", ["", "/"])
def test_oauth_callback_accepts_equivalent_root_paths(monkeypatch, configured_path, browser_path):
    monkeypatch.setattr(backend, "CALLBACK_URL", "https://127.0.0.1" + configured_path)
    callback = f"https://127.0.0.1{browser_path}?code=a%2Bb%40&session=synthetic&state=ok"
    assert backend.callback_code(callback, "ok") == "a+b@"
    assert parse_qs(urlsplit(backend.authorization_url("ok")).query)["redirect_uri"] == [
        backend.CALLBACK_URL
    ]


async def test_mult_account_requires_fixed_selection(setup, monkeypatch):
    runtime, broker, _ = setup
    broker.accounts.append({"accountNumber": "5678", "hashValue": "another"})
    with pytest.raises(backend.BackendError, match="BAD_REQUEST"):
        await runtime.rest.initialize_account()
    monkeypatch.setattr(backend, "ACCOUNT_HASH", "another")
    await runtime.rest.initialize_account()
    assert runtime.rest.account_hash == "another"


async def test_account_positions_orders_contract_and_failed_snapshot_retention(api):
    client, runtime, broker = api
    await runtime.refresh_both()
    response = await client.get("/api/v1/account")
    assert response.json()["margin_balance"] == "15000.00"
    assert response.json()["buying_power"] == "54000.00"
    assert response.json()["cash_balance"] is None
    assert response.json()["available_funds"] is None
    assert response.json()["intraday_buying_power"] is None
    assert response.json()["stock_buying_power"] is None
    positions = (await client.get("/api/v1/positions")).json()
    assert positions["positions"][0]["quantity"] == "10.5"
    timestamp = runtime.state.account_updated_at
    broker.read_failure = True
    with pytest.raises(backend.BackendError):
        await runtime.refresh("account")
    assert runtime.state.account_updated_at == timestamp
    assert (await client.get("/api/v1/account")).status_code == 200
    assert runtime.health()["schwab_rest"] == "unavailable"
    order_request = next(r for r in broker.requests if r.url.path.endswith("/orders"))
    assert "status" not in order_request.url.params
    start = backend.datetime.fromisoformat(order_request.url.params["fromEnteredTime"])
    end = backend.datetime.fromisoformat(order_request.url.params["toEnteredTime"])
    assert end - start == backend.timedelta(days=59)


async def test_account_balance_fields_keep_native_sources_and_zero_values(api):
    client, runtime, broker = api
    account = broker.account["securitiesAccount"]
    account["currentBalances"].update(
        availableFunds=25000.25,
        intradayBuyingPowerAmount=120000.5,
        dayTradingBuyingPower=0.0,
        cashBalance=0.0,
        marginBalance=-5000.75,
    )
    account["projectedBalances"] = {"stockBuyingPower": 65000.5, "availableFunds": 24000.0}
    await runtime.refresh("account")
    result = (await client.get("/api/v1/account")).json()
    assert result["available_funds"] == "25000.25"
    assert result["intraday_buying_power"] == "120000.5"
    assert result["day_trading_buying_power"] == "0.0"
    assert result["stock_buying_power"] == "65000.5"
    assert result["buying_power"] == "54000.00"
    assert result["cash_balance"] == "0.0"
    assert result["margin_balance"] == "-5000.75"
    assert not broker.writes()


async def test_orders_parent_child_nullable_and_filter(api):
    client, runtime, broker = api
    child = raw_order()
    child.pop("orderId")
    child.pop("enteredTime")
    child.pop("cancelable")
    child["status"] = "AWAITING_PARENT_ORDER"
    broker.order_list = [raw_order(orderStrategyType="TRIGGER", childOrderStrategies=[child])]
    result = (await client.get("/api/v1/orders?symbol=nvda&refresh=true")).json()
    child = result["orders"][0]["child_orders"][0]
    assert child["order_id"] is None and child["parent_order_id"] == "123"
    assert child["entered_at"] is None and child["cancelable"] is None
    assert child["quantity"] == "10" and child["status"] == "AWAITING_PARENT_ORDER"
    assert (await client.get("/api/v1/orders?symbol=AAPL")).json()["orders"] == []


async def test_refreshes_coalesce_concurrent_reads(setup):
    runtime, broker, _ = setup
    await asyncio.gather(*(runtime.refresh("account") for _ in range(20)))
    requests = [r for r in broker.requests if r.url.path.endswith("/accounts/hash")]
    assert len(requests) == 1


async def test_quotes_refresh_rest_and_preserve_independent_stream_sides(api):
    client, runtime, broker = api
    first = (await client.get("/api/v1/quotes/NVDA")).json()
    assert first["suggested_buy_stop"] == "101.01" and first["suggested_sell_stop"] == "95.00"
    runtime.set_stream_status("connected")
    await runtime.handle_stream_data(
        {"service": "LEVELONE_EQUITIES", "content": [{"key": "NVDA", "1": "100.20"}]}, 0
    )
    broker.quote["NVDA"]["quote"].update(bidPrice="90", askPrice="100.50", highPrice="102")
    result = (await client.get("/api/v1/quotes/NVDA?refresh=true")).json()
    assert result["bid"] == "100.20" and result["ask"] == "100.50"
    assert result["suggested_buy_stop"] == "102.01"
    await runtime.handle_stream_data(
        {"service": "LEVELONE_EQUITIES", "content": [{"key": "NVDA", "2": "100.30"}]}, 0
    )
    result = (await client.get("/api/v1/quotes/NVDA")).json()
    assert result["bid"] == "100.20" and result["ask"] == "100.30"
    assert runtime.state.subscribed_symbols == {"NVDA"}
    assert len([r for r in broker.requests if r.url.path == "/marketdata/v1/quotes"]) == 2
    broker.read_failure = True
    assert (await client.get("/api/v1/quotes/NVDA?refresh=true")).status_code == 503


async def test_disconnected_stream_falls_back_to_rest_and_missing_high_low(setup):
    runtime, broker, _ = setup
    broker.quote["NVDA"]["quote"].update(highPrice=None, lowPrice=None)
    runtime.state.stream_quotes["NVDA"] = {"bid": "1", "ask": "2"}
    result = await runtime.get_quote("NVDA")
    assert result["bid"] == "99.90" and result["suggested_buy_stop"] is None
    assert result["suggested_sell_stop"] is None


class FakeSocket:
    def __init__(self, reject=None):
        self.frames = asyncio.Queue()
        self.sent = []
        self.reject = reject

    async def send(self, raw):
        request = json.loads(raw)["requests"][0]
        self.sent.append(request)
        await self.frames.put(
            json.dumps(
                {
                    "response": [
                        {
                            **request,
                            "content": {"code": 3 if request["command"] == self.reject else 0},
                        }
                    ]
                }
            )
        )

    def __aiter__(self):
        return self

    async def __anext__(self):
        frame = await self.frames.get()
        if frame is None:
            raise StopAsyncIteration
        return frame

    async def close(self):
        await self.frames.put(None)


async def wait_until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.005)


async def test_stream_login_subs_add_reconnect_and_bidask_fields_only(setup):
    runtime, _, _ = setup
    runtime.stream.info = {
        "schwabClientCustomerId": "customer",
        "schwabClientCorrelId": "correl",
        "schwabClientChannel": "channel",
        "schwabClientFunctionId": "function",
    }
    runtime.state.subscribed_symbols.add("NVDA")
    for connection in range(2):
        socket = FakeSocket()
        task = asyncio.create_task(runtime.stream.session(socket))
        await wait_until(lambda: runtime.state.stream_status == "connected")
        assert socket.sent[0]["command"] == "LOGIN"
        assert socket.sent[0]["parameters"]["Authorization"] == "fake-access"
        activity = socket.sent[1]
        assert activity["parameters"] == {"keys": "Account Activity", "fields": "0,1,2,3"}
        equity = socket.sent[2]
        assert equity["command"] == "SUBS" and equity["parameters"]["fields"] == "0,1,2"
        if connection == 0:
            runtime.state.subscribed_symbols.add("AAPL")
            await runtime.stream.subscribe_symbols()
            assert socket.sent[-1]["command"] == "ADD"
            assert socket.sent[-1]["parameters"] == {"keys": "AAPL", "fields": "0,1,2"}
            before = len(socket.sent)
            await runtime.stream.subscribe_symbols()
            assert len(socket.sent) == before
        else:
            assert equity["parameters"]["keys"] == "AAPL,NVDA"
        await socket.close()
        await task
        assert runtime.state.stream_status == "disconnected"


async def test_stream_login_rejection_does_not_mark_connected(setup):
    runtime, _, _ = setup
    runtime.stream.info = {
        "schwabClientCustomerId": "c",
        "schwabClientCorrelId": "r",
        "schwabClientChannel": "c",
        "schwabClientFunctionId": "f",
    }
    socket = FakeSocket(reject="LOGIN")
    with pytest.raises(backend.StreamFailure):
        await runtime.stream.session(socket)
    assert runtime.state.stream_status == "disconnected"
    assert len(socket.sent) == 1
    assert runtime.tokens.credentials.expiration == 0


async def test_stream_run_reconnects_and_passes_heartbeat_settings(setup, monkeypatch):
    runtime, broker, _ = setup
    first, second = FakeSocket(), FakeSocket()
    sockets = asyncio.Queue()
    await sockets.put(first)
    await sockets.put(second)
    options = {}

    class Connections:
        def __aiter__(self):
            return self

        async def __anext__(self):
            return await sockets.get()

    def fake_connect(url, **kwargs):
        options.update(kwargs)
        assert url == "wss://fake.test/stream"
        return Connections()

    async def preferences(path, params=None):
        return {
            "streamerInfo": [
                {
                    "streamerSocketUrl": "wss://fake.test/stream",
                    "schwabClientCustomerId": "c",
                    "schwabClientCorrelId": "r",
                    "schwabClientChannel": "c",
                    "schwabClientFunctionId": "f",
                }
            ]
        }

    monkeypatch.setattr(backend, "connect", fake_connect)
    monkeypatch.setattr(backend, "INIT_RETRY_SECONDS", 0.01)
    monkeypatch.setattr(runtime.rest, "get", preferences)
    runtime.state.subscribed_symbols.add("NVDA")
    task = runtime.background(runtime.stream.run())
    await wait_until(lambda: runtime.state.stream_status == "connected")
    await first.close()
    await wait_until(lambda: len(second.sent) == 3 and runtime.state.stream_status == "connected")
    assert second.sent[2]["command"] == "SUBS"
    assert options["ping_interval"] == 20 and options["ping_timeout"] == 20
    assert runtime.refresh_requested.is_set()
    assert not broker.writes()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_cancelled_write_is_unknown_and_releases_inflight_lock(setup):
    runtime, broker, _ = setup
    broker.block_write = asyncio.Event()
    task = asyncio.create_task(runtime.trading.buy_market("NVDA", 1))
    await broker.started_write.wait()
    task.cancel()
    with pytest.raises(backend.BackendError, match="ORDER_RESULT_UNKNOWN"):
        await task
    assert len(broker.writes()) == 1
    broker.block_write.set()
    assert (await runtime.trading.buy_market("NVDA", 1))["result"] == "accepted"
    assert len(broker.writes()) == 2


@pytest.mark.parametrize("quantity_location", ["both", "leg", "order"])
async def test_replacement_quantity_is_json_integer_with_fallback(setup, quantity_location):
    runtime, broker, _ = setup
    # GET numbers pass through parse_float=Decimal before the actual PUT is inspected.
    quantity = 100.0
    order = broker.order_list[0]
    order["quantity"] = quantity
    order["orderLegCollection"][0]["quantity"] = quantity
    if quantity_location == "leg":
        del order["quantity"]
    elif quantity_location == "order":
        del order["orderLegCollection"][0]["quantity"]
    await runtime.trading.replace_stop(123, Decimal("92"))
    payload = json.loads(broker.writes()[0].content)
    assert "quantity" not in payload
    assert payload["orderLegCollection"][0]["quantity"] == 100
    assert type(payload["orderLegCollection"][0]["quantity"]) is int


@pytest.mark.parametrize("quantity", [10.5, 0, -1, None])
async def test_replace_does_not_truncate_or_guess_quantity(api, quantity):
    client, _, broker = api
    order = broker.order_list[0]
    order["quantity"] = quantity
    order["orderLegCollection"][0]["quantity"] = quantity
    response = await client.put("/api/v1/orders/123/stop", json={"new_stop": "92"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORDER_CONFLICT"
    assert "数量" in response.json()["error"]["message"]
    assert not broker.writes()


async def test_replace_missing_duration_returns_explicit_error_without_put(api):
    client, _, broker = api
    del broker.order_list[0]["duration"]
    response = await client.put("/api/v1/orders/123/stop", json={"new_stop": "92"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORDER_CONFLICT"
    assert "有效期" in response.json()["error"]["message"]
    assert not broker.writes()


async def test_replace_omits_empty_optional_settings(api):
    client, _, broker = api
    broker.order_list[0].update(taxLotMethod=None, specialInstruction="")
    response = await client.put("/api/v1/orders/123/stop", json={"new_stop": "92"})
    assert response.status_code == 200
    payload = json.loads(broker.writes()[0].content)
    assert "taxLotMethod" not in payload and "specialInstruction" not in payload


async def test_missing_order_uses_broker_error_response(api):
    client, _, broker = api
    broker.order_read_status = 404
    response = await client.get("/api/v1/orders/999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_fill_dedup_account_filter_no_offline_replay_and_async_sound(setup, monkeypatch):
    runtime, _, _ = setup
    sound = asyncio.Event()
    release = asyncio.Event()

    async def fake_sound():
        sound.set()
        await release.wait()

    monkeypatch.setattr(backend, "play_fill_sound", fake_sound)
    listener = runtime.events.listen(runtime.snapshot())
    await anext(listener)
    connected = time.time()
    content = {
        "1": "1234",
        "2": "OrderFillCompleted",
        "3": json.dumps({"SchwabOrderID": "123", "BaseEvent": {"OrderInfo": {"Symbol": "NVDA"}}}),
    }
    data = {
        "service": "ACCT_ACTIVITY",
        "timestamp": int((connected + 1) * 1000),
        "content": [content],
    }
    await runtime.handle_stream_data(data, connected)
    await runtime.handle_stream_data(data, connected)
    await sound.wait()
    event = await anext(listener)
    assert "event: order_filled" in event and '"symbol":"NVDA"' in event
    assert runtime.state.notified_fills == {"123"}
    assert runtime.refresh_requested.is_set()
    content["3"] = json.dumps({"SchwabOrderID": "124"})
    data["timestamp"] = int((connected - 1) * 1000)
    await runtime.handle_stream_data(data, connected)
    assert runtime.state.notified_fills == {"123"}
    content["1"] = "another-account"
    data["timestamp"] = int((connected + 2) * 1000)
    await runtime.handle_stream_data(data, connected)
    assert runtime.state.notified_fills == {"123"}
    release.set()
    await listener.aclose()


async def test_sse_multiclient_snapshot_quote_contract_and_cleanup(setup):
    runtime, _, _ = setup
    first = runtime.events.listen(runtime.snapshot())
    second = runtime.events.listen(runtime.snapshot())
    assert "snapshot_updated" in await anext(first)
    assert "snapshot_updated" in await anext(second)
    runtime.state.subscribed_symbols.add("NVDA")
    await runtime.handle_stream_data(
        {"service": "LEVELONE_EQUITIES", "content": [{"key": "NVDA", "1": 100}]}, 0
    )
    event = await anext(first)
    assert event == await anext(second)
    payload = json.loads(event.split("data: ")[1])
    assert set(payload) == {"symbol", "bid", "ask", "updated_at"}
    assert payload["bid"] == "100"
    await first.aclose()
    await second.aclose()
    assert not runtime.events.clients


async def test_sse_slow_client_is_disconnected(setup):
    runtime, _, _ = setup
    listener = runtime.events.listen(runtime.snapshot())
    await anext(listener)
    for _ in range(257):
        runtime.events.publish("stream_status", {"connected": False})
    with pytest.raises(StopAsyncIteration):
        await anext(listener)
    assert not runtime.events.clients


@pytest.mark.parametrize(
    "headers", [{"Host": "evil.test"}, {"Origin": "https://evil.test"}, {"Origin": "null"}]
)
async def test_local_access_blocks_untrusted_writes(api, headers):
    client, _, broker = api
    response = await client.post(
        "/api/v1/orders/market-buy", json={"symbol": "NVDA", "qty": 1}, headers=headers
    )
    assert response.status_code == 400
    assert not broker.writes()


async def test_json_required_and_standard_cors_preflight(api):
    client, _, broker = api
    response = await client.post(
        "/api/v1/orders/market-buy",
        content='{"symbol":"NVDA","qty":1}',
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 400
    response = await client.options(
        "/api/v1/orders/market-buy",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert not broker.writes()


async def test_delete_ignores_body_and_only_cancels_path_target(api):
    client, _, broker = api
    response = await client.request("DELETE", "/api/v1/orders/123", json={"other_order": 456})
    assert response.status_code == 202
    writes = broker.writes()
    assert len(writes) == 1 and writes[0].url.path.endswith("/orders/123")
    assert writes[0].content == b""


@pytest.mark.parametrize("wake_with_event", [False, True])
async def test_maintenance_refreshes_on_interval_or_event(setup, monkeypatch, wake_with_event):
    runtime, broker, _ = setup
    monkeypatch.setattr(backend, "INIT_RETRY_SECONDS", 3600 if wake_with_event else 0.01)

    async def idle_stream():
        await asyncio.Event().wait()

    monkeypatch.setattr(runtime.stream, "run", idle_stream)
    await runtime.start()
    await wait_until(lambda: runtime.state.account_updated_at is not None)
    broker.account["securitiesAccount"]["positions"][0]["longQuantity"] = 20
    if wake_with_event:
        runtime.refresh_requested.set()
    await wait_until(lambda: runtime.state.positions[0]["quantity"] == "20")


async def test_event_during_refresh_requests_another_refresh(setup, monkeypatch):
    runtime, _, _ = setup
    monkeypatch.setattr(backend, "INIT_RETRY_SECONDS", 3600)
    started, release, refreshed_again = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def refresh_both():
        if started.is_set():
            refreshed_again.set()
        else:
            started.set()
            await release.wait()

    async def idle_stream():
        await asyncio.Event().wait()

    monkeypatch.setattr(runtime, "refresh_both", refresh_both)
    monkeypatch.setattr(runtime.stream, "run", idle_stream)
    await runtime.start()
    await asyncio.wait_for(started.wait(), timeout=2)
    runtime.refresh_requested.set()
    release.set()
    await asyncio.wait_for(refreshed_again.wait(), timeout=2)


async def test_local_api_starts_while_keychain_unavailable_and_recovers(setup, monkeypatch):
    runtime, broker, store = setup
    runtime.tokens.credentials = None
    runtime.tokens.status = "auth_required"
    store.credentials = None
    runtime.rest.account_hash = None
    monkeypatch.setattr(backend, "INIT_RETRY_SECONDS", 0.01)
    app = backend.create_app(runtime=runtime)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:5678"
        ) as client:
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
            assert response.json()["auth_status"] == "auth_required"
            assert response.json()["account_initialized"] is False
            store.credentials = credentials()
            await wait_until(lambda: runtime.state.account_updated_at is not None)
            assert (await client.get("/api/v1/health")).json()["auth_status"] == "valid"
            assert not broker.writes()


async def test_network_failure_initialization_recovers_without_restart(setup, monkeypatch):
    runtime, broker, _ = setup
    runtime.rest.account_hash = None
    broker.read_failure = True
    monkeypatch.setattr(backend, "INIT_RETRY_SECONDS", 0.01)

    async def idle_stream():
        await asyncio.Event().wait()

    monkeypatch.setattr(runtime.stream, "run", idle_stream)
    await runtime.start()
    await wait_until(lambda: runtime.initialization_error is not None)
    assert runtime.health()["service"] == "running"
    broker.read_failure = False
    await wait_until(lambda: runtime.initialization_error is None)
    assert runtime.health()["schwab_rest"] == "connected"


def test_exactly_twelve_business_routes():
    runtime = object.__new__(backend.Runtime)
    app = backend.create_app(runtime=runtime)
    assert len(app.routes) == 12


def test_request_models_accept_decimals_without_string_roundtrip():
    price = Decimal("92.123")
    assert backend.ReplaceRequest(new_stop=price).new_stop is price
    request = backend.BreakoutRequest(
        symbol="NVDA", qty=1, buy_stop=Decimal("100"), sell_stop=price
    )
    assert request.sell_stop is price


def test_keychain_stores_one_oauth_json_record(monkeypatch):
    entries, writes = {}, []

    class FakeKeyring:
        def get_password(self, service, key):
            return entries.get((service, key))

        def set_password(self, service, key, value):
            entries[service, key] = value
            writes.append(key)

        def delete_password(self, service, key):
            del entries[service, key]

    monkeypatch.setattr(backend.KeychainStore, "backend", staticmethod(FakeKeyring))
    store = backend.KeychainStore()
    store.set_secret("fake-secret")
    expected = credentials()
    store.save(expected)
    assert writes == ["client_secret", "oauth_tokens"]
    assert store.load() == expected
    assert json.loads(entries[backend.KEYCHAIN_SERVICE, "oauth_tokens"]) == vars(expected)
    store.clear()
    assert store.load() is None and store.secret() == "fake-secret"


async def test_auth_callback_uses_visible_input(setup, monkeypatch):
    _, broker, store = setup
    prompts = []
    auth_http = httpx.AsyncClient(transport=httpx.MockTransport(broker))
    monkeypatch.setattr(backend, "KeychainStore", lambda: store)
    monkeypatch.setattr(backend.secrets, "token_urlsafe", lambda _: "fake-state")
    monkeypatch.setattr(backend.webbrowser, "open", lambda _: None)
    monkeypatch.setattr(backend.httpx, "AsyncClient", lambda **_: auth_http)

    def visible_input(prompt):
        prompts.append(prompt)
        return "https://127.0.0.1?code=fake-code&state=fake-state"

    monkeypatch.setattr("builtins.input", visible_input)
    await backend.authorize()
    assert prompts == ["请粘贴完整 Callback URL: "]
    assert store.credentials.access_token == "renewed-access"


def test_main_reports_exception_type_and_message(monkeypatch, capsys):
    async def fail_auth():
        raise RuntimeError("test Keychain failure")

    monkeypatch.setattr(backend, "authorize", fail_auth)
    monkeypatch.setattr(backend.sys, "argv", ["schwab_backend.py", "auth"])
    with pytest.raises(SystemExit) as error:
        backend.main()
    assert error.value.code == 1
    assert "RuntimeError" in (output := capsys.readouterr().err)
    assert "test Keychain failure" in output


async def test_new_port_and_origins(api):
    client, _, broker = api
    assert backend.PORT == 5678
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    response = await client.post(
        "/api/v1/orders/market-buy",
        json={"symbol": "NVDA", "qty": 1},
        headers={"Origin": "http://127.0.0.1:5678"},
    )
    assert response.status_code == 201
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5678"
    assert len(broker.writes()) == 1


async def test_execution_details_in_order_reads_and_snapshot(api):
    client, runtime, broker = api
    execution = {
        "legId": 1,
        "quantity": 5.0,
        "price": 140.25,
        "time": "2026-10-16T13:56:38+0000",
    }
    child = raw_order(
        124,
        status="FILLED",
        filledQuantity=10,
        orderActivityCollection=[
            {
                "activityId": activity_id,
                "activityType": "EXECUTION",
                "executionType": "FILL",
                "executionLegs": [execution],
            }
            for activity_id in (11, 12)
        ],
    )
    broker.order_list = [raw_order(childOrderStrategies=[child])]
    await runtime.refresh("orders")
    expected = [
        {
            "activity_id": str(activity_id),
            "leg_id": "1",
            "quantity": "5.0",
            "price": "140.25",
            "time": "2026-10-16T13:56:38Z",
        }
        for activity_id in (11, 12)
    ]
    orders = (await client.get("/api/v1/orders")).json()["orders"]
    assert orders[0]["executions"] == []
    assert orders[0]["child_orders"][0]["executions"] == expected
    assert runtime.snapshot()["orders"] == orders
    single = (await client.get("/api/v1/orders/123")).json()
    assert single["child_orders"][0]["executions"] == expected


async def test_native_open_profit_and_quote_reference_fields(api):
    client, runtime, broker = api
    broker.account["securitiesAccount"]["positions"][0].update(
        longOpenProfitLoss=-1511.399999999998,
        currentDayProfitLoss=472.200000000001,
        currentDayProfitLossPercentage=2.69,
    )
    await runtime.refresh("account")
    position = (await client.get("/api/v1/positions")).json()["positions"][0]
    assert position["open_profit_loss"] == "-1511.399999999998"
    assert position["day_profit_loss"] == "472.200000000001"
    assert position["day_profit_loss_percent"] == "2.69"
    broker.quote["NVDA"]["quote"].update(
        lastPrice=216.72, closePrice=214.13, highPrice=0.0, lowPrice=0.0
    )
    quote = (await client.get("/api/v1/quotes/NVDA")).json()
    assert quote["last_price"] == "216.72"
    assert quote["close_price"] == "214.13"
    assert "regular_market_time" not in quote
    assert quote["suggested_buy_stop"] is None
    quote_requests = [r for r in broker.requests if r.url.path == "/marketdata/v1/quotes"]
    assert len(quote_requests) == 1
    assert quote_requests[0].url.params["fields"] == "quote"


@pytest.mark.parametrize("destination", [None, "", "AUTO", "BEST", "SMART", "INET"])
async def test_replacement_omits_route_echo_and_broker_execution_venue(setup, destination):
    runtime, broker, _ = setup
    broker.order_list[0].update(requestedDestination=destination, destinationLinkName="SOHO")
    await runtime.trading.replace_stop(123, Decimal("4.95"))
    payload = json.loads(broker.writes()[0].content)
    assert "requestedDestination" not in payload
    assert "destinationLinkName" not in payload
    assert payload["stopPrice"] == "4.95"
    assert len(broker.writes()) == 1


async def test_cmct_response_defaults_produce_only_core_equity_stop_fields(setup):
    runtime, broker, _ = setup
    raw = broker.order_list[0]
    raw.update(
        quantity=3000.0,
        stopPrice="4.56",
        complexOrderStrategyType="NONE",
        requestedDestination="AUTO",
        destinationLinkName="SOHO",
        stopType="STANDARD",
    )
    raw["orderLegCollection"][0].update(quantity=3000.0)
    raw["orderLegCollection"][0]["instrument"].update(symbol="CMCT", cusip="12564W219")
    original = copy.deepcopy(raw)
    await runtime.trading.replace_stop(123, Decimal("4.95"))
    assert len(broker.writes()) == 1
    assert json.loads(broker.writes()[0].content) == {
        "session": "NORMAL",
        "duration": "GOOD_TILL_CANCEL",
        "orderType": "STOP",
        "orderStrategyType": "SINGLE",
        "stopPrice": "4.95",
        "orderLegCollection": [
            {
                "instruction": "SELL",
                "quantity": 3000,
                "instrument": {"symbol": "CMCT", "assetType": "EQUITY"},
            }
        ],
    }
    assert raw == original


@pytest.mark.parametrize(
    "settings",
    [
        {"stopType": "BID"},
        {"stopType": "MARK"},
        {"stopPriceLinkBasis": "BID"},
        {"stopPriceLinkType": "PERCENT"},
        {"stopPriceOffset": "1.25"},
        {"activationPrice": "80"},
    ],
)
async def test_replacement_refuses_to_reset_original_trigger_settings(api, settings):
    client, _, broker = api
    broker.order_list[0].update(settings)
    original = copy.deepcopy(broker.order_list[0])
    response = await client.put("/api/v1/orders/123/stop", json={"new_stop": "4.95"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORDER_CONFLICT"
    assert "不能自动更改原触发设置" in response.json()["error"]["message"]
    assert not broker.writes()
    assert broker.order_list[0] == original


async def test_replacement_does_not_interpret_dollar_quantity_as_shares(setup):
    runtime, broker, _ = setup
    broker.order_list[0]["orderLegCollection"][0]["quantityType"] = "DOLLARS"
    with pytest.raises(backend.BackendError, match="ORDER_CONFLICT"):
        await runtime.trading.replace_stop(123, Decimal("4.95"))
    assert not broker.writes()


@pytest.mark.parametrize("method", ["FIFO", "LIFO"])
async def test_minimal_replacement_keeps_explicit_tax_lot_selection(setup, method):
    runtime, broker, _ = setup
    broker.order_list[0].update(taxLotMethod=method)
    await runtime.trading.replace_stop(123, Decimal("4.95"))
    assert json.loads(broker.writes()[0].content)["taxLotMethod"] == method

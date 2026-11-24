"""Longbridge account contexts, one K-line entry and per-account budgets."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from pathlib import Path

from longbridge.openapi import AdjustType, AsyncQuoteContext, Config, Period, PushCandlestickMode, SubType, TradeSessions

from ..config import redact, credential_section
from ..paths import RuntimePaths
from .usage import SymbolUsage

SDK_PERIODS = {'1d': Period.Day, '5m': Period.Min_5, '15m': Period.Min_15,
               '30m': Period.Min_30, '1h': Period.Min_60, '2h': Period.Min_120}
log = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, limit: int = 10, window: float = 1.0):
        self.limit, self.window = limit, window
        self.starts = deque()
        self.lock = asyncio.Lock()

    async def wait(self, background=False):
        while True:
            async with self.lock:
                now = time.monotonic()
                while self.starts and now - self.starts[0][0] >= self.window:
                    self.starts.popleft()
                background_starts = [t for t, bg in self.starts if bg]
                if len(self.starts) < self.limit and (not background or len(background_starts) < 8):
                    self.starts.append((now, background))
                    return
                oldest = self.starts[0][0] if len(self.starts) >= self.limit else background_starts[0]
                delay = max(0, oldest + self.window - now)
            # Never hold the lock while waiting for the background allowance.
            await asyncio.sleep(delay)


class AccountContext:
    def __init__(self, values, region):
        self.id = values['id']
        self.secrets = tuple(values[field].strip() for field in ('app_key', 'app_secret', 'access_token'))
        domain = 'cn' if region == 'cn' else 'com'
        self.config = Config.from_apikey(
            *self.secrets, enable_overnight=True, enable_print_quote_packages=False,
            push_candlestick_mode=PushCandlestickMode.Realtime,
            http_url=f'https://openapi.longbridge.{domain}',
            quote_ws_url=f'wss://openapi-quote.longbridge.{domain}/v2')
        self.context = None
        self.limiter = RateLimiter()
        self.inflight, self.background = asyncio.Semaphore(5), asyncio.Semaphore(3)
        self.candle_symbols = set()


class LongbridgeClient:
    def __init__(self, credentials: Path, allowed: set[str], runtime: Path,
                 region: str = 'cn', timeout: float = 15):
        self.allowed = frozenset(allowed)
        self.candle_allowed = self.allowed
        values = credential_section(credentials, 'longbridge')['accounts']
        ids = [value['id'] for value in values]
        if not ids or len(set(ids)) != len(ids) or any(not account for account in ids):
            raise ValueError('Longbridge accounts require nonempty unique IDs')
        os.environ['LONGBRIDGE_REGION'] = 'cn' if region == 'cn' else 'hk'
        self.accounts = {value['id']: AccountContext(value, region) for value in values}
        self.primary = self.accounts[ids[0]]
        self.secrets = tuple(secret for account in self.accounts.values() for secret in account.secrets)
        self.timeout = timeout
        self.usage = SymbolUsage(RuntimePaths(runtime).longbridge_usage, ids)
        self.usage_task = None
        self.candle_contexts = {}
        self.on_candle, self.candle_loop = None, None
        self.on_account_change = None

    def check(self, symbols: list[str], *, full=False) -> None:
        allowed = self.candle_allowed if full else self.allowed
        if not set(symbols) <= allowed:
            scope = 'Focus and Holdings' if full else 'quote subscription'
            raise ValueError(f'API request outside current {scope} universe')

    def context(self, account=None):
        account = account or self.primary
        if account.context is None:
            account.context = ctx = AsyncQuoteContext.create(account.config)
            ctx.set_on_candlestick(lambda symbol, event: self._candle_push(ctx, symbol, event))
            log.info('Longbridge context created account=%s', account.id)
        return account.context

    def set_on_candlestick(self, callback, on_account_change=None):
        self.on_candle = callback
        self.on_account_change = on_account_change
        self.candle_loop = asyncio.get_running_loop()

    def _candle_push(self, ctx, symbol, event):
        callback, loop = self.on_candle, self.candle_loop
        if callback is None or loop is None:
            return
        def deliver():
            tf = next(tf for tf, period in SDK_PERIODS.items() if period == event.period)
            account = self.candle_contexts.get((symbol, tf))
            if callback is self.on_candle and account is not None and account.context is ctx:
                callback(symbol, event)
        try:
            loop.call_soon_threadsafe(deliver)
        except RuntimeError:
            pass

    def close(self):
        # Tasks and callbacks stop before SDK contexts are released; usage survives reconnects.
        self.candle_contexts.clear()
        for account in self.accounts.values():
            if account.context is not None:
                account.context.set_on_candlestick(lambda *_: None)
                account.context = None
            account.candle_symbols.clear()

    async def aclose(self):
        self.set_on_candlestick(None)
        self.close()
        if self.usage_task is not None:
            self.usage_task.cancel()
            await asyncio.gather(self.usage_task, return_exceptions=True)
            self.usage_task = None
        await self.usage.flush()

    async def call(self, method, *args, background=False, symbols=None, full=False, account=None):
        account = account or self.primary
        if background:
            async with account.background:
                return await self._call(account, method, args, True, symbols, full)
        return await self._call(account, method, args, False, symbols, full)

    async def _call(self, account, method, args, background, symbols=None, full=False):
        async with account.inflight:
            await account.limiter.wait(background)
            if symbols is not None:
                self.check(symbols, full=full)
            try:
                return await asyncio.wait_for(method(*args), timeout=self.timeout)
            except TimeoutError:
                raise TimeoutError(f'Longbridge request timed out after {self.timeout}s') from None
            except Exception as exc:
                raise RuntimeError(redact(str(exc), self.secrets)) from None

    async def kline_request(self, symbol, timeframe, *, count=None, background=False):
        self.check([symbol], full=True)
        account = self.accounts[self.usage.access(symbol)]
        if self.on_account_change and any(s == symbol and owner is not account
                                          for (s, _), owner in self.candle_contexts.items()):
            self.on_account_change(symbol)
        if self.usage_task is None:
            self.usage_task = asyncio.create_task(self.usage.run())
        ctx = self.context(account)
        if count is not None:
            return await self.call(ctx.candlesticks, symbol, SDK_PERIODS[timeframe], count,
                                   AdjustType.ForwardAdjust, TradeSessions.Intraday,
                                   background=background, symbols=[symbol], full=True, account=account)
        key = symbol, timeframe
        previous = self.candle_contexts.get(key)
        if previous is not None and previous is not account:
            await self.unsubscribe_candles(symbol, timeframe)
        # Explicit subscriptions keep SDK period deletion local, as on the primary account.
        if account is not self.primary and symbol not in account.candle_symbols:
            await self.call(ctx.subscribe, [symbol], [SubType.Quote, SubType.Trade],
                            symbols=[symbol], full=True, account=account)
            account.candle_symbols.add(symbol)
        self.candle_contexts[key] = account
        return await self.call(ctx.subscribe_candlesticks, symbol, SDK_PERIODS[timeframe],
                               TradeSessions.Intraday, symbols=[symbol], full=True, account=account)

    async def candles(self, symbol: str, timeframe: str, count: int = 1000, *, background=False):
        if not 1 <= count <= 1000:
            raise ValueError('Count must be 1..1000')
        return await self.kline_request(symbol, timeframe, count=count, background=background)

    async def subscribe(self, ctx, symbols: list[str], *, quote_only=False):
        self.check(symbols, full=not quote_only)
        types = [SubType.Quote] if quote_only else [SubType.Quote, SubType.Trade]
        await self.call(ctx.subscribe, symbols, types, symbols=symbols, full=not quote_only)

    async def subscribe_candles(self, symbol, timeframe):
        return await self.kline_request(symbol, timeframe)

    async def unsubscribe_candles(self, symbol, timeframe):
        key = symbol, timeframe
        account = self.candle_contexts.get(key)
        if account is None:
            return
        await account.context.unsubscribe_candlesticks(symbol, SDK_PERIODS[timeframe])
        self.candle_contexts.pop(key, None)
        if (account is not self.primary and symbol in account.candle_symbols
                and not any(s == symbol and owner is account
                            for (s, _), owner in self.candle_contexts.items())):
            await self.call(account.context.unsubscribe, [symbol], [SubType.Quote, SubType.Trade], account=account)
            account.candle_symbols.discard(symbol)

    async def snapshot(self, ctx, symbols: list[str]):
        self.check(symbols)
        return await self.call(ctx.quote, symbols, symbols=symbols)

    async def unsubscribe(self, ctx, symbols: list[str], *, quote_only=False):
        # Removed symbols must still be unsubscribed after the whitelist changes.
        await self.call(ctx.unsubscribe, symbols, [SubType.Quote] if quote_only else [SubType.Quote, SubType.Trade])

    async def validate_ticker(self, ticker: str):
        from ..workspace import normalize_ticker
        symbol = normalize_ticker(ticker) + '.US'
        rows = await self.call(self.context().static_info, [symbol])
        info = next((row for row in rows if row.symbol == symbol and row.name_en), None)
        if info is None:
            raise ValueError('US ticker not found')
        return {'ticker': ticker, 'name': info.name_en}

"""The single Longbridge SDK context and its request budget."""
from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from pathlib import Path

from longbridge.openapi import AdjustType, AsyncQuoteContext, Config, Period, PushCandlestickMode, SubType, TradeSessions

from ..config import redact

SDK_PERIODS = {'1d': Period.Day, '5m': Period.Min_5, '15m': Period.Min_15,
               '30m': Period.Min_30, '1h': Period.Min_60, '2h': Period.Min_120}


def read_credentials(path: Path) -> tuple[str, str, str]:
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if len(lines) != 6 or lines[::2] != ['App Key', 'App Secret', 'App Token']:
        raise ValueError('Expected App Key / App Secret / App Token labels, each followed by its value')
    return tuple(lines[1::2])


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


class LongbridgeClient:
    def __init__(self, credentials: Path, allowed: set[str], runtime: Path,
                 region: str = 'cn', timeout: float = 15):
        self.allowed = frozenset(allowed)
        self.candle_allowed = self.allowed
        self.secrets = read_credentials(credentials)
        domain = 'cn' if region == 'cn' else 'com'
        os.environ['LONGBRIDGE_REGION'] = 'cn' if region == 'cn' else 'hk'
        self.config = Config.from_apikey(
            *self.secrets, enable_print_quote_packages=False, push_candlestick_mode=PushCandlestickMode.Realtime,
            http_url=f'https://openapi.longbridge.{domain}',
            quote_ws_url=f'wss://openapi-quote.longbridge.{domain}/v2')
        self.timeout, self.limiter = timeout, RateLimiter()
        self._context = None
        self.inflight = asyncio.Semaphore(5)
        self.background = asyncio.Semaphore(3)

    def check(self, symbols: list[str], *, full=False) -> None:
        allowed = self.candle_allowed if full else self.allowed
        if not set(symbols) <= allowed:
            scope = 'Focus and Holdings' if full else 'quote subscription'
            raise ValueError(f'API request outside current {scope} universe')

    def context(self):
        if self._context is None:
            self._context = AsyncQuoteContext.create(self.config)
        return self._context

    def close(self):
        # All requests and Quote callbacks must be stopped before dropping the SDK context.
        self._context = None

    async def call(self, method, *args, background=False, symbols=None, full=False):
        if background:
            async with self.background:
                return await self._call(method, args, True, symbols, full)
        return await self._call(method, args, False, symbols, full)

    async def _call(self, method, args, background, symbols=None, full=False):
        async with self.inflight:
            await self.limiter.wait(background)
            if symbols is not None:
                self.check(symbols, full=full)
            try:
                return await asyncio.wait_for(method(*args), timeout=self.timeout)
            except TimeoutError:
                raise TimeoutError(f'Longbridge request timed out after {self.timeout}s') from None
            except Exception as exc:
                raise RuntimeError(redact(str(exc), self.secrets)) from None

    async def candles(self, symbol: str, timeframe: str, count: int = 1000, *, background=False):
        self.check([symbol], full=True)
        if not 1 <= count <= 1000:
            raise ValueError('Count must be 1..1000')
        ctx = self.context()
        return await self.call(ctx.candlesticks, symbol, SDK_PERIODS[timeframe], count,
                               AdjustType.ForwardAdjust, TradeSessions.Intraday, background=background, symbols=[symbol], full=True)

    async def subscribe(self, ctx, symbols: list[str], *, quote_only=False):
        self.check(symbols, full=not quote_only)
        types = [SubType.Quote] if quote_only else [SubType.Quote, SubType.Trade]
        await self.call(ctx.subscribe, symbols, types, symbols=symbols, full=not quote_only)

    async def subscribe_candles(self, ctx, symbol, timeframe):
        self.check([symbol], full=True)
        return await self.call(ctx.subscribe_candlesticks, symbol, SDK_PERIODS[timeframe],
                               TradeSessions.Intraday, symbols=[symbol], full=True)

    async def unsubscribe_candles(self, ctx, symbol, timeframe):
        # Quote/Trade remain explicitly subscribed until all periods are removed.
        # This operation therefore only removes the SDK's local period state.
        await ctx.unsubscribe_candlesticks(symbol, SDK_PERIODS[timeframe])

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

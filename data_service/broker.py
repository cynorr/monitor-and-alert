from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from pathlib import Path

from longbridge.openapi import AdjustType, AsyncQuoteContext, Config, Period, SubType, TradeSessions

from .config import read_credentials, redact

SDK_PERIODS = {'1d': Period.Day, '5m': Period.Min_5, '15m': Period.Min_15,
               '30m': Period.Min_30, '1h': Period.Min_60}


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


class Broker:
    def __init__(self, credentials: Path, allowed: set[str], runtime: Path,
                 region: str = 'cn', timeout: float = 15):
        self.allowed = frozenset(allowed)
        self.secrets = read_credentials(credentials)
        domain = 'cn' if region == 'cn' else 'com'
        os.environ['LONGBRIDGE_REGION'] = 'cn' if region == 'cn' else 'hk'
        self.config = Config.from_apikey(
            *self.secrets, enable_print_quote_packages=False,
            http_url=f'https://openapi.longbridge.{domain}',
            quote_ws_url=f'wss://openapi-quote.longbridge.{domain}/v2')
        self.timeout, self.limiter = timeout, RateLimiter()
        self._context = None
        self.inflight = asyncio.Semaphore(5)
        self.background = asyncio.Semaphore(3)

    def check(self, symbols: list[str]) -> None:
        if not set(symbols) <= self.allowed:
            raise ValueError('API request outside startup focus/wait universe')

    def context(self):
        if self._context is None:
            self._context = AsyncQuoteContext.create(self.config)
        return self._context

    async def call(self, method, *args, background=False):
        if background:
            async with self.background:
                return await self._call(method, args, True)
        return await self._call(method, args, False)

    async def _call(self, method, args, background):
        async with self.inflight:
            await self.limiter.wait(background)
            try:
                return await asyncio.wait_for(method(*args), timeout=self.timeout)
            except TimeoutError:
                raise TimeoutError(f'Longbridge request timed out after {self.timeout}s') from None
            except Exception as exc:
                raise RuntimeError(redact(str(exc), self.secrets)) from None

    async def candles(self, symbol: str, timeframe: str, count: int = 1000, *, background=False):
        self.check([symbol])
        if not 1 <= count <= 1000:
            raise ValueError('Count must be 1..1000')
        ctx = self.context()
        return await self.call(ctx.candlesticks, symbol, SDK_PERIODS[timeframe], count,
                               AdjustType.NoAdjust, TradeSessions.Intraday, background=background)

    async def subscribe(self, ctx, symbols: list[str]):
        self.check(symbols)
        await self.call(ctx.subscribe, symbols, [SubType.Quote])

    async def snapshot(self, ctx, symbols: list[str]):
        self.check(symbols)
        return await self.call(ctx.quote, symbols)

    async def unsubscribe(self, ctx, symbols: list[str]):
        self.check(symbols)
        await self.call(ctx.unsubscribe, symbols, [SubType.Quote])

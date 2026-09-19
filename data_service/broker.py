from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from pathlib import Path

from longbridge.openapi import AdjustType, AsyncQuoteContext, Config, Period, SubType, TradeSessions

from .calendar import ET
from .config import read_credentials, redact
from .store import HistoryQuotaTracker

SDK_PERIODS = {'1d': Period.Day, '5m': Period.Min_5, '15m': Period.Min_15,
               '30m': Period.Min_30, '1h': Period.Min_60}


class RateLimiter:
    def __init__(self, interval: float = 0.55):
        self.interval, self.last = interval, 0.0
        self.lock = asyncio.Lock()

    async def wait(self):
        async with self.lock:
            await asyncio.sleep(max(0, self.last + self.interval - time.monotonic()))
            self.last = time.monotonic()


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
        self.history_context = None
        self.quota = HistoryQuotaTracker(runtime / 'history_symbol_usage.json')

    def check(self, symbols: list[str]) -> None:
        if not set(symbols) <= self.allowed:
            raise ValueError('API request outside startup focus/wait universe')

    def context(self):
        return AsyncQuoteContext.create(self.config)

    async def call(self, method, *args):
        await self.limiter.wait()
        try:
            return await asyncio.wait_for(method(*args), timeout=self.timeout)
        except TimeoutError:
            raise TimeoutError(f'Longbridge request timed out after {self.timeout}s') from None
        except Exception as exc:
            raise RuntimeError(redact(str(exc), self.secrets)) from None

    async def candles(self, symbol: str, timeframe: str, count: int = 1000,
                      before: int | None = None):
        self.check([symbol])
        if not 1 <= count <= 1000:
            raise ValueError('Count must be 1..1000')
        self.quota.record(datetime.now(ET).strftime('%Y-%m'), symbol)
        if self.history_context is None:
            self.history_context = self.context()
        ctx = self.history_context
        if before is None:
            return await self.call(ctx.candlesticks, symbol, SDK_PERIODS[timeframe], count,
                                   AdjustType.NoAdjust, TradeSessions.Intraday)
        # Offset API accepts exchange-local wall time, not UTC wall time.
        walltime = datetime.fromtimestamp(before, ET).replace(tzinfo=None)
        return await self.call(ctx.history_candlesticks_by_offset, symbol, SDK_PERIODS[timeframe],
                               AdjustType.NoAdjust, False, count, walltime, TradeSessions.Intraday)

    async def subscribe(self, ctx, symbols: list[str]):
        self.check(symbols)
        await self.call(ctx.subscribe, symbols, [SubType.Quote])

    async def snapshot(self, ctx, symbols: list[str]):
        self.check(symbols)
        return await self.call(ctx.quote, symbols)

    async def unsubscribe(self, ctx, symbols: list[str]):
        self.check(symbols)
        await self.call(ctx.unsubscribe, symbols, [SubType.Quote])

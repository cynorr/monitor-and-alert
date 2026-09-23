"""Deterministic synthetic sessions. No credentials, SDK, network or production DB."""
from __future__ import annotations

import asyncio
import math
import time
import zlib
from datetime import date, datetime, timedelta
from functools import lru_cache
from types import SimpleNamespace

from data_service.calendar import ET, TradingCalendar


class SessionClock:
    """Advance exchange time, skipping closed sessions without changing system time."""
    def __init__(self, calendar, start, speed=1):
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError('speed must be a positive finite number')
        if not calendar.is_open(start):
            raise ValueError('start must be inside a regular trading session')
        self.calendar, self.value, self.speed = calendar, float(start), speed
        self.last = time.monotonic()

    def advance(self, seconds):
        while seconds > 0:
            day = datetime.fromtimestamp(self.value, ET).date()
            _, closed = self.calendar.session(day)
            remaining = closed - self.value
            if seconds < remaining:
                self.value += seconds
                return
            seconds -= remaining
            next_day = day + timedelta(days=1)
            while not self.calendar.session(next_day):
                next_day += timedelta(days=1)
            self.value = float(self.calendar.session(next_day)[0])

    def __call__(self):
        real = time.monotonic()
        self.advance((real - self.last) * self.speed)
        self.last = real
        return int(self.value)


def default_start(calendar):
    today = datetime.now(ET).date()
    day = calendar.days(today - timedelta(days=10), today)[-1]
    opened, closed = calendar.session(day)
    return min(opened + 4 * 3600 + 14 * 60 + 45, closed - 15)


class Market:
    def __init__(self, symbols, calendar: TradingCalendar, clock):
        self.allowed = frozenset(symbols)
        self.calendar, self.clock = calendar, clock

    def check(self, symbols):
        if not set(symbols) <= self.allowed:
            raise ValueError('Symbol outside simulation workspace')

    @lru_cache(maxsize=16000)
    def path(self, symbol: str, day: date):
        self.check([symbol])
        opened, closed = self.calendar.session(day)
        seed = zlib.crc32(symbol.encode())
        index = day.toordinal()
        anchor = 15 + seed % 380
        base = anchor * (1 + 0.12 * math.sin(index / 47 + seed % 17) + 0.035 * math.sin(index / 9))
        closing = base * (1 + 0.024 * math.sin(index + seed))
        high, low = max(base, closing) * 1.012, min(base, closing) * 0.988
        prices = (base, high, low, closing) if (seed + index) % 2 else (base, low, high, closing)
        length = closed - opened
        knots = (opened, opened + length // 3, opened + 2 * length // 3, closed)
        rate = 15 + (seed + index) % 150
        return knots, prices, rate

    def price(self, symbol, day, ts):
        knots, prices, _ = self.path(symbol, day)
        for i in range(3):
            if ts <= knots[i + 1]:
                fraction = max(0, (ts - knots[i]) / (knots[i + 1] - knots[i]))
                return prices[i] + (prices[i + 1] - prices[i]) * fraction
        return prices[-1]

    def segment(self, symbol, day, start, end):
        knots, _, rate = self.path(symbol, day)
        times = [start] + [t for t in knots if start < t < end] + [end]
        prices = [self.price(symbol, day, t) for t in times]
        turnover = sum((prices[i] + prices[i + 1]) * .5 * (times[i + 1] - times[i]) * rate for i in range(len(times) - 1))
        return prices[0], max(prices), min(prices), prices[-1], rate * (end - start), turnover

    def bar(self, symbol, tf, ts):
        day = datetime.fromtimestamp(ts, ET).date()
        start = self.calendar.session(day)[0] if tf == '1d' else ts
        end = self.calendar.bar_end(ts, tf)
        o, h, l, c, v, turnover = self.segment(symbol, day, start, end)
        return SimpleNamespace(timestamp=datetime.fromtimestamp(ts, ET), open=o, high=h, low=l,
                               close=c, volume=v, turnover=turnover, trade_session='Intraday')

    @lru_cache(maxsize=64)
    def timestamps(self, tf, target):
        day = datetime.fromtimestamp(target, ET).date()
        days = self.calendar.days(day - timedelta(days=2200 if tf == '1d' else 380), day)
        times = []
        for day in reversed(days):
            for ts, _ in reversed(self.calendar.grid(day, tf)):
                if ts <= target:
                    times.append(ts)
                    if len(times) == 1000:
                        return tuple(reversed(times))
        return tuple(reversed(times))

    async def candles(self, symbol, timeframe, count=1000, *, background=False):
        self.check([symbol])
        if not 1 <= count <= 1000:
            raise ValueError('Count must be 1..1000')
        now = int(self.clock())
        target = self.calendar.latest_closed(timeframe, now)
        await asyncio.sleep(0)  # Let quote publication and other symbols progress.
        return [self.bar(symbol, timeframe, ts) for ts in self.timestamps(timeframe, target)[-count:]]

    def quote(self, symbol, now, sequence=0):
        day = datetime.fromtimestamp(now, ET).date()
        opened = self.calendar.session(day)[0]
        o, h, l, c, volume, turnover = self.segment(symbol, day, opened, now)
        _, _, rate = self.path(symbol, day)
        return {'symbol':symbol, 'sequence':sequence, 'last_done':f'{c:.6f}',
                'open':f'{o:.6f}', 'high':f'{h:.6f}', 'low':f'{l:.6f}', 'timestamp':now,
                'volume':volume, 'turnover':f'{turnover:.6f}', 'trade_status':0,
                'trade_session':0, 'current_volume':rate, 'current_turnover':f'{rate*c:.6f}', 'tag':0}


class SimulatedQuotes:
    def __init__(self, market, cache):
        self.market, self.cache = market, cache
        self.connection_health = 'CONNECTED'
        self.last_quote_received_at = None
        self.push_count = 0
        self.raw, self.values = {}, {}
        self.tick()

    def tick(self):
        now = int(self.market.clock())
        for symbol in self.market.allowed:
            previous = self.raw.get(symbol)
            raw = self.market.quote(symbol, now, (previous or {}).get('sequence', 0) + 1)
            if previous and datetime.fromtimestamp(previous['timestamp'], ET).date() == datetime.fromtimestamp(now, ET).date():
                raw['current_volume'] = raw['volume'] - previous['volume']
                raw['current_turnover'] = f"{float(raw['turnover']) - float(previous['turnover']):.6f}"
            price = float(raw['last_done'])
            value = {'last_price':price, 'timestamp':now, 'trade_session':'Intraday',
                     'cumulative_volume':raw['volume'], 'bid_price':price-.01, 'ask_price':price+.01,
                     'source':'simulation'}
            self.raw[symbol], self.values[symbol] = raw, value
            self.cache.apply_quote(symbol, value)
            self.push_count += 1
        self.last_quote_received_at = now

    def output(self, symbol, now):
        self.market.check([symbol])
        return {'symbol':symbol, 'regular':self.values.get(symbol), 'extended':{},
                'connection_health':self.connection_health, 'error':None}

    async def run(self):
        try:
            while True:
                self.tick()
                await asyncio.sleep(0.2)
        finally:
            self.connection_health = 'DISCONNECTED'

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

ET = ZoneInfo('America/New_York')
UTC = timezone.utc
PERIODS = {'5m': 5, '15m': 15, '30m': 30, '1h': 60, '1d': 0}
PHASES = ('1d', '5m', '15m', '30m', '1h')


def timestamp(value: datetime) -> int:
    if value.tzinfo is None:
        raise ValueError('Naive SDK timestamp; UTC offset required')
    return int(value.timestamp())


class TradingCalendar:
    def __init__(self, today: date | None = None):
        today = today or datetime.now(ET).date()
        self.calendar = xcals.get_calendar('XNYS', start=f'{today.year - 12}-01-01',
                                           end=f'{today.year + 2}-12-31')

    @lru_cache(maxsize=6000)
    def session(self, day: date) -> tuple[int, int] | None:
        key = day.isoformat()
        if not self.calendar.is_session(key):
            return None
        return (int(self.calendar.session_open(key).timestamp()),
                int(self.calendar.session_close(key).timestamp()))

    def days(self, start: date, end: date) -> list[date]:
        if start > end:
            return []
        return [t.date() for t in self.calendar.sessions_in_range(start.isoformat(), end.isoformat())]

    def completed_days(self, now: int, count: int) -> list[date]:
        today = datetime.fromtimestamp(now, ET).date()
        days = self.days(today - timedelta(days=count * 2 + 30), today)
        return [d for d in days if self.session(d)[1] <= now][-count:]

    @lru_cache(maxsize=30000)
    def grid(self, day: date, timeframe: str) -> tuple[tuple[int, int], ...]:
        if timeframe not in PERIODS:
            raise ValueError('Unsupported timeframe')
        session = self.session(day)
        if not session:
            return ()
        opened, closed = session
        if timeframe == '1d':
            midnight = int(datetime.combine(day, datetime.min.time(), ET).timestamp())
            return ((midnight, closed),)
        step = PERIODS[timeframe] * 60
        return tuple((start, min(start + step, closed)) for start in range(opened, closed, step))

    def bar_end(self, ts: int, timeframe: str) -> int:
        day = datetime.fromtimestamp(ts, ET).date()
        for start, end in self.grid(day, timeframe):
            if start == ts:
                return end
        raise ValueError(f'Invalid {timeframe} regular-session timestamp: {ts}')

    def expected(self, timeframe: str, start: int, end: int, as_of: int) -> list[int]:
        if start > end:
            return []
        first, last = (datetime.fromtimestamp(t, ET).date() for t in (start, end))
        return [ts for day in self.days(first, last) for ts, close in self.grid(day, timeframe)
                if start <= ts <= end and close <= as_of]

    @lru_cache(maxsize=10000)
    def latest_closed(self, timeframe: str, now: int) -> int:
        today = datetime.fromtimestamp(now, ET).date()
        candidates = [ts for day in self.days(today - timedelta(days=15), today)
                      for ts, end in self.grid(day, timeframe) if end <= now]
        return max(candidates)

    def is_open(self, now: int) -> bool:
        session = self.session(datetime.fromtimestamp(now, ET).date())
        return bool(session and session[0] <= now < session[1])

    def active_start(self, timeframe: str, now: int) -> int | None:
        day = datetime.fromtimestamp(now, ET).date()
        for start, end in self.grid(day, timeframe):
            opened = self.session(day)[0] if timeframe == '1d' else start
            if opened <= now < end:
                return start
        return None

from __future__ import annotations

import json
import math
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .calendar import PHASES, TradingCalendar


@dataclass(frozen=True)
class Bar:
    symbol: str
    timeframe: str
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float | None = None

    @property
    def invalid_range(self) -> bool:
        return self.low > min(self.open, self.close) or self.high < max(self.open, self.close) or self.high < self.low

    def validate(self, calendar: TradingCalendar, now: int) -> None:
        if self.timeframe not in PHASES:
            raise ValueError('Only official periods may be persisted')
        values = (self.open, self.high, self.low, self.close)
        if any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError('OHLC must be finite and positive')
        if not isinstance(self.volume, int) or isinstance(self.volume, bool) or self.volume < 0:
            raise ValueError('Volume must be a nonnegative integer')
        if self.turnover is not None and (not math.isfinite(self.turnover) or self.turnover < 0):
            raise ValueError('Turnover must be finite and nonnegative')
        if calendar.bar_end(self.ts, self.timeframe) > now:
            raise ValueError('Forming candle cannot be persisted')


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as file:
            name = file.name
            json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
            file.write('\n')
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


class BarStore:
    def __init__(self, path: Path, calendar: TradingCalendar, allowed: set[str]):
        self.calendar, self.allowed = calendar, frozenset(allowed)
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS bars (
                symbol TEXT NOT NULL, timeframe TEXT NOT NULL, ts INTEGER NOT NULL,
                open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,
                close REAL NOT NULL, volume INTEGER NOT NULL,
                PRIMARY KEY(symbol, timeframe, ts)
            );
            CREATE TABLE IF NOT EXISTS batches (
                symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                run_id TEXT NOT NULL, as_of INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(symbol, timeframe)
            );
        ''')
        if 'turnover' not in {r['name'] for r in self.db.execute('PRAGMA table_info(bars)')}:
            self.db.execute('ALTER TABLE bars ADD COLUMN turnover REAL')
        self.revisions: dict[tuple[str, str], int] = {}
        self.quality_revisions: dict[tuple[str, str], int] = {}

    def check(self, symbol: str) -> None:
        if symbol not in self.allowed:
            raise ValueError(f'Symbol outside focus/wait: {symbol}')

    def upsert(self, bars: list[Bar], now: int, batch: dict | None = None) -> None:
        for bar in bars:
            self.check(bar.symbol)
            bar.validate(self.calendar, now)
        keys = {(b.symbol, b.timeframe) for b in bars}
        if batch:
            keys.add((batch['symbol'], batch['timeframe']))
        # Only changed market values invalidate chart history/indicator caches.
        changed = set()
        with self.db:
            for key in keys:
                before = self.db.total_changes
                self.db.executemany("""INSERT INTO bars (symbol,timeframe,ts,open,high,low,close,volume,turnover)
                    VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(symbol,timeframe,ts) DO UPDATE SET
                    open=excluded.open,high=excluded.high,low=excluded.low,
                    close=excluded.close,volume=excluded.volume,turnover=excluded.turnover
                    WHERE bars.open IS NOT excluded.open OR bars.high IS NOT excluded.high
                       OR bars.low IS NOT excluded.low OR bars.close IS NOT excluded.close
                       OR bars.volume IS NOT excluded.volume OR bars.turnover IS NOT excluded.turnover""",
                    [tuple(asdict(bar).values()) for bar in bars if (bar.symbol, bar.timeframe) == key])
                if batch and key == (batch['symbol'], batch['timeframe']):
                    self.check(batch['symbol'])
                    # Unplottable revisions are absent; OHLC range contradictions are retained.
                    self.db.executemany('DELETE FROM bars WHERE symbol=? AND timeframe=? AND ts=?',
                        [(*key, r['ts']) for r in batch.get('rejected', []) if r['ts'] is not None])
                if self.db.total_changes != before:
                    changed.add(key)
            if batch is not None:
                self.db.execute("""INSERT INTO batches VALUES (?,?,?,?,?)
                    ON CONFLICT(symbol,timeframe) DO UPDATE SET
                    run_id=excluded.run_id,as_of=excluded.as_of,payload=excluded.payload""",
                    (batch['symbol'], batch['timeframe'], '', batch['as_of'], json.dumps(batch)))
        for key in changed:
            self.revisions[key] = self.revisions.get(key, 0) + 1
        for key in keys:
            self.quality_revisions[key] = self.quality_revisions.get(key, 0) + 1

    def bars(self, symbol: str, timeframe: str, start: int = 0, end: int = 2**62,
             limit: int | None = None) -> list[Bar]:
        self.check(symbol)
        sql = 'SELECT * FROM bars WHERE symbol=? AND timeframe=? AND ts BETWEEN ? AND ? ORDER BY ts'
        args = [symbol, timeframe, start, end]
        if limit is not None:
            sql += ' DESC LIMIT ?'
            args.append(limit)
        rows = list(self.db.execute(sql, args))
        if limit is not None:
            rows.reverse()
        return [Bar(**dict(row)) for row in rows]

    def batch(self, symbol: str, timeframe: str) -> dict | None:
        self.check(symbol)
        row = self.db.execute('SELECT payload FROM batches WHERE symbol=? AND timeframe=?',
                              (symbol, timeframe)).fetchone()
        return json.loads(row[0]) if row else None

    def window(self, symbol: str, timeframe: str) -> list[Bar]:
        batch = self.batch(symbol, timeframe)
        start = (batch or {}).get('window_start', 0)
        return self.bars(symbol, timeframe, start=start, limit=1000)

    def close(self) -> None:
        self.db.close()

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .calendar import TradingCalendar

log = logging.getLogger(__name__)


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

    def validate(self, calendar: TradingCalendar, now: int) -> None:
        values = (self.open, self.high, self.low, self.close)
        if any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError('OHLC must be finite and positive')
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close) or self.high < self.low:
            raise ValueError('Invalid OHLC range')
        if not isinstance(self.volume, int) or isinstance(self.volume, bool) or self.volume < 0:
            raise ValueError('Volume must be a nonnegative integer')
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
            CREATE TABLE IF NOT EXISTS metadata (
                symbol TEXT PRIMARY KEY, payload TEXT NOT NULL
            );
        ''')

    def check(self, symbol: str) -> None:
        if symbol not in self.allowed:
            raise ValueError(f'Symbol outside focus/wait: {symbol}')

    def upsert(self, bars: list[Bar], now: int, batch: dict | None = None) -> None:
        for bar in bars:
            self.check(bar.symbol)
            bar.validate(self.calendar, now)
        with self.db:
            self.db.executemany('''INSERT INTO bars VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(symbol,timeframe,ts) DO UPDATE SET
                open=excluded.open,high=excluded.high,low=excluded.low,
                close=excluded.close,volume=excluded.volume''',
                [tuple(asdict(bar).values()) for bar in bars])
            if batch is not None:
                self.check(batch['symbol'])
                self.db.execute('''INSERT INTO batches VALUES (?,?,?,?,?)
                    ON CONFLICT(symbol,timeframe) DO UPDATE SET
                    run_id=excluded.run_id,as_of=excluded.as_of,payload=excluded.payload''',
                    (batch['symbol'], batch['timeframe'], batch['run_id'], batch['as_of'], json.dumps(batch)))

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

    def metadata(self, symbol: str) -> dict:
        self.check(symbol)
        row = self.db.execute('SELECT payload FROM metadata WHERE symbol=?', (symbol,)).fetchone()
        return json.loads(row[0]) if row else {}

    def set_metadata(self, symbol: str, value: dict) -> None:
        self.check(symbol)
        with self.db:
            self.db.execute('INSERT INTO metadata VALUES (?,?) ON CONFLICT(symbol) DO UPDATE SET payload=excluded.payload',
                            (symbol, json.dumps(value)))

    def close(self) -> None:
        self.db.close()


class HistoryQuotaTracker:
    def __init__(self, path: Path):
        self.path = path
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict) or not all(
                    isinstance(k, str) and isinstance(v, list) and all(isinstance(s, str) for s in v)
                    for k, v in data.items()):
                raise ValueError('Invalid quota tracker')
            self.data = data
        except (OSError, ValueError):
            self.data = {}

    def record(self, month: str, symbol: str) -> None:
        values = set(self.data.get(month, []))
        if symbol in values:
            return
        self.data[month] = sorted(values | {symbol})
        try:
            atomic_json(self.path, self.data)
        except OSError as exc:
            log.warning('Quota tracker write failed: %s', exc)

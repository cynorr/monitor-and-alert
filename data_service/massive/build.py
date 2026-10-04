"""Stream raw days into an atomically published split-adjusted SQLite database."""
from __future__ import annotations

import hashlib
import math
import os
import sqlite3
import tempfile
import time
from collections import defaultdict
from contextlib import closing
from dataclasses import astuple
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .daily import read_day
from .splits import read_existing
from ..downloader import append_ohlc_log, ohlc_comparison
from ..store import BAR_SCHEMA, Bar


def daily_files(directory, target):
    return sorted(path for path in Path(directory).glob('????-??-??.json') if date.fromisoformat(path.stem) <= target)


def input_revision(paths, target):
    digest = hashlib.sha256()
    for path in daily_files(paths.daily_dir, target):
        stat = path.stat()
        digest.update(f'{path.name}:{stat.st_size}:{stat.st_mtime_ns}\n'.encode())
    digest.update(Path(paths.splits_file).read_bytes())
    digest.update(b'split_adjusted/half_up/v1')
    return digest.hexdigest()


def round_volume(value):
    if not math.isfinite(value) or value < 0:
        raise ValueError('Invalid split-adjusted volume')
    result = int(Decimal(str(value)).to_integral_value(rounding=ROUND_HALF_UP))
    if result > 2**63 - 1:
        raise ValueError('Volume exceeds SQLite INTEGER range')
    return result


def metadata(path):
    with closing(sqlite3.connect(f'{Path(path).resolve().as_uri()}?mode=ro', uri=True)) as db:
        return dict(db.execute('SELECT key,value FROM metadata'))


def build(paths, target, calendar, *, now=None):
    now = int(time.time()) if now is None else now
    target_stamp = calendar.grid(target, '1d')
    if not target_stamp or target_stamp[0][1] > now:
        raise ValueError('Massive export requires a completed trading date')
    if paths.daily_db.resolve() == paths.bars_db.resolve():
        raise ValueError('Massive and Longbridge databases must be separate')
    files = daily_files(paths.daily_dir, target)
    if not files or files[-1].stem != target.isoformat():
        raise ValueError('Missing completed raw daily response')
    snapshot = read_existing(paths.splits_file)
    if snapshot is None or snapshot['end_date'] < target:
        raise ValueError('Split coverage does not include the completed trading date')
    factors = defaultdict(list)
    for row in snapshot['results']:
        factor = float(row['split_from']) / float(row['split_to'])
        if not math.isfinite(factor) or factor <= 0:
            raise ValueError('Invalid split adjustment factor')
        factors[row['ticker']].append((row['execution_date'], factor))
    revision = input_revision(paths, target)
    output = Path(paths.daily_db)
    output.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix='massive-', suffix='.sqlite3.tmp', dir=output.parent, delete=False)
    temporary = Path(handle.name)
    handle.close()
    invalid_log = output.parent / 'invalid_ohlc.jsonl'
    values = {'completed_date': target.isoformat(), 'adjustment': 'split_adjusted',
              'volume_rounding': 'half_up', 'source': 'massive_grouped_daily',
              'session': 'massive_daily', 'turnover': 'vwap_times_unrounded_volume',
              'input_revision': revision}
    try:
        with closing(sqlite3.connect(temporary)) as db:
            db.executescript(BAR_SCHEMA)
            with db:
                for path in files:
                    day = date.fromisoformat(path.stem)
                    grid = calendar.grid(day, '1d')
                    if not grid:
                        raise ValueError('Raw daily file is not a trading session')
                    stamp = grid[0][0]
                    bars, anomalies = [], []
                    for row in read_day(path, day):
                        factor = 1.0
                        for execution, ratio in factors[row['T']]:
                            if day.isoformat() < execution:
                                factor *= ratio
                        if not math.isfinite(factor) or factor <= 0:
                            raise ValueError('Cumulative split factor is invalid')
                        volume = row['v'] / factor
                        turnover = None
                        if row.get('vw') is not None and row['vw'] > 0:
                            amount = row['vw'] * factor * volume
                            if math.isfinite(amount):
                                turnover = amount
                        bar = Bar(f"{row['T']}.US", '1d', stamp,
                                  *(float(row[key]) * factor for key in ('o', 'h', 'l', 'c')),
                                  round_volume(volume), turnover)
                        bar.validate(calendar, now)
                        bars.append(astuple(bar))
                        if bar.invalid_range:
                            anomalies.append(ohlc_comparison(bar, calendar, now, 'massive_daily',
                                {key: row[key] for key in ('o', 'h', 'l', 'c', 'v')}))
                    db.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?)', bars)
                    append_ohlc_log(invalid_log, anomalies)
                db.execute('''DELETE FROM bars WHERE rowid IN (
                    SELECT rowid FROM (SELECT rowid, ROW_NUMBER() OVER
                    (PARTITION BY symbol ORDER BY ts DESC) AS position FROM bars) WHERE position>1000)''')
                db.execute('CREATE INDEX bars_by_time ON bars(timeframe,ts,symbol)')
                db.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
                db.executemany('INSERT INTO metadata VALUES (?,?)', values.items())
            if not db.execute("SELECT 1 FROM bars WHERE timeframe='1d' AND ts=? LIMIT 1", (target_stamp[0][0],)).fetchone():
                raise ValueError('No market bars for the completed date')
        if input_revision(paths, target) != revision:
            raise ValueError('Massive inputs changed while building daily bars')
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return values

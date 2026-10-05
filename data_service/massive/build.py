"""Build split-adjusted Daily SQLite, appending new raw days when inputs permit."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import sqlite3
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

LOGGER = logging.getLogger(__name__)


def daily_files(directory, target):
    return sorted(path for path in Path(directory).glob('????-??-??.json') if date.fromisoformat(path.stem) <= target)


def file_fingerprint(path):
    stat = path.stat()
    return f'{stat.st_size}:{stat.st_mtime_ns}'


def input_revision(paths, target):
    digest = hashlib.sha256()
    for path in daily_files(paths.daily_dir, target):
        digest.update(f'{path.name}:{file_fingerprint(path)}\n'.encode())
    digest.update(Path(paths.splits_file).read_bytes())
    digest.update(b'split_adjusted/half_up/v2')
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


def adjusted_bar(row, day, stamp, factors, calendar, now):
    factor = 1.0
    for execution, ratio in factors.get(row['T'], ()):
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
    return bar


def appended_files(previous, files, manifest, split_revision):
    old = json.loads(previous.get('raw_files', '{}'))
    if previous.get('split_revision') != split_revision or any(manifest.get(name) != value for name, value in old.items()):
        return None
    added = [path for path in files if path.name not in old]
    if any(path.stem <= previous['completed_date'] for path in added):
        return None
    return added


def build(paths, target, calendar, *, now=None):
    started = time.perf_counter()
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
    manifest = {path.name: file_fingerprint(path) for path in files}
    split_revision = hashlib.sha256(json.dumps(snapshot['results'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    values = {'completed_date': target.isoformat(), 'adjustment': 'split_adjusted',
              'volume_rounding': 'half_up', 'source': 'massive_grouped_daily',
              'session': 'massive_daily', 'turnover': 'vwap_times_unrounded_volume',
              'input_revision': input_revision(paths, target),
              'raw_files': json.dumps(manifest, sort_keys=True, separators=(',', ':')),
              'split_revision': split_revision}
    output = Path(paths.daily_db)
    output.parent.mkdir(parents=True, exist_ok=True)
    pending, mode = files, 'rebuild'
    if output.exists():
        previous = metadata(output)
        pending = appended_files(previous, files, manifest, split_revision)
        if pending is None:
            output.unlink()
            pending = files
        elif previous.get('input_revision') == values['input_revision'] and previous.get('completed_date') == values['completed_date']:
            return values
        else:
            mode = 'incremental'
    touched = set()
    try:
        with closing(sqlite3.connect(output)) as db:
            if mode == 'rebuild':
                db.executescript(BAR_SCHEMA + '''
                    CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
            with db:
                for path in pending:
                    day = date.fromisoformat(path.stem)
                    grid = calendar.grid(day, '1d')
                    if not grid:
                        raise ValueError('Raw daily file is not a trading session')
                    bars, anomalies = [], []
                    for row in read_day(path, day):
                        bar = adjusted_bar(row, day, grid[0][0], factors, calendar, now)
                        bars.append(astuple(bar))
                        touched.add(bar.symbol)
                        if bar.invalid_range:
                            anomalies.append(ohlc_comparison(bar, calendar, now, 'massive_daily',
                                {key: row[key] for key in ('o', 'h', 'l', 'c', 'v')}))
                    db.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?)', bars)
                    append_ohlc_log(output.parent / 'invalid_ohlc.jsonl', anomalies)
                if len(files) > 1000:
                    db.executemany('''DELETE FROM bars WHERE symbol=? AND timeframe='1d' AND ts < (
                        SELECT ts FROM bars WHERE symbol=? AND timeframe='1d' ORDER BY ts DESC LIMIT 1 OFFSET 999)''',
                        [(symbol, symbol) for symbol in touched])
                if mode == 'rebuild':
                    db.execute('CREATE INDEX bars_by_time ON bars(timeframe,ts,symbol)')
                db.executemany('INSERT OR REPLACE INTO metadata VALUES (?,?)', values.items())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    LOGGER.info('Massive bars mode=%s raw_files=%d tickers=%d elapsed=%.3fs',
                mode, len(pending), len(touched), time.perf_counter() - started)
    return values

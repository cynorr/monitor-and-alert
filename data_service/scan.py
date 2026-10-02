"""Read the upstream daily database and generate one closed-day cross section."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd

from .calendar import ET
from .charts import bar_row
from .downloader import ohlc_comparison, append_ohlc_log
from .features.screening import apply_filter, add_rank, mark_candidate
from .features.snapshot import feature_row, feature_frame
from .indicators import series, daily_summary, adr_adv, return_from_low
from .store import read_bars
from .workspace import inherit_workspace

log = logging.getLogger(__name__)


def connect_daily(path):
    db = sqlite3.connect(f'{Path(path).resolve().as_uri()}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def day_start(calendar, value):
    grid = calendar.grid(date.fromisoformat(value), '1d')
    if not grid:
        raise ValueError('Choose a trading date')
    return grid[0][0]


def latest_completed_date(path):
    with closing(connect_daily(path)) as db:
        row = db.execute("SELECT value FROM metadata WHERE key='completed_date'").fetchone()
    if not row:
        raise ValueError('Upstream daily database must publish metadata.completed_date')
    return row[0]


def read_snapshot(days, value):
    return json.loads((days / value / 'scan.json').read_text())


def candidates(snapshot):
    return {row['symbol'].removesuffix('.US') for row in snapshot['rows'] if row['candidate']}


def previous_candidates(days, value):
    previous = max((p for p in days.glob('*/scan.json') if p.parent.name < value), default=None)
    return candidates(json.loads(previous.read_text())) if previous else set()


def checked_history(db, symbol, cutoff, calendar, now, limit, log_path, log_before=None):
    history = read_bars(db, symbol, '1d', end=cutoff, limit=limit)
    if not symbol.endswith('.US'):
        raise ValueError('Daily symbols must include .US')
    anomalies = []
    for bar in history:
        bar.validate(calendar, now)
        if bar.invalid_range and log_path and (log_before is None or bar.ts < log_before):
            anomalies.append(ohlc_comparison(bar, calendar, now, 'Intraday',
                {key: getattr(bar, key) for key in ('open', 'high', 'low', 'close', 'volume')}))
    if log_path:
        append_ohlc_log(log_path, anomalies)
    return history


def build_day(path, value, calendar, now=None, log_path=None, mock=False):
    started = time.perf_counter()
    cutoff = day_start(calendar, value)
    now = int(time.time()) if now is None else now
    if calendar.bar_end(cutoff, '1d') > now:
        raise ValueError('Choose a completed trading date')
    rows = []
    window_starts = {}
    with closing(connect_daily(path)) as db:
        symbols = [row[0] for row in db.execute("SELECT symbol FROM bars WHERE timeframe='1d' AND ts=? ORDER BY symbol", (cutoff,))]
        if not symbols:
            raise ValueError('No daily bars on the requested date')
        # All symbols need only ADR/ADV's 20 records before eligibility is known.
        for symbol in symbols:
            history = checked_history(db, symbol, cutoff, calendar, now, 20, log_path)
            window_starts[symbol] = history[0].ts
            metrics = adr_adv({key: [getattr(bar, key) for bar in history]
                               for key in ('high', 'low', 'close', 'volume')})
            rows.append({'symbol': symbol, 'close': history[-1].close, **metrics})
        screen = apply_filter(pd.DataFrame(rows))
        for name in ('rfl1m', 'rfl3m', 'rfl6m'):
            screen[name] = float('nan')
        # Only eligible symbols need 21/63/126-record lows and cross-sectional ranks.
        for index in screen.index[screen['eligible']]:
            symbol = screen.at[index, 'symbol']
            history = checked_history(db, symbol, cutoff, calendar, now, 126,
                                      log_path, log_before=window_starts[symbol])
            window_starts[symbol] = history[0].ts
            metrics = return_from_low({key: [getattr(bar, key) for bar in history]
                                       for key in ('low', 'close')})
            for name, value_ in metrics.items():
                screen.at[index, name] = value_
        screen = mark_candidate(add_rank(screen))
        selected = screen.loc[screen['candidate'], 'symbol'].tolist()
        screened = time.perf_counter()
        feature_rows = []
        # Only candidates need full history to retain EMA/ATR seeds and atomic events.
        for symbol in selected:
            history = checked_history(db, symbol, cutoff, calendar, now, 1000,
                                      log_path, log_before=window_starts[symbol])
            history_frame = pd.DataFrame([vars(bar) for bar in history])
            history_frame['date'] = pd.to_datetime(history_frame['ts'], unit='s', utc=True).dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
            feature_rows.append(feature_row(history_frame))
    # Retain light market metrics for Focus/Wait/carried rows outside today's candidates.
    records = json.loads(screen.to_json(orient='records', double_precision=15))
    if feature_rows:
        features = feature_frame(feature_rows).drop(columns=['date', 'open', 'high', 'low', 'volume'])
        by_symbol = {row['symbol']: row for row in json.loads(features.to_json(orient='records', double_precision=15))}
        for row in records:
            row.update(by_symbol.get(row['symbol'], {}))
    finished = time.perf_counter()
    log.info('Scan %s: symbols=%d candidates=%d screening=%.3fs features=%.3fs total=%.3fs',
             value, len(symbols), len(selected), screened - started, finished - screened, finished - started)
    return {'date': value, 'mock': mock, 'rows': records}


def publish_day(days, snapshot):
    folder = days / snapshot['date']
    folder.mkdir(parents=True, exist_ok=True)
    workspace = folder / 'workspace.json'
    if not workspace.exists():
        previous = max((p for p in days.glob('*/workspace.json') if p.parent.name < snapshot['date']), default=None)
        data = inherit_workspace(json.loads(previous.read_text()) if previous else None,
                                 previous_candidates(days, snapshot['date']), candidates(snapshot), snapshot['date'])
    (folder / 'scan.json').write_text(json.dumps(snapshot, allow_nan=False) + '\n')
    if not workspace.exists():
        workspace.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def daily_chart(path, symbol, value, calendar):
    with closing(connect_daily(path)) as db:
        bars = read_bars(db, symbol, '1d', end=day_start(calendar, value))
    rows = [bar_row(bar) for bar in bars]
    base = series(rows)
    summary = daily_summary(bars, calendar, calendar.bar_end(day_start(calendar, value), '1d'))
    return {'revision': 1, 'bars': rows, 'indicators': base['series'], 'active': None,
            'indicator_preview': {}}, summary

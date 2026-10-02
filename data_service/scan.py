"""Read the upstream daily database and generate one closed-day cross section."""
from __future__ import annotations

import json
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
from .indicators import series, daily_summary
from .store import read_bars
from .workspace import inherit_workspace


def connect_daily(path):
    db = sqlite3.connect(f'{Path(path).resolve().as_uri()}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def day_start(calendar, value):
    grid = calendar.grid(date.fromisoformat(value), '1d')
    if not grid:
        raise ValueError('Choose a trading date')
    return grid[0][0]


def read_snapshot(days, value):
    return json.loads((days / value / 'scan.json').read_text())


def candidates(snapshot):
    return {row['symbol'].removesuffix('.US') for row in snapshot['rows'] if row['candidate']}


def previous_candidates(days, value):
    previous = max((p for p in days.glob('*/scan.json') if p.parent.name < value), default=None)
    return candidates(json.loads(previous.read_text())) if previous else set()


def build_day(path, value, calendar, now=None, log_path=None, mock=False):
    cutoff = day_start(calendar, value)
    now = int(time.time()) if now is None else now
    if calendar.bar_end(cutoff, '1d') > now:
        raise ValueError('Choose a completed trading date')
    rows = []
    with closing(connect_daily(path)) as db:
        symbols = [row[0] for row in db.execute("SELECT symbol FROM bars WHERE timeframe='1d' AND ts=? ORDER BY symbol", (cutoff,))]
        if not symbols:
            raise ValueError('No daily bars on the requested date')
        # Keep only one ticker's history in memory; use the chart's bounded reader.
        for symbol in symbols:
            history = read_bars(db, symbol, '1d', end=cutoff)
            anomalies = []
            for bar in history:
                bar.validate(calendar, now)
                if not bar.symbol.endswith('.US'):
                    raise ValueError('Daily symbols must include .US')
                if bar.invalid_range and log_path:
                    anomalies.append(ohlc_comparison(bar, calendar, now, 'Intraday',
                        {key: getattr(bar, key) for key in ('open','high','low','close','volume')}))
            if log_path:
                append_ohlc_log(log_path, anomalies)
            frame = pd.DataFrame([vars(bar) for bar in history])
            frame['date'] = pd.to_datetime(frame['ts'], unit='s', utc=True).dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
            rows.append(feature_row(frame))
    frame = feature_frame(rows)
    frame = mark_candidate(add_rank(apply_filter(frame)))
    # Persist scalars used by screening, not a second copy of bars/indicator series.
    frame = frame.drop(columns=['date','open','high','low','volume'])
    return {'date': value, 'mock': mock, 'rows': json.loads(frame.to_json(orient='records', double_precision=15))}


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

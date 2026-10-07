"""Read the upstream daily database and generate one closed-day cross section."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from copy import deepcopy
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd

from .calendar import ET
from .charts import bar_row
from .downloader import ohlc_comparison, append_ohlc_log
from .features.screening import apply_filter, add_rank, mark_candidate
from .features.snapshot import feature_row, feature_frame
from .indicators import series, daily_summary, adr_adv, return_from_low, volume_context, volume_comparison
from .store import atomic_json, read_bars
from .workspace import inherit_workspace, migrate_workspace
from .preferences import DEFAULT, validate_preferences
from .list_rules import apply_rules
from .massive.settings import load_config, directory_for_database
from .symbol_directory import read_directory

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


def workspace_scope(days, value):
    """Include all Focus and Excluded members from this day or its predecessor."""
    days = Path(days)
    path = days / value / 'workspace.json'
    if not path.exists():
        path = max((p for p in days.glob('*/workspace.json') if p.parent.name < value), default=None)
    if path is None:
        return set()
    data = migrate_workspace(json.loads(path.read_text()), value)
    return {ticker for ticker, state in data['statuses'].items()
            if state['status'] in ('focus', 'excluded')}


def _symbols(tickers):
    return {ticker.removesuffix('.US') + '.US' for ticker in tickers}


def _feature_row(history):
    frame = pd.DataFrame([vars(bar) for bar in history])
    frame['date'] = pd.to_datetime(frame['ts'], unit='s', utc=True).dt.tz_convert(ET).dt.tz_localize(None).dt.normalize()
    return feature_row(frame)


def _feature_updates(rows):
    if not rows:
        return {}
    # Complete metrics, including RFL values, without changing screening or ranks.
    features = feature_frame(rows).drop(columns=['date', 'open', 'high', 'low', 'close', 'volume',
                                                 'adr20', 'adv20'])
    return {row['symbol']: row for row in json.loads(features.to_json(orient='records', double_precision=15))}


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


def build_day(path, value, calendar, now=None, log_path=None, mock=False, *, tracked_tickers=(),
              directory_path=None, screening_config=None):
    started = time.perf_counter()
    cutoff = day_start(calendar, value)
    now = int(time.time()) if now is None else now
    if calendar.bar_end(cutoff, '1d') > now:
        raise ValueError('Choose a completed trading date')
    config = screening_config or load_config()
    directory = read_directory(directory_path or directory_for_database(path))['symbols']
    rows = []
    window_starts = {}
    with closing(connect_daily(path)) as db:
        symbols = [row[0] for row in db.execute("SELECT symbol FROM bars WHERE timeframe='1d' AND ts=? ORDER BY symbol", (cutoff,))]
        if not symbols:
            raise ValueError('No daily bars on the requested date')
        # Classify first, then require enough actual records for SMA50 before RFL.
        for symbol in symbols:
            info = directory.get(symbol)
            etf_pass = not config.exclude_etfs or (info is not None and not info['etf'])
            limit = max(20, config.min_daily_bars) if etf_pass else 20
            history = checked_history(db, symbol, cutoff, calendar, now, limit, log_path)
            window_starts[symbol] = history[0].ts
            metrics = adr_adv({key: [getattr(bar, key) for bar in history[-20:]]
                               for key in ('high', 'low', 'close', 'volume')})
            rows.append({'symbol': symbol, 'close': history[-1].close, **metrics,
                         'etf': info['etf'] if info else None,
                         'etf_pass': etf_pass, 'history_pass': len(history) >= config.min_daily_bars})
        screen = apply_filter(pd.DataFrame(rows), config)
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
        screen = mark_candidate(add_rank(screen), config)
        selected = screen.loc[screen['candidate'], 'symbol'].tolist()
        feature_symbols = sorted((set(selected) | _symbols(tracked_tickers)) & set(symbols))
        screened = time.perf_counter()
        feature_rows = []
        # Candidates and all retained Focus/Excluded members need complete features.
        for symbol in feature_symbols:
            history = checked_history(db, symbol, cutoff, calendar, now, 1000,
                                      log_path, log_before=window_starts[symbol])
            feature_rows.append(_feature_row(history))
    records = json.loads(screen.to_json(orient='records', double_precision=15))
    by_symbol = _feature_updates(feature_rows)
    for row in records:
        row.update(by_symbol.get(row['symbol'], {}))
    finished = time.perf_counter()
    log.info('Scan %s: symbols=%d candidates=%d screening=%.3fs features=%.3fs total=%.3fs',
             value, len(symbols), len(selected), screened - started, finished - screened, finished - started)
    return {'date': value, 'mock': mock, 'rows': records, 'feature_scope': feature_symbols}


def enrich_snapshot(path, snapshot, calendar, *, tracked_tickers=(), log_path=None):
    """Complete a local snapshot's missing features without rescreening the market."""
    result = deepcopy(snapshot)
    rows = {row['symbol']: row for row in result['rows']}
    existing = {symbol for symbol, row in rows.items() if 'ema10' in row
                and all(row.get(name) is not None for name in ('rfl1m', 'rfl3m', 'rfl6m'))}
    requested = {symbol for symbol, row in rows.items() if row['candidate']} | _symbols(tracked_tickers)
    pending = sorted((requested & set(rows)) - existing)
    feature_rows = []
    if pending:
        cutoff = day_start(calendar, result['date'])
        with closing(connect_daily(path)) as db:
            for symbol in pending:
                history = checked_history(db, symbol, cutoff, calendar, int(time.time()), 1000, log_path)
                if history and history[-1].ts == cutoff:
                    feature_rows.append(_feature_row(history))
    updates = _feature_updates(feature_rows)
    for symbol, feature in updates.items():
        rows[symbol].update(feature)
    result['feature_scope'] = sorted(existing | set(updates))
    return result


def publish_day(days, snapshot):
    days = Path(days)
    folder = days / snapshot['date']
    folder.mkdir(parents=True, exist_ok=True)
    workspace = folder / 'workspace.json'
    if workspace.exists():
        data = json.loads(workspace.read_text())
    else:
        previous = max((p for p in days.glob('*/workspace.json') if p.parent.name < snapshot['date']), default=None)
        data = inherit_workspace(json.loads(previous.read_text()) if previous else None,
                                 previous_candidates(days, snapshot['date']), candidates(snapshot), snapshot['date'])
    preferences_path = days.parent / 'preferences.json'
    preferences = validate_preferences(json.loads(preferences_path.read_text()) if preferences_path.exists() else deepcopy(DEFAULT))
    data = apply_rules(data, snapshot, preferences)
    atomic_json(workspace, data)
    atomic_json(folder / 'scan.json', snapshot)


def daily_chart(path, symbol, value, calendar):
    with closing(connect_daily(path)) as db:
        bars = read_bars(db, symbol, '1d', end=day_start(calendar, value))
    rows = [bar_row(bar) for bar in bars]
    volume = volume_context(rows, '1d')
    for row in rows:
        row['volume_comparison'] = volume_comparison(row, '1d', calendar, volume)
    base = series(rows)
    summary = daily_summary(bars, calendar, calendar.bar_end(day_start(calendar, value), '1d'))
    return {'revision': 1, 'bars': rows, 'indicators': base['series'], 'active': None,
            'indicator_preview': {}}, summary

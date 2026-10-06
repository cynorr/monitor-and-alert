"""Deterministic synthetic daily data in the exact upstream SQLite contract."""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_service.calendar import TradingCalendar
from data_service.scan import build_day, publish_day, workspace_scope
from data_service.store import BAR_SCHEMA, atomic_json
from data_service.symbol_directory import make_snapshot


def build_mock(root, end='2026-09-30', count=48):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / 'daily.sqlite3'
    if path.exists():
        raise ValueError('Mock database already exists; choose a new output directory')
    calendar = TradingCalendar(date.fromisoformat(end))
    days = calendar.days(date.fromisoformat(end) - timedelta(days=400), date.fromisoformat(end))[-220:]
    symbols = ['PAYS','NVDA','AAPL','MSFT','TSLA','AMD'] + [f'MOCK{i:03d}' for i in range(count - 6)]
    with sqlite3.connect(path) as db:
        db.executescript(BAR_SCHEMA + 'CREATE INDEX bars_by_time ON bars(timeframe,ts,symbol);')
        db.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('INSERT INTO metadata VALUES (?,?)', ('completed_date', end))
        for index, ticker in enumerate(symbols):
            history = days[-(8 if index == count-1 else 220):]
            previous = 8 + index * 1.3
            records = []
            for step, day in enumerate(history):
                drift = .0015 + index % 7 * .0008
                close = previous * (1 + drift + .025 * math.sin(step / 9 + index))
                opened = previous * (1 + .009 * math.cos(step / 7 + index))
                amplitude = .014 if index % 9 == 0 else .034 + (index % 5) * .006
                high, low = max(opened, close) * (1 + amplitude), min(opened, close) * (1 - amplitude)
                volume = 100_000 if index % 10 == 0 else 1_000_000 + int(350_000 * (1 + math.sin(step / 11 + index)))
                records.append((ticker + '.US','1d',calendar.grid(day,'1d')[0][0],opened,high,low,close,volume,close*volume))
                previous = close
            db.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?)', records)
    atomic_json(root / 'symbol-directory.json', make_snapshot({
        ticker + '.US': {'name': f'{ticker} synthetic security', 'etf': False, 'test_issue': False}
        for ticker in symbols}))
    folder = root / 'days'
    for day in days[-2:]:
        tracked = workspace_scope(folder, day.isoformat())
        snapshot = build_day(path, day.isoformat(), calendar, now=calendar.session(days[-1])[1], mock=True,
                             tracked_tickers=tracked)
        publish_day(folder, snapshot)
    workspace_path = folder / end / 'workspace.json'
    workspace = json.loads(workspace_path.read_text())
    for ticker in ('PAYS', 'NVDA'):
        workspace['statuses'][ticker] = {'status': 'focus', 'section': 'unclassified', 'tags': [], 'status_at': end}
        for order in workspace['orders'].values():
            order[:] = [member for member in order if member != ticker]
    workspace['orders']['focus'] = ['PAYS', 'NVDA']
    workspace_path.write_text(json.dumps(workspace, indent=2) + '\n')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('runtime/scan-mock'))
    parser.add_argument('--date', default='2026-09-30')
    args = parser.parse_args()
    print(build_mock(args.output, args.date).resolve())

from dataclasses import replace
from datetime import date, timedelta
import json
import sqlite3

import pytest

from data_service import scan
from data_service.calendar import TradingCalendar
from data_service.massive.settings import load_config
from data_service.store import BAR_SCHEMA, atomic_json
from data_service.symbol_directory import make_snapshot


def market(tmp_path):
    calendar = TradingCalendar(date(2026, 10, 1))
    days = calendar.days(date(2026, 10, 1) - timedelta(days=100), date(2026, 10, 1))[-51:]
    path = tmp_path / 'daily.sqlite3'
    specs = [('ETF', 50, 100), ('YOUNG', 49, 90), ('UNKNOWN', 50, 80),
             ('STOCK', 50, 20), ('SECOND', 50, 15)]
    with sqlite3.connect(path) as db:
        db.executescript(BAR_SCHEMA)
        for ticker, count, close in specs:
            db.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?)', [
                (ticker + '.US', '1d', calendar.grid(day, '1d')[0][0], close, close * 1.1,
                 10, close, 1_000_000, None) for day in days[-count:]])
        # A future record cannot give YOUNG its fiftieth sample at the cutoff.
        db.execute('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?)',
                   ('YOUNG.US', '1d', calendar.grid(date(2026, 10, 2), '1d')[0][0], 90, 99, 10, 90, 1_000_000, None))
    directory = tmp_path / 'symbol-directory.json'
    symbols = {ticker + '.US': {'name': None if ticker == 'STOCK' else ticker + ' security',
               'etf': ticker == 'ETF'} for ticker, _, _ in specs if ticker != 'UNKNOWN'}
    atomic_json(directory, make_snapshot(symbols))
    return path, calendar, directory


def test_etf_and_49_records_filtered_before_rfl_ranking(tmp_path, monkeypatch):
    path, calendar, _ = market(tmp_path)
    called = []
    original = scan.return_from_low
    def rfl(history):
        called.append(history['close'][-1])
        return original(history)
    monkeypatch.setattr(scan, 'return_from_low', rfl)
    snapshot = scan.build_day(path, '2026-10-01', calendar, screening_config=replace(load_config(), rfl_top_n=1))
    rows = {row['symbol']: row for row in snapshot['rows']}
    assert called == [15, 20]  # Only confirmed non-ETF securities with sufficient history.
    assert scan.candidates(snapshot) == {'STOCK'}
    assert rows['STOCK.US']['rfl1m_rank'] == rows['STOCK.US']['rfl6m_rank'] == 1
    assert rows['STOCK.US']['sma50'] == 20 and rows['STOCK.US']['security_name'] is None
    for symbol in ('ETF.US', 'YOUNG.US', 'UNKNOWN.US'):
        assert not rows[symbol]['eligible'] and not rows[symbol]['candidate']
        assert rows[symbol]['rfl1m'] is rows[symbol]['rfl6m_rank'] is None
        assert 'ema10' not in rows[symbol]
    assert not rows['ETF.US']['etf_pass'] and not rows['YOUNG.US']['history_pass']
    assert not rows['UNKNOWN.US']['etf_pass']
    json.dumps(snapshot, allow_nan=False)


def test_retained_members_keep_features_even_when_not_scan_candidates(tmp_path):
    path, calendar, _ = market(tmp_path)
    result = scan.build_day(path, '2026-10-01', calendar, tracked_tickers={'ETF', 'YOUNG'},
                            screening_config=replace(load_config(), rfl_top_n=1))
    rows = {row['symbol']: row for row in result['rows']}
    assert rows['ETF.US']['sma50'] == 100 and not rows['ETF.US']['candidate']
    assert rows['YOUNG.US']['sma50'] is None and not rows['YOUNG.US']['candidate']
    for symbol, close in (('ETF.US', 100), ('YOUNG.US', 90)):
        for name in ('rfl1m', 'rfl3m', 'rfl6m'):
            assert rows[symbol][name] == pytest.approx((close / 10 - 1) * 100)
            assert rows[symbol][name + '_rank'] is None
    assert result['feature_scope'] == ['ETF.US', 'STOCK.US', 'YOUNG.US']

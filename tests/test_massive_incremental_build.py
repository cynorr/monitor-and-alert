"""Offline checks for simple incremental append and input-change rebuilds."""
from contextlib import closing
from datetime import date, timedelta
import sqlite3

import pytest

from data_service.calendar import TradingCalendar
from data_service.massive import build
from data_service.paths import RuntimePaths
from data_service.store import atomic_json

TARGET = date(2026, 10, 1)


def save_day(paths, calendar, day, *, price=10., volume=500_000.25):
    row = {'T': 'TEST', 'o': price, 'h': price + 2, 'l': price - 1, 'c': price + 1,
           'v': volume, 'vw': price + .5, 't': calendar.grid(day, '1d')[0][0] * 1000}
    atomic_json(paths.daily_dir / f'{day}.json', {'status': 'OK', 'adjusted': False,
                                               'resultsCount': 1, 'results': [row]})


def save_splits(paths, events=()):
    atomic_json(paths.splits_file, {'status': 'OK', 'start_date': '2020-01-01', 'end_date': str(TARGET),
                                   'resultsCount': len(events), 'results': list(events)})


def inputs(tmp_path):
    paths = RuntimePaths(tmp_path)
    calendar = TradingCalendar(TARGET)
    days = calendar.days(TARGET - timedelta(days=14), TARGET)
    for day in days:
        save_day(paths, calendar, day)
    save_splits(paths)
    return paths, calendar, days


def publish(paths, calendar, target=TARGET):
    return build.build(paths, target, calendar, now=calendar.session(target)[1])


def rows(path):
    with closing(sqlite3.connect(path)) as db:
        return db.execute('SELECT * FROM bars ORDER BY symbol,ts').fetchall()


def test_append_reads_only_new_raw_day_and_unchanged_reads_none(tmp_path, monkeypatch):
    paths, calendar, days = inputs(tmp_path)
    publish(paths, calendar, days[-2])
    original, read = build.read_day, []
    def tracked(path, day):
        read.append(day)
        return original(path, day)
    monkeypatch.setattr(build, 'read_day', tracked)
    result = publish(paths, calendar)
    assert read == [TARGET]
    assert len(rows(paths.daily_db)) == len(days)
    assert result == build.metadata(paths.daily_db)
    read.clear()
    assert publish(paths, calendar) == result
    assert read == []


def test_split_change_rebuilds_all_raw_days_and_matches_fresh_build(tmp_path, monkeypatch):
    paths, calendar, days = inputs(tmp_path)
    publish(paths, calendar)
    save_splits(paths, [{'id': 'split', 'ticker': 'TEST', 'execution_date': '2026-09-25',
                        'adjustment_type': 'forward', 'split_from': 1, 'split_to': 2}])
    original, read = build.read_day, []
    def tracked(path, day):
        read.append(day)
        return original(path, day)
    monkeypatch.setattr(build, 'read_day', tracked)
    publish(paths, calendar)
    assert read == days
    rebuilt = rows(paths.daily_db)
    assert rebuilt[0][3] == 5. and rebuilt[0][7] == 1_000_001
    paths.daily_db.unlink()
    publish(paths, calendar)
    assert rows(paths.daily_db) == rebuilt


def test_old_raw_correction_rebuilds_all_days(tmp_path, monkeypatch):
    paths, calendar, days = inputs(tmp_path)
    publish(paths, calendar)
    save_day(paths, calendar, days[0], price=20.)
    original, read = build.read_day, []
    def tracked(path, day):
        read.append(day)
        return original(path, day)
    monkeypatch.setattr(build, 'read_day', tracked)
    publish(paths, calendar)
    assert read == days
    assert rows(paths.daily_db)[0][3:7] == (20., 22., 19., 21.)


def test_failed_append_removes_derived_database_then_corrected_run_rebuilds(tmp_path):
    paths, calendar, days = inputs(tmp_path)
    publish(paths, calendar, days[-2])
    save_day(paths, calendar, TARGET, price=0.)
    with pytest.raises(ValueError, match='positive'):
        publish(paths, calendar)
    assert not paths.daily_db.exists()
    save_day(paths, calendar, TARGET)
    publish(paths, calendar)
    assert len(rows(paths.daily_db)) == len(days)
    assert build.metadata(paths.daily_db)['completed_date'] == str(TARGET)

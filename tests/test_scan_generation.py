import asyncio
import json
import sqlite3
from datetime import date

import pytest

from data_service import scan
from data_service.calendar import TradingCalendar
from data_service.features import screening
from data_service.store import BAR_SCHEMA
from data_service.workbench import Workbench
from data_service.workspace import Workspace
from scripts.build_scan_mock import build_mock


def small_source(tmp_path, rows):
    path = tmp_path / 'daily.sqlite3'
    calendar = TradingCalendar(date(2026, 10, 1))
    stamp = scan.day_start(calendar, '2026-10-01')
    with sqlite3.connect(path) as db:
        db.executescript(BAR_SCHEMA + 'CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);')
        db.execute('INSERT INTO metadata VALUES (?,?)', ('completed_date', '2026-10-01'))
        db.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?)',
                       [(symbol, '1d', stamp, close, high, low, close, volume, None)
                        for symbol, close, high, low, volume in rows])
    return path, calendar, calendar.session(date(2026, 10, 1))[1]


def test_screen_first_without_price_floor_and_build_only_candidates(tmp_path, monkeypatch):
    path, calendar, now = small_source(tmp_path, [
        ('LOW.US', .8, .85, .7, 10_000_000),
        ('ALSO.US', 10., 11., 9., 1_000_000),
        ('ILLIQUID.US', 10., 11., 9., 1),
    ])
    monkeypatch.setattr(screening, 'TOP_N', 1)
    called = []
    original = scan.feature_row
    def feature_row(history):
        called.append(history['symbol'].iloc[-1])
        return original(history)
    monkeypatch.setattr(scan, 'feature_row', feature_row)
    snapshot = scan.build_day(path, '2026-10-01', calendar, now)
    rows = {row['symbol']: row for row in snapshot['rows']}
    assert called == ['LOW.US']
    assert rows['LOW.US']['candidate'] and rows['LOW.US']['close'] < 5
    assert rows['LOW.US']['ma_arrangement'] == 'missing'
    assert rows['ALSO.US']['eligible'] and not rows['ALSO.US']['candidate']
    assert 'ema20' not in rows['ALSO.US'] and 'extended_k' not in rows['ILLIQUID.US']
    assert rows['ILLIQUID.US']['rfl1m'] is None
    json.dumps(snapshot, allow_nan=False)


def test_no_candidates_does_not_build_features(tmp_path, monkeypatch):
    path, calendar, now = small_source(tmp_path, [('NONE.US', 10., 10., 10., 1)])
    monkeypatch.setattr(scan, 'feature_row', lambda history: pytest.fail('No candidate needs features'))
    snapshot = scan.build_day(path, '2026-10-01', calendar, now)
    assert not scan.candidates(snapshot)
    assert snapshot['rows'][0]['rfl6m_rank'] is None


def test_retained_scope_builds_features_without_changing_screening_and_skips_hidden(tmp_path, monkeypatch):
    path, calendar, now = small_source(tmp_path, [
        ('LOW.US', .8, .85, .7, 10_000_000),
        ('ALSO.US', 10., 11., 9., 1_000_000),
        ('ILLIQUID.US', 10., 11., 9., 1),
    ])
    monkeypatch.setattr(screening, 'TOP_N', 1)
    called = []
    original = scan.feature_row
    def feature_row(history):
        called.append(history['symbol'].iloc[-1])
        return original(history)
    monkeypatch.setattr(scan, 'feature_row', feature_row)
    snapshot = scan.build_day(path, '2026-10-01', calendar, now,
                              tracked_tickers={'ILLIQUID', 'MISSING'}, hidden_tickers={'LOW'})
    rows = {row['symbol']: row for row in snapshot['rows']}
    assert called == snapshot['feature_scope'] == ['ILLIQUID.US']
    assert rows['LOW.US']['candidate'] and 'ema10' not in rows['LOW.US']
    assert not rows['ILLIQUID.US']['eligible'] and 'extended_k' in rows['ILLIQUID.US']
    assert rows['ILLIQUID.US']['rfl1m'] is None and rows['ILLIQUID.US']['rfl1m_rank'] is None
    assert 'ema10' not in rows['ALSO.US']


def test_enrich_legacy_snapshot_only_missing_scope_once_and_preserves_inputs(tmp_path, monkeypatch):
    path, calendar, now = small_source(tmp_path, [
        ('LOW.US', .8, .85, .7, 10_000_000),
        ('ALSO.US', 10., 11., 9., 1_000_000),
        ('ILLIQUID.US', 10., 11., 9., 1),
    ])
    monkeypatch.setattr(screening, 'TOP_N', 1)
    snapshot = scan.build_day(path, '2026-10-01', calendar, now)
    snapshot.pop('feature_scope')
    before = json.dumps(snapshot, sort_keys=True)
    called = []
    original = scan.feature_row
    def feature_row(history):
        called.append(history['symbol'].iloc[-1])
        return original(history)
    monkeypatch.setattr(scan, 'feature_row', feature_row)
    enriched = scan.enrich_snapshot(path, snapshot, calendar,
                                    tracked_tickers={'ILLIQUID', 'ALSO'}, hidden_tickers={'ALSO.US'})
    assert called == ['ILLIQUID.US']
    assert enriched['feature_scope'] == ['ILLIQUID.US', 'LOW.US']
    rows = {row['symbol']: row for row in enriched['rows']}
    assert rows['ILLIQUID.US']['rfl1m'] is None and not rows['ILLIQUID.US']['candidate']
    assert 'ema10' not in rows['ALSO.US']
    assert json.dumps(snapshot, sort_keys=True) == before
    assert scan.enrich_snapshot(path, enriched, calendar, tracked_tickers={'ILLIQUID.US'}) == enriched
    assert called == ['ILLIQUID.US']


def test_enrich_does_not_use_previous_day_as_current_feature(tmp_path):
    path, calendar, now = small_source(tmp_path, [('TODAY.US', 10., 10., 10., 1)])
    previous_stamp = scan.day_start(calendar, '2026-09-30')
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?)',
                   ('GONE.US', '1d', previous_stamp, 10., 11., 9., 10., 1_000_000, None))
    snapshot = scan.build_day(path, '2026-10-01', calendar, now)
    snapshot['rows'].append({'symbol': 'GONE.US', 'candidate': False})
    enriched = scan.enrich_snapshot(path, snapshot, calendar, tracked_tickers={'GONE'})
    assert enriched['rows'][-1] == {'symbol': 'GONE.US', 'candidate': False}
    assert 'GONE.US' not in enriched['feature_scope']


def test_workspace_scope_keeps_non_candidate_excluded_and_hidden_has_expiry(tmp_path):
    path = tmp_path / 'days' / '2026-09-30' / 'workspace.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'version': 3, 'statuses': {
        'FOCUS': {'status': 'focus', 'section': 'unclassified', 'status_at': '2026-09-30'},
        'REVIEW': {'status': 'excluded', 'section': 'review', 'status_at': '2026-09-30'},
        'BROKEN': {'status': 'excluded', 'section': 'broken', 'status_at': '2026-09-30', 'excluded_at': '2026-09-30'},
        'HIDDEN': {'status': 'excluded', 'section': 'hidden', 'status_at': '2026-09-29', 'excluded_at': '2026-09-29'},
    }, 'orders': {'discover': [], 'focus': ['FOCUS'], 'excluded': ['REVIEW', 'BROKEN', 'HIDDEN']}}))
    tracked, hidden = scan.workspace_scope(tmp_path / 'days', '2026-10-01')
    assert tracked == {'FOCUS', 'REVIEW', 'BROKEN'} and hidden == {'HIDDEN'}
    tracked, hidden = scan.workspace_scope(tmp_path / 'days', '2026-10-06')
    assert 'HIDDEN' in tracked and not hidden


def test_publish_classifies_candidates_and_preserves_same_day_manual_focus(tmp_path):
    days = tmp_path / 'days'
    previous = days / '2026-09-30' / 'workspace.json'
    previous.parent.mkdir(parents=True)
    previous.write_text(json.dumps({'version': 2, 'statuses': {
        'ALSO': {'status': 'wait', 'status_at': '2026-09-30'},
    }, 'orders': {'focus': [], 'wait': ['ALSO'], 'hidden': []}}))
    previous_bytes = previous.read_bytes()
    (tmp_path / 'preferences.json').write_text(json.dumps({
        'activeList': 'wait', 'sort': 'default', 'activeTag': 'default',
        'tags': [{'id': 'default', 'name': 'Default', 'filters': {}},
                 {'id': 'extended', 'name': 'Extended', 'filters': {'extended_k': {'min': 1.5}}}],
    }))
    snapshot = {'date': '2026-10-01', 'rows': [
        {'symbol': 'LOW.US', 'candidate': True, 'extended_k': 2},
        {'symbol': 'ALSO.US', 'candidate': False, 'extended_k': 0},
    ]}
    scan.publish_day(days, snapshot)
    current = days / snapshot['date'] / 'workspace.json'
    data = json.loads(current.read_text())
    assert data['statuses']['LOW']['status'] == 'excluded'
    assert data['statuses']['LOW']['section'] == 'extended'
    assert data['orders']['focus'] == ['ALSO']
    assert previous.read_bytes() == previous_bytes
    # An explicit same-day admission overrides the negative rule across regeneration.
    data['statuses']['LOW'].update(status='focus', section='unclassified', manual_focus_date=snapshot['date'])
    data['orders']['focus'].insert(0, 'LOW')
    data['orders']['excluded'].remove('LOW')
    current.write_text(json.dumps(data))
    scan.publish_day(days, snapshot)
    regenerated = json.loads(current.read_text())
    assert regenerated['statuses']['LOW']['status'] == 'focus'
    assert regenerated['statuses']['LOW']['tags'] == ['extended']
    assert regenerated['orders']['focus'] == ['LOW', 'ALSO']


def test_publish_invalid_preferences_keeps_existing_day(tmp_path):
    days = tmp_path / 'days'
    snapshot = {'date': '2026-10-01', 'rows': [{'symbol': 'TEST.US', 'candidate': True}]}
    scan.publish_day(days, snapshot)
    folder = days / snapshot['date']
    before = {name: (folder / name).read_bytes() for name in ('workspace.json', 'scan.json')}
    (tmp_path / 'preferences.json').write_text(json.dumps({
        'activeList': 'discover', 'sort': 'default', 'activeTag': 'default', 'tags': [],
    }))
    with pytest.raises(ValueError, match='tags'):
        scan.publish_day(days, snapshot)
    assert before == {name: (folder / name).read_bytes() for name in before}


def test_invalid_non_candidate_is_still_rejected(tmp_path):
    path, calendar, now = small_source(tmp_path, [('NONE.US', 10., 10., 10., 1.25)])
    with pytest.raises(ValueError, match='Volume'):
        scan.build_day(path, '2026-10-01', calendar, now)


def test_range_anomaly_logged_once_across_stages(tmp_path):
    path = build_mock(tmp_path, count=12)
    calendar = TradingCalendar(date(2026, 9, 30))
    stamp = scan.day_start(calendar, '2026-09-30')
    with sqlite3.connect(path) as db:
        db.execute("UPDATE bars SET close=high*1.05 WHERE symbol='NVDA.US' AND ts=?", (stamp,))
    log = tmp_path / 'invalid_ohlc.jsonl'
    snapshot = scan.build_day(path, '2026-09-30', calendar, calendar.session(date(2026, 9, 30))[1], log)
    assert 'NVDA' in scan.candidates(snapshot)
    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert len([r for r in records if r['symbol'] == 'NVDA.US' and r['start'] == stamp]) == 1


def test_refresh_uses_completed_metadata_and_selects_new_day(tmp_path):
    path = build_mock(tmp_path, count=12)
    calendar = TradingCalendar(date(2026, 10, 1))
    stamp = scan.day_start(calendar, '2026-10-01')
    previous = tmp_path / 'days' / '2026-09-30' / 'workspace.json'
    before = previous.read_bytes()
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO bars SELECT symbol,timeframe,?,open,high,low,close,volume,turnover FROM bars WHERE ts=(SELECT MAX(ts) FROM bars)", (stamp,))
        db.execute("UPDATE metadata SET value='2026-10-01' WHERE key='completed_date'")
    app = Workbench(Workspace(root=tmp_path / 'days'), tmp_path, path,
                    lambda allowed: pytest.fail('Scan must not connect to a broker'), calendar=calendar)
    async def scenario():
        # Refresh must leave an explicitly selected historical date and open the new day.
        await app.action('scan', {'date': '2026-09-29'})
        state = await app.action('scan', {'generate': True})
        assert state['date'] == app.workspace.date == '2026-10-01'
        assert state['editable'] and '2026-10-01' in state['dates']
        assert app.workspace.data['orders']['focus'] == ['PAYS', 'NVDA']
        assert 'wait' not in app.workspace.data['orders']
        assert previous.read_bytes() == before
        new_before = app.workspace.path.read_bytes()
        await app.action('scan', {'generate': True})
        assert app.workspace.path.read_bytes() == new_before
        assert not app.generating
        # Explicit historical regeneration remains available to API/CLI callers.
        state = await app.action('scan', {'date': '2026-09-29', 'generate': True})
        assert state['date'] == '2026-09-29' and not state['editable']
        await app.close()
    asyncio.run(scenario())


def test_refresh_metadata_failure_preserves_workspace_and_resets_busy(tmp_path):
    path = build_mock(tmp_path, count=12)
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM metadata WHERE key='completed_date'")
    app = Workbench(Workspace(root=tmp_path / 'days'), tmp_path, path,
                    lambda allowed: pytest.fail('Scan must not connect to a broker'))
    before = app.workspace.path.read_bytes()
    with pytest.raises(ValueError, match='completed_date'):
        asyncio.run(app.action('scan', {'generate': True}))
    assert not app.generating and app.selected_date == '2026-09-30'
    assert app.workspace.path.read_bytes() == before

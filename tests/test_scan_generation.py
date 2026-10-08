import asyncio
import json
import sqlite3
from datetime import date
from datetime import timedelta
from dataclasses import replace

import pytest

from data_service import scan
from data_service.calendar import TradingCalendar
from data_service.massive.settings import load_config
from data_service.store import BAR_SCHEMA, atomic_json
from data_service.symbol_directory import make_snapshot
from data_service.workbench import Workbench
from data_service.workspace import Workspace
from scripts.build_scan_mock import build_mock


def small_source(tmp_path, rows):
    path = tmp_path / 'daily.sqlite3'
    calendar = TradingCalendar(date(2026, 10, 1))
    days = calendar.days(date(2026, 10, 1) - timedelta(days=100), date(2026, 10, 1))[-50:]
    with sqlite3.connect(path) as db:
        db.executescript(BAR_SCHEMA + 'CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);')
        db.execute('INSERT INTO metadata VALUES (?,?)', ('completed_date', '2026-10-01'))
        db.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?)',
                       [(symbol, '1d', calendar.grid(day, '1d')[0][0], close, high, low, close, volume, None)
                        for symbol, close, high, low, volume in rows for day in days])
    atomic_json(tmp_path / 'symbol-directory.json', make_snapshot({
        row[0]: {'name': None, 'etf': False, 'test_issue': False} for row in rows}))
    return path, calendar, calendar.session(date(2026, 10, 1))[1]


def test_screen_first_without_price_floor_and_build_only_candidates(tmp_path, monkeypatch):
    path, calendar, now = small_source(tmp_path, [
        ('LOW.US', .8, .85, .7, 10_000_000),
        ('ALSO.US', 10., 11., 9., 1_000_000),
        ('ILLIQUID.US', 10., 11., 9., 1),
    ])
    called = []
    original = scan.feature_row
    def feature_row(history):
        called.append(history['symbol'].iloc[-1])
        return original(history)
    monkeypatch.setattr(scan, 'feature_row', feature_row)
    snapshot = scan.build_day(path, '2026-10-01', calendar, now, screening_config=replace(load_config(), rfl_top_n=1))
    rows = {row['symbol']: row for row in snapshot['rows']}
    assert called == ['LOW.US']
    assert rows['LOW.US']['candidate'] and rows['LOW.US']['close'] < 5
    assert rows['LOW.US']['sma50'] == pytest.approx(.8)
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


def test_retained_scope_completes_rfl_and_features_without_changing_screening(tmp_path, monkeypatch):
    path, calendar, now = small_source(tmp_path, [
        ('LOW.US', .8, .85, .7, 10_000_000),
        ('ALSO.US', 10., 11., 9., 1_000_000),
        ('ILLIQUID.US', 10., 11., 9., 1),
    ])
    called = []
    original = scan.feature_row
    def feature_row(history):
        called.append(history['symbol'].iloc[-1])
        return original(history)
    monkeypatch.setattr(scan, 'feature_row', feature_row)
    snapshot = scan.build_day(path, '2026-10-01', calendar, now,
                              screening_config=replace(load_config(), rfl_top_n=1),
                              tracked_tickers={'ILLIQUID', 'ALSO', 'LOW', 'MISSING'})
    rows = {row['symbol']: row for row in snapshot['rows']}
    assert called == snapshot['feature_scope'] == ['ALSO.US', 'ILLIQUID.US', 'LOW.US']
    assert rows['LOW.US']['candidate'] and 'ema10' in rows['LOW.US']
    assert not rows['ILLIQUID.US']['eligible'] and 'extended_k' in rows['ILLIQUID.US']
    assert not rows['ILLIQUID.US']['candidate']
    for name in ('rfl1m', 'rfl3m', 'rfl6m'):
        assert rows['ILLIQUID.US'][name] == pytest.approx((10 / 9 - 1) * 100)
        assert rows['ILLIQUID.US'][name + '_rank'] is None
        assert rows['ALSO.US'][name + '_rank'] == 2
    assert not rows['ALSO.US']['candidate'] and rows['ALSO.US']['sma50'] == 10


def test_enrich_completes_saved_rfl_and_missing_features_once_and_preserves_ranks(tmp_path, monkeypatch):
    path, calendar, now = small_source(tmp_path, [
        ('LOW.US', .8, .85, .7, 10_000_000),
        ('ALSO.US', 10., 11., 9., 1_000_000),
        ('ILLIQUID.US', 10., 11., 9., 1),
    ])
    snapshot = scan.build_day(path, '2026-10-01', calendar, now, tracked_tickers={'ILLIQUID'},
                              screening_config=replace(load_config(), rfl_top_n=1))
    for row in snapshot['rows']:
        if row['symbol'] == 'ILLIQUID.US':
            row.update(rfl1m=None, rfl3m=None, rfl6m=None)
    before = json.dumps(snapshot, sort_keys=True)
    called = []
    original = scan.feature_row
    def feature_row(history):
        called.append(history['symbol'].iloc[-1])
        return original(history)
    monkeypatch.setattr(scan, 'feature_row', feature_row)
    enriched = scan.enrich_snapshot(path, snapshot, calendar, tracked_tickers={'ILLIQUID', 'ALSO'})
    assert called == ['ALSO.US', 'ILLIQUID.US']
    assert enriched['feature_scope'] == ['ALSO.US', 'ILLIQUID.US', 'LOW.US']
    rows = {row['symbol']: row for row in enriched['rows']}
    assert rows['ILLIQUID.US']['rfl1m'] == pytest.approx((10 / 9 - 1) * 100)
    assert 'ema10' in rows['ALSO.US']
    for original_row in snapshot['rows']:
        for field in ('eligible', 'candidate', 'rfl1m_rank', 'rfl3m_rank', 'rfl6m_rank'):
            assert rows[original_row['symbol']][field] == original_row[field]
    assert json.dumps(snapshot, sort_keys=True) == before
    assert scan.enrich_snapshot(path, enriched, calendar, tracked_tickers={'ILLIQUID.US'}) == enriched
    assert called == ['ALSO.US', 'ILLIQUID.US']


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


def test_workspace_scope_includes_all_inherited_focus_and_excluded_members(tmp_path):
    path = tmp_path / 'days' / '2026-09-30' / 'workspace.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'version': 3, 'statuses': {
        'FOCUS': {'status': 'focus', 'section': 'unclassified', 'status_at': '2026-09-30'},
        'REVIEW': {'status': 'excluded', 'section': 'review', 'status_at': '2026-09-30'},
        'BROKEN': {'status': 'excluded', 'section': 'broken', 'status_at': '2026-09-30', 'excluded_at': '2026-09-30'},
        'UNDER': {'status': 'excluded', 'section': 'under50', 'status_at': '2026-09-30', 'excluded_at': '2026-09-30'},
        'HIDDEN': {'status': 'excluded', 'section': 'hidden', 'status_at': '2026-09-29', 'excluded_at': '2026-09-29'},
        'DISCOVER': {'status': 'discover', 'section': 'unclassified', 'status_at': '2026-09-30'},
    }, 'orders': {'discover': [], 'focus': ['FOCUS'], 'excluded': ['REVIEW', 'BROKEN', 'UNDER', 'HIDDEN']}}))
    tracked = scan.workspace_scope(tmp_path / 'days', '2026-10-01')
    assert tracked == {'FOCUS', 'REVIEW', 'BROKEN', 'UNDER', 'HIDDEN'}
    source, calendar, now = small_source(tmp_path, [
        (ticker + '.US', 10., 11., 9., 1)
        for ticker in ('FOCUS', 'REVIEW', 'BROKEN', 'UNDER', 'HIDDEN', 'DISCOVER')])
    snapshot = scan.build_day(source, '2026-10-01', calendar, now, tracked_tickers=tracked)
    assert snapshot['feature_scope'] == ['BROKEN.US', 'FOCUS.US', 'HIDDEN.US', 'REVIEW.US', 'UNDER.US']
    for row in snapshot['rows']:
        assert not row['candidate'] and row['rfl1m_rank'] is None
        if row['symbol'].removesuffix('.US') in tracked:
            assert row['sma50'] == 10 and row['rfl6m'] == pytest.approx((10 / 9 - 1) * 100)
        else:
            assert 'ema10' not in row


@pytest.mark.parametrize('section,name,filters,fields', [
    ('extended', 'Extended', {'extended_k': {'min': 1.5}}, {'extended_k': 2}),
    ('under50', 'Under-50', {'ma_arrangement': {'values': ['under50']}}, {'ma_arrangement': 'under50'}),
])
def test_publish_classifies_candidates_and_preserves_same_day_manual_focus(tmp_path, section, name, filters, fields):
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
                 {'id': section, 'name': name, 'filters': filters}],
    }))
    snapshot = {'date': '2026-10-01', 'rows': [
        {'symbol': 'LOW.US', 'candidate': True, **fields},
        {'symbol': 'ALSO.US', 'candidate': False, 'extended_k': 0},
    ]}
    scan.publish_day(days, snapshot)
    current = days / snapshot['date'] / 'workspace.json'
    data = json.loads(current.read_text())
    assert data['statuses']['LOW']['status'] == 'excluded'
    assert data['statuses']['LOW']['section'] == section
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
    assert regenerated['statuses']['LOW']['tags'] == [section]
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
        # Specified-date rebuilding is a CLI operation; HTTP must reject it.
        with pytest.raises(ValueError, match='scan --date'):
            await app.action('scan', {'date': '2026-09-29', 'generate': True})
        assert app.selected_date == '2026-10-01' and not app.generating
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

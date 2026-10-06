import asyncio
from datetime import date, timedelta
import json
import sqlite3

import pytest

from data_service.calendar import TradingCalendar
from data_service.massive import daily, splits, build
from data_service.paths import RuntimePaths
from data_service import pipeline
from data_service.pipeline import MassivePipeline
from data_service.scan import build_day, publish_day
from data_service.store import atomic_json
from data_service.symbol_directory import make_snapshot

TARGET = date(2026, 10, 1)


def split_event(identifier, day, *, before=1, after=2):
    return {'id': identifier, 'ticker': 'TEST', 'execution_date': day,
            'adjustment_type': 'forward', 'split_from': before, 'split_to': after}


def raw_day(calendar, day, *, volume=500_000.25):
    return {'status': 'OK', 'adjusted': False, 'resultsCount': 1,
            'results': [{'T': 'TEST', 'o': 10., 'h': 12., 'l': 9., 'c': 11., 'v': volume,
                         'vw': 10.5, 'n': 1, 't': calendar.grid(day, '1d')[0][0] * 1000}]}


def inputs(tmp_path):
    paths = RuntimePaths(tmp_path)
    atomic_json(paths.symbol_directory, make_snapshot({'TEST.US': {'name': None, 'etf': False, 'test_issue': False}}))
    calendar = TradingCalendar(TARGET)
    for day in calendar.days(TARGET - timedelta(days=14), TARGET):
        atomic_json(paths.daily_dir / f'{day}.json', raw_day(calendar, day))
    atomic_json(paths.splits_file, {'status': 'OK', 'start_date': '2024-07-12', 'end_date': str(TARGET),
                                   'resultsCount': 1, 'results': [split_event('split', '2026-09-25')]})
    return paths, calendar


def fixed_dates(monkeypatch, calendar):
    monkeypatch.setattr(daily, 'target_date', lambda calendar, now=None: TARGET)
    monkeypatch.setattr(daily, 'mature_date', lambda now=None: TARGET)
    monkeypatch.setattr(pipeline, 'RETRY_DELAYS', (0, 0, 0))
    monkeypatch.setattr(pipeline.time, 'time', lambda: calendar.session(TARGET)[1] + 1)


def test_split_window_replaces_deletions_keeps_old_history_and_rejects_gap():
    old = {'start_date': date(2020, 1, 1), 'end_date': TARGET,
           'results': [split_event('old', '2022-01-01'), split_event('removed', '2025-01-01')]}
    merged = splits.merge(old, [split_event('new', '2026-01-01')], date(2024, 10, 1), TARGET)
    assert merged['start_date'] == '2020-01-01'
    assert [row['id'] for row in merged['results']] == ['old', 'new']
    old['end_date'] = date(2024, 9, 29)
    with pytest.raises(ValueError, match='join'):
        splits.merge(old, [], date(2024, 10, 1), TARGET)


@pytest.mark.parametrize('value', [True, float('nan'), float('inf'), 0, -1])
def test_split_invalid_ratios_rejected(value):
    with pytest.raises(ValueError, match='ratios'):
        splits.check_rows([split_event('bad', '2026-01-01', before=value)], date(2024, 10, 1), TARGET)


def test_split_partial_pagination_failure_preserves_previous_file(tmp_path):
    paths, _ = inputs(tmp_path)
    before = paths.splits_file.read_bytes()
    calls = []
    async def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            return {'status': 'OK', 'results': [split_event('new', '2026-01-01')],
                    'next_url': 'https://api.massive.com/stocks/v1/splits?cursor=next'}
        raise RuntimeError('failed second page')
    with pytest.raises(RuntimeError):
        asyncio.run(splits.update(paths.splits_file, TARGET, fetch))
    assert paths.splits_file.read_bytes() == before


def test_daily_uses_calendar_and_keeps_existing_raw_bytes(tmp_path):
    paths, calendar = inputs(tmp_path)
    before = {path.name: path.read_bytes() for path in paths.daily_dir.glob('*.json')}
    async def fetch(url):
        pytest.fail('Existing daily responses must not be downloaded again')
    asyncio.run(daily.update(paths.daily_dir, TARGET, calendar, fetch))
    assert before == {path.name: path.read_bytes() for path in paths.daily_dir.glob('*.json')}
    # Independence Day is observed on July 3, so mature Saturday July 4 uses July 2.
    from datetime import datetime
    from data_service.calendar import ET
    assert daily.target_date(calendar, int(datetime(2026, 7, 4, 19, tzinfo=ET).timestamp())) == date(2026, 7, 2)


def test_builder_adjusts_before_execution_rounds_volume_and_keeps_raw(tmp_path):
    paths, calendar = inputs(tmp_path)
    before = {path.name: path.read_bytes() for path in paths.daily_dir.glob('*.json')}
    result = build.build(paths, TARGET, calendar, now=calendar.session(TARGET)[1])
    with sqlite3.connect(paths.daily_db) as db:
        earliest = db.execute('SELECT open,volume,turnover FROM bars ORDER BY ts LIMIT 1').fetchone()
        latest = db.execute('SELECT open,volume,typeof(volume) FROM bars ORDER BY ts DESC LIMIT 1').fetchone()
    assert earliest == (5., 1_000_001, 5_250_002.625)
    assert latest == (10., 500_000, 'integer')
    assert result['adjustment'] == 'split_adjusted' and result['volume_rounding'] == 'half_up'
    assert result['input_revision'] == build.input_revision(paths, TARGET)
    assert before == {path.name: path.read_bytes() for path in paths.daily_dir.glob('*.json')}
    assert not paths.bars_db.exists()


def test_builder_failure_removes_derived_database_and_logs_ohlc_without_fix(tmp_path):
    paths, calendar = inputs(tmp_path)
    raw = raw_day(calendar, TARGET)
    raw['results'][0]['c'] = 13.
    atomic_json(paths.daily_dir / f'{TARGET}.json', raw)
    build.build(paths, TARGET, calendar, now=calendar.session(TARGET)[1])
    with sqlite3.connect(paths.daily_db) as db:
        assert db.execute('SELECT close,high FROM bars ORDER BY ts DESC LIMIT 1').fetchone() == (13., 12.)
    assert (paths.daily_db.parent / 'invalid_ohlc.jsonl').exists()
    raw['results'][0]['o'] = 0
    atomic_json(paths.daily_dir / f'{TARGET}.json', raw)
    with pytest.raises(ValueError):
        build.build(paths, TARGET, calendar, now=calendar.session(TARGET)[1])
    assert not paths.daily_db.exists()


def test_ready_restart_skips_credentials_and_network(tmp_path, monkeypatch):
    paths, calendar = inputs(tmp_path)
    fixed_dates(monkeypatch, calendar)
    meta = build.build(paths, TARGET, calendar)
    snapshot = build_day(paths.daily_db, str(TARGET), calendar)
    snapshot.update(input_revision=meta['input_revision'], updated_at=pipeline.updated_at())
    publish_day(paths.days, snapshot)
    atomic_json(paths.pipeline_status, {'running': True, 'extended': {'status': 'ready'}})
    monkeypatch.setattr(pipeline, 'read_massive_token', lambda path: pytest.fail('Ready startup must not read credentials'))
    app = MassivePipeline(paths, calendar)
    assert app.state()['ready']
    assert asyncio.run(app.run()) is None
    assert app.session is None
    saved = json.loads(paths.pipeline_status.read_bytes())
    assert saved['ready'] and not saved['running'] and 'extended' not in saved


def test_interrupted_status_does_not_override_artifact_readiness(tmp_path, monkeypatch):
    paths, calendar = inputs(tmp_path)
    fixed_dates(monkeypatch, calendar)
    atomic_json(paths.pipeline_status, {'running': True, 'ready': True,
                                       'bars': {'status': 'ready'}, 'features': {'status': 'ready'}})
    app = MassivePipeline(paths, calendar)
    assert not app.state()['running'] and not app.state()['ready']
    assert app.state()['bars']['status'] == app.state()['features']['status'] == 'idle'


def test_feature_failure_reports_once(tmp_path, monkeypatch):
    paths, calendar = inputs(tmp_path)
    fixed_dates(monkeypatch, calendar)
    previous = {'date': '2026-09-30', 'mock': False, 'rows': [],
                'input_revision': 'old', 'updated_at': '2026-09-30T23:00:00+00:00'}
    atomic_json(paths.days / previous['date'] / 'scan.json', previous)
    called = {'bars': 0, 'features': 0}
    original = build.build
    def build_bars(*args, **kwargs):
        called['bars'] += 1
        return original(*args, **kwargs)
    def fail_feature(*args, **kwargs):
        called['features'] += 1
        raise RuntimeError('unsafe https://example.test/private?apiKey=TOP_SECRET_VALUE')
    monkeypatch.setattr(build, 'build', build_bars)
    monkeypatch.setattr(pipeline, 'build_day', fail_feature)
    app = MassivePipeline(paths, calendar)
    assert asyncio.run(app.run()) is None
    state = app.state()
    assert called == {'bars': 1, 'features': 1}
    assert state['bars']['status'] == 'ready' and state['features']['status'] == 'error'
    assert state['features']['date'] == previous['date'] and state['features']['updated_at'] == previous['updated_at']
    assert 'TOP_SECRET_VALUE' not in json.dumps(state) and 'https://' not in json.dumps(state)
    assert json.loads((paths.days / previous['date'] / 'scan.json').read_bytes()) == previous


def test_success_publishes_revision_and_callback(tmp_path, monkeypatch):
    paths, calendar = inputs(tmp_path)
    fixed_dates(monkeypatch, calendar)
    app = MassivePipeline(paths, calendar)
    published = []
    snapshot = asyncio.run(app.run(on_publish=published.append))
    assert snapshot['date'] == str(TARGET) and published == [snapshot]
    state = app.state()
    assert state['ready'] and not state['running']
    assert state['features']['input_revision'] == snapshot['input_revision'] == state['bars']['input_revision']
    assert json.loads(paths.pipeline_status.read_bytes()) == state
    restored = MassivePipeline(paths, calendar)
    assert restored.state()['ready']


def test_split_failure_blocks_adjusted_publication_without_repeating_daily(tmp_path, monkeypatch):
    paths, calendar = inputs(tmp_path)
    fixed_dates(monkeypatch, calendar)
    paths.splits_file.unlink()
    calls = []
    async def fail(url):
        calls.append(url)
        raise RuntimeError('private response')
    app = MassivePipeline(paths, calendar)
    monkeypatch.setattr(app, '_fetch_json', fail)
    assert asyncio.run(app.run()) is None
    state = app.state()
    assert len(calls) == 4 and all('/stocks/v1/splits' in url for url in calls)
    assert state['daily']['status'] == 'ready' and state['splits']['status'] == 'error'
    assert state['bars']['status'] == state['features']['status'] == 'idle'
    assert not paths.daily_db.exists() and not state['ready']


def test_input_read_failure_is_reported_by_bars_stage(tmp_path, monkeypatch):
    paths, calendar = inputs(tmp_path)
    fixed_dates(monkeypatch, calendar)
    calls = []
    def unreadable(*args):
        calls.append(True)
        raise OSError('private input path')
    monkeypatch.setattr(build, 'input_revision', unreadable)
    app = MassivePipeline(paths, calendar)
    calls.clear()
    assert asyncio.run(app.run()) is None
    assert len(calls) == 2  # readiness check plus one build attempt
    assert app.state()['bars']['status'] == 'error'
    assert not app.state()['ready'] and not paths.daily_db.exists()


def test_cancel_and_duplicate_run_release_pipeline(tmp_path, monkeypatch):
    paths, calendar = inputs(tmp_path)
    fixed_dates(monkeypatch, calendar)
    paths.splits_file.unlink()
    app = MassivePipeline(paths, calendar)
    async def exercise():
        entered, pending = asyncio.Event(), asyncio.Event()
        async def fetch(url):
            entered.set()
            await pending.wait()
        monkeypatch.setattr(app, '_fetch_json', fetch)
        task = asyncio.create_task(app.run())
        await entered.wait()
        assert await app.run(force=True) is None
        assert app.state()['running']
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not app.state()['running'] and app.state()['splits']['status'] == 'idle'
        assert not json.loads(paths.pipeline_status.read_bytes())['running']
        await app.close()
    asyncio.run(exercise())


def test_status_write_failure_does_not_claim_ready(tmp_path, monkeypatch):
    paths, calendar = inputs(tmp_path)
    fixed_dates(monkeypatch, calendar)
    app = MassivePipeline(paths, calendar)
    def unwritable(*args):
        raise OSError('cannot publish state')
    monkeypatch.setattr(pipeline, 'atomic_json', unwritable)
    assert asyncio.run(app.run()) is None
    state = app.state()
    assert not state['ready'] and not state['running']
    assert state['bars']['status'] == 'error' and state['error'] == 'Pipeline status could not be saved'


def test_force_refreshes_splits_but_preserves_raw_and_workspace(tmp_path, monkeypatch):
    paths, calendar = inputs(tmp_path)
    fixed_dates(monkeypatch, calendar)
    app = MassivePipeline(paths, calendar)
    asyncio.run(app.run())
    raw = {p.name: p.read_bytes() for p in paths.daily_dir.glob('*.json')}
    workspace = paths.days / str(TARGET) / 'workspace.json'
    before = workspace.read_bytes()
    urls = []
    async def fetch(url):
        urls.append(url)
        return {'status': 'OK', 'results': []}
    monkeypatch.setattr(app, '_fetch_json', fetch)
    snapshot = asyncio.run(app.run(force=True))
    assert len(urls) == 1 and '/stocks/v1/splits' in urls[0]
    assert app.state()['ready'] and snapshot['input_revision'] == app.state()['bars']['input_revision']
    assert workspace.read_bytes() == before
    assert raw == {p.name: p.read_bytes() for p in paths.daily_dir.glob('*.json')}


def test_missing_directory_stops_before_massive_requests_and_keeps_previous_scan(tmp_path, monkeypatch):
    paths, calendar = inputs(tmp_path)
    fixed_dates(monkeypatch, calendar)
    app = MassivePipeline(paths, calendar)
    asyncio.run(app.run())
    previous = (paths.days / str(TARGET) / 'scan.json').read_bytes()
    paths.symbol_directory.unlink()
    paths.splits_file.unlink()
    monkeypatch.setattr(app, '_fetch_json', lambda url: pytest.fail('Directory errors must not spend Massive bandwidth'))
    assert asyncio.run(app.run(force=True)) is None
    assert app.state()['features']['status'] == 'error'
    assert 'pull_symbol_directory' in app.state()['features']['error']
    assert not app.state()['ready'] and app.session is None
    assert (paths.days / str(TARGET) / 'scan.json').read_bytes() == previous

import asyncio
import json
import shutil
import sqlite3
from datetime import date
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from aiohttp import ClientSession, web

from data_service.calendar import TradingCalendar
from data_service.http_api import create_app
from data_service.indicators import daily_summary
from data_service.preferences import INITIAL_PREFERENCES, validate_preferences
from data_service.scan import build_day, daily_chart, publish_day, read_snapshot, candidates
from data_service.workbench import Workbench
from data_service.list_rules import apply_rules
from data_service.workspace import Workspace, derive_day_view, inherit_workspace
from scripts.build_scan_mock import build_mock
from simulator.market import Market


@pytest.fixture(scope='module')
def mock_data(tmp_path_factory):
    root = tmp_path_factory.mktemp('scan-source')
    build_mock(root, count=12)
    return root


@pytest.fixture
def app_data(tmp_path, mock_data):
    root = tmp_path / 'runtime'
    shutil.copytree(mock_data, root)
    return root


def test_source_contract_date_cutoff_and_shared_metrics(app_data):
    cal = TradingCalendar(date(2026,9,30))
    path = app_data / 'daily.sqlite3'
    now = cal.session(date(2026,9,30))[1]
    first = build_day(path, '2026-09-29', cal, now)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE bars SET close=close*2,high=high*2 WHERE ts=?", (cal.grid(date(2026,9,30),'1d')[0][0],))
    assert build_day(path, '2026-09-29', cal, now) == first
    row = next(row for row in first['rows'] if row['symbol'] == 'NVDA.US')
    chart, summary = daily_chart(path, 'NVDA.US', '2026-09-29', cal)
    assert chart['active'] is None
    assert row['adr20'] == pytest.approx(summary['adr20'])
    assert row['adv20'] == pytest.approx(summary['adv20'])
    assert row['ema20'] == pytest.approx(chart['indicators']['ema20'][-1]['value'])
    assert chart['bars'][-1]['time'] == cal.grid(date(2026,9,29),'1d')[0][0]
    with sqlite3.connect(path) as db:
        db.execute("UPDATE bars SET volume=1.25 WHERE symbol='NVDA.US' AND ts=?", (chart['bars'][-1]['time'],))
    with pytest.raises(ValueError, match='Volume'):
        build_day(path, '2026-09-29', cal, now)


def test_hidden_calendar_boundary_inheritance_and_carried():
    data = {'carried':['CARRY'], 'statuses': {'A': {'status':'hidden','status_at':'2026-09-23'},
            'CARRY': {'status':'focus','status_at':'2026-09-23'}},
            'orders': {'focus':['CARRY'], 'wait':[], 'hidden':['A']}}
    hidden = derive_day_view('2026-09-29', {'A','NEW'}, {'A'}, data)
    assert hidden.excluded == ('A',) and hidden.new == {'NEW'}
    inherited = inherit_workspace(data, {'A'}, {'A'}, '2026-09-30')
    assert 'A' in inherited['statuses']
    classified = apply_rules(inherited, {'date': '2026-09-30', 'rows': [{'symbol': 'A.US', 'candidate': True}]}, {'tags': []})
    returned = derive_day_view('2026-09-30', {'A'}, {'A'}, classified)
    assert returned.returned == {'A'} and 'A' in returned.discover and not returned.excluded
    inherited = inherit_workspace(data, {'A'}, {'A'}, '2026-10-01')
    assert set(inherited['statuses']) == {'CARRY', 'A'} and inherited['carried'] == ['CARRY']
    assert 'A' in inherit_workspace(data, set(), {'A'}, '2026-09-29')['statuses']


def test_batch_move_once_and_same_day_generation_keeps_manual_state(app_data):
    ws = Workspace(root=app_data / 'days')
    snapshot = read_snapshot(ws.root, ws.date)
    members = candidates(snapshot)
    view = derive_day_view(ws.date, members, set(), ws.data)
    moving = list(view.discover[:2])
    events = []
    ws.on_change = lambda: events.append(True)
    ws.move_members(moving, 'discover', 'focus', members, set())
    assert ws.data['orders']['focus'][:2] == moving and len(events) == 1
    before = ws.path.read_bytes()
    with pytest.raises(ValueError, match='destination'):
        ws.move_members(moving, 'discover', 'wait', members, set())
    assert ws.path.read_bytes() == before
    publish_day(ws.root, snapshot)
    assert ws.path.read_bytes() == before
    ws.move_members(['PAYS'], 'focus', 'hidden', members, set())
    assert 'PAYS' in derive_day_view(ws.date, members, set(), ws.data).excluded
    ws.move_members(['PAYS'], 'excluded', 'discover', members, set())
    assert 'PAYS' not in ws.data['statuses'] and 'PAYS' not in ws.data['orders']['discover']


class FakeBroker:
    def __init__(self, allowed, calendar):
        self.allowed, self.calls, self.closed = frozenset(allowed), [], False
        self.market = Market(list(allowed), calendar, lambda: int(__import__('time').time()))
        self.callback = None

    def context(self):
        self.calls.append(('context',))
        return self

    def set_on_quote(self, callback): self.callback = callback
    def check(self, symbols):
        assert set(symbols) <= self.allowed

    async def candles(self, symbol, tf, count=1000, background=False):
        self.check([symbol])
        self.calls.append(('bars',symbol,tf))
        return await self.market.candles(symbol,tf,count,background=background)

    async def subscribe(self, ctx, symbols):
        self.check(symbols)
        self.calls.append(('subscribe',tuple(symbols)))

    async def unsubscribe(self, ctx, symbols): self.calls.append(('unsubscribe',tuple(symbols)))
    async def snapshot(self, ctx, symbols):
        self.check(symbols)
        return [SimpleNamespace(symbol=symbol, timestamp=datetime.now(timezone.utc), last_done=10, volume=100) for symbol in symbols]

    async def validate_ticker(self, ticker): return {'ticker':ticker, 'name':'Simulated security'}

    def close(self): self.closed = True


def make_app(root, *, mock=True, pipeline=None):
    cal = TradingCalendar(date(2026,9,30))
    brokers = []
    def factory(allowed):
        broker = FakeBroker(allowed, cal)
        brokers.append(broker)
        return broker
    app = Workbench(Workspace(root=root / 'days'), root, root / 'daily.sqlite3', factory, calendar=cal, mock=mock, pipeline=pipeline)
    return app, brokers


def test_mock_scan_stays_offline_until_explicit_monitor_switch(app_data):
    async def scenario():
        app, brokers = make_app(app_data)
        assert not brokers and app.monitor is None
        row = next(row for row in app.scan_board() if row['status'] == 'discover')
        app.select(row['symbol'],'5m')
        assert set(app.view(row['symbol'],'5m')['charts']) == {'1d'}
        await app.list_action({'action':'move','source':'discover','target':'focus','tickers':[row['ticker']]})
        assert not brokers
        await app.switch_mode('monitor')
        await asyncio.sleep(.1)
        first, task = brokers[0], app.monitor_task
        assert row['symbol'] in app.monitor.symbols
        assert all(row['status'] == 'focus' for row in app.list_state()['board'])
        assert any(call[0]=='context' for call in first.calls)
        await app.switch_mode('scan')
        assert app.monitor is None and app.monitor_task is None and task.done() and first.closed
        before = len(first.calls)
        app.view(row['symbol'],'5m')
        await app.list_action({'action':'move','source':'focus','target':'hidden','tickers':[row['ticker']]})
        await asyncio.sleep(.05)
        assert len(first.calls) == before
        await app.switch_mode('monitor')
        assert row['symbol'] not in app.monitor.symbols and len(brokers) == 2
        await app.close()
        assert all(broker.closed for broker in brokers)
    asyncio.run(scenario())


def test_scan_http_ws_historical_readonly_origin_and_refresh(app_data):
    async def scenario():
        app, brokers = make_app(app_data)
        runner = web.AppRunner(create_app(app))
        await runner.setup()
        site = web.TCPSite(runner,'127.0.0.1',0)
        await site.start()
        base = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
        try:
            async with ClientSession() as client, client.ws_connect(base + '/v1/stream') as stream:
                initial = await stream.receive_json(timeout=2)
                assert initial['app_mode']=='scan' and initial['mock']
                symbol = initial['board'][0]['symbol']
                await stream.send_json({'type':'select','symbol':symbol,'timeframe':'5m','request_id':3,'mode':'scan'})
                while True:
                    payload = await stream.receive_json(timeout=2)
                    if payload['type']=='view': break
                assert payload['request_id']==3 and 'bars' in payload['charts']['1d']
                response = await client.post(base + '/v1/mode',json={'mode':'monitor'},headers={'Origin':'https://outside.example'})
                assert response.status == 403 and not brokers
                response = await client.post(base + '/v1/scan',json={'date':'2026-09-29'})
                assert response.status == 200 and not (await response.json())['editable']
                response = await client.post(base + '/v1/list',json={'action':'delete','ticker':'PAYS'})
                assert response.status == 400
                response = await client.post(base + '/v1/scan',json={'date':'2026-09-30'})
                assert response.status == 200
                before = app.workspace.path.read_bytes()
                response = await client.post(base + '/v1/scan',json={'generate':True})
                assert response.status == 200 and app.workspace.path.read_bytes()==before
                await stream.send_json({'type':'select','symbol':symbol,'timeframe':'5m','request_id':4,'mode':'monitor'})
                while True:
                    message = await stream.receive_json(timeout=2)
                    if message['type']=='error': break
                assert 'previous mode' in message['error'] and not brokers
        finally:
            await runner.cleanup()
            await app.close()
    asyncio.run(scenario())


def test_preferences_reject_unknown_rules_and_keep_exact_thresholds():
    data = {**json.loads(json.dumps(INITIAL_PREFERENCES)), 'tags': [{'id': 'sample', 'name': 'Sample', 'role': 'label', 'filters': {}}]}
    data['tags'][0]['filters']={'adv20':{'min':5_123_456.75}, 'ma_arrangement':{'values':['ema10_lead','straddle']}}
    assert validate_preferences(data)['tags'][0]['filters']['adv20']['min'] == 5_123_456.75
    data['tags'][0]['filters']['BROKEN'] = {'values': ['true']}
    with pytest.raises(ValueError, match='Unknown'):
        validate_preferences(data)


@pytest.mark.parametrize('background', ['transparent', 'frosted'])
def test_preferences_appearance_roundtrip_and_legacy_compatibility(background):
    legacy = {**json.loads(json.dumps(INITIAL_PREFERENCES)), 'tags': [{'id': 'sample', 'name': 'Sample', 'role': 'label', 'filters': {}}]}
    assert 'appearance' not in validate_preferences(legacy)['tags'][0]
    data = {**json.loads(json.dumps(INITIAL_PREFERENCES)), 'tags': [{'id': 'sample', 'name': 'Sample', 'role': 'label', 'filters': {}}]}
    appearance = {'icon': 'surf', 'color': '#2962ff', 'background': background, 'backgroundColor': '#E4B400'}
    data['tags'][0]['appearance'] = appearance
    data['tags'][0]['filters'] = {'adv20': {'min': 5_123_456.75}}
    saved = json.loads(json.dumps(validate_preferences(data)))
    assert saved['tags'][0]['appearance'] == appearance
    assert saved['tags'][0]['filters'] == {'adv20': {'min': 5_123_456.75}}
    assert saved['tags'][0]['role'] == 'label'


@pytest.mark.parametrize('invalid', [
    None,
    {'icon': 'surf'},
    {'icon': '<svg/>', 'color': '#2962ff', 'background': 'transparent', 'backgroundColor': '#e4b400'},
    {'icon': 'surf', 'color': '#fff', 'background': 'transparent', 'backgroundColor': '#e4b400'},
    {'icon': 'surf', 'color': '#2962ff', 'background': 'url(image)', 'backgroundColor': '#e4b400'},
    {'icon': 'surf', 'color': '#2962ff', 'background': 'frosted', 'backgroundColor': 42},
    {'icon': 'surf', 'color': '#2962ff', 'background': 'frosted', 'backgroundColor': '#e4b400', 'svg': '<svg/>'},
])
def test_preferences_reject_invalid_appearance(invalid):
    data = {**json.loads(json.dumps(INITIAL_PREFERENCES)), 'tags': [{'id': 'sample', 'name': 'Sample', 'role': 'label', 'filters': {}}]}
    data['tags'][0]['appearance'] = invalid
    with pytest.raises(ValueError, match='appearance'):
        validate_preferences(data)


def test_scan_rejects_forming_day_and_keeps_range_anomalies(app_data):
    cal = TradingCalendar(date(2026, 9, 30))
    path = app_data / 'daily.sqlite3'
    end = cal.session(date(2026, 9, 30))[1]
    with pytest.raises(ValueError, match='completed'):
        build_day(path, '2026-09-30', cal, end - 1)
    stamp = cal.grid(date(2026, 9, 30), '1d')[0][0]
    with sqlite3.connect(path) as db:
        db.execute("UPDATE bars SET high=low*.9 WHERE symbol='NVDA.US' AND ts=?", (stamp,))
        original = db.execute("SELECT open,high,low,close,volume FROM bars WHERE symbol='NVDA.US' AND ts=?", (stamp,)).fetchone()
    log = app_data / 'invalid_ohlc.jsonl'
    build_day(path, '2026-09-30', cal, end, log)
    item = json.loads(log.read_text().splitlines()[-1])
    assert item['symbol'] == 'NVDA.US' and item['start'] == stamp
    assert tuple(item['ohlcv'].values()) == original
    chart, _ = daily_chart(path, 'NVDA.US', '2026-09-30', cal)
    assert chart['bars'][-1]['high'] == original[1]


def test_missing_first_scan_is_a_readonly_view_and_failed_preferences_keep_state(app_data):
    async def scenario():
        app, brokers = make_app(app_data, mock=False)
        await app.switch_mode('monitor')
        task, broker = app.monitor_task, brokers[0]
        (app.workspace.root / app.selected_date / 'scan.json').unlink()
        data = await app.switch_mode('scan')
        assert data['app_mode'] == 'scan' and data['board'] == [] and not data['editable']
        assert app.monitor_task is task and not task.done() and not broker.closed
        before = json.loads(json.dumps(app.preferences))
        updated = json.loads(json.dumps(before))
        updated['sort'] = 'rfl3m'
        app.preferences_path = app_data / 'missing' / 'preferences.json'
        with pytest.raises(FileNotFoundError):
            await app.action('preferences', updated)
        assert app.preferences == before
        await app.close()
        assert brokers[0].closed
    asyncio.run(scenario())


class FakePipeline:
    def __init__(self, root):
        self.root, self.calls, self.closed = root, [], False
        self.release = asyncio.Event()
        stage = {'status': 'ready', 'target': '2026-10-01', 'updated_at': '2026-09-30T22:15:01+00:00', 'error': None}
        self.value = {'target_date': '2026-10-01', 'ready': False, 'running': False,
                      **{name: dict(stage) for name in ('daily', 'splits', 'bars', 'features')}}
        self.value['features'].update(date='2026-09-30', input_revision='old')
        self.value['bars']['input_revision'] = 'old'

    def state(self):
        return self.value

    async def run(self, force=False, on_publish=None):
        self.calls.append(force)
        self.value['running'] = True
        self.value['features']['status'] = 'running'
        try:
            await self.release.wait()
            snapshot = read_snapshot(self.root / 'days', '2026-09-30')
            snapshot['date'] = '2026-10-01'
            publish_day(self.root / 'days', snapshot)
            self.value['features'].update(status='ready', date='2026-10-01', updated_at='2026-10-01T22:15:02+00:00')
            self.value['ready'] = True
            if on_publish:
                on_publish(snapshot)
            return snapshot
        finally:
            self.value['running'] = False

    async def close(self):
        self.closed = True


@pytest.mark.parametrize('with_pipeline', [False, True])
def test_refresh_skips_completed_scan_and_opens_latest_date(app_data, monkeypatch, with_pipeline):
    async def scenario():
        pipeline = FakePipeline(app_data) if with_pipeline else None
        if pipeline:
            pipeline.value.update(target_date='2026-09-30', ready=True)
            async def ready_run(force=False, on_publish=None):
                pipeline.calls.append(force)
                assert not force
                return None
            monkeypatch.setattr(pipeline, 'run', ready_run)
        app, brokers = make_app(app_data, mock=not with_pipeline, pipeline=pipeline)
        monkeypatch.setattr('data_service.workbench.build_day', lambda *a, **kw: pytest.fail('Completed scan must not be rebuilt'))
        before = {path: path.stat().st_mtime_ns for path in (app_data / 'days').glob('*/*.json')}
        await app.action('scan', {'date': '2026-09-29'})
        run_id = app.run_id
        result = await app.action('scan', {'generate': True})
        assert result['date'] == '2026-09-30' and app.run_id != run_id
        await app.action('scan', {'generate': True})
        assert before == {path: path.stat().st_mtime_ns for path in (app_data / 'days').glob('*/*.json')}
        if pipeline:
            assert pipeline.calls == [False, False]
        with pytest.raises(ValueError, match='scan --date'):
            await app.action('scan', {'date': '2026-09-29', 'generate': True})
        assert not brokers
        await app.close()
    asyncio.run(scenario())


def test_real_scan_keeps_background_market_and_preparation_does_not_lock_modes_or_history(app_data):
    async def scenario():
        pipeline = FakePipeline(app_data)
        app, brokers = make_app(app_data, mock=False, pipeline=pipeline)
        await app.start_background()
        await asyncio.sleep(.05)
        monitor, task = app.monitor, app.monitor_task
        assert len(brokers) == 1 and pipeline.calls == [False]
        assert app.list_state()['scan_running'] and app.list_state()['massive']['features']['date'] == '2026-09-30'
        await app.switch_mode('monitor')
        await app.switch_mode('scan')
        assert app.monitor is monitor and app.monitor_task is task and not brokers[0].closed
        row = next(row for row in app.scan_board() if row['status'] == 'discover')
        app.select(row['symbol'], '5m')
        assert row['symbol'] not in monitor.symbols  # Scan selection alone never expands subscriptions.
        await app.list_action({'action': 'move', 'source': 'discover', 'target': 'focus', 'tickers': [row['ticker']]})
        assert row['symbol'] in monitor.symbols and row['symbol'] in brokers[0].allowed
        await app.action('scan', {'date': '2026-09-29'})
        pipeline.release.set()
        await app.pipeline_task
        assert app.mode == 'scan' and app.selected_date == '2026-09-29'
        assert app.workspace.date == '2026-10-01'
        await app.switch_mode('monitor')
        assert app.monitor is monitor and len(brokers) == 1
        assert monitor.store.path == app_data / 'longbridge' / 'bars.sqlite3'
        await app.close()
        assert pipeline.closed and task.done() and brokers[0].closed
    asyncio.run(scenario())


def test_first_scan_without_snapshot_can_stream_preparation_and_switch_monitor(app_data):
    async def scenario():
        pipeline = FakePipeline(app_data)
        app, brokers = make_app(app_data, mock=False, pipeline=pipeline)
        (app.workspace.root / app.selected_date / 'scan.json').unlink()
        await app.start_background()
        runner = web.AppRunner(create_app(app))
        await runner.setup()
        await (site := web.TCPSite(runner, '127.0.0.1', 0)).start()
        base = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
        try:
            async with ClientSession() as client, client.ws_connect(base + '/v1/stream') as stream:
                message = await stream.receive_json(timeout=2)
                assert message['type'] == 'list' and message['board'] == [] and message['scan_running']
                assert message['massive']['features']['date'] == '2026-09-30'
                response = await client.post(base + '/v1/mode', json={'mode': 'monitor'})
                assert response.status == 200 and (await response.json())['app_mode'] == 'monitor'
                assert len(brokers) == 1
        finally:
            await runner.cleanup()
            await app.close()
    asyncio.run(scenario())


def test_mock_and_bounded_background_never_run_massive(app_data):
    async def scenario():
        class ForbiddenPipeline:
            def state(self): raise AssertionError('Pipeline should not be constructed into this session')
            async def run(self, **kwargs): raise AssertionError('Real Massive must stay disabled')
        for options in ({'mock': True}, {'mock': False, 'only': ['NVDA']}):
            brokers = []
            def factory(allowed):
                brokers.append(FakeBroker(allowed, TradingCalendar()))
                return brokers[-1]
            app = Workbench(Workspace(root=app_data / 'days'), app_data, app_data / 'daily.sqlite3', factory,
                            pipeline=ForbiddenPipeline(), **options)
            await app.start_background()
            assert app.pipeline is None and app.list_state()['massive'] is None
            if options['mock']:
                assert not brokers
            else:
                assert brokers[0].allowed == {'NVDA.US'}
            await app.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('role,name', [('extended', 'Extended'), ('under50', 'Under-50')])
@pytest.mark.parametrize('trigger', ['startup', 'preferences'])
def test_local_lists_classify_on_startup_or_tag_save_and_keep_hidden_out_of_matching(app_data, role, name, trigger):
    async def scenario():
        app, brokers = make_app(app_data, mock=False)
        app.workspace.data['statuses']['AAPL'] = {'status': 'excluded', 'section': 'hidden',
                                                 'excluded_at': app.workspace.date, 'status_at': app.workspace.date}
        app.workspace.data['orders']['excluded'] = ['AAPL']
        negative = {'id': 'negative', 'name': name, 'role': role, 'filters': {'adr20': {'min': 0}}}
        try:
            if trigger == 'startup':
                app.preferences['tags'].append(negative)
                await app.start_background()
            else:
                await app.start_background()
                preferences = json.loads(json.dumps(app.preferences))
                preferences['tags'].append(negative)
                await app.action('preferences', preferences)
                saved = json.loads(app.preferences_path.read_text())['tags'][-1]
                assert saved == negative
            assert app.monitor is not None and brokers
            assert app.workspace.data['statuses']['NVDA']['section'] == role
            assert app.workspace.data['statuses']['NVDA']['status'] == 'excluded'
            assert app.workspace.data['statuses']['AAPL']['section'] == 'hidden'
            assert app.workspace.data['statuses']['AAPL']['tags'] == []
            assert not app.monitor.symbols
            assert all(row['status'] == 'excluded' for row in app.scan_board())
        finally:
            await app.close()
    asyncio.run(scenario())


def test_shared_actions_save_primary_section_manual_tags_and_daily_exclusion(app_data):
    async def scenario():
        app, brokers = make_app(app_data)
        app.preferences['tags'].extend([
            {'id': 'setup', 'name': 'Surf', 'role': 'setup', 'filters': {'below_days': {'max': -1}}},
            {'id': 'ext', 'name': 'Extended', 'role': 'extended', 'filters': {'extended_k': {'min': 10000}}},
        ])
        await app.prepare_lists()
        await app.list_action({'action': 'add', 'ticker': 'TSLA', 'list_name': 'focus', 'section': 'setup'})
        # Existing Discover membership is recomputed on entry; the source/target override is discarded.
        assert app.workspace.data['statuses']['TSLA']['section'] == 'unclassified'
        assert app.workspace.data['orders']['focus'][0] == 'TSLA'
        await app.list_action({'action': 'tag', 'ticker': 'TSLA', 'tags': ['setup']})
        row = next(row for row in app.scan_board() if row['ticker'] == 'TSLA')
        assert row['tags'] == ['setup'] and row['manual_tags'] == ['setup']
        before = app.workspace.path.read_bytes()
        with pytest.raises(ValueError, match='Setup or Label'):
            await app.list_action({'action': 'tag', 'ticker': 'NVDA', 'tags': ['ext']})
        assert app.workspace.path.read_bytes() == before
        await app.list_action({'action': 'hide', 'ticker': 'TSLA'})
        assert app.workspace.data['statuses']['TSLA']['section'] == 'hidden'
        assert not brokers
    asyncio.run(scenario())


def test_failed_local_list_preparation_preserves_workspace_and_starts_monitor(app_data, monkeypatch):
    async def scenario():
        app, brokers = make_app(app_data, mock=False)
        before = json.loads(json.dumps(app.workspace.data))
        def failed(*args, **kwargs):
            raise ValueError('Incomplete local daily')
        monkeypatch.setattr('data_service.workbench.enrich_snapshot', failed)
        await app.start_background()
        try:
            assert app.workspace.data == before
            assert app.workspace.error == 'Could not refresh List from local Daily'
            assert app.monitor is not None and len(brokers) == 1
        finally:
            await app.close()
    asyncio.run(scenario())


def test_massive_cli_works_without_workspace_or_longbridge_credentials(tmp_path, monkeypatch, capsys):
    import sys
    from data_service import __main__ as cli
    calls = []
    class ReadyPipeline:
        def __init__(self, paths, **kwargs):
            calls.append(paths.root)
        async def run(self, force=False):
            calls.append(force)
        def state(self):
            return {'ready': True}
        async def close(self):
            calls.append('closed')
    def forbidden(*args, **kwargs):
        raise AssertionError('Massive CLI must not load workspace or construct a broker')
    monkeypatch.setitem(sys.modules, 'data_service.pipeline', SimpleNamespace(MassivePipeline=ReadyPipeline))
    monkeypatch.setattr(cli, 'load_tickers', forbidden)
    monkeypatch.setattr(cli, 'resolve_latest_workspace', forbidden)
    monkeypatch.setattr(cli, 'run', forbidden)
    assert cli.main(['massive', '--runtime', str(tmp_path), '--force']) == 0
    assert calls == [tmp_path, True, 'closed']
    assert json.loads(capsys.readouterr().out) == {'ready': True}


def test_massive_cli_uses_the_same_runtime_lock(tmp_path, monkeypatch):
    import fcntl
    import sys
    from data_service import __main__ as cli
    def forbidden(*args, **kwargs):
        raise AssertionError('A busy runtime must not start another pipeline')
    monkeypatch.setitem(sys.modules, 'data_service.pipeline', SimpleNamespace(MassivePipeline=forbidden))
    with (tmp_path / 'service.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert cli.main(['massive', '--runtime', str(tmp_path)]) == 1

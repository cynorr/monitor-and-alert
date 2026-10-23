"""Alert business boundaries. Temporary databases; no broker or credentials."""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from aiohttp import ClientSession, web

from data_service.alerts import AlertEngine, price_cents
from data_service.longbridge.realtime import RealtimeFeed
from data_service.http_api import create_app
from test_data_service import at, cal
from test_scan_integration import make_app, app_data, mock_data


@pytest.fixture
def engine(tmp_path, cal):
    clock = [at('2026-10-05T09:31:00')]
    value = AlertEngine(tmp_path / 'alerts.sqlite3', cal, clock=lambda: clock[0])
    value.maintain({'NVDA.US'}, True)
    yield value, clock
    value.close()


def tick(engine, price, *, timestamp=None, session='Intraday', source='push'):
    engine.quote('NVDA.US', dict(last_price=price, timestamp=timestamp or int(engine.now()),
                                trade_session=session, source=source))


@pytest.mark.parametrize('start,end,direction', [(9,10,'up'), (11,10,'down'), (9,12,'up'), (11,8,'down')])
def test_reaches_or_crosses_once_and_persists(engine, start, end, direction):
    value, clock = engine
    alert = value.create('nvda', 10)
    second = value.create('NVDA.US', 10)
    assert alert['id'] != second['id']
    tick(value, start)
    assert not value.state()['unread']
    clock[0] += 1; tick(value, end)
    events = value.state()['unread']
    assert events == ['NVDA.US']
    assert value.db.execute('SELECT direction FROM unread').fetchone()[0] == direction
    tick(value, start); tick(value, end)
    assert value.state()['unread'] == ['NVDA.US']
    assert value.db.execute("SELECT count(*) FROM alerts WHERE state='triggered'").fetchone()[0] == 2


def test_raw_price_precision_equality_and_snapshot_order(engine):
    value, clock = engine
    alert = value.create('NVDA.US', '10.005')
    assert alert['price_cents'] == 1001
    tick(value, 10.009)
    tick(value, 10.011, source='snapshot')  # Same-second older snapshot cannot replace push.
    assert not value.state()['unread']
    tick(value, 10.011)  # Same-second push is meaningful and raw precision crosses 10.01.
    assert value.db.execute('SELECT direction FROM unread').fetchone()[0] == 'up'
    value.read('NVDA.US')
    value.reset(); tick(value, 10.01)
    equal = value.create('NVDA.US', 10.01)
    tick(value, 10.01); tick(value, 10.02)
    assert value.alerts[equal['id']]['state'] == 'active'
    tick(value, 10.01)
    assert value.db.execute('SELECT direction FROM unread').fetchone()[0] == 'down'


def test_read_only_clears_border_and_never_deletes_gray_or_rearmed_line(engine):
    value, clock = engine
    alert = value.create('NVDA.US', 10)
    tick(value, 9); tick(value, 10)
    value.read('NVDA.US')
    assert not value.state()['unread']
    assert value.alerts[alert['id']]['state'] == 'triggered'
    clock[0] += 11; value.maintain({'NVDA.US'}, True)
    assert value.alerts[alert['id']]['state'] == 'triggered'
    value.rearm(alert['id'], 10, 1)
    with pytest.raises(ValueError, match='changed'):
        value.rearm(alert['id'], 10, 1)
    value.read('NVDA.US')
    assert value.alerts[alert['id']]['state'] == 'active'
    tick(value, 11); tick(value, 10)
    assert value.state()['unread'] == ['NVDA.US']
    value.read('NVDA.US')
    assert value.alerts[alert['id']]['state'] == 'triggered'


def test_extended_after_hours_new_day_restart_and_sleep_never_catch_up(engine, tmp_path, cal):
    value, clock = engine
    alert = value.create('NVDA.US', 10)
    tick(value, 9); tick(value, 12, session='Post')
    assert not value.state()['unread']
    clock[0] = at('2026-10-05T17:00:00')
    tick(value, 12, timestamp=at('2026-10-05T15:50:00'))
    clock[0] = at('2026-10-06T09:31:00'); value.maintain({'NVDA.US'}, True)
    tick(value, 12)
    assert not value.state()['unread']
    value.reset(); tick(value, 8)
    assert not value.state()['unread']
    clock[0] += 35; tick(value, 12)  # Main loop stopped during sleep.
    assert not value.state()['unread']
    path = tmp_path / 'restart.sqlite3'
    restarted = AlertEngine(path, cal, clock=lambda: clock[0])
    restarted.maintain({'NVDA.US'}, True)
    item = restarted.create('NVDA.US', 10)
    tick(restarted, 9); restarted.close()
    restarted = AlertEngine(path, cal, clock=lambda: clock[0])
    try:
        restarted.maintain({'NVDA.US'}, True); tick(restarted, 12)
        assert restarted.alerts[item['id']]['state'] == 'active' and not restarted.state()['unread']
    finally:
        restarted.close()


def test_scope_removal_cleans_unread_and_expiry_removes_lines(engine):
    value, clock = engine
    alert = value.create('NVDA.US', 10)
    tick(value, 9); tick(value, 10)
    value.maintain(set(), False)  # Unknown initial Holdings isn't an empty accepted scope.
    assert alert['id'] in value.alerts
    value.maintain(set(), True)
    assert not value.alerts and not value.state()['unread']
    value.maintain({'NVDA.US'}, True)
    assert not value.alerts
    other = value.create('NVDA.US', 10)
    clock[0] = other['expires_at']; value.maintain({'NVDA.US'}, True)
    assert not value.alerts and not value.state()['unread']


@pytest.mark.parametrize('fired,closed', [
    ('2026-10-05T15:59:00', '2026-10-05T16:00:00'),
    ('2026-11-27T12:59:00', '2026-11-27T13:00:00'),
])
def test_unread_expires_at_regular_close_without_changing_price_lines(tmp_path, cal, fired, closed):
    clock = [at(fired)]
    value = AlertEngine(tmp_path / 'alerts.sqlite3', cal, clock=lambda: clock[0])
    try:
        value.maintain({'NVDA.US'}, True)
        gray = value.create('NVDA.US', 10)
        value.create('NVDA.US', 20)
        tick(value, 9); tick(value, 10)
        before = value.state()['alerts']
        assert value.state()['unread'] == ['NVDA.US']
        clock[0] = at(closed)
        value.maintain(set(), False)  # Time expiry does not wait for Holdings scope readiness.
        assert not value.state()['unread']
        assert value.state()['alerts'] == before
        assert value.alerts[gray['id']]['state'] == 'triggered'
        assert not value.db.execute('SELECT * FROM unread').fetchall()
    finally:
        value.close()


@pytest.mark.parametrize('restored_at,unread', [
    ('2026-10-23T15:59:01', ['NVDA.US']),
    ('2026-10-23T17:00:00', []),
    ('2026-10-24T08:00:00', []),
    ('2026-10-26T08:00:00', []),
    ('2026-10-26T09:31:00', []),
])
def test_unread_restart_or_wake_only_restores_current_regular(tmp_path, cal, restored_at, unread):
    clock = [at('2026-10-23T15:59:00')]
    path = tmp_path / 'alerts.sqlite3'
    sound = RecordingSound()
    value = AlertEngine(path, cal, clock=lambda: clock[0], sound=sound)
    value.maintain({'NVDA.US'}, True)
    value.create('NVDA.US', 10)
    tick(value, 9); tick(value, 10)
    prices = value.state()['alerts']
    value.close()
    clock[0] = at(restored_at)
    value = AlertEngine(path, cal, clock=lambda: clock[0], sound=sound)
    try:
        assert [row['symbol'] for row in value.db.execute('SELECT symbol FROM unread')] == unread
        assert value.state()['alerts'] == prices
        assert sound.calls == [('NVDA.US', 'up')]
        # State output also clears after sleep, even before the existing maintenance loop resumes.
        clock[0] = at('2026-10-26T16:00:00')
        assert not value.state()['unread']
        assert value.state()['alerts'] == prices
    finally:
        value.close()


@pytest.mark.parametrize('price', [0,-1,0.004,float('nan'),float('inf'),True,None])
def test_invalid_threshold_rejected(price):
    with pytest.raises(ValueError, match='positive and finite'):
        price_cents(price)


def test_quote_pipeline_accepts_same_second_push_rejects_old_snapshot_and_resets_before_connect(cal):
    from unittest.mock import patch
    received, resets = [], []
    service = RealtimeFeed(None, ['NVDA.US'], cal, on_quote=lambda s,q: received.append(q))
    event = lambda price: SimpleNamespace(timestamp=datetime.fromtimestamp(at('2026-10-05T09:31:00')),
                                          last_done=price, volume=100, trade_session='Intraday')
    with patch('data_service.longbridge.realtime.time.time', return_value=at('2026-10-05T09:31:00')):
        service.apply('NVDA.US', event(9)); service.apply('NVDA.US', event(10))
        service.apply('NVDA.US', event(8), snapshot=True)
    assert [q['last_price'] for q in received] == [9,10,10]


@pytest.mark.parametrize('source', ['discover', 'under50'])
def test_scan_and_manual_promotions_share_fresh_focus_classification(app_data, source):
    async def scenario():
        app, brokers = make_app(app_data)
        try:
            row = next(row for row in app.scan_board() if row['status'] == 'discover')
            ticker = row['ticker']
            app.preferences['tags'].extend([
                {'id':'first', 'name':'Surf', 'role':'setup', 'filters':{'adr20':{'min':0}}},
                {'id':'second', 'name':'Bounce', 'role':'setup', 'filters':{'adr20':{'min':0}}}])
            matched = ['first', 'second']
            if source == 'under50':
                app.preferences['tags'].append({'id':'under', 'name':'Under-50', 'role':'under50', 'filters':{'adr20':{'min':0}}})
                matched.append('under')
            await app.prepare_lists()
            state = app.workspace.data['statuses'].setdefault(ticker, {'status':'discover'})
            assert state['status'] == ('excluded' if source == 'under50' else 'discover')
            if source == 'under50':
                assert state['section'] == 'under50'
            state.update(tags=['stale'], manual_tags=['second'], manual_tags_date=app.workspace.date,
                         manual_section_date=app.workspace.date, section='second')
            result = await app.action('alerts', {'action':'create','symbol':row['symbol'],'price':12.345,'mode':'scan'})
            selected = app.workspace.data['statuses'][ticker]
            assert selected['section'] == 'first' and selected['tags'] == matched
            assert 'manual_tags' not in selected and 'manual_section_date' not in selected
            assert app.workspace.data['orders']['focus'][0] == ticker
            assert result['alerts'][0]['price_cents'] == 1235 and not brokers
            app.workspace.move_ticker(ticker, 'second', 1)
            saved = app.workspace.path.read_bytes()
            await app.action('alerts', {'action':'create','symbol':row['symbol'],'price':15,'mode':'scan'})
            assert app.workspace.path.read_bytes() == saved
            app.workspace.hide_ticker(ticker)
            assert not app.alerts.alerts
            await app.list_action({'action':'move','target':'focus','ticker': ticker})
            assert app.workspace.data['statuses'][ticker]['section'] == 'first'
            assert app.workspace.data['orders']['focus'][0] == ticker
        finally:
            await app.close()
    asyncio.run(scenario())


def test_alert_http_origin_and_independent_empty_selection_stream(app_data):
    async def scenario():
        app, _ = make_app(app_data)
        app.alerts.now = lambda: at('2026-10-05T09:31:00')
        runner = web.AppRunner(create_app(app)); await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0); await site.start()
        url = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
        try:
            async with ClientSession() as client, client.ws_connect(url + '/v1/stream') as stream:
                await stream.receive_json()
                initial = await stream.receive_json()
                assert initial['type'] == 'alerts' and not initial['alerts']
                target = next(row for row in app.scan_board() if row['status'] == 'focus')['symbol']
                payload = {'action':'create','symbol':target,'price':10,'mode':'scan'}
                response = await client.post(url + '/v1/alerts', json=payload, headers={'Origin':'https://outside.example'})
                assert response.status == 403 and not app.alerts.alerts
                response = await client.post(url + '/v1/alerts', json=payload)
                assert response.status == 200
                while True:
                    state = await stream.receive_json(timeout=2)
                    if state['type'] == 'alerts': break
                assert len(state['alerts']) == 1
                alert = state['alerts'][0]
                app.alerts.notify(target, 'up', alert=alert)
                while True:
                    state = await stream.receive_json(timeout=2)
                    if state['type'] == 'alerts' and state['unread']: break
                assert state['unread'] == [target] and state['alerts'][0]['state'] == 'triggered'
                response = await client.post(url + '/v1/alerts', json={'action':'read','symbol':target})
                read = await response.json()
                assert not read['unread'] and read['alerts'][0]['state'] == 'triggered'
                response = await client.post(url + '/v1/alerts', json={'action':'delete','id':state['alerts'][0]['id']})
                assert response.status == 200 and not (await response.json())['alerts']
        finally:
            await runner.cleanup(); await app.close()
    asyncio.run(scenario())


def test_reconnect_snapshot_establishes_baseline_before_next_live_cross(engine, tmp_path, cal):
    from unittest.mock import patch
    from data_service.config import Ticker
    from data_service.monitor import MonitorService
    value, clock = engine
    alert = value.create('NVDA.US', 10)
    tick(value, 9)
    class Broker:
        def context(self): return self
        def set_on_quote(self, callback): pass
        def set_on_candlestick(self, callback): pass
        async def subscribe_candles(self, ctx, symbol, timeframe): return []
        async def subscribe(self, ctx, symbols): pass
        async def snapshot(self, ctx, symbols):
            return [SimpleNamespace(symbol='NVDA.US', timestamp=datetime.fromtimestamp(clock[0]), last_done=12, volume=100)]
    service = MonitorService([Ticker(symbol='NVDA.US', ticker='NVDA', status='focus')], tmp_path / 'bars', Broker(), cal, alerts=value)
    async def scenario():
        with patch('data_service.longbridge.realtime.time.time', return_value=clock[0]):
            service.quotes.has_connected = True
            await service.quotes.connect()
            assert not value.state()['unread']
            service.quotes.apply('NVDA.US', SimpleNamespace(timestamp=datetime.fromtimestamp(clock[0]), last_done=10,
                                                           volume=101, trade_session='Intraday'))
            assert value.db.execute('SELECT direction FROM unread').fetchone()[0] == 'down'
    try:
        asyncio.run(scenario())
    finally:
        service.store.close()


def test_focus_saved_alert_write_rejected_returns_explicit_partial_result(app_data):
    async def scenario():
        app, _ = make_app(app_data)
        try:
            row = next(row for row in app.scan_board() if row['status'] == 'discover')
            app.alerts.db.execute('PRAGMA query_only=ON')
            result = await app.action('alerts', {'action':'create','symbol':row['symbol'],'price':10,'mode':'scan'})
            assert result['partial'] is True
            assert result['error'] == 'Added to Focus; alert was not saved'
            assert app.workspace.section(row['ticker']) == 'focus'
            assert not result['alerts']
        finally:
            await app.close()
    asyncio.run(scenario())


class RecordingSound:
    def __init__(self): self.calls = []
    def play(self, symbol, direction): self.calls.append((symbol, direction))
    def state(self): return {'enabled': True, 'error': None, 'playing': []}


def test_shared_notify_keeps_only_latest_unread_and_restore_never_replays(tmp_path, cal):
    sound = RecordingSound()
    clock = lambda: at('2026-10-05T09:31:00')
    path = tmp_path / 'alerts.sqlite3'
    value = AlertEngine(path, cal, clock=clock, sound=sound)
    value.maintain({'NVDA.US'}, True)
    alert = value.create('NVDA.US', 10)
    tick(value, 9); tick(value, 10)
    tick(value, 9); tick(value, 11)
    assert sound.calls == [('NVDA.US', 'up')]
    value.notify('NVDA.US', 'urgent')
    assert value.state()['unread'] == ['NVDA.US']
    assert value.db.execute('SELECT direction FROM unread').fetchone()[0] == 'urgent'
    value.close()
    restored = AlertEngine(path, cal, clock=clock, sound=sound)
    try:
        assert restored.state()['unread'] == ['NVDA.US']
        assert len(sound.calls) == 2
        restored.read('NVDA.US')
        assert restored.alerts[alert['id']]['state'] == 'triggered'
        assert len(sound.calls) == 2 and 'events' not in restored.state()
    finally:
        restored.close()


def test_failed_trigger_save_does_not_play_sound(engine):
    value, _ = engine
    value.sound = sound = RecordingSound()
    value.create('NVDA.US', 10)
    tick(value, 9)
    value.db.execute('PRAGMA query_only=ON')
    tick(value, 10)
    assert not value.state()['unread'] and not sound.calls
    assert value.alerts[next(iter(value.alerts))]['state'] == 'active'
    assert value.state()['error'] == 'Could not save alert trigger'


def test_workbench_sound_lifecycle_and_mock_defaults(app_data):
    from data_service.alerts.sound import AlertSound
    async def scenario():
        app, _ = make_app(app_data)
        assert app.sound is None and app.alert_state()['sound']['enabled'] is False
        app.sound = app.alerts.sound = AlertSound()
        await app.start_background()
        await app.close()
        assert not app.sound.tasks
        formal, _ = make_app(app_data, mock=False)
        assert isinstance(formal.sound, AlertSound) and formal.alerts.sound is formal.sound
        await formal.close()
    asyncio.run(scenario())


def test_old_card_table_migrates_latest_per_symbol_without_replaying(tmp_path, cal):
    import sqlite3
    path = tmp_path / 'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE events (symbol TEXT,direction TEXT,fired_at REAL,handled_at REAL)')
        now = at('2026-10-05T09:31:00')
        db.executemany('INSERT INTO events VALUES (?,?,?,?)', [
            ('NVDA.US','up',now-1,None), ('NVDA.US','down',now,None), ('MU.US','up',now,now+1)])
    sound = RecordingSound()
    value = AlertEngine(path, cal, clock=lambda: now, sound=sound)
    try:
        assert value.state()['unread'] == ['NVDA.US']
        assert value.db.execute('SELECT direction FROM unread').fetchone()[0] == 'down'
        assert not value.db.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone()
        assert not sound.calls
    finally:
        value.close()

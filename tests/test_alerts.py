"""Alert business boundaries. Temporary databases; no broker or credentials."""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from aiohttp import ClientSession, web

from data_service.alerts import AlertEngine, price_cents
from data_service.quotes import QuoteService
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
    assert not value.state()['events']
    clock[0] += 1; tick(value, end)
    events = value.state()['events']
    assert len(events) == 2 and all(e['direction'] == direction for e in events)
    tick(value, start); tick(value, end)
    assert len(value.state()['events']) == 2
    assert value.db.execute("SELECT count(*) FROM alerts WHERE state='triggered'").fetchone()[0] == 2


def test_raw_price_precision_equality_and_snapshot_order(engine):
    value, clock = engine
    alert = value.create('NVDA.US', '10.005')
    assert alert['price_cents'] == 1001
    tick(value, 10.009)
    tick(value, 10.011, source='snapshot')  # Same-second older snapshot cannot replace push.
    assert not value.state()['events']
    tick(value, 10.011)  # Same-second push is meaningful and raw precision crosses 10.01.
    assert value.state()['events'][0]['direction'] == 'up'
    value.acknowledge(value.state()['events'][0]['id'])
    value.reset(); tick(value, 10.01)
    equal = value.create('NVDA.US', 10.01)
    tick(value, 10.01); tick(value, 10.02)
    assert value.alerts[equal['id']]['state'] == 'active'
    tick(value, 10.01)
    assert value.state()['events'][0]['direction'] == 'down'


def test_rearm_old_card_cannot_delete_new_active_or_new_trigger(engine):
    value, clock = engine
    alert = value.create('NVDA.US', 10)
    tick(value, 9); tick(value, 10)
    old = value.state()['events'][0]
    value.rearm(alert['id'], 10, 1)
    with pytest.raises(ValueError, match='changed'):
        value.rearm(alert['id'], 10, 1)
    tick(value, 11); tick(value, 10)
    value.acknowledge(old['id'])
    assert value.alerts[alert['id']]['generation'] == 2
    assert value.alerts[alert['id']]['state'] == 'triggered'
    value.acknowledge(value.state()['events'][0]['id'])
    assert alert['id'] not in value.alerts


def test_extended_after_hours_new_day_restart_and_sleep_never_catch_up(engine, tmp_path, cal):
    value, clock = engine
    alert = value.create('NVDA.US', 10)
    tick(value, 9); tick(value, 12, session='Post')
    assert not value.state()['events']
    clock[0] = at('2026-10-05T17:00:00')
    tick(value, 12, timestamp=at('2026-10-05T15:50:00'))
    clock[0] = at('2026-10-06T09:31:00'); value.maintain({'NVDA.US'}, True)
    tick(value, 12)
    assert not value.state()['events']
    value.reset(); tick(value, 8)
    assert not value.state()['events']
    clock[0] += 35; tick(value, 12)  # Main loop stopped during sleep.
    assert not value.state()['events']
    path = tmp_path / 'restart.sqlite3'
    restarted = AlertEngine(path, cal, clock=lambda: clock[0])
    restarted.maintain({'NVDA.US'}, True)
    item = restarted.create('NVDA.US', 10)
    tick(restarted, 9); restarted.close()
    restarted = AlertEngine(path, cal, clock=lambda: clock[0])
    try:
        restarted.maintain({'NVDA.US'}, True); tick(restarted, 12)
        assert restarted.alerts[item['id']]['state'] == 'active' and not restarted.state()['events']
    finally:
        restarted.close()


def test_scope_expiry_and_cards_survive_line_removal(engine):
    value, clock = engine
    alert = value.create('NVDA.US', 10)
    tick(value, 9); tick(value, 10)
    value.maintain(set(), False)  # Unknown initial Holdings isn't an empty accepted scope.
    assert alert['id'] in value.alerts
    value.maintain(set(), True)
    assert not value.alerts and len(value.state()['events']) == 1
    value.maintain({'NVDA.US'}, True)
    assert not value.alerts
    other = value.create('NVDA.US', 10)
    clock[0] = other['expires_at']; value.maintain({'NVDA.US'}, True)
    assert not value.alerts and len(value.state()['events']) == 1


@pytest.mark.parametrize('price', [0,-1,0.004,float('nan'),float('inf'),True,None])
def test_invalid_threshold_rejected(price):
    with pytest.raises(ValueError, match='positive and finite'):
        price_cents(price)


def test_quote_pipeline_accepts_same_second_push_rejects_old_snapshot_and_resets_before_connect(cal):
    from unittest.mock import patch
    received, resets = [], []
    service = QuoteService(None, ['NVDA.US'], cal, on_quote=lambda s,q: received.append(q))
    event = lambda price: SimpleNamespace(timestamp=datetime.fromtimestamp(at('2026-10-05T09:31:00')),
                                          last_done=price, volume=100, trade_session='Intraday')
    with patch('data_service.quotes.time.time', return_value=at('2026-10-05T09:31:00')):
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
            app.workspace.delete_ticker(ticker)
            assert not app.alerts.alerts
            await app.list_action({'action':'move','source':'excluded','target':'focus','tickers':[ticker]})
            assert app.workspace.data['statuses'][ticker]['section'] == 'first'
            assert app.workspace.data['orders']['focus'][0] == ticker
        finally:
            await app.close()
    asyncio.run(scenario())


def test_alert_http_origin_and_independent_empty_selection_stream(app_data):
    async def scenario():
        app, _ = make_app(app_data)
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
                response = await client.post(url + '/v1/alerts', json={'action':'delete','id':state['alerts'][0]['id']})
                assert response.status == 200 and not (await response.json())['alerts']
        finally:
            await runner.cleanup(); await app.close()
    asyncio.run(scenario())


def test_reconnect_snapshot_establishes_baseline_before_next_live_cross(engine, tmp_path, cal):
    from unittest.mock import patch
    from data_service.config import Ticker
    from data_service.service import DataService
    value, clock = engine
    alert = value.create('NVDA.US', 10)
    tick(value, 9)
    class Broker:
        def context(self): return self
        def set_on_quote(self, callback): pass
        async def subscribe(self, ctx, symbols): pass
        async def snapshot(self, ctx, symbols):
            return [SimpleNamespace(symbol='NVDA.US', timestamp=datetime.fromtimestamp(clock[0]), last_done=12, volume=100)]
    service = DataService([Ticker(symbol='NVDA.US', ticker='NVDA', status='focus')], tmp_path / 'bars', Broker(), cal, alerts=value)
    async def scenario():
        with patch('data_service.quotes.time.time', return_value=clock[0]):
            service.quotes.has_connected = True
            await service.quotes.connect()
            assert not value.state()['events']
            service.quotes.apply('NVDA.US', SimpleNamespace(timestamp=datetime.fromtimestamp(clock[0]), last_done=10,
                                                           volume=101, trade_session='Intraday'))
            assert value.state()['events'][0]['direction'] == 'down'
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


def test_sound_only_follows_committed_new_events_and_restart_keeps_cards(tmp_path, cal):
    from data_service.alerts.sound import AlertSound
    sound = AlertSound()
    clock = lambda: at('2026-10-05T09:31:00')
    path = tmp_path / 'alerts.sqlite3'
    value = AlertEngine(path, cal, clock=clock, sound=sound)
    value.maintain({'NVDA.US'}, True)
    alert = value.create('NVDA.US', 10)
    tick(value, 9); tick(value, 10)
    tick(value, 9); tick(value, 11)
    assert sound.queue.qsize() == 1
    assert sound.queue.get_nowait() == 'up'
    sound.queue.task_done()
    value.rearm(alert['id'], 10, 1)
    tick(value, 10)
    assert sound.queue.get_nowait() == 'down'
    sound.queue.task_done()
    events = value.state()['events']
    assert len(events) == 2
    value.close()
    restored = AlertEngine(path, cal, clock=clock, sound=sound)
    try:
        assert restored.state()['events'] == events
        assert restored.state()['sound'] == {'enabled': True, 'error': None}
        assert 'notification' not in restored.state()
        assert sound.queue.empty()
        restored.acknowledge(events[0]['id'])
        assert len(restored.state()['events']) == 1 and sound.queue.empty()
    finally:
        restored.close()


def test_failed_trigger_save_does_not_play_sound(engine):
    from data_service.alerts.sound import AlertSound
    value, _ = engine
    value.sound = sound = AlertSound()
    value.create('NVDA.US', 10)
    tick(value, 9)
    value.db.execute('PRAGMA query_only=ON')
    tick(value, 10)
    assert not value.state()['events'] and sound.queue.empty()
    assert value.state()['error'] == 'Could not save alert trigger'


def test_workbench_sound_lifecycle_and_mock_defaults(app_data):
    from data_service.alerts.sound import AlertSound
    async def scenario():
        app, _ = make_app(app_data)
        assert app.sound is None and app.alert_state()['sound']['enabled'] is False
        app.sound = app.alerts.sound = AlertSound()
        await app.start_background()
        task = app.sound_task
        assert task is not None
        await app.close()
        assert task.cancelled() and app.sound_task is None
        formal, _ = make_app(app_data, mock=False)
        assert isinstance(formal.sound, AlertSound) and formal.alerts.sound is formal.sound
        await formal.close()
    asyncio.run(scenario())

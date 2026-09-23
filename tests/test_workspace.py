import asyncio
import copy
import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from aiohttp import ClientSession, web

from data_service.broker import Broker, RateLimiter
from data_service.http_api import create_app
from data_service.quotes import QuoteService
from data_service.service import DataService
from data_service.workspace import Workspace, normalize_ticker, resolve_latest_workspace
from test_data_service import cal, at


def document(focus=('PAYS', 'NVDA'), wait=('TSLA',)):
    return {'version': 2, 'extra': {'keep': True}, 'carried': ['PAYS', 'HID'],
            'orders': {'focus': list(focus), 'wait': list(wait), 'hidden': ['HID']},
            'statuses': {**{t: {'status': group, 'status_at': '2020-01-01', 'extra': 1}
                           for group, items in [('focus', focus), ('wait', wait)] for t in items},
                         'HID': {'status': 'hidden', 'status_at': '2020-01-01', 'extra': 2}}}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def test_mutations_persist_order_dates_and_preserve_unowned_fields(tmp_path):
    path = write(tmp_path / 'workspace.json', document())
    ws = Workspace(path)
    original = copy.deepcopy(ws.data)
    ws.move_ticker('NVDA', 'focus', 0)
    saved = json.loads(path.read_text())
    assert saved['orders']['focus'] == ['NVDA', 'PAYS']
    assert saved['statuses']['NVDA'] == {'status': 'focus', 'status_at': date.today().isoformat(), 'extra': 1}
    assert saved['statuses']['PAYS'] == original['statuses']['PAYS']
    ws.move_ticker('NVDA', 'wait', 1)
    assert ws.data['orders']['focus'] == ['PAYS'] and ws.data['orders']['wait'] == ['TSLA', 'NVDA']
    assert ws.data['statuses']['NVDA']['status'] == 'wait'
    before = path.read_bytes()
    assert not ws.add_ticker('NVDA', 'focus')
    assert before == path.read_bytes()
    assert ws.add_ticker('HID', 'focus')
    assert ws.data['orders']['focus'][0] == 'HID'
    assert ws.data['statuses']['HID']['extra'] == 2
    ws.delete_ticker('HID')
    saved = json.loads(path.read_text())
    assert 'HID' not in saved['statuses']
    for key in ('version', 'extra', 'carried'):
        assert saved[key] == original[key]
    assert saved['orders']['hidden'] == original['orders']['hidden']
    assert saved['statuses']['TSLA'] == original['statuses']['TSLA']


def test_latest_workspace_and_pinned_override(tmp_path):
    old = write(tmp_path / '2026-09-21/workspace.json', document())
    write(tmp_path / 'not-a-date/workspace.json', document())
    (tmp_path / '2026-09-30').mkdir()
    assert resolve_latest_workspace(tmp_path) == old
    ws = Workspace(root=tmp_path)
    latest = write(tmp_path / '2026-09-22/workspace.json', document(['AMD'], []))
    before = latest.read_bytes()
    ws.reload()
    assert ws.path == latest and ws.tickers()[0].ticker == 'AMD'
    assert latest.read_bytes() == before
    pinned = Workspace(old, root=tmp_path)
    pinned.reload()
    assert pinned.path == old


def test_failed_write_does_not_turn_retry_into_false_duplicate(tmp_path, monkeypatch):
    path = write(tmp_path / 'workspace.json', document())
    ws = Workspace(path)
    original = path.read_bytes()
    calls = []
    ws.on_change = lambda: calls.append(True)
    with monkeypatch.context() as patch:
        def fail(*args, **kwargs):
            raise PermissionError('read only')
        patch.setattr(type(path), 'write_text', fail)
        with pytest.raises(PermissionError):
            ws.add_ticker('AMD', 'focus')
    assert ws.section('AMD') is None and not calls
    assert path.read_bytes() == original and ws.error
    assert ws.add_ticker('AMD', 'focus')
    assert ws.data['orders']['focus'][0] == 'AMD' and ws.error is None


def test_broker_rechecks_whitelist_after_waiting_for_request_budget():
    async def scenario():
        gate = asyncio.Event()
        class Limiter:
            async def wait(self, background=False): await gate.wait()
        broker = object.__new__(Broker)
        broker.allowed = frozenset({'PAYS.US'})
        broker.timeout, broker.secrets = 2, ()
        broker.limiter, broker.inflight = Limiter(), asyncio.Semaphore(5)
        calls = []
        async def request(): calls.append(True)
        task = asyncio.create_task(broker.call(request, symbols=['PAYS.US']))
        await asyncio.sleep(0)
        broker.allowed = frozenset()
        gate.set()
        with pytest.raises(ValueError, match='outside current'):
            await task
        assert not calls
    asyncio.run(scenario())


@pytest.mark.parametrize('ticker', ['', '700.HK', 'AAPL.US', 'FOO SG', '../x', None])
def test_ticker_input_rejects_market_suffix_and_invalid_input(ticker):
    with pytest.raises(ValueError):
        normalize_ticker(ticker)


def test_native_events_reload_and_switch_new_day_without_writing(tmp_path):
    async def scenario():
        path = write(tmp_path / '2026-09-21/workspace.json', document())
        ws = Workspace(root=tmp_path)
        changed = asyncio.Event()
        ws.on_change = changed.set
        ws.start_watcher()
        try:
            write(path, document(['AMD'], []))
            await asyncio.wait_for(changed.wait(), 6)
            assert ws.tickers()[0].ticker == 'AMD'
            changed.clear()
            folder = tmp_path / '2026-09-22'
            folder.mkdir()
            # Directory exists before its workspace arrives.
            await asyncio.sleep(.15)
            newer = write(folder / 'workspace.json', document([], ['AAPL']))
            before = newer.read_bytes()
            await asyncio.wait_for(changed.wait(), 6)
            assert ws.path == newer and ws.tickers()[0].ticker == 'AAPL'
            assert newer.read_bytes() == before
            changed.clear()
            # Scan may replace the file by rename; watcher follows its path.
            replacement = write(folder / 'scan-save.json', document([], []))
            replacement.replace(newer)
            await asyncio.wait_for(changed.wait(), 6)
            assert ws.tickers() == []
        finally:
            ws.stop_watcher()
    asyncio.run(scenario())


def test_dynamic_universe_retains_existing_state_cancels_removed_and_supports_empty(tmp_path, cal):
    async def scenario():
        ws = Workspace(write(tmp_path / 'workspace.json', document()))
        service = DataService(ws.tickers(), tmp_path, calendar=cal)
        service.attach_workspace(ws)
        try:
            state = service.sync['PAYS.US', '5m']
            state.complete = True
            ws.move_ticker('PAYS', 'wait', 0)
            assert service.sync['PAYS.US', '5m'] is state and state.complete
            pending = asyncio.create_task(asyncio.sleep(60))
            service.sync['NVDA.US', '5m'].task = pending
            ws.delete_ticker('NVDA')
            await asyncio.sleep(0)
            assert pending.cancelled()
            assert 'NVDA.US' not in service.store.allowed
            assert all(s != 'NVDA.US' for s, _ in service.sync)
            for t in list(ws.tickers()):
                ws.delete_ticker(t.ticker)
            assert service.focus[0] == '' and service.board() == [] and service.sync == {}
            ws.add_ticker('AMD', 'wait')
            assert service.focus[0] == 'AMD.US' and len(service.sync) == 5
            assert all(s.pending and s.refresh for s in service.sync.values())
        finally:
            service.store.close()
    asyncio.run(scenario())


def test_static_info_uses_same_context_and_does_not_authorize_market_data():
    class Context:
        async def static_info(self, symbols):
            assert symbols == ['NVDA.US']
            return [SimpleNamespace(symbol='NVDA.US', name_en='NVIDIA')]
    broker = object.__new__(Broker)
    broker.allowed = frozenset()
    broker._context = Context()
    broker.timeout, broker.secrets = 2, ()
    broker.limiter, broker.inflight, broker.background = RateLimiter(), asyncio.Semaphore(5), asyncio.Semaphore(3)
    assert asyncio.run(broker.validate_ticker('NVDA'))['name'] == 'NVIDIA'
    with pytest.raises(ValueError):
        broker.check(['NVDA.US'])
    class Missing(Context):
        async def static_info(self, symbols):
            return []
    broker._context = Missing()
    with pytest.raises(ValueError, match='not found'):
        asyncio.run(broker.validate_ticker('NVDA'))


def test_quote_membership_add_remove_retry_and_empty(cal):
    class Context:
        def set_on_quote(self, callback):
            self.callback = callback
    class Fake:
        def __init__(self):
            self.calls, self.fail = [], False
        def context(self):
            return Context()
        async def subscribe(self, ctx, symbols):
            self.calls.append(('subscribe', tuple(symbols)))
            if self.fail: raise RuntimeError('subscription failed')
        async def unsubscribe(self, ctx, symbols):
            self.calls.append(('unsubscribe', tuple(symbols)))
        async def snapshot(self, ctx, symbols):
            return [SimpleNamespace(symbol=s, timestamp=datetime.now(), last_done=10, volume=100) for s in symbols]
    async def scenario():
        broker = Fake()
        recovered = []
        q = QuoteService(broker, ['PAYS.US'], cal, on_reconnect=lambda: recovered.append(1))
        await q.connect()
        broker.fail = True
        q.set_symbols(['PAYS.US', 'NVDA.US'])
        await q.update_subscriptions()
        assert q.subscription_errors == {'NVDA.US': 'subscription failed'}
        broker.fail = False
        await q.update_subscriptions()
        assert not q.subscription_errors and 'NVDA.US' in q.values
        assert broker.calls.count(('subscribe', ('PAYS.US',))) == 1 and not recovered
        q.set_symbols(['NVDA.US'])
        await q.update_subscriptions()
        assert ('unsubscribe', ('PAYS.US',)) in broker.calls and 'PAYS.US' not in q.values
        q.set_symbols([])
        await q.update_subscriptions()
        assert not q.subscribed
        await q.disconnect()
    asyncio.run(scenario())


def test_list_http_mutations_validation_failure_origin_and_empty_stream(tmp_path, cal):
    class Fake:
        def check(self, symbols): pass
        async def validate_ticker(self, ticker):
            if ticker == 'BAD': raise ValueError('US ticker not found')
            if ticker == 'FAIL': raise TimeoutError('validation unavailable')
            return {'name': 'Validated stock'}
    async def scenario():
        wsfile = Workspace(write(tmp_path / 'workspace.json', document([], [])))
        service = DataService([], tmp_path, Fake(), calendar=cal, clock=lambda: at('2026-09-18T13:44:45'))
        service.attach_workspace(wsfile)
        runner = web.AppRunner(create_app(service))
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        base = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
        try:
            async with ClientSession() as client, client.ws_connect(base + '/v1/stream') as stream:
                assert (await stream.receive_json(timeout=2))['board'] == []
                before = wsfile.path.read_bytes()
                for ticker, code in [('BAD', 400), ('FAIL', 503)]:
                    response = await client.post(base + '/v1/list', json={'action': 'add', 'ticker': ticker, 'section': 'focus'})
                    assert response.status == code
                    assert before == wsfile.path.read_bytes()
                response = await client.post(base + '/v1/list', json={'action': 'add', 'ticker': 'nvda', 'section': 'wait'})
                assert response.status == 200
                assert (await response.json())['board'][0]['ticker'] == 'NVDA'
                assert json.loads(wsfile.path.read_text())['orders']['wait'] == ['NVDA']
                message = await stream.receive_json(timeout=2)
                assert message['board'][0]['ticker'] == 'NVDA'
                await stream.send_json({'type': 'select', 'symbol': 'NVDA.US', 'timeframe': '5m', 'request_id': 7})
                while True:
                    message = await stream.receive_json(timeout=2)
                    if message['type'] == 'view': break
                assert message['request_id'] == 7 and 'bars' in message['charts']['5m']
                response = await client.post(base + '/v1/list', json={'action': 'delete', 'ticker': 'NVDA'}, headers={'Origin': 'https://outside.example'})
                assert response.status == 403
                response = await client.post(base + '/v1/list', data='{}', headers={'Content-Type': 'text/plain'})
                assert response.status == 415
                response = await client.post(base + '/v1/list', json={'action': 'delete', 'ticker': 'NVDA'})
                assert response.status == 200
                while True:
                    message = await stream.receive_json(timeout=2)
                    if message['type'] == 'list': break
                assert message['board'] == [] and not stream.closed
        finally:
            await runner.cleanup()
            service.store.close()
    asyncio.run(scenario())

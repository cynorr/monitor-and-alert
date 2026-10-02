"""Offline holdings acquisition, valuation, lifecycle and chart transport checks."""
import asyncio
import copy
from decimal import Decimal as D
import json
from unittest.mock import patch

import pytest
from aiohttp import ClientSession, web

from data_service.config import Ticker
from data_service.calendar import TradingCalendar
from data_service.holdings import Holdings, build, value_positions
from data_service.http_api import create_app
from data_service.service import DataService
from data_service.snaptrade import SnapTrade
from data_service.workbench import Workbench
from data_service.workspace import Workspace
from test_holdings import activity, snapshot
from test_scan_integration import FakeBroker, app_data, mock_data
from test_data_service import cal


def raw_snapshot():
    raw = snapshot([activity('b', 'BUY', '100', '10', '2026-09-01'),
                    activity('s', 'SELL', '25', '15', '2026-09-03')], '75')
    raw['account']['id'] = 'acct'
    raw['account']['sync_status'] = {'transactions': {'last_successful_sync': '2026-09-16'}}
    raw['activities_through'] = '2026-09-16'
    raw['cash'] = '-200'
    return raw


def rules(folder):
    (folder / 'sequences.txt').write_text('')
    (folder / 'merge_buys.txt').write_text('')
    return folder


class FakeSnapTrade:
    secrets = ('secret-key',)
    def __init__(self, raw):
        self.raw, self.calls, self.closed = raw, 0, False
        self.fail = False
    async def refresh(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError('Request failed secret-key')
        return copy.deepcopy(self.raw)
    def commit(self, raw): self.raw = raw
    async def close(self): self.closed = True


def test_latest_session_reprices_only_market_values_and_unrealized_profit():
    base = build(raw_snapshot(), [])
    original = copy.deepcopy(base)
    quotes = {'XYZ.US': {
        'Intraday': {'timestamp': 100, 'last_price': 13, 'trade_session': 'Intraday'},
        'Post': {'timestamp': 90, 'last_price': 99, 'trade_session': 'Post'},
        'Overnight': {'timestamp': 120, 'last_price': 14.5, 'trade_session': 'Overnight'},
    }}
    result = value_positions(base, quotes)
    sequence = result['holdings'][0]['sequences'][0]
    assert result['holdings'][0]['price'] == D('14.5')
    assert result['holdings'][0]['price_session'] == 'Overnight'
    assert sequence['market_value'] == D('1087.5')
    assert sequence['unrealized_pnl'] == D('337.5')
    assert sequence['realized_pnl'] == D('125')
    assert sequence['total_pnl'] == D('462.5')
    assert sequence['total_pnl_percent'] == D('46.25')
    assert sequence['buy_price'] == D(10) and sequence['sells'] == original['holdings'][0]['sequences'][0]['sells']
    assert result['funds']['account_total'] == D('887.5')
    assert result['funds']['cash'] == D('-200')
    assert base == original
    # A newer regular quote wins over older extended-session values.
    quotes['XYZ.US']['Intraday']['timestamp'] = 130
    assert value_positions(base, quotes)['holdings'][0]['price'] == D(13)


def test_missing_or_invalid_longbridge_price_falls_back_to_last_snaptrade_price():
    base = build(raw_snapshot(), [])
    for quotes in ({}, {'XYZ.US': {'Post': {'last_price': float('nan'), 'timestamp': 10, 'trade_session': 'Post'}}}):
        result = value_positions(base, quotes)
        assert result['holdings'][0]['price'] == D(12)
        assert result['holdings'][0]['price_source'] == 'snaptrade'
        assert result['funds']['account_total'] == D(700)
    empty = copy.deepcopy(raw_snapshot())
    empty['positions']['results'] = []
    result = value_positions(build(empty, []), {})
    assert result['funds']['stock_market_value'] == 0 and result['funds']['account_total'] == D(-200)
    assert result['summary']['pnl_percent'] is None


def test_refresh_is_immediate_and_failed_fetch_or_accounting_preserves_snapshot(tmp_path):
    async def scenario():
        client = FakeSnapTrade(raw_snapshot())
        holdings = Holdings(client, rules(tmp_path))
        changed = asyncio.Event()
        task = asyncio.create_task(holdings.run(changed.set))
        await asyncio.wait_for(changed.wait(), .5)
        assert client.calls == 1
        previous = holdings.base
        client.fail = True
        assert not await holdings.refresh()
        assert holdings.base is previous and 'secret-key' not in holdings.error
        client.fail = False
        client.raw['positions']['results'][0]['units'] = '76'
        assert not await holdings.refresh()
        assert holdings.base is previous
        client.raw['positions']['results'][0]['units'] = '75'
        assert await holdings.refresh() and holdings.error is None
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert client.closed
    asyncio.run(scenario())


def test_failed_poll_waits_for_next_cycle_and_success_updates_membership(tmp_path):
    async def scenario():
        client = FakeSnapTrade(raw_snapshot())
        client.fail = True
        holdings = Holdings(client, rules(tmp_path))
        previous = holdings.base
        waiting, permit, changed = asyncio.Event(), asyncio.Event(), asyncio.Event()
        delays = []
        async def sleep(delay):
            delays.append(delay)
            waiting.set()
            await permit.wait()
            permit.clear()
        with patch('data_service.holdings.asyncio.sleep', sleep):
            task = asyncio.create_task(holdings.run(changed.set))
            await asyncio.wait_for(waiting.wait(), .5)
            assert client.calls == 1 and holdings.base is previous and not changed.is_set()
            assert 29 <= delays[0] <= 30
            client.fail = False
            permit.set()
            await asyncio.wait_for(changed.wait(), .5)
            assert client.calls == 2 and holdings.base is not previous and holdings.error is None
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_snaptrade_uses_configured_account_reuses_history_and_only_commits_success(tmp_path):
    async def scenario():
        path = tmp_path / 'latest.json'
        client = SnapTrade('test-client', 'test-key', 'acct', path)
        raw, calls = raw_snapshot(), []
        detail = raw['account']
        async def get(resource, params=None):
            calls.append((resource, params))
            return {'/accounts/acct': detail,
                    '/accounts/acct/positions/all': raw['positions'],
                    '/accounts/acct/balances': [{'currency': {'code': 'USD'}, 'cash': D(-200)}],
                    '/accounts/acct/orders': [],
                    '/accounts/acct/activities': {'data': raw['activities'], 'pagination': {'total': 2}}}[resource]
        client.get = get
        first = await client.refresh()
        assert not path.exists() and client.raw is None
        client.commit(first)
        previous = path.read_bytes()
        assert path.stat().st_mode & 0o777 == 0o600
        assert calls[0][0] == '/accounts/acct/positions/all'
        assert all(resource != '/accounts' for resource, _ in calls)
        calls.clear()
        await client.refresh()
        assert len(calls) == 4 and not any(p.endswith('/activities') for p, _ in calls)
        detail['sync_status']['transactions']['last_successful_sync'] = '2026-09-17'
        await client.refresh()
        assert sum(p.endswith('/activities') for p, _ in calls) == 1
        assert path.read_bytes() == previous
        await client.close()
    asyncio.run(scenario())


def test_signed_get_and_shared_rolling_account_budget(tmp_path):
    async def scenario():
        client = SnapTrade('test-client', 'test-key', 'acct', tmp_path / 'latest.json')
        requests, clock = [], [0.0]
        class Response:
            status = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def text(self): return '{"cash": 0.125}'
        class Session:
            def get(self, url, headers):
                requests.append((url, headers))
                return Response()
        client.session = Session()
        async def sleep(delay): clock[0] += delay
        with patch('data_service.snaptrade.time.monotonic', lambda: clock[0]), patch('data_service.snaptrade.asyncio.sleep', sleep):
            for _ in range(11):
                assert (await client.get('/accounts/acct/balances'))['cash'] == D('.125')
        assert len(requests) == 11 and clock[0] >= 60.1
        assert all(url.startswith('https://api.snaptrade.com/api/v1/accounts/acct/balances?clientId=test-client&timestamp=') for url, _ in requests)
        assert all(headers['Signature'] and 'test-key' not in url for url, headers in requests)
    asyncio.run(scenario())


def test_bad_cache_does_not_block_startup_and_http_error_never_exposes_request(tmp_path):
    async def scenario():
        path = tmp_path / 'latest.json'
        path.write_text('{broken')
        client = SnapTrade('test-client', 'secret-key', 'acct', path)
        assert client.raw is None
        class Response:
            status = 429
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def text(self): raise AssertionError('Do not expose an arbitrary error body')
        class Session:
            def get(self, url, headers): return Response()
        client.session = Session()
        with pytest.raises(RuntimeError, match='^SnapTrade HTTP 429$'):
            await client.get('/accounts/acct/positions/all')
        assert path.read_text() == '{broken' and client.raw is None
        path.write_text(json.dumps({'account': {'id': 'another'}}))
        assert SnapTrade('test-client', 'secret-key', 'acct', path).raw is None
    asyncio.run(scenario())


def test_independent_membership_shares_market_state_and_never_changes_workspace(tmp_path, cal):
    service = DataService([Ticker('XYZ.US', 'XYZ', 'focus')], tmp_path, calendar=cal)
    try:
        existing = service.sync['XYZ.US', '5m']
        service.update_holdings(['XYZ.US', 'OTHER.US'])
        assert service.symbols == ['XYZ.US', 'OTHER.US'] and len(service.sync) == 10
        assert service.sync['XYZ.US', '5m'] is existing
        assert [row['ticker'] for row in service.board()] == ['XYZ']
        service.update_tickers([])
        assert service.symbols == ['XYZ.US', 'OTHER.US']
        assert service.sync['XYZ.US', '5m'] is existing
        service.select('OTHER.US', '4h')
        assert set(service.view('OTHER.US', '4h')['charts']) == {'1d', '4h'}
        service.update_holdings(['XYZ.US'])
        assert 'OTHER.US' not in service.store.allowed and service.focus[0] == 'XYZ.US'
        service.update_holdings([])
        assert service.symbols == [] and not service.sync
    finally:
        service.store.close()


def make_holdings_app(root):
    workspace = Workspace(root=root / 'days')
    client = FakeSnapTrade(raw_snapshot())
    controller = Holdings(client, rules(root))
    def broker_factory(allowed):
        broker = FakeBroker(allowed, controller_calendar)
        broker.market.check = broker.check
        return broker
    controller_calendar = TradingCalendar()
    app = Workbench(workspace, root, root / 'daily.sqlite3', broker_factory,
                    calendar=controller_calendar, holdings_factory=lambda: controller)
    return app, client


def test_workbench_http_ws_holdings_only_selection_duplicate_and_scan_stop(app_data):
    async def scenario():
        app, client = make_holdings_app(app_data)
        original = app.workspace.path.read_bytes()
        assert client.calls == 0 and app.holdings_state() is None
        await app.switch_mode('monitor')
        await asyncio.sleep(.05)
        assert client.calls == 1 and 'XYZ.US' in app.symbols
        for _ in range(30):
            if app.monitor.view('XYZ.US', '4h')['charts']['1d']['bars'] and app.monitor.view('XYZ.US', '4h')['charts']['4h']['bars']:
                break
            await asyncio.sleep(.05)
        assert app.monitor.view('XYZ.US', '4h')['charts']['1d']['bars']
        assert app.monitor.view('XYZ.US', '4h')['charts']['4h']['bars']
        app.monitor.update_tickers([Ticker('XYZ.US', 'XYZ', 'focus')])
        assert app.symbols.count('XYZ.US') == 1
        runner = web.AppRunner(create_app(app))
        await runner.setup()
        await (site := web.TCPSite(runner, '127.0.0.1', 0)).start()
        base = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
        try:
            async with ClientSession() as session:
                response = await session.get(base + '/v1/holdings')
                assert response.status == 200 and (await response.json())['data']['holdings'][0]['ticker'] == 'XYZ'
                async with session.ws_connect(base + '/v1/stream') as ws:
                    assert ws.compress == 0
                    await ws.send_json({'type': 'select', 'symbol': 'XYZ.US', 'timeframe': '4h', 'request_id': 42, 'mode': 'monitor'})
                    while True:
                        message = await ws.receive_json(timeout=2)
                        if message['type'] == 'list': assert message['holdings']['data']['holdings'][0]['ticker'] == 'XYZ'
                        if message['type'] == 'view' and message['request_id'] == 42: break
                    assert set(message['charts']) == {'1d', '4h'}
                    assert client.calls == 1  # HTTP/WS reads do not trigger acquisition.
                    client.fail = True
                    previous = app.holdings.base
                    assert not await app.holdings.refresh()
                    assert app.holdings.base is previous and not app.monitor_task.done()
            assert app.workspace.path.read_bytes() == original
            await app.switch_mode('scan')
            assert client.closed and app.holdings_task is None and app.holdings_state() is None
            await app.switch_mode('monitor')
            await asyncio.sleep(.01)
            assert client.calls == 3  # startup, explicit failed refresh, immediate re-entry refresh
        finally:
            await runner.cleanup()
            await app.close()
    asyncio.run(scenario())


def test_mock_and_bounded_sessions_never_construct_holdings(app_data):
    async def scenario():
        def forbidden(): raise AssertionError('Real holdings must remain disabled')
        for options in ({'mock': True}, {'only': ['NVDA']}):
            workspace = Workspace(root=app_data / 'days')
            app = Workbench(workspace, app_data, app_data / 'daily.sqlite3',
                            lambda allowed: FakeBroker(allowed, TradingCalendar()),
                            holdings_factory=forbidden, **options)
            await app.switch_mode('monitor')
            assert app.holdings_state() is None
            await app.close()
    asyncio.run(scenario())

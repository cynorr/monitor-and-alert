"""Metadata can update independently of Ready and bar revisions."""
import asyncio

from aiohttp import ClientSession, web
import pytest

from data_service.additional_info import AdditionalInfo
from data_service.http_api import create_app
from data_service.store import atomic_json
from data_service.workbench import Workbench
from data_service.workspace import Workspace


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    day = tmp_path / 'days' / '2026-09-30'
    day.mkdir(parents=True)
    atomic_json(day / 'workspace.json', {
        'version': 3, 'statuses': {'XYZ': {'status': 'focus', 'section': 'unclassified'}},
        'orders': {'discover': [], 'focus': ['XYZ'], 'excluded': []},
    })
    atomic_json(day / 'scan.json', {'date': '2026-09-30', 'mock': True, 'rows': [
        {'symbol': 'XYZ.US', 'candidate': False, 'close': 10, 'adr20': 5, 'adv20': 6000000}
    ]})
    def no_broker(*_): pytest.fail('Additional info must not construct a broker')
    info = AdditionalInfo(tmp_path / 'additional-info', enabled=False)
    app = Workbench(Workspace(root=tmp_path / 'days'), tmp_path, tmp_path / 'daily.sqlite3',
                    no_broker, mock=True, additional_info=info)
    app.mode = 'scan'
    monkeypatch.setattr('data_service.workbench.daily_chart', lambda *_: (
        {'revision': 1, 'bars': [], 'indicators': {}}, {}))
    return app


def test_optional_info_never_changes_chart_revision_and_get_does_not_fetch(workbench):
    app = workbench
    assert app.additional_info('XYZ.US')['company_name'] is None
    first = app.view('XYZ.US', '5m')
    app.additional.companies['XYZ.US'] = {'company_name': 'XYZ Inc.'}
    app.additional.revision += 1
    second = app.view('XYZ.US', '5m', {'1d': 1})
    assert 'security_name' not in first and 'bars' not in second['charts']['1d']
    assert asyncio.run(app.api('/v1/additional-info', {'symbol': ['XYZ.US']}))['company_name'] == 'XYZ Inc.'
    assert app.monitor is None


def test_background_start_does_not_wait_for_optional_feed(workbench, monkeypatch):
    app = workbench
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        async def blocked():
            entered.set()
            await release.wait()
        monkeypatch.setattr(app.additional, 'run', blocked)
        await asyncio.wait_for(app.start_background(), 1)
        await asyncio.wait_for(entered.wait(), 1)
        assert not app.additional_task.done()
        assert app.view('XYZ.US', '5m')['charts']['1d']['revision'] == 1
        await app.close()
    asyncio.run(run())


def test_websocket_additional_message_has_selection_identity_and_preserves_cached_bars(workbench):
    async def run():
        app = workbench
        runner = web.AppRunner(create_app(app))
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        async def receive(ws, kind):
            for _ in range(10):
                data = await ws.receive_json(timeout=2)
                if data['type'] == kind: return data
            pytest.fail('Missing ' + kind)
        try:
            async with ClientSession() as client:
                async with client.ws_connect(f'http://127.0.0.1:{port}/v1/stream') as ws:
                    base = f'http://127.0.0.1:{port}'
                    response = await client.get(base + '/v1/additional-info?symbol=XYZ.US')
                    assert response.status == 200 and (await response.json())['company_name'] is None
                    app.additional.enabled = True
                    response = await client.post(base + '/v1/additional-info', json={'action': 'refresh'},
                                                 headers={'Origin': 'http://other.invalid'})
                    assert response.status == 403 and not app.additional.force
                    response = await client.post(base + '/v1/additional-info', json={'action': 'refresh'})
                    assert response.status == 200 and (await response.json())['running']
                    assert app.additional.wakeup.is_set() and app.monitor is None
                    await ws.send_json({'type': 'select', 'symbol': 'XYZ.US', 'timeframe': '5m',
                                        'request_id': 31, 'mode': 'scan', 'source': 'watchlist'})
                    first = await receive(ws, 'additional_info')
                    assert first['company_name'] is None and first['request_id'] == 31
                    await receive(ws, 'view')
                    app.additional.companies['XYZ.US'] = {'company_name': 'XYZ & Co.'}
                    app.additional.revision += 1
                    info = await receive(ws, 'additional_info')
                    assert (info['symbol'], info['mode'], info['source']) == ('XYZ.US', 'scan', 'watchlist')
                    assert info['company_name'] == 'XYZ & Co.'
                    chart = (await receive(ws, 'view'))['charts']['1d']
                    assert chart['revision'] == 1 and 'bars' not in chart
        finally:
            await runner.cleanup()
    asyncio.run(run())

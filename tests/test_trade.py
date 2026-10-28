"""Trade integration uses fake credentials and a broker MockTransport; never real writes."""
import asyncio
import copy
import time
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from aiohttp import ClientSession, web

from data_service import schwab_backend as broker
from data_service.http_api import create_app
from data_service.trade import SchwabTrade, portfolio
from data_service.workbench import Workbench
from data_service.workspace import Workspace
from test_scan_integration import app_data, mock_data, FakeBroker


class MemoryStore:
    def load(self): return None
    def secret(self): return 'fake'


def order(oid='1', symbol='XYZ', side='SELL', status='FILLED', day='2026-10-26T15:00:00Z', **changes):
    row = {'order_id': oid, 'parent_order_id': None, 'symbol': symbol, 'asset_type': 'EQUITY',
           'instruction': side, 'status': status, 'order_type': 'STOP', 'strategy_type': 'SINGLE',
           'quantity': '10', 'filled_quantity': '10', 'stop_price': '9', 'editable': True,
           'cancelable': False, 'executions': [{'quantity': '10', 'price': '11', 'time': day}], 'child_orders': []}
    return {**row, **changes}


def position(symbol='XYZ'):
    return {'symbol': symbol, 'quantity': '5', 'average_price': '10', 'market_value': '60',
            'open_profit_loss': '10', 'day_profit_loss': '4'}


def runtime(handler=None):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler or (lambda r: httpx.Response(200, json={}))))
    value = broker.Runtime(store=MemoryStore(), http=http)
    value.tokens.credentials = broker.Credentials('fake-access', 'fake-refresh', time.time() + 10000)
    value.rest.account_hash = 'fake-account'
    value.state.account_updated_at = value.state.orders_updated_at = '2026-10-26T15:00:00Z'
    value.state.account = {'liquidation_value': '123', 'stock_buying_power': '99', 'available_funds': '42'}
    return value


def test_sold_and_holding_share_one_symbol_without_cost_matching_or_duplicate_fills():
    sell = order()
    parent = order('2', side='BUY', status='FILLED', child_orders=[sell])
    rows = portfolio([position()], [parent, sell], '2026-10-26')
    assert len(rows) == 1 and rows[0]['kind'] == 'holding'
    assert rows[0]['sold_today']['quantity'] == '10'
    assert rows[0]['sold_today']['amount'] == '110'
    assert rows[0]['position']['open_profit_loss'] == '10'
    assert portfolio([], [sell], '2026-10-26')[0]['kind'] == 'sold'
    assert portfolio([], [sell], '2026-10-27') == []


def test_sold_today_keeps_original_filled_and_new_york_date_scope():
    assert portfolio([], [order(status='CANCELED')], '2026-10-26') == []
    assert portfolio([], [order(day='2026-10-27T01:00:00Z')], '2026-10-26')[0]['kind'] == 'sold'
    assert portfolio([], [order(asset_type='OPTION')], '2026-10-26') == []
    rows = portfolio([], [order(status='WORKING', side='BUY', executions=[])], '2026-10-26')
    assert rows[0]['kind'] == 'entry'


@pytest.mark.asyncio
async def test_schwab_financial_fields_survive_longbridge_quotes_and_subscriptions_do_not_get_quotes():
    calls = []
    value = runtime(lambda r: (calls.append(r), httpx.Response(200, json={}))[1])
    trade = SchwabTrade(value)
    value.state.positions = [position()]
    original = copy.deepcopy(value.state.positions)
    now = datetime(2026, 10, 26, 15, tzinfo=timezone.utc).timestamp()
    result = trade.state(now, {'XYZ.US': {'regular': {'last_price': 999, 'prev_close': 10, 'timestamp': now},
                                        'latest': {'last_price': 999, 'trade_session': 'Intraday', 'timestamp': now}}})
    assert result['rows'][0]['position'] == original[0]
    assert result['account']['liquidation_value'] == '123'
    assert trade.held_symbols() == {'XYZ.US'}
    trade.subscribe(['XYZ.US', 'ABC.US', 'ABC.US'])
    assert value.state.subscribed_symbols == {'XYZ', 'ABC'} and calls == []
    await value.close()


@pytest.mark.asyncio
async def test_integrated_routes_validate_before_write_and_preserve_unknown_without_retry():
    calls = []
    def transport(request):
        calls.append(request)
        if request.method == 'GET':
            return httpx.Response(200, json={'XYZ': {'assetMainType': 'EQUITY', 'quote': {'askPrice': '11.90', 'bidPrice': '11.80'}}})
        raise httpx.ReadTimeout('synthetic', request=request)
    value = runtime(transport)
    trade = SchwabTrade(value)
    service = SimpleNamespace(mode='trade', trade=trade, symbols=['XYZ.US'])
    runner = web.AppRunner(create_app(service))
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    base = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
    payload = {'symbol': 'XYZ', 'qty': 5, 'buy_stop': '12', 'sell_stop': '10.5'}
    try:
        async with ClientSession() as session:
            for invalid in ({**payload, 'qty': True}, {**payload, 'unexpected': True}, {**payload, 'buy_stop': 12}):
                response = await session.post(base + '/v1/trade/orders/breakout-buy', json=invalid)
                assert response.status == 422
            assert calls == []
            response = await session.post(base + '/v1/trade/orders/breakout-buy', json=payload, headers={'Origin': 'https://example.com'})
            assert response.status == 403 and calls == []
            response = await session.post(base + '/v1/trade/orders/breakout-buy', json=payload)
            assert response.status == 504 and (await response.json())['result'] == 'unknown'
            assert [r.method for r in calls] == ['GET', 'POST']
            service.mode = 'monitor'
            response = await session.delete(base + '/v1/trade/orders/1')
            assert response.status == 409 and len(calls) == 2
    finally:
        await runner.cleanup()
        await value.close()


def test_trade_mode_scope_and_sold_today_do_not_duplicate_holding_role(app_data):
    async def scenario():
        ws = Workspace(root=app_data / 'days')
        value = runtime()
        trade = SchwabTrade(value)
        app = Workbench(ws, app_data, app_data / 'daily.sqlite3', lambda allowed: FakeBroker(allowed, app.calendar), trade_factory=lambda: trade)
        try:
            app.start_monitor()
            value.state.positions = [position()]
            value.state.orders = [order(), order('3', symbol='SOLD')]
            await app.switch_mode('trade')
            rows = app.list_state()['trade']['rows']
            assert len([r for r in rows if r['symbol'] == 'XYZ.US']) == 1
            assert app.monitor.intraday.holdings == {'XYZ.US'}
            assert 'SOLD.US' not in app.monitor.intraday.focus | app.monitor.intraday.holdings
            assert {'XYZ.US', 'SOLD.US'} <= set(app.monitor.symbols)
            assert app.list_state()['holdings'] is None
            assert app.view('XYZ.US', '5m')['app_mode'] == 'trade'
            await app.switch_mode('scan')
            assert app.monitor.intraday.holdings == {'XYZ.US'}
            await app.switch_mode('monitor')
            assert app.list_state()['trade'] is None
        finally:
            await app.close()
            await value.close()
    asyncio.run(scenario())

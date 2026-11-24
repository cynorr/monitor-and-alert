"""Financial request sequencing only: dummy credentials/transport, no live writes."""
import json
from datetime import datetime, timezone

import httpx
import pytest

from data_service import schwab_backend as broker
from data_service.schwab import SchwabService, PositionStopRequest
from pydantic import ValidationError
from test_schwab_backend import Broker, MemoryStore, credentials, raw_order


class StrategyBroker(Broker):
    def __init__(self, stops):
        super().__init__()
        self.order_list = stops
        self.account['securitiesAccount']['positions'][0]['longQuantity'] = 100
        self.reject_replace = False
        self.unknown_replace = False
        self.pending_cancel = False

    async def __call__(self, request):
        if request.method == 'PUT' and self.reject_replace:
            self.requests.append(request)
            return httpx.Response(400, json={'message': 'Replacement unsupported'})
        if request.method == 'PUT' and self.unknown_replace:
            self.requests.append(request)
            raise httpx.ReadTimeout('uncertain', request=request)
        result = await super().__call__(request)
        if request.method == 'DELETE':
            oid = request.url.path.rsplit('/', 1)[1]
            for stop in self.order_list:
                if str(stop['orderId']) == oid:
                    stop['status'] = 'PENDING_CANCEL' if self.pending_cancel else 'CANCELED'
        if request.method == 'GET' and '/orders/' in request.url.path:
            oid = request.url.path.rsplit('/', 1)[1]
            return httpx.Response(200, json=next(o for o in self.order_list if str(o['orderId']) == oid))
        return result


@pytest.fixture
async def strategy():
    server = StrategyBroker([raw_order(quantity=100, orderLegCollection=raw_order()['orderLegCollection'])])
    http = httpx.AsyncClient(transport=httpx.MockTransport(server))
    runtime = broker.Runtime(http=http, store=MemoryStore(credentials()))
    await runtime.rest.initialize_account()
    trade = SchwabService(runtime)
    # Static reference values test payload construction, not market-data computation.
    now = int(datetime(2026, 11, 17, 15, tzinfo=timezone.utc).timestamp())
    trade.reference = lambda symbol: {'high': 100, 'atr20': 5, 'ema10': 94, 'ema20': 95,
                                     'server_time': now, 'session_close': now + 21600,
                                     'release_at': now + 19800}
    yield trade, server
    await runtime.close()


def payloads(server):
    return [(r.method, json.loads(r.content) if r.content else None) for r in server.writes()]


@pytest.mark.asyncio
@pytest.mark.parametrize('reserved,expected', [(50, ['POST']), (100, ['DELETE', 'POST'])])
async def test_market_sell_only_cancels_when_uncovered_shares_are_insufficient(strategy, reserved, expected):
    trade, server = strategy
    server.order_list[0]['quantity'] = reserved
    result = await trade.action('market-sell', {'symbol': 'NVDA', 'qty': 30})
    writes = payloads(server)
    assert result['result'] == 'accepted'
    assert [method for method, _ in writes] == expected
    assert writes[-1][1]['orderLegCollection'][0]['quantity'] == 30
    assert writes[-1][1]['orderType'] == 'MARKET'


@pytest.mark.asyncio
async def test_active_entry_child_does_not_reserve_current_holding(strategy):
    trade, server = strategy
    child = raw_order(124, status='AWAITING_PARENT_ORDER')
    parent = raw_order(123, orderStrategyType='TRIGGER', childOrderStrategies=[child])
    parent['orderLegCollection'][0]['instruction'] = 'BUY'
    server.order_list = [parent]
    await trade.action('market-sell', {'symbol': 'NVDA', 'qty': 30})
    assert [m for m, _ in payloads(server)] == ['POST']


@pytest.mark.asyncio
@pytest.mark.parametrize('count,expected', [(0, ['POST']), (1, ['PUT']), (2, ['DELETE', 'DELETE', 'POST'])])
async def test_atr_uses_full_holding_and_one_gtc_stop(strategy, count, expected):
    trade, server = strategy
    server.order_list = [raw_order(123 + i) for i in range(count)]
    await trade.action('atr-stop', {'symbol': 'NVDA'})
    writes = payloads(server)
    assert [m for m, _ in writes] == expected
    order = writes[-1][1]
    assert order['stopPrice'] == '94.50'
    assert order['orderLegCollection'][0]['quantity'] == 100
    assert order['duration'] == 'GOOD_TILL_CANCEL' and 'releaseTime' not in order


@pytest.mark.asyncio
async def test_invalid_stop_stops_before_any_cancellation(strategy):
    trade, server = strategy
    with pytest.raises(broker.BackendError, match='RISK_LIMIT_EXCEEDED'):
        await trade.action('ema-stop', {'symbol': 'NVDA', 'ema': 20, 'price': '100'})
    assert server.writes() == []


@pytest.mark.asyncio
@pytest.mark.parametrize('reject,expected', [(False, ['PUT']), (True, ['PUT', 'DELETE', 'POST'])])
async def test_ema_day_release_replaces_stop_with_explicit_rejection_fallback(strategy, reject, expected):
    trade, server = strategy
    server.reject_replace = reject
    await trade.action('ema-stop', {'symbol': 'NVDA', 'ema': 20})
    writes = payloads(server)
    assert [m for m, _ in writes] == expected
    order = writes[-1][1]
    assert order['stopPrice'] == '95.00' and order['duration'] == 'DAY'
    assert order['session'] == 'NORMAL' and order['releaseTime'] == '2026-11-17T20:30:00Z'
    assert order['orderLegCollection'][0]['quantity'] == 100


@pytest.mark.asyncio
async def test_ema_unknown_replace_never_cancels_or_reposts(strategy):
    trade, server = strategy
    server.unknown_replace = True
    with pytest.raises(broker.BackendError, match='ORDER_RESULT_UNKNOWN'):
        await trade.action('ema-stop', {'symbol': 'NVDA', 'ema': 10})
    assert [m for m, _ in payloads(server)] == ['PUT']


@pytest.mark.asyncio
async def test_edit_delayed_stop_quantity_preserves_day_and_release_time(strategy):
    trade, server = strategy
    server.order_list[0].update(duration='DAY', releaseTime='2026-11-17T20:30:00Z',
                                status='AWAITING_RELEASE_TIME', editable=False)
    await trade.action('stop', {'new_stop': '92.00', 'qty': 70}, '123')
    writes = payloads(server)
    assert len(writes) == 1 and writes[0][0] == 'PUT'
    order = writes[0][1]
    assert order['orderLegCollection'][0]['quantity'] == 70
    assert order['duration'] == 'DAY' and order['releaseTime'] == '2026-11-17T20:30:00Z'
    assert broker.map_order(server.order_list[0])['release_time'] == order['releaseTime']


@pytest.mark.asyncio
async def test_manual_atr_price_is_not_replaced_with_formula(strategy):
    trade, server = strategy
    await trade.action('atr-stop', {'symbol': 'NVDA', 'price': '93.12'})
    assert payloads(server)[0][1]['stopPrice'] == '93.12'


@pytest.mark.asyncio
async def test_ema_after_activation_is_immediate_day_and_after_close_has_no_writes(strategy):
    trade, server = strategy
    ref = trade.reference('NVDA.US')
    trade.reference = lambda symbol: {**ref, 'server_time': ref['release_at'] + 1}
    await trade.action('ema-stop', {'symbol': 'NVDA', 'ema': 10})
    assert 'releaseTime' not in payloads(server)[-1][1]
    server.requests.clear()
    trade.reference = lambda symbol: {**ref, 'server_time': ref['session_close']}
    with pytest.raises(broker.BackendError, match='ORDER_CONFLICT'):
        await trade.action('ema-stop', {'symbol': 'NVDA', 'ema': 10})
    assert server.writes() == []


@pytest.mark.asyncio
async def test_failed_market_after_cancel_reports_partial_progress(strategy):
    trade, server = strategy
    original = trade.runtime.trading.sell_market
    async def rejected(*args):
        raise broker.BackendError(502, 'SCHWAB_REJECTED', 'Rejected')
    trade.runtime.trading.sell_market = rejected
    try:
        with pytest.raises(broker.BackendError) as error:
            await trade.action('market-sell', {'symbol': 'NVDA', 'qty': 30})
        assert error.value.details['cancel_requested'] == ['123']
        assert 'follow-up order not accepted' in error.value.message
        assert [m for m, _ in payloads(server)] == ['DELETE']
    finally:
        trade.runtime.trading.sell_market = original


@pytest.mark.asyncio
async def test_market_waits_for_canceled_readback_before_selling(strategy):
    trade, server = strategy
    server.pending_cancel = True
    original = server.__call__
    reads = []
    async def transport(request):
        if request.method == 'GET' and '/orders/' in request.url.path:
            reads.append(request)
            assert all(r.method != 'POST' for r in server.writes())
            if len(reads) == 2:
                server.order_list[0]['status'] = 'CANCELED'
        return await original(request)
    trade.runtime.http._transport = httpx.MockTransport(transport)
    await trade.action('market-sell', {'symbol': 'NVDA', 'qty': 30})
    assert len(reads) == 2
    assert [m for m, _ in payloads(server)] == ['DELETE', 'POST']


@pytest.mark.asyncio
async def test_entry_and_duplicate_stop_projection_do_not_duplicate_cancels(strategy):
    trade, server = strategy
    stop = raw_order(124)
    parent = raw_order(123, status='FILLED', childOrderStrategies=[stop])
    parent['orderLegCollection'][0]['instruction'] = 'BUY'
    server.order_list = [parent, stop]
    await trade.action('market-sell', {'symbol': 'NVDA', 'qty': 100})
    assert [m for m, _ in payloads(server)] == ['DELETE', 'POST']


@pytest.mark.asyncio
async def test_stop_quantity_cannot_exceed_holding_or_other_reserved_stops(strategy):
    trade, server = strategy
    server.order_list = [raw_order(123), raw_order(124, quantity=80)]
    with pytest.raises(broker.BackendError, match='ORDER_CONFLICT'):
        await trade.action('stop', {'new_stop': '92.00', 'qty': 30}, '123')
    assert server.writes() == []


@pytest.mark.parametrize('qty', [0, -1, True, '10', 10.5])
def test_new_stop_quantity_keeps_strict_whole_share_contract(qty):
    with pytest.raises(ValidationError):
        broker.ReplaceRequest.model_validate({'new_stop': '92', 'qty': qty})


def test_strategy_request_does_not_accept_max_or_client_full_position_quantity():
    for payload in ({'symbol': 'NVDA', 'ema': 'Max'}, {'symbol': 'NVDA', 'qty': 10}):
        with pytest.raises(ValidationError):
            PositionStopRequest.model_validate(payload)

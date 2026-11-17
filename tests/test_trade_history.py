"""FIFO arithmetic and read-only protocol contracts; never send broker writes."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import httpx

from data_service.trade import SchwabTrade
from data_service.trade_history import Fill, analyze, display_fills, holding_days, transaction_fills
from test_trade import runtime


TODAY = date(2026, 11, 18)


def fill(oid, side, qty, price, ago=0, hour=15):
    at = datetime(2026, 11, 18, hour, tzinfo=timezone.utc) - timedelta(days=ago)
    return Fill(str(oid), 'XYZ', side, at, Decimal(qty), Decimal(qty) * Decimal(price))


def tx(oid=1, **changes):
    return {'orderId': oid, 'activityId': 1, 'type': 'TRADE', 'status': 'VALID',
            'tradeDate': '2026-11-17T15:00:00Z', 'transferItems': [
                {'instrument': {'assetType': 'EQUITY', 'symbol': 'XYZ'},
                 'amount': '100', 'price': '10', 'cost': '-1000', 'positionEffect': 'OPENING'}], **changes}


def test_fifo_days_advance_when_oldest_remaining_batch_is_sold():
    fills = [fill(1, 'BUY', 100, 10, 10), fill(2, 'BUY', 200, 12, 3), fill(3, 'SELL', 100, 15)]
    data = analyze(fills, Decimal(200), TODAY, True)
    assert data['holding_days'] == 3
    assert Decimal(data['sold_percent']) == Decimal(100) / 300 * 100
    assert data['trades'][-1]['pnl'] == '500'
    assert data['trades'][-1]['pnl_percent'] == '50.0'


def test_addition_marks_new_without_resetting_oldest_days_and_dilutes_whole_round_sold():
    fills = [fill(1, 'BUY', 100, 10, 10), fill(2, 'SELL', 30, 15, 1), fill(3, 'BUY', 200, 12)]
    data = analyze(fills, Decimal(270), TODAY, True)
    assert data['holding_days'] == 10 and data['is_new']
    assert Decimal(data['sold_percent']) == 10


def test_window_truncated_old_sale_cannot_contaminate_latest_round():
    fills = [fill(1, 'SELL', 100, 10, 300), fill(2, 'BUY', 200, 12, 60), fill(3, 'SELL', 60, 15)]
    data = analyze(fills, Decimal(140), TODAY, True)
    assert data['holding_days'] == 60
    assert Decimal(data['sold_percent']) == 30
    assert [t['order_id'] for t in data['trades']] == ['2', '3']


def test_same_day_flat_then_reentry_resets_sold_but_keeps_closed_round_details():
    fills = [fill(1, 'BUY', 100, 10, 10), fill(2, 'SELL', 100, 15, hour=15),
             fill(3, 'BUY', 200, 12, hour=18)]
    data = analyze(fills, Decimal(200), TODAY, True)
    assert data['holding_days'] == 0 and data['sold_percent'] == '0' and data['is_new']
    assert [t['order_id'] for t in data['trades']] == ['1', '2', '3']
    assert data['trades'][1]['pnl'] == '500'


def test_pure_closed_today_freezes_days_and_reports_full_sold_without_position_cost():
    fills = [fill(1, 'BUY', 100, 10, 10), fill(2, 'SELL', 100, 15)]
    data = analyze(fills, Decimal(0), TODAY, True)
    assert data['holding_days'] == 10 and data['sold_percent'] == '100'
    assert data['trades'][-1]['pnl'] == '500'


def test_unknown_opening_lot_can_be_consumed_leaving_known_days_but_unknown_round_sold():
    fills = [fill(1, 'BUY', 50, 12, 3), fill(2, 'SELL', 100, 15)]
    data = analyze(fills, Decimal(50), TODAY, True)
    assert data['holding_days'] == 3 and not data['days_over_year']
    assert data['sold_percent'] is None and data['trades'][-1]['pnl'] is None


def test_old_unknown_remaining_lot_only_claims_over_year_after_successful_history_read():
    fills = [fill(1, 'BUY', 50, 12, 3)]
    for ready in [False, True]:
        data = analyze(fills, Decimal(150), TODAY, ready)
        assert data['holding_days'] is None and data['days_over_year'] == ready
        assert data['sold_percent'] is None


def test_negative_reverse_balance_is_not_reset_or_hidden_by_a_guessed_cycle():
    data = analyze([fill(1, 'BUY', 200, 12)], Decimal(100), TODAY, True)
    assert data['holding_days'] is None and data['sold_percent'] is None
    assert data['trades'] == [] and data['is_new']


def test_counting_retains_weekdays_first_week_then_calendar_days_and_ny_dates():
    friday = date(2026, 11, 6)
    assert holding_days(friday, date(2026, 11, 9)) == 1
    assert holding_days(friday, date(2026, 11, 13)) == 5
    assert holding_days(friday, date(2026, 11, 14)) == 8
    at = datetime(2026, 11, 18, 1, tzinfo=timezone.utc)
    assert not analyze([Fill('1', 'XYZ', 'BUY', at, Decimal(1), Decimal(10))], Decimal(1), TODAY, True)['is_new']


def test_transaction_scope_discards_no_order_id_options_short_and_invalid_records():
    option = {'instrument': {'assetType': 'OPTION', 'symbol': 'XYZ-CALL'}, 'amount': '1', 'price': '2', 'positionEffect': 'OPENING'}
    short = {'instrument': {'assetType': 'EQUITY', 'symbol': 'XYZ'}, 'amount': '-100', 'price': '10', 'positionEffect': 'OPENING'}
    rows = [tx(), tx(), tx(None), tx(2, status='PENDING'), tx(3, transferItems=[option]), tx(4, transferItems=[short])]
    result = transaction_fills(rows)
    assert len(result) == 1 and result[0].quantity == 100 and result[0].amount == 1000


def test_day_boundary_gives_orders_today_and_transactions_exclusive_ownership_tomorrow():
    orders = [{'order_id': '1', 'parent_order_id': None, 'symbol': 'XYZ', 'asset_type': 'EQUITY',
               'status': 'FILLED', 'instruction': 'BUY', 'child_orders': [],
               'executions': [{'time': '2026-11-18T15:00:00Z', 'quantity': '100', 'price': '12'}]}]
    history = [fill(1, 'BUY', 100, 11)]
    assert display_fills(history, orders, TODAY)[0].amount == 1200
    assert display_fills(history, orders, TODAY + timedelta(days=1))[0].amount == 1100
    assert len(display_fills(history, orders, TODAY)) == 1


@pytest.mark.asyncio
async def test_history_uses_existing_authenticated_get_and_does_not_poison_trading_health():
    calls = []
    fail = False
    def transport(request):
        calls.append(request)
        return httpx.Response(503 if fail else 200, json=[] if fail else [tx()])
    value = runtime(transport)
    trade = SchwabTrade(value)
    changed = []
    now = datetime(2026, 11, 18, 18, tzinfo=timezone.utc)
    await trade.refresh_history(now, lambda: changed.append(True))
    assert trade.history_ready and len(trade.history) == 1 and changed == [True]
    assert calls[0].method == 'GET' and calls[0].url.path.endswith('/transactions')
    assert calls[0].url.params['types'] == 'TRADE'
    assert calls[0].url.params['endDate'] == '2026-11-18T18:00:00.000Z'
    fail = True
    await trade.refresh_history(now, lambda: changed.append(True))
    assert len(trade.history) == 1 and changed == [True]
    assert value.rest.status == 'connected' and not value.rest.failures
    await value.close()

"""Schwab-only account projection and integration; no local execution ledger."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import logging

from .calendar import ET
from . import schwab_backend as broker

ACTIVE = {'WORKING', 'AWAITING_STOP_CONDITION', 'AWAITING_PARENT_ORDER',
          'PENDING_ACTIVATION', 'QUEUED', 'PENDING_REPLACE', 'PENDING_CANCEL',
          'PARTIALLY_FILLED', 'ACCEPTED', 'PENDING_ACKNOWLEDGEMENT'}


def symbol_key(symbol):
    return symbol if symbol.endswith('.US') else symbol + '.US'


def portfolio(positions, orders, day):
    """Preserve the original trader's FILLED / last-execution-day sale scope."""
    rows = {}
    def row(symbol):
        return rows.setdefault(symbol, {'symbol': symbol_key(symbol), 'ticker': symbol,
                                       'position': None, 'orders': [], 'sold_today': None})
    for position in positions:
        if (broker.decimal_value(position['quantity']) or 0) > 0:
            row(position['symbol'])['position'] = position
    seen = set()
    for order in broker.flatten_orders(orders):
        oid, symbol = order['order_id'], order['symbol']
        if not symbol or (oid is not None and oid in seen):
            continue
        if oid is not None:
            seen.add(oid)
        if order.get('asset_type') not in (None, 'EQUITY'):
            continue
        if order['status'] in ACTIVE:
            row(symbol)['orders'].append(order)
        fills = order['executions']
        if oid is None or order['instruction'] != 'SELL' or order['status'] != 'FILLED' or not fills:
            continue
        last = max(datetime.fromisoformat(f['time'].replace('Z', '+00:00')) for f in fills)
        quantity = broker.positive(order['filled_quantity'])
        if last.astimezone(ET).date().isoformat() != day or quantity is None:
            continue
        item = row(symbol)
        sold = item['sold_today'] or {'quantity': Decimal(0), 'amount': Decimal(0), 'executions': []}
        sold['quantity'] += quantity
        sold['amount'] += sum(Decimal(f['quantity']) * Decimal(f['price']) for f in fills)
        sold['executions'].extend({**f, 'order_id': oid} for f in fills)
        item['sold_today'] = sold
    result = []
    for item in rows.values():
        item['kind'] = 'holding' if item['position'] else 'entry' if any(
            o['instruction'] == 'BUY' for o in item['orders']) else 'sold' if item['sold_today'] else 'order'
        sold = item['sold_today']
        if sold:
            sold['average_price'] = broker.decimal_text(sold['amount'] / sold['quantity'])
            sold['quantity'], sold['amount'] = broker.decimal_text(sold['quantity']), broker.decimal_text(sold['amount'])
        result.append(item)
    return sorted(result, key=lambda r: ({'entry': 0, 'holding': 1, 'order': 2, 'sold': 3}[r['kind']], r['ticker']))


class SchwabTrade:
    def __init__(self, runtime=None):
        # Root INFO logging must not print account hashes in HTTP request URLs.
        for name in ('httpx', 'aiohttp.access'):
            logging.getLogger(name).setLevel(logging.WARNING)
        self.runtime = runtime or broker.Runtime()

    def rows(self, now):
        day = datetime.fromtimestamp(now, ET).date().isoformat()
        return portfolio(self.runtime.state.positions, self.runtime.state.orders, day)

    def symbols(self, now):
        return [r['symbol'] for r in self.rows(now)]

    def held_symbols(self):
        return {symbol_key(p['symbol']) for p in self.runtime.state.positions
                if (broker.decimal_value(p['quantity']) or 0) > 0}

    def subscribe(self, symbols):
        wanted = {s.removesuffix('.US') for s in symbols}
        added = wanted - self.runtime.state.subscribed_symbols
        self.runtime.state.subscribed_symbols.update(wanted)
        if added and self.runtime.stream.logged_in:
            self.runtime.background(self.runtime.stream.subscribe_symbols())

    def quote(self, symbol):
        ticker = symbol.removesuffix('.US')
        fallback = self.runtime.state.quotes.get(ticker, {})
        stream = self.runtime.state.stream_quotes.get(ticker, {}) if self.runtime.state.stream_status == 'connected' else {}
        return {'symbol': symbol, 'bid': stream.get('bid', fallback.get('bid')),
                'ask': stream.get('ask', fallback.get('ask')),
                'updated_at': stream.get('updated_at', fallback.get('updated_at'))}

    def state(self, now, quotes):
        rows = self.rows(now)
        for item in rows:
            quote = quotes.get(item['symbol'], {})
            regular, latest = quote.get('regular'), quote.get('latest')
            previous = broker.positive(regular.get('prev_close')) if regular else None
            price = broker.positive(regular.get('last_price')) if regular else None
            item['change_percent'] = broker.decimal_text((price / previous - 1) * 100) if price and previous else None
            ext = broker.positive(latest.get('last_price')) if latest else None
            item['extended_percent'] = broker.decimal_text((ext / price - 1) * 100) if (
                ext and price and latest['trade_session'] != 'Intraday' and latest['timestamp'] > regular['timestamp']) else None
        return {'account': self.runtime.state.account, 'rows': rows, 'orders': self.runtime.state.orders,
                'account_updated_at': self.runtime.state.account_updated_at,
                'orders_updated_at': self.runtime.state.orders_updated_at,
                'health': self.runtime.health(),
                'limits': {'buy_amount': str(broker.MAX_ORDER_AMOUNT_USD),
                           'loss': str(broker.MAX_LOSS_PER_TRADE_USD), 'stop_ratio': str(broker.MAX_STOP_LOSS_RATIO)}}

    async def run(self, changed):
        await self.runtime.start()
        async for event in self.runtime.events.listen(self.runtime.snapshot()):
            if event.startswith('event: snapshot_updated'):
                changed()

    async def action(self, operation, payload, order_id=None):
        gateway = self.runtime.trading
        if operation in ('market-buy', 'market-sell', 'breakout-buy'):
            model = broker.BreakoutRequest if operation == 'breakout-buy' else broker.MarketRequest
            data = model.model_validate(payload)
            if operation == 'breakout-buy':
                return await gateway.buy_breakout(data.symbol, data.qty, data.buy_stop, data.sell_stop)
            return await (gateway.buy_market if operation == 'market-buy' else gateway.sell_market)(data.symbol, data.qty)
        if operation == 'stop':
            data = broker.ReplaceRequest.model_validate(payload)
            return await gateway.replace_stop(order_id, data.new_stop)
        return await gateway.cancel_order(order_id)

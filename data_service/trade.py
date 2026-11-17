"""Schwab-only account projection and integration; no local execution ledger."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Annotated, Literal

from pydantic import Field, field_validator

from .calendar import ET
from . import schwab_backend as broker
from .trade_history import transaction_fills, display_fills, analyze

ACTIVE = {'WORKING', 'AWAITING_STOP_CONDITION', 'AWAITING_PARENT_ORDER',
          'AWAITING_RELEASE_TIME',
          'PENDING_ACTIVATION', 'QUEUED', 'PENDING_REPLACE', 'PENDING_CANCEL',
          'PARTIALLY_FILLED', 'ACCEPTED', 'PENDING_ACKNOWLEDGEMENT'}


class PositionStopRequest(broker.StrictRequest):
    symbol: str
    price: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)] | None = None
    ema: Literal[10, 20] = 10

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, value):
        return broker.symbol_value(value)

    @field_validator('price', mode='before')
    @classmethod
    def decimal_input(cls, value):
        return None if value is None else broker.BreakoutRequest.decimal_input(value)


def position_stops(orders, symbol):
    """Current-position Stops, excluding protective children of unfilled entries."""
    flat = list({o['order_id']: o for o in broker.flatten_orders(orders) if o['order_id']}.values())
    entries = {o['order_id'] for o in flat if o['instruction'] == 'BUY' and o['status'] in ACTIVE}
    return [o for o in flat if o['symbol'] == symbol and o['instruction'] == 'SELL'
            and o['order_type'] == 'STOP' and o['strategy_type'] == 'SINGLE'
            and o.get('session') == 'NORMAL' and o['status'] in ACTIVE
            and o['status'] != 'AWAITING_PARENT_ORDER' and o['parent_order_id'] not in entries]


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
        self.reference = None  # Bound to Workbench's existing Longbridge chart cache.
        self.history = []
        self.history_ready = False
        self.history_updated_at = None
        self.history_attempt_day = None
        self.history_task = None

    def rows(self, now):
        day = datetime.fromtimestamp(now, ET).date()
        fills = display_fills(self.history, self.runtime.state.orders, day)
        rows = portfolio(self.runtime.state.positions, self.runtime.state.orders, day.isoformat())
        for row in rows:
            selected = [f for f in fills if f.symbol == row['ticker']]
            qty = Decimal(row['position']['quantity']) if row['position'] else Decimal(0)
            row.update(analyze(selected, qty, day, self.history_ready))
        return rows

    def symbols(self, now):
        return [row['symbol'] for row in portfolio(self.runtime.state.positions, self.runtime.state.orders,
                                                  datetime.fromtimestamp(now, ET).date().isoformat())]

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
                'history_updated_at': self.history_updated_at,
                'account_updated_at': self.runtime.state.account_updated_at,
                'orders_updated_at': self.runtime.state.orders_updated_at,
                'health': self.runtime.health(),
                'limits': {'buy_amount': str(broker.MAX_ORDER_AMOUNT_USD),
                           'loss': str(broker.MAX_LOSS_PER_TRADE_USD), 'stop_ratio': str(broker.MAX_STOP_LOSS_RATIO)}}

    async def run(self, changed):
        await self.runtime.start()
        async for event in self.runtime.events.listen(self.runtime.snapshot()):
            now = datetime.now(timezone.utc)
            day = now.astimezone(ET).date()
            if (self.runtime.rest.account_hash and self.runtime.state.orders_updated_at
                    and self.history_attempt_day != day
                    and (self.history_task is None or self.history_task.done())):
                self.history_attempt_day = day
                self.history_task = self.runtime.background(self.refresh_history(now, changed))
            if event.startswith('event: snapshot_updated'):
                changed()

    async def refresh_history(self, now, changed):
        try:
            raw = await self.runtime.rest.transactions(now - timedelta(days=365), now)
            if len(raw) >= 3000:
                raise broker.conflict('Transaction history reached the response limit')
            history = transaction_fills(raw)
        except (broker.BackendError, KeyError, TypeError, ValueError) as error:
            logging.getLogger(__name__).warning('Schwab history read failed: %s', type(error).__name__)
            return
        finally:
            # This optional display read must not poison the trading REST health.
            if self.runtime.rest.account_hash:
                self.runtime.rest.failures.discard(self.runtime.rest.account_path('/transactions'))
        self.history, self.history_ready = history, True
        self.history_updated_at = now.isoformat().replace('+00:00', 'Z')
        changed()

    def held(self, symbol):
        return sum((Decimal(p['quantity']) for p in self.runtime.state.positions
                    if p['symbol'] == symbol), Decimal(0))

    async def account_orders(self, symbol):
        await self.runtime.refresh_both()
        held = self.held(symbol)
        if held <= 0:
            raise broker.conflict('A positive holding is required')
        return held, position_stops(self.runtime.state.orders, symbol)

    async def validate_stop(self, symbol, price):
        quote = await self.runtime.trading.trade_quote(symbol)
        bid = self.runtime.trading.require_price(quote, 'bidPrice')
        if price is None or price <= 0 or price >= bid:
            raise broker.BackendError(422, 'RISK_LIMIT_EXCEEDED', 'Stop must be positive and below Bid')

    async def cancel_stops(self, stops, completed):
        for stop in stops:
            if not stop['order_id'] or not stop['cancelable']:
                raise broker.conflict('Stop cannot be canceled; check current orders')
        for stop in stops:
            await self.runtime.trading.cancel_order(stop['order_id'])
            completed.append(stop['order_id'])
        # DELETE acceptance alone does not release reserved shares.
        pending = set(completed)
        deadline = asyncio.get_running_loop().time() + 5
        while pending:
            for oid in tuple(pending):
                raw = await self.runtime.rest.order(oid)
                if raw.get('status') == 'CANCELED':
                    pending.remove(oid)
                elif raw.get('status') != 'PENDING_CANCEL':
                    raise broker.conflict('Stop cancellation not confirmed; check current orders')
            if pending:
                if asyncio.get_running_loop().time() >= deadline:
                    raise broker.conflict('Stop cancellation pending; no follow-up order sent')
                await asyncio.sleep(.25)

    async def market_sell(self, data, completed):
        held, stops = await self.account_orders(data.symbol)
        if data.qty > held:
            raise broker.BackendError(422, 'RISK_LIMIT_EXCEEDED', 'Sell quantity exceeds holding')
        reserved = sum((Decimal(o['quantity']) for o in stops), Decimal(0))
        if max(0, held - reserved) < data.qty:
            await self.cancel_stops(stops, completed)
        return await self.runtime.trading.sell_market(data.symbol, data.qty)

    async def position_stop(self, operation, data, completed):
        held, stops = await self.account_orders(data.symbol)
        if held != held.to_integral_value():
            raise broker.conflict('Full-position Stop requires whole shares')
        held = int(held)
        ref = self.reference(symbol_key(data.symbol)) if self.reference else {}
        duration, release_time = 'GOOD_TILL_CANCEL', None
        if operation == 'ema-stop':
            now, closed = ref.get('server_time'), ref.get('session_close')
            if now is None or closed is None or now >= closed:
                raise broker.conflict('Today\'s EMA order is unavailable after the session closes')
            duration = 'DAY'
            if ref['release_at'] > now:
                release_time = datetime.fromtimestamp(ref['release_at'], timezone.utc).isoformat().replace('+00:00', 'Z')
            automatic = broker.positive(ref.get(f'ema{data.ema}'))
        else:
            high, atr = broker.positive(ref.get('high')), broker.positive(ref.get('atr20'))
            automatic = high - Decimal('1.1') * atr if high is not None and atr is not None else None
        price = data.price if data.price is not None else automatic
        price = price.quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if price is not None else None
        await self.validate_stop(data.symbol, price)  # Before touching any existing protection.
        gateway = self.runtime.trading
        if len(stops) == 1:
            try:
                return await gateway.replace_stop(stops[0]['order_id'], price, held,
                                                  duration=duration, release_time=release_time)
            except broker.BackendError as error:
                # Only explicit inability to replace permits EMA's cancel/create path.
                if operation != 'ema-stop' or error.code not in {'ORDER_CONFLICT', 'SCHWAB_REJECTED'}:
                    raise
        if stops:
            await self.cancel_stops(stops, completed)
            await self.runtime.refresh('account')
            held = self.held(data.symbol)
            if held <= 0 or held != held.to_integral_value():
                raise broker.conflict('Holding changed; no new Stop sent')
        return await gateway.place_stop(data.symbol, int(held), price, duration=duration, release_time=release_time)

    async def action(self, operation, payload, order_id=None):
        completed = []
        # One explicit financial workflow at a time, including its intermediate writes.
        async with self.runtime.trading.operation(('trade',)):
            try:
                return await self._action(operation, payload, order_id, completed)
            except broker.BackendError as error:
                if completed:
                    error.details = {**(error.details or {}), 'cancel_requested': completed}
                    error.message = ('Stop cancellation requested; follow-up result unknown. Check Schwab.'
                                     if error.code == 'ORDER_RESULT_UNKNOWN' else
                                     'Stop cancellation requested; follow-up order not accepted. Check Schwab.')
                raise

    async def _action(self, operation, payload, order_id, completed):
        gateway = self.runtime.trading
        if operation in ('atr-stop', 'ema-stop'):
            return await self.position_stop(operation, PositionStopRequest.model_validate(payload), completed)
        if operation in ('market-buy', 'market-sell', 'breakout-buy'):
            model = broker.BreakoutRequest if operation == 'breakout-buy' else broker.MarketRequest
            data = model.model_validate(payload)
            if operation == 'breakout-buy':
                return await gateway.buy_breakout(data.symbol, data.qty, data.buy_stop, data.sell_stop)
            return await self.market_sell(data, completed) if operation == 'market-sell' else await gateway.buy_market(data.symbol, data.qty)
        if operation == 'stop':
            data = broker.ReplaceRequest.model_validate(payload)
            raw = await self.runtime.rest.order(broker.order_id_value(order_id))
            order = broker.map_order(raw)
            held, stops = await self.account_orders(order['symbol'])
            qty = data.qty if data.qty is not None else broker.positive(order['quantity'])
            reserved = sum((Decimal(o['quantity']) for o in stops if o['order_id'] != order['order_id']), Decimal(0))
            if qty is None or qty > held - reserved:
                raise broker.conflict('Stop quantity exceeds unreserved holding')
            await self.validate_stop(order['symbol'], data.new_stop)
            return await gateway.replace_stop(order_id, data.new_stop, data.qty)
        return await gateway.cancel_order(order_id)

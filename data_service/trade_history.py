"""Read-only Schwab stock/ETF fills and FIFO display fields; no trading writes."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .calendar import ET
from .schwab_backend import decimal_text, flatten_orders, positive


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: str
    at: datetime
    quantity: Decimal
    amount: Decimal

    @property
    def day(self):
        return self.at.astimezone(ET).date()


def fill_time(value):
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.tzinfo is None:
        raise ValueError('Execution time requires a UTC offset')
    return at.astimezone(timezone.utc)


def aggregate(items):
    groups = {}
    for item in items:
        key = item.order_id, item.symbol, item.side
        old = groups.get(key)
        groups[key] = Fill(*key, max(old.at, item.at), old.quantity + item.quantity,
                           old.amount + item.amount) if old else item
    return sorted(groups.values(), key=lambda item: (item.at, item.order_id))


def transaction_fills(transactions):
    """Only VALID long equity buys/sells with an order ID. Ignore all option legs."""
    items, seen = [], set()
    for row in transactions:
        oid = row.get('orderId')
        if not oid or row.get('type') != 'TRADE' or row.get('status') != 'VALID':
            continue
        key = row.get('activityId')
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        at = fill_time(row.get('tradeDate') or row['time'])
        for leg in row.get('transferItems', []):
            instrument = leg.get('instrument', {})
            if instrument.get('assetType') != 'EQUITY' or not instrument.get('symbol'):
                continue
            quantity = Decimal(str(leg.get('amount') or 0))
            if not quantity.is_finite():
                continue
            effect, price = leg.get('positionEffect'), positive(leg.get('price'))
            side = ('BUY' if quantity > 0 and effect == 'OPENING' else
                    'SELL' if quantity < 0 and effect == 'CLOSING' else None)
            if side and price:
                items.append(Fill(str(oid), instrument['symbol'], side, at, abs(quantity), abs(quantity) * price))
    return aggregate(items)


def order_fills(orders):
    items, seen = [], set()
    for order in flatten_orders(orders):
        oid = order['order_id']
        if not oid or oid in seen:
            continue
        seen.add(oid)
        if (order.get('asset_type') != 'EQUITY' or order['status'] != 'FILLED'
                or order['instruction'] not in ('BUY', 'SELL') or not order['symbol']):
            continue
        for execution in order['executions']:
            qty, price = positive(execution['quantity']), positive(execution['price'])
            if qty and price:
                items.append(Fill(oid, order['symbol'], order['instruction'], fill_time(execution['time']),
                                  qty, qty * price))
    return aggregate(items)


def display_fills(history, orders, today):
    # Each NY date has one owner: Transactions for history; Orders for today.
    values = {(f.order_id, f.symbol, f.side): f for f in history if f.day < today}
    values.update(((f.order_id, f.symbol, f.side), f) for f in order_fills(orders) if f.day == today)
    return sorted(values.values(), key=lambda item: (item.at, item.order_id))


def holding_days(opened, today):
    elapsed = (today - opened).days
    return sum((opened + timedelta(days=i)).weekday() < 5 for i in range(1, elapsed + 1)) if elapsed <= 7 else elapsed


def _round(fills, held, today, history_ready):
    """Find the latest zero backwards, then FIFO only that round forwards."""
    balance, start = held, 0
    for index in range(len(fills) - 1, -1, -1):
        fill = fills[index]
        balance += fill.quantity if fill.side == 'SELL' else -fill.quantity
        if balance < 0:
            return None
        if balance == 0:
            start = index
            break
    complete = balance == 0
    lots = deque([] if complete else [[balance, None, None]])
    buys = sells = Decimal(0)
    details, last_days, last_old = [], None, False
    for fill in fills[start:]:
        price = fill.amount / fill.quantity
        pnl = percent = days = None
        if fill.side == 'BUY':
            lots.append([fill.quantity, price, fill.day])
            buys += fill.quantity
        else:
            sells += fill.quantity
            left, cost, known = fill.quantity, Decimal(0), True
            oldest = lots[0][2] if lots else None
            days = holding_days(oldest, fill.day) if oldest else None
            while left:
                if not lots:
                    return None
                lot = lots[0]
                take = min(left, lot[0])
                if lot[1] is None:
                    known = False
                else:
                    cost += take * lot[1]
                left -= take
                lot[0] -= take
                if lot[0] == 0:
                    lots.popleft()
            if known:
                pnl = fill.amount - cost
                percent = pnl / cost * 100 if cost else None
            last_days, last_old = days, oldest is None and history_ready
        details.append({'order_id': fill.order_id, 'side': fill.side,
                        'time': fill.at.isoformat().replace('+00:00', 'Z'), 'date': fill.day.isoformat(),
                        'quantity': decimal_text(fill.quantity), 'price': decimal_text(price),
                        'amount': decimal_text(fill.amount), 'pnl': decimal_text(pnl),
                        'pnl_percent': decimal_text(percent), 'holding_days': days})
    if sum((lot[0] for lot in lots), Decimal(0)) != held:
        return None
    oldest = lots[0][2] if lots else None
    return {'start': start, 'trades': details,
            'holding_days': holding_days(oldest, today) if oldest else last_days if not held else None,
            'days_over_year': (oldest is None and history_ready) if held else last_old,
            'sold_percent': decimal_text(sells / buys * 100) if complete and buys else None}


def analyze(fills, held, today, history_ready):
    result = {'holding_days': None, 'days_over_year': False, 'sold_percent': None,
              'is_new': any(f.side == 'BUY' and f.day == today for f in fills),
              'trades': []}
    if not fills:
        return result
    # Same-second opposite sides do not establish a reliable buy/sell sequence.
    sides = defaultdict(set)
    for fill in fills:
        sides[fill.at].add(fill.side)
    current = _round(fills, held, today, history_ready)
    if current is None or any(len(sides[f.at]) > 1 for f in fills[current['start']:]):
        return result
    result.update({k: v for k, v in current.items() if k != 'start'})
    # Earlier rounds closed today remain available under the same symbol.
    prefix = fills[:current['start']]
    previous = []
    while prefix and prefix[-1].side == 'SELL' and prefix[-1].day == today:
        closed = _round(prefix, Decimal(0), today, history_ready)
        if closed is None:
            break
        previous = closed['trades'] + previous
        prefix = prefix[:closed['start']]
    result['trades'] = previous + result['trades']
    return result

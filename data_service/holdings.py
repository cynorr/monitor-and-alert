"""Independent holdings accounting and cached valuation; no HTTP server or broker calls."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import time

from .config import redact
from .calendar import ET

D = Decimal


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2,
                      default=lambda number: format(number.normalize(), 'f'))


def stock_positions(raw):
    return {p['instrument']['id']: p for p in raw['positions']['results']
            if p['instrument']['kind'] in ('stock', 'etf') and D(p['units']) != 0}


def account_day(timestamp):
    return datetime.fromisoformat(timestamp.replace('Z', '+00:00')).astimezone(ET).date().isoformat()


def holding_days(opened, as_of):
    start, end = date.fromisoformat(opened), date.fromisoformat(as_of)
    elapsed = (end - start).days
    return sum((start + timedelta(days=i)).weekday() < 5 for i in range(1, elapsed + 1)) if elapsed <= 7 else elapsed


def display_positions(raw, as_of):
    """Current positions plus instruments with executions selling shares today."""
    positions = stock_positions(raw)
    for rows, symbol_key, side_key, date_key, quantity_key, price_key in (
        (raw['activities'], 'symbol', 'type', 'trade_date', 'units', 'price'),
        (raw['orders'], 'universal_symbol', 'action', 'time_executed', 'filled_quantity', 'execution_price'),
    ):
        for row in rows:
            symbol = row[symbol_key]
            if (row['option_symbol'] or not symbol or row[side_key] != 'SELL'
                    or not row[quantity_key] or D(row[quantity_key]) == 0
                    or not row[date_key] or row[date_key][:10] != as_of):
                continue
            if symbol['id'] in positions:
                continue
            kind = symbol['type']['code']
            if kind not in ('cs', 'ad', 'et') or symbol['currency']['code'] != 'USD':
                continue
            positions[symbol['id']] = {
                'instrument': {'id': symbol['id'], 'symbol': symbol['symbol'], 'kind': 'etf' if kind == 'et' else 'stock'},
                'units': '0', 'price': row[price_key], 'currency': 'USD',
            }
    return positions


def read_rules(raw, folder):
    def lines(name):
        return [words for line in (folder / name).read_text().splitlines()
                if (words := line.split('#', 1)[0].split())]

    merges, bindings = lines('merge_buys.txt'), lines('sequences.txt')
    requested = {oid for row in merges + bindings for oid in row}
    metadata = {}
    for a in raw['activities']:
        if (a['external_reference_id'] in requested and a['symbol'] and not a['option_symbol']
                and a['type'] in ('BUY', 'SELL')):
            metadata[a['external_reference_id']] = (a['symbol']['symbol'], a['type'])
    for o in raw['orders']:
        if o['brokerage_order_id'] in requested and o['universal_symbol'] and not o['option_symbol']:
            metadata[o['brokerage_order_id']] = (o['universal_symbol']['symbol'], o['action'])
    rules, owners = [], {}
    for ids in merges:
        rule = {'ticker': metadata[ids[0]][0], 'buys': ids, 'sells': []}
        rules.append(rule)
        for oid in ids:
            if oid in owners or metadata[oid] != (rule['ticker'], 'BUY'):
                raise ValueError(f'Invalid buy merge: {oid}')
            owners[oid] = rule
    for buy, *sells in bindings:
        if buy not in owners:
            rule = {'ticker': metadata[buy][0], 'buys': [buy], 'sells': []}
            rules.append(rule)
            owners[buy] = rule
        rule = owners[buy]
        if metadata[buy] != (rule['ticker'], 'BUY'):
            raise ValueError(f'First column must be BUY: {buy}')
        for oid in sells:
            if metadata[oid] != (rule['ticker'], 'SELL'):
                raise ValueError(f'Sell must belong to the same ticker: {oid}')
        rule['sells'].extend(sells)
    return rules


def trades(raw, positions):
    """Aggregate activity fills by order ID, then overlay cumulative order fills."""
    result = {}
    for a in raw['activities']:
        if a['option_symbol'] or not a['symbol'] or a['symbol']['id'] not in positions:
            continue
        if a['type'] not in ('BUY', 'SELL'):
            if D(a['units']) != 0:
                raise ValueError(f"Share-changing event requires agreement: {a['id']}")
            continue
        oid, sid = a['external_reference_id'], a['symbol']['id']
        if not oid:
            raise ValueError(f"Missing brokerage reference: {a['id']}")
        qty, price = abs(D(a['units'])), D(a['price'])
        trade = result.setdefault(oid, {
            'id': oid, 'instrument_id': sid, 'ticker': a['symbol']['symbol'],
            'side': a['type'], 'date': a['trade_date'][:10],
            'last_fill_date': a['trade_date'][:10], 'quantity': D(0),
            'value': D(0), 'activity_ids': [], 'source': 'activities',
        })
        if (trade['instrument_id'], trade['side']) != (sid, a['type']):
            raise ValueError(f'Order ID links different instruments/sides: {oid}')
        trade['date'] = min(trade['date'], a['trade_date'][:10])
        trade['last_fill_date'] = max(trade['last_fill_date'], a['trade_date'][:10])
        trade['quantity'] += qty
        trade['value'] += qty * price
        trade['activity_ids'].append(a['id'])
    for o in raw['orders']:
        symbol = o['universal_symbol']
        if o['option_symbol'] or not symbol or symbol['id'] not in positions:
            continue
        if not o['filled_quantity']:
            continue
        qty = D(o['filled_quantity'])
        if qty == 0:
            continue
        oid, sid = o['brokerage_order_id'], symbol['id']
        executed = o['time_executed'][:10]
        previous = result.get(oid)
        if previous and (previous['instrument_id'] != sid or previous['side'] != o['action']
                         or previous['quantity'] > qty):
            raise ValueError(f'Activity/order conflict: {oid}')
        result[oid] = {
            'id': oid, 'instrument_id': sid, 'ticker': symbol['symbol'],
            'side': o['action'], 'date': min(previous['date'], executed) if previous else executed,
            'last_fill_date': executed, 'quantity': qty,
            'value': qty * D(o['execution_price']),
            'activity_ids': previous['activity_ids'] if previous else [], 'source': 'orders',
        }
    return result


def current_trades(rows, held, as_of):
    """Keep the current episode and preceding episodes closed today."""
    remaining, selected = held, []
    ordered = sorted(rows, key=lambda t: (t['date'], t['side'] != 'BUY', t['id']), reverse=True)
    for index, trade in enumerate(ordered):
        if trade['side'] not in ('BUY', 'SELL'):
            raise ValueError(f"Unsupported side: {trade['side']}")
        remaining -= trade['quantity'] if trade['side'] == 'BUY' else -trade['quantity']
        selected.append(trade)
        if remaining == 0:
            if (index + 1 == len(ordered) or ordered[index + 1]['side'] != 'SELL'
                    or ordered[index + 1]['last_fill_date'] != as_of):
                return list(reversed(selected))
        if remaining < 0:
            raise ValueError(f"History/holdings quantity mismatch: {trade['ticker']}")
    raise ValueError('Buy origin is missing from history')


def sequences(rows, rules):
    """Explicit groups first; otherwise a sell must have one available buy group."""
    by_id = {t['id']: t for t in rows}
    groups, buy_owner, sell_owner = [], {}, {}
    for rule in rules:
        ids = rule['buys'] + rule['sells']
        if not set(ids) & by_id.keys():
            continue  # A declaration for an older, closed holding episode.
        group = {'buy_ids': rule['buys'], 'sell_ids': [], 'remaining': D(0)}
        groups.append(group)
        for side, owners in (('BUY', buy_owner), ('SELL', sell_owner)):
            for oid in rule['buys' if side == 'BUY' else 'sells']:
                if by_id[oid]['side'] != side or oid in owners:
                    raise ValueError(f'Duplicate or wrong-side sequence ID: {oid}')
                owners[oid] = group
    for trade in rows:
        oid = trade['id']
        if trade['side'] == 'BUY':
            if oid not in buy_owner:
                group = {'buy_ids': [oid], 'sell_ids': [], 'remaining': D(0)}
                groups.append(group)
                buy_owner[oid] = group
            buy_owner[oid]['remaining'] += trade['quantity']
        else:
            if oid in sell_owner:
                group = sell_owner[oid]
            else:
                candidates = [g for g in groups if g['remaining'] > 0]
                if len(candidates) != 1:
                    raise ValueError(f"Ambiguous sell; add to sequences.txt: {trade['ticker']} {oid}")
                group = candidates[0]
            group['remaining'] -= trade['quantity']
            if group['remaining'] < 0:
                raise ValueError(f'Sell exceeds its buy group: {oid}')
            group['sell_ids'].append(oid)
    for group in groups:
        if group['sell_ids'] and max(by_id[i]['last_fill_date'] for i in group['buy_ids']) > min(
                by_id[i]['date'] for i in group['sell_ids']):
            raise ValueError('Buying again after a sale within a merged group requires agreement')
    return groups


def performance(group, by_id, price, as_of):
    buys = [by_id[i] for i in group['buy_ids']]
    sells = [by_id[i] for i in group['sell_ids']]
    bought = sum(t['quantity'] for t in buys)
    cost = sum(t['value'] for t in buys)
    sold = sum((t['quantity'] for t in sells), D(0))
    entry = cost / bought
    realized = sum((t['value'] for t in sells), D(0)) - entry * sold
    remaining = bought - sold
    unrealized = remaining * (price - entry)
    opened = min(t['date'] for t in buys)
    closed = remaining == 0
    return {
        'buy_ids': group['buy_ids'], 'opened_on': opened,
        'holding_days': holding_days(opened, as_of), 'closed_today': closed,
        'buy_quantity': bought, 'buy_price': entry, 'buy_value': cost,
        'sold_quantity': sold, 'held_quantity': remaining,
        'sold_percent': sold / bought * 100, 'market_value': remaining * price,
        'realized_pnl': realized,
        'realized_pnl_percent': realized / (entry * sold) * 100 if sold else None,
        'unrealized_pnl': unrealized,
        'unrealized_pnl_percent': (price / entry - 1) * 100,
        'total_pnl': realized if closed else unrealized,
        'total_pnl_percent': realized / cost * 100 if closed else (price / entry - 1) * 100,
        'buys': buys,
        'sells': [{**t, 'pnl': t['value'] - entry * t['quantity'],
                   'pnl_percent': (t['value'] / t['quantity'] / entry - 1) * 100,
                   'sold_percent': t['quantity'] / bought * 100,
                   'holding_days': holding_days(opened, t['date'])}
                  for t in sells],
    }


def build(raw, rules):
    as_of = account_day(raw['fetched_at'])
    positions = display_positions(raw, as_of)
    normalized = trades(raw, positions)
    by_symbol = defaultdict(list)
    for trade in normalized.values():
        by_symbol[trade['instrument_id']].append(trade)
    holdings = []
    for sid, position in positions.items():
        ticker = position['instrument']['symbol']
        held, price = D(position['units']), D(position['price'])
        if not held.is_finite() or held < 0 or position['currency'] != 'USD':
            raise ValueError('Scope is USD long stock/ETF positions only')
        if not price.is_finite() or price <= 0:
            raise ValueError('SnapTrade fallback price must be finite and positive')
        net = sum((t['quantity'] if t['side'] == 'BUY' else -t['quantity']
                   for t in by_symbol[sid]), D(0))
        if net != held:
            raise ValueError(f'History/holdings quantity mismatch: {ticker}: {net} != {held}')
        rows = current_trades(by_symbol[sid], held, as_of)
        matching_rules = [r for r in rules if r['ticker'] == ticker]
        for rule in matching_rules:
            for oid in rule['buys'] + rule['sells']:
                if normalized[oid]['instrument_id'] != sid:
                    raise ValueError(f'Wrong ticker in sequence: {oid}')
        groups = sequences(rows, matching_rules)
        items = sorted((performance(g, normalized, price, as_of) for g in groups
                        if g['remaining'] > 0 or max(normalized[i]['last_fill_date'] for i in g['sell_ids']) == as_of),
                       key=lambda s: (s['opened_on'], s['buy_ids']))
        if sum(i['held_quantity'] for i in items) != held:
            raise ValueError(f'Sequences do not reconcile with holdings: {ticker}')
        holdings.append({'ticker': ticker, 'instrument_id': sid,
                         'kind': position['instrument']['kind'], 'quantity': held,
                         'price': price, 'market_value': held * price, 'sequences': items})
    market_value = sum((h['market_value'] for h in holdings), D(0))
    open_rows = [s for h in holdings for s in h['sequences'] if not s['closed_today']]
    total_pnl = sum((s['total_pnl'] for s in open_rows), D(0))
    remaining_cost = sum((s['held_quantity'] * s['buy_price'] for s in open_rows), D(0))
    return {
        'fetched_at': raw['fetched_at'], 'source_timestamps': raw['source_timestamps'],
        'positions_as_of': raw['positions']['data_freshness']['as_of'],
        'pnl_basis': 'execution prices, before fees and taxes; manual allocation, not tax lots',
        'funds': {
            'stock_market_value': market_value,
            'account_total': D(raw['account']['balance']['total']['amount']),
            'cash': D(raw['cash']),
        },
        'summary': {'pnl': total_pnl, 'pnl_percent': total_pnl / remaining_cost * 100 if remaining_cost else None},
        'holdings': holdings,
    }


def symbol_for(ticker):
    return ticker if ticker.endswith('.US') else ticker + '.US'


def value_positions(base, quotes, as_of=None):
    """Reprice accepted positions without repeating trade matching or changing fills."""
    holdings = []
    as_of = as_of or account_day(base['fetched_at'])
    for holding in base['holdings']:
        sequences_today = [s for s in holding['sequences'] if not s['closed_today']
                           or max(t['last_fill_date'] for t in s['sells']) == as_of]
        if not sequences_today:
            continue
        sessions = quotes.get(symbol_for(holding['ticker']), {})
        candidates = []
        for quote in sessions.values():
            price = D(str(quote['last_price']))
            if price.is_finite() and price > 0:
                candidates.append((quote['timestamp'], price, quote['trade_session']))
        latest = max(candidates, key=lambda item: item[0]) if candidates else None
        price = latest[1] if latest else holding['price']
        regular = sessions.get('Intraday', {})
        def valid_price(field):
            value = D(str(regular.get(field))) if regular.get(field) is not None else None
            return value if value is not None and value.is_finite() and value > 0 else None
        regular_price, previous_close = valid_price('last_price'), valid_price('prev_close')
        change = (regular_price / previous_close - 1) * 100 if regular_price and previous_close else None
        extended = max((item for item in candidates if item[2] != 'Intraday'
                        and item[0] > regular.get('timestamp', 0)), default=None, key=lambda item: item[0])
        ext = (extended[1] / regular_price - 1) * 100 if extended and regular_price else None
        # Pre/overnight start a new session against the last regular close.
        # Regular/post use the previous day's close, preserving the full day's move.
        reference = (regular_price if latest[2] in ('Pre', 'Overnight') else previous_close) if latest else None
        items = []
        for sequence in sequences_today:
            unrealized = sequence['held_quantity'] * (price - sequence['buy_price'])
            today_buys = [t for t in sequence['buys'] if t['date'] == as_of]
            today_quantity = sum((t['quantity'] for t in today_buys), D(0))
            old_quantity = sequence['buy_quantity'] - today_quantity
            day_reference = ((sum((t['value'] for t in today_buys), D(0)) + (reference or D(0)) * old_quantity)
                             / sequence['buy_quantity']) if not old_quantity or reference else None
            closed = sequence['closed_today']
            today_sales = [t for t in sequence['sells'] if t['last_fill_date'] == as_of]
            day_pnl = (sum((t['value'] - t['quantity'] * day_reference for t in today_sales), D(0)) if closed else
                       sequence['held_quantity'] * (price - day_reference)) if day_reference is not None and (closed or latest) else None
            total = sequence['realized_pnl'] if closed else unrealized
            items.append({**sequence, 'market_value': sequence['held_quantity'] * price,
                          'holding_days': holding_days(sequence['opened_on'], as_of),
                          'is_new': sequence['opened_on'] == as_of,
                          'unrealized_pnl': unrealized,
                          'unrealized_pnl_percent': (price / sequence['buy_price'] - 1) * 100,
                          'total_pnl': total, 'total_pnl_percent': total / sequence['buy_value'] * 100 if closed else (price / sequence['buy_price'] - 1) * 100,
                          'day_reference_price': day_reference,
                          'day_reference_source': 'entry' if not old_quantity else 'mixed' if today_quantity else 'previous_close',
                          'day_pnl': day_pnl})
        holdings.append({**holding, 'price': price, 'market_value': holding['quantity'] * price,
                         'sequences': items, 'price_source': 'longbridge' if latest else 'snaptrade',
                         'price_timestamp': latest[0] if latest else base['positions_as_of'],
                         'price_session': latest[2] if latest else None,
                         'change_percent': change, 'extended_percent': ext,
                         'day_reference_price': reference})
    market_value = sum((holding['market_value'] for holding in holdings), D(0))
    open_rows = [s for h in holdings for s in h['sequences'] if not s['closed_today']]
    total_pnl = sum((s['total_pnl'] for s in open_rows), D(0))
    remaining_cost = sum((s['held_quantity'] * s['buy_price'] for s in open_rows), D(0))
    day_values = [s['day_pnl'] for h in holdings for s in h['sequences']]
    day_pnl = sum(day_values, D(0)) if all(value is not None for value in day_values) else None
    return {**base, 'holdings': holdings,
            'funds': {**base['funds'], 'stock_market_value': market_value,
                      'account_total': market_value + base['funds']['cash']},
            'summary': {'pnl': total_pnl, 'pnl_percent': total_pnl / remaining_cost * 100 if remaining_cost else None,
                        'day_pnl': day_pnl}}


class Holdings:
    def __init__(self, client, rules: Path, *, interval=30):
        self.client, self.rules, self.interval = client, rules, interval
        self.base, self.error, self.loading = None, None, True
        # A previous accepted raw snapshot can supply fallback values at startup.
        if client.raw:
            try:
                self.base = build(client.raw, read_rules(client.raw, rules))
            except Exception as exc:
                self.error = redact(str(exc), client.secrets)

    @property
    def symbols(self):
        return self.symbols_for(datetime.now(ET).date().isoformat())

    def symbols_for(self, as_of):
        return list(dict.fromkeys(symbol_for(h['ticker']) for h in self.base['holdings']
                                  if any(not s['closed_today'] or s['sells'][-1]['last_fill_date'] == as_of
                                         for s in h['sequences']))) if self.base else []

    def state(self, quotes=None, as_of=None):
        return {'data': json.loads(dumps(value_positions(self.base, quotes or {}, as_of))) if self.base else None,
                'loading': self.loading, 'error': self.error}

    async def refresh(self):
        try:
            raw = await self.client.refresh()
            base = build(raw, read_rules(raw, self.rules))
            self.client.commit(raw)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = redact(str(exc), self.client.secrets)
            return False
        else:
            self.base, self.error = base, None
            return True
        finally:
            self.loading = False

    async def run(self, on_change):
        try:
            while True:
                started = time.monotonic()
                # The first refresh happens immediately, before the first timer wait.
                if await self.refresh():
                    on_change()
                await asyncio.sleep(max(0, self.interval - (time.monotonic() - started)))
        finally:
            await self.client.close()

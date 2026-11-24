"""Symbol state and crossing notifications in the existing backend event loop."""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime
from pathlib import Path

from ..calendar import ET
from ..indicators import adr_mdv, preview
from .volume import VolumeHistory

CONFIG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'intraday-state.json'
log = logging.getLogger(__name__)


def load_config(path=None):
    value = json.loads(Path(path or CONFIG_PATH).read_text())
    for direction in ('up', 'down'):
        low, high = (value[f'{direction}_{level}'] for level in ('notice', 'urgent'))
        if not all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in (low, high)) or not 0 < low < high:
            raise ValueError(f'Intraday State: {direction} thresholds must be positive and increasing')
    levels = value['volume_levels']
    if len(levels) != 3 or any(not isinstance(n, (int, float)) or isinstance(n, bool) or not math.isfinite(n) or n <= 0 for n in levels) or levels != sorted(set(levels)):
        raise ValueError('Intraday State: three positive increasing volume levels required')
    return value


def level(value, low, high):
    return 0 if value is None or value < low else 2 if value >= high else 1


class IntradayState:
    def __init__(self, charts, *, notify=None, clock=time.time, config_path=None):
        self.charts, self.calendar, self.now = charts, charts.calendar, clock
        self.config, self.notify = load_config(config_path), notify
        self.volume = VolumeHistory(charts)
        self.focus, self.holdings = set(), set()
        self.quotes, self.previous, self.values, self.ranks, self.baselines = {}, {}, {}, {}, {}
        self.last_tick = 0
        self.day = None

    def scope(self, focus, holdings):
        focus, holdings = set(focus), set(holdings)
        changed = (self.focus ^ focus) | (self.holdings ^ holdings)
        self.focus, self.holdings = focus, holdings
        for symbol in changed:
            for mapping in (self.quotes, self.previous, self.values, self.ranks, self.baselines, self.volume.cache):
                mapping.pop(symbol, None)

    def reset(self):
        self.quotes.clear()
        self.previous.clear()
        self.values.clear()
        self.ranks.clear()

    def recover(self):
        """Keep displayed values while the first fresh quote reestablishes crossings."""
        self.quotes.clear()
        self.previous.clear()

    def quote(self, symbol, quote):
        now = int(self.now())
        if symbol not in self.focus | self.holdings or quote['trade_session'] != 'Intraday':
            return
        day = datetime.fromtimestamp(now, ET).date()
        session = self.calendar.session(day)
        if not session or not session[0] <= now < session[1] or not session[0] <= quote['timestamp'] <= now:
            return
        previous = self.quotes.get(symbol)
        if previous and (quote['timestamp'] < previous['timestamp'] or
                         (quote['timestamp'] == previous['timestamp'] and quote.get('source') == 'snapshot')):
            return
        if self.day != day:
            self.reset()
            self.baselines.clear()
            self.day = day
        self.quotes[symbol] = quote
        self.update(symbol, now)

    def price(self, symbol, now):
        quote = self.quotes.get(symbol)
        if not quote or not all(quote.get(field) for field in ('open', 'high', 'low')):
            return None
        price = quote['last_price']
        revision, rows, base, _ = self.charts.closed(symbol, '1d')
        day = datetime.fromtimestamp(now, ET).date()
        cached = self.baselines.get(symbol)
        signature = day, revision
        if cached is None or cached[0] != signature:
            closed = [row for row in rows if datetime.fromtimestamp(row['time'], ET).date() < day][-20:]
            adr = adr_mdv({key: [row[key] for row in closed] for key in ('high', 'low', 'close', 'volume')})['adr20'] if closed else None
            self.baselines[symbol] = signature, float(adr) if adr is not None else None
        adr = self.baselines[symbol][1]
        if adr is None or adr <= 0:
            return None
        up = ((price - quote['low']) / quote['low']) / (adr / 100)
        down = ((quote['high'] - price) / quote['high']) / (adr / 100)
        holding = symbol in self.holdings
        above = price > quote['open']
        up_level = level(up, self.config['up_notice'], self.config['up_urgent']) if holding or above else 0
        down_level = level(down, self.config['down_notice'], self.config['down_urgent']) if holding else 0
        state = ('down-urgent' if down_level == 2 else 'down-notice') if down_level else (
                'up-urgent' if up_level == 2 else 'up-notice' if up_level else 'neutral')
        indicators = preview(base, self.charts.forming(symbol, '1d', now))
        distances = {name: price - indicators[name]['value'] for name in ('ema10', 'ema20') if name in indicators}
        return {'role': 'holding' if holding else 'candidate', 'state': state, 'above_open': above,
                'adr20': adr, 'up_adr': up, 'down_adr': down, 'up_level': up_level, 'down_level': down_level,
                'price': price, 'timestamp': quote['timestamp'], 'ema_distances': distances}

    def update(self, symbol, now):
        if symbol not in self.focus | self.holdings or not self.calendar.is_open(now):
            return
        value = self.price(symbol, now)
        old = self.previous.get(symbol)
        if value is not None and old is not None:
            up = value['up_level'] > old['up_level']
            down = value['down_level'] > old['down_level']
            ema = (value['role'] == 'holding' or value['above_open']) and any(
                old['ema_distances'].get(name, float('inf')) < 0 <= distance
                for name, distance in value['ema_distances'].items())
            if down and value['down_level'] == 2:
                direction, severity = 'down', 2
            elif up and value['up_level'] == 2:
                direction, severity = 'up', 2
            elif down:
                direction, severity = 'down', 1
            else:
                direction, severity = ('up' if up or ema else None), 1
            if direction:
                if self.notify:
                    self.notify(symbol, direction, severity)
                log.info('Intraday State %s %s level=%s price=%.4f up=%.2f down=%.2f', symbol, direction, severity,
                         value['price'], value['up_adr'], value['down_adr'])
        if value is not None:
            self.previous[symbol] = value
            if self.values.get(symbol, {}).get('state') is None:
                self.ranks.pop(symbol, None)
        else:
            value = self.values.get(symbol) or {
                'role': 'holding' if symbol in self.holdings else 'candidate', 'state': None,
                **dict.fromkeys(('above_open', 'adr20', 'up_adr', 'down_adr', 'up_level', 'down_level', 'price', 'timestamp'))}
        volumes = dict(zip(('cum_vol', 'local_vol'), self.volume.current(symbol, now)))
        for key, comparison in volumes.items():
            if comparison['actual'] is None and self.values.get(symbol, {}).get(key):
                volumes[key] = self.values[symbol][key]
            else:
                comparison['level'] = sum(comparison['ratio'] >= threshold for threshold in self.config['volume_levels']) if comparison['ratio'] is not None else 0
        self.values[symbol] = {key: val for key, val in value.items() if key != 'ema_distances'} | volumes
        self.rank(symbol, now)

    def rank(self, symbol, now):
        value = self.values[symbol]
        if value['role'] == 'holding':
            tier = {'down-urgent': 4, 'down-notice': 3, 'up-urgent': 2, 'up-notice': 1, 'neutral': 0, None: 0}[value['state']]
        else:
            tier = 3 if value['up_level'] == 2 else 2 if value['up_level'] else int(bool(value['above_open']))
        volume_levels = [sum(comparison['ratio'] >= threshold for threshold in self.config['volume_levels'])
                         if comparison and comparison['ratio'] is not None else 0
                         for comparison in (value['cum_vol'], value['local_vol'])]
        bucket = self.calendar.active_start('5m', now)
        previous = self.ranks.get(symbol)
        # Ordinary strength, volume ranks and demotions wait for the 5m boundary.
        if previous is None or previous[0] != bucket or (tier > previous[1][0] and value['state'] != 'neutral'):
            self.ranks[symbol] = bucket, [tier, *volume_levels]
        value['rank'] = self.ranks[symbol][1]

    def tick(self, now=None):
        now = int(self.now()) if now is None else int(now)
        if not self.calendar.is_open(now):
            self.reset()
            return
        if now == self.last_tick:
            return
        self.last_tick = now
        for symbol in self.focus | self.holdings:
            self.update(symbol, now)

    def state(self):
        return {'enabled': True, 'symbols': self.values}

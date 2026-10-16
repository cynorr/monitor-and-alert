from __future__ import annotations

import math
import sqlite3
import time
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from ..calendar import ET
from ..workspace import normalize_ticker

LIFETIME = 7 * 24 * 60 * 60


def symbol_key(value):
    if not isinstance(value, str):
        raise ValueError('Choose a US symbol')
    return normalize_ticker(value.strip().upper().removesuffix('.US')) + '.US'


def price_cents(value):
    try:
        if isinstance(value, bool):
            raise ValueError()
        price = Decimal(str(value))
        if not price.is_finite():
            raise ValueError()
        cents = int((price * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        if not 0 < cents < 2**63:
            raise ValueError()
        return cents
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise ValueError('Alert price must be positive and finite') from None


class AlertEngine:
    def __init__(self, path, calendar, *, clock=time.time, sound=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS alerts (
                id TEXT PRIMARY KEY, symbol TEXT NOT NULL, price_cents INTEGER NOT NULL,
                generation INTEGER NOT NULL, state TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL, expires_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, alert_id TEXT NOT NULL, generation INTEGER NOT NULL,
                symbol TEXT NOT NULL, direction TEXT NOT NULL, price_cents INTEGER NOT NULL,
                actual_price REAL NOT NULL, quote_time INTEGER NOT NULL,
                fired_at REAL NOT NULL, handled_at REAL);
        ''')
        self.calendar, self.now, self.sound = calendar, clock, sound
        self.alerts = {row['id']: dict(row) for row in self.db.execute('SELECT * FROM alerts')}
        self.by_symbol = {}
        self.baselines, self.latest = {}, {}
        self.allowed, self.scope_known = set(), False
        self.revision, self.error = 0, None
        self.heartbeat = self.now()
        self._index()

    def _index(self):
        self.by_symbol = {}
        for alert in self.alerts.values():
            self.by_symbol.setdefault(alert['symbol'], []).append(alert)

    def _changed(self):
        self.revision += 1
        self.error = None
        self._index()

    def reset(self):
        self.baselines.clear()
        self.latest.clear()

    def maintain(self, allowed, scope_known):
        now = self.now()
        if now - self.heartbeat > 30:
            self.reset()
        self.heartbeat = now
        allowed = set(allowed)
        if allowed != self.allowed or scope_known != self.scope_known:
            self.revision += 1
        self.allowed, self.scope_known = allowed, scope_known
        removed = [a['id'] for a in self.alerts.values() if a['expires_at'] <= now or
                   (scope_known and a['symbol'] not in allowed)]
        if removed:
            with self.db:
                self.db.executemany('DELETE FROM alerts WHERE id=?', [(key,) for key in removed])
            for key in removed:
                self.alerts.pop(key)
                self.baselines.pop(key, None)
            self._changed()
        for symbol in list(self.latest):
            if symbol not in allowed:
                self.latest.pop(symbol)

    def _regular_day(self, now, quote_time):
        day = datetime.fromtimestamp(now, ET).date()
        session = self.calendar.session(day)
        return day.isoformat() if session and session[0] <= now < session[1] and session[0] <= quote_time < session[1] else None

    def _baseline(self, alert):
        quote = self.latest.get(alert['symbol'])
        if quote and self._regular_day(self.now(), quote['timestamp']):
            self.baselines[alert['id']] = (quote['day'], quote['last_price'])
        else:
            self.baselines.pop(alert['id'], None)

    def create(self, symbol, price):
        """Core function entry; callers establish Focus/Holdings eligibility first."""
        symbol, cents = symbol_key(symbol), price_cents(price)
        if symbol not in self.allowed:
            raise ValueError('Alert symbol must be in current Focus or Holdings')
        now = self.now()
        alert = dict(id=uuid.uuid4().hex, symbol=symbol, price_cents=cents, generation=1,
                     state='active', created_at=now, updated_at=now, expires_at=now + LIFETIME)
        with self.db:
            self.db.execute('INSERT INTO alerts VALUES (:id,:symbol,:price_cents,:generation,:state,:created_at,:updated_at,:expires_at)', alert)
        self.alerts[alert['id']] = alert
        self._baseline(alert)
        self._changed()
        return alert

    def rearm(self, key, price, expected_generation=None):
        cents = price_cents(price)
        alert = self.alerts.get(key)
        if not alert or alert['symbol'] not in self.allowed:
            raise ValueError('Alert is no longer available')
        if expected_generation is not None and (type(expected_generation) is not int or expected_generation != alert['generation']):
            raise ValueError('Alert changed; please select it again')
        now = self.now()
        updated = dict(alert, price_cents=cents, generation=alert['generation'] + 1, state='active',
                       updated_at=now, expires_at=now + LIFETIME)
        with self.db:
            self.db.execute('UPDATE alerts SET price_cents=:price_cents,generation=:generation,state=:state,updated_at=:updated_at,expires_at=:expires_at WHERE id=:id', updated)
        self.alerts[key] = updated
        self._baseline(updated)
        self._changed()

    def delete(self, key):
        with self.db:
            self.db.execute('DELETE FROM alerts WHERE id=?', (key,))
        self.alerts.pop(key, None)
        self.baselines.pop(key, None)
        self._changed()

    def acknowledge(self, event_id):
        event = self.db.execute('SELECT * FROM events WHERE id=? AND handled_at IS NULL', (event_id,)).fetchone()
        if not event:
            return
        alert = self.alerts.get(event['alert_id'])
        delete = alert and alert['generation'] == event['generation'] and alert['state'] == 'triggered'
        with self.db:
            self.db.execute('UPDATE events SET handled_at=? WHERE id=?', (self.now(), event_id))
            if delete:
                self.db.execute('DELETE FROM alerts WHERE id=?', (alert['id'],))
        if delete:
            self.alerts.pop(alert['id'])
            self.baselines.pop(alert['id'], None)
        self._changed()

    def quote(self, symbol, quote):
        now = self.now()
        if now - self.heartbeat > 30:
            self.reset()
            self.heartbeat = now
        if symbol not in self.allowed or quote['trade_session'] != 'Intraday':
            return
        price, ts = quote['last_price'], quote['timestamp']
        if not math.isfinite(price) or price <= 0:
            return
        day = self._regular_day(now, ts)
        if not day:
            return
        previous = self.latest.get(symbol)
        if previous and (ts < previous['timestamp'] or (ts == previous['timestamp'] and
                         (price == previous['last_price'] or quote.get('source') == 'snapshot'))):
            return
        self.latest[symbol] = dict(quote, day=day)
        for alert in list(self.by_symbol.get(symbol, [])):
            if alert['state'] != 'active' or alert['expires_at'] <= now:
                continue
            baseline = self.baselines.get(alert['id'])
            self.baselines[alert['id']] = day, price
            if not baseline or baseline[0] != day:
                continue
            threshold = alert['price_cents'] / 100
            direction = 'up' if baseline[1] < threshold <= price else 'down' if baseline[1] > threshold >= price else None
            if direction:
                event = dict(id=uuid.uuid4().hex, alert_id=alert['id'], generation=alert['generation'],
                             symbol=symbol, direction=direction, price_cents=alert['price_cents'],
                             actual_price=price, quote_time=ts, fired_at=now, handled_at=None)
                try:
                    with self.db:
                        self.db.execute("UPDATE alerts SET state='triggered', updated_at=? WHERE id=?", (now, alert['id']))
                        self.db.execute('INSERT INTO events VALUES (:id,:alert_id,:generation,:symbol,:direction,:price_cents,:actual_price,:quote_time,:fired_at,:handled_at)', event)
                except sqlite3.Error:
                    self.baselines[alert['id']] = baseline
                    self.error = 'Could not save alert trigger'
                    self.revision += 1
                    continue
                self.alerts[alert['id']] = dict(alert, state='triggered', updated_at=now)
                self._changed()
                if self.sound:
                    self.sound.play(direction)

    def state(self):
        return {'revision': self.revision, 'alerts': list(self.alerts.values()),
                'events': [dict(row) for row in self.db.execute('SELECT * FROM events WHERE handled_at IS NULL ORDER BY fired_at DESC, rowid DESC')],
                'eligible_symbols': sorted(self.allowed), 'scope_known': self.scope_known,
                'sound': self.sound.state() if self.sound else {'enabled': False, 'error': None}, 'error': self.error}

    def close(self):
        self.db.close()

from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from types import SimpleNamespace

from .calendar import ET
from .downloader import sdk_timestamp

log = logging.getLogger(__name__)


class QuoteService:
    def __init__(self, broker, symbols: list[str], calendar, stale_seconds: int = 90, on_quote=None, on_reconnect=None):
        self.broker, self.symbols, self.calendar = broker, symbols, calendar
        self.stale_seconds = stale_seconds
        self.on_quote, self.on_reconnect = on_quote, on_reconnect
        self.has_connected = False
        self.values: dict[str, dict] = {}
        self.last_push_monotonic = 0.0
        self.last_quote_received_at = None
        self.connection_health = 'CONNECTING'
        self.errors: dict[str, str] = {}
        self.push_count = 0
        self.generation = 0
        self.connected_at = 0.0
        self.ctx = None
        self.subscription_errors: dict[str, str] = {}
        self.subscribed = set()
        self.changed = asyncio.Event()

    def set_symbols(self, symbols):
        removed = set(self.symbols) - set(symbols)
        self.symbols = list(symbols)
        for symbol in removed:
            for mapping in (self.values, self.errors, self.subscription_errors):
                mapping.pop(symbol, None)
        self.changed.set()

    async def update_subscriptions(self):
        """Run on the same Quote loop as connect/retry, using the existing context."""
        removed = self.subscribed - set(self.symbols)
        if removed:
            await self.broker.unsubscribe(self.ctx, sorted(removed))
            self.subscribed.difference_update(removed)
        added = [s for s in self.symbols if s not in self.subscribed]
        for symbol in added:
            if symbol not in self.symbols:
                continue
            try:
                await self.broker.subscribe(self.ctx, [symbol])
                self.subscribed.add(symbol)
                self.connected_at = time.monotonic()
                self.has_connected = True
                self.subscription_errors.pop(symbol, None)
                if symbol in self.symbols:
                    await self._snapshot(self.ctx, [symbol])
            except Exception as exc:
                if symbol in self.symbols:
                    if symbol in self.subscribed:
                        self.errors[symbol] = str(exc)
                    else:
                        self.subscription_errors[symbol] = str(exc)

    def apply(self, symbol, event, snapshot=False, session_override=None):
        if symbol not in self.symbols:
            return
        try:
            ts = sdk_timestamp(event.timestamp)
            price, volume = float(event.last_done), int(event.volume)
            if not math.isfinite(price) or price <= 0 or volume < 0 or ts > time.time() + 10:
                raise ValueError('Invalid quote price, volume or timestamp')
            session = session_override or ('Intraday' if snapshot else str(event.trade_session).split('.')[-1])
            if session == 'Normal':
                session = 'Intraday'
            entry = self.values.setdefault(symbol, {})
            previous = entry.get(session)
            if previous and previous['timestamp'] > ts:
                return
            entry[session] = {'last_price': price, 'cumulative_volume': volume,
                              'timestamp': ts, 'trade_session': session,
                              'received_at': int(time.time()), 'source': 'snapshot' if snapshot else 'push',
                              'trade_status': str(getattr(event, 'trade_status', 'Unknown')).split('.')[-1]}
            for field in ('prev_close', 'bid_price', 'ask_price'):
                value = getattr(event, field, (previous or {}).get(field))
                try:
                    value = float(value)
                    if math.isfinite(value) and value > 0:
                        entry[session][field] = value
                except (TypeError, ValueError, OverflowError):
                    pass
            if self.on_quote:
                self.on_quote(symbol, entry[session])
            if not snapshot:
                self.last_push_monotonic = time.monotonic()
                self.last_quote_received_at = int(time.time())
                self.push_count += 1
            self.errors.pop(symbol, None)
        except (ValueError, TypeError, OverflowError) as exc:
            self.errors[symbol] = str(exc)

    def output(self, symbol: str, now: int) -> dict:
        self.broker.check([symbol])
        sessions = self.values.get(symbol, {})
        regular = sessions.get('Intraday')
        current = bool(regular and datetime.fromtimestamp(regular['timestamp'], ET).date()
                       == datetime.fromtimestamp(now, ET).date())
        return {'symbol': symbol, 'regular': regular,
                'extended': {key: value for key, value in sessions.items() if key != 'Intraday'},
                'connection_health': self.connection_health,
                'regular_quote_age_seconds': now - regular['timestamp'] if regular else None,
                'current_regular_session': current and self.calendar.is_open(now),
                'error': self.subscription_errors.get(symbol) or self.errors.get(symbol)}

    async def _snapshot(self, ctx, symbols):
        rows = await self.broker.snapshot(ctx, symbols)
        for row in rows:
            self.apply(row.symbol, row, snapshot=True)
            for field, session in (('pre_market_quote', 'Pre'), ('post_market_quote', 'Post'),
                                   ('overnight_quote', 'Overnight'), ('over_night_quote', 'Overnight')):
                extended = getattr(row, field, None)
                if extended is not None:
                    event = SimpleNamespace(timestamp=extended.timestamp, last_done=extended.last_done,
                                            volume=extended.volume, trade_session=session)
                    # Snapshot extended values must retain their actual session.
                    self.apply(row.symbol, event, snapshot=True, session_override=session)

    async def connect(self):
        self.generation += 1
        generation = self.generation
        loop = asyncio.get_running_loop()
        self.ctx = ctx = self.broker.context()
        self.subscription_errors = {}
        connect_started = time.monotonic()

        def callback(symbol, event):
            def deliver():
                if generation == self.generation:
                    self.apply(symbol, event)
            try:
                loop.call_soon_threadsafe(deliver)
            except RuntimeError:
                pass

        ctx.set_on_quote(callback)
        if not self.symbols:
            self.connection_health = 'CONNECTED'
            return
        subscribed = []
        for start in range(0, len(self.symbols), 20):
            chunk = self.symbols[start:start + 20]
            try:
                await self.broker.subscribe(ctx, chunk)
                self.subscribed.update(chunk)
                subscribed.extend(chunk)
            except Exception as exc:
                if isinstance(exc, TimeoutError):
                    raise
                for symbol in chunk:
                    try:
                        await self.broker.subscribe(ctx, [symbol])
                        self.subscribed.add(symbol)
                        subscribed.append(symbol)
                    except Exception as single:
                        self.subscription_errors[symbol] = str(single)
        if not subscribed:
            raise RuntimeError('No focus/wait symbols could be subscribed')
        snapshot_ok = False
        for start in range(0, len(subscribed), 20):
            chunk = subscribed[start:start + 20]
            try:
                await self._snapshot(ctx, chunk)
                snapshot_ok = True
            except Exception:
                for symbol in chunk:
                    try:
                        await self._snapshot(ctx, [symbol])
                        snapshot_ok = True
                    except Exception as exc:
                        self.errors[symbol] = str(exc)
        if not snapshot_ok and self.last_push_monotonic < connect_started:
            raise RuntimeError('No quote snapshot or fresh push available after subscribe')
        self.connected_at = time.monotonic()
        self.connection_health = 'CONNECTED'
        if self.has_connected and self.on_reconnect:
            self.on_reconnect()
        self.has_connected = True
        log.info('Quote connected symbols=%d', len(subscribed))

    async def disconnect(self):
        self.generation += 1
        ctx, self.ctx = self.ctx, None
        if ctx is not None:
            ctx.set_on_quote(lambda *_: None)
            try:
                if self.subscribed:
                    await self.broker.unsubscribe(ctx, sorted(self.subscribed))
                    self.subscribed.clear()
            except Exception:
                pass

    async def run(self):
        backoff = 2
        try:
            while True:
                try:
                    self.connection_health = 'CONNECTING'
                    await self.connect()
                    backoff = 2
                    last_snapshot = time.monotonic()
                    while True:
                        try:
                            await asyncio.wait_for(self.changed.wait(), timeout=1)
                        except TimeoutError:
                            pass
                        if self.changed.is_set():
                            self.changed.clear()
                            await self.update_subscriptions()
                        now = int(time.time())
                        if self.symbols and self.calendar.is_open(now):
                            if time.monotonic() - max(self.last_push_monotonic, self.connected_at) > self.stale_seconds:
                                raise TimeoutError('No universe quote push; reconnecting stale connection')
                        self.connection_health = 'CONNECTED'
                        # Periodic snapshots also restore state after SDK-internal reconnects.
                        if time.monotonic() - last_snapshot >= 30:
                            await self.update_subscriptions()
                            for start in range(0, len(self.symbols), 20):
                                chunk = self.symbols[start:start + 20]
                                try:
                                    await self._snapshot(self.ctx, chunk)
                                except TimeoutError:
                                    raise
                                except Exception as exc:
                                    for symbol in chunk:
                                        self.errors[symbol] = str(exc)
                            last_snapshot = time.monotonic()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.connection_health = 'DISCONNECTED'
                    log.warning('Quote disconnected: %s', exc)
                    await self.disconnect()
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
        finally:
            await self.disconnect()
            self.connection_health = 'DISCONNECTED'

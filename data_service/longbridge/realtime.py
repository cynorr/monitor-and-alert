"""Realtime quotes and native SDK candles on the shared Longbridge context."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime
from types import SimpleNamespace

from .client import SDK_PERIODS
from ..calendar import ET, PHASES
from .history import sdk_timestamp

log = logging.getLogger(__name__)


class RealtimeFeed:
    def __init__(self, broker, symbols: list[str], calendar, stale_seconds: int = 90,
                 on_quote=None, on_reconnect=None, on_reset=None, on_candle=None, candle_priority=None):
        self.broker, self.symbols, self.calendar = broker, symbols, calendar
        self.stale_seconds = stale_seconds
        self.on_quote, self.on_reconnect, self.on_reset = on_quote, on_reconnect, on_reset
        self.on_candle, self.candle_priority = on_candle, candle_priority
        self.has_connected = False
        self.values = {}
        self.last_push_monotonic = 0.0
        self.last_quote_received_at = None
        self.connection_health = 'CONNECTING'
        self.errors, self.subscription_errors, self.candle_errors = {}, {}, {}
        self.push_count, self.generation, self.connected_at = 0, 0, 0.0
        self.ctx = None
        self.subscribed, self.quote_subscribed, self.candle_subscribed = set(), set(), set()
        self.extra_symbols = []
        self.candle_refresh, self.initializing = set(), {}
        self.changed = asyncio.Event()

    def recover(self):
        self.candle_refresh.update((symbol, tf) for symbol in self.symbols for tf in PHASES)
        self.changed.set()

    @property
    def all_symbols(self):
        return list(dict.fromkeys(self.symbols + self.extra_symbols))

    def set_symbols(self, symbols, extra_symbols=()):
        symbols = list(symbols)
        extra_symbols = sorted(set(extra_symbols) - set(symbols))
        if symbols == self.symbols and extra_symbols == self.extra_symbols:
            return
        removed = set(self.all_symbols) - set(symbols) - set(extra_symbols)
        self.symbols, self.extra_symbols = symbols, extra_symbols
        for symbol in removed:
            for mapping in (self.values, self.errors, self.subscription_errors):
                mapping.pop(symbol, None)
        self.candle_errors = {key: value for key, value in self.candle_errors.items() if key[0] in symbols}
        self.candle_refresh = {key for key in self.candle_refresh if key[0] in symbols}
        self.changed.set()

    async def _subscribe_missing(self, symbols, *, quote_only=False):
        subscribed = self.quote_subscribed if quote_only else self.subscribed
        added = [symbol for symbol in symbols if symbol not in subscribed]
        snapshot_ok = False
        for start in range(0, len(added), 500):
            chunk = added[start:start + 500]
            successful = []
            try:
                if quote_only:
                    await self.broker.subscribe(self.ctx, chunk, quote_only=True)
                else:
                    await self.broker.subscribe(self.ctx, chunk)
                successful = chunk
            except TimeoutError as exc:
                if not quote_only:
                    raise
                for symbol in chunk:
                    self.subscription_errors[symbol] = str(exc)
            except Exception:
                for symbol in chunk:
                    try:
                        if quote_only:
                            await self.broker.subscribe(self.ctx, [symbol], quote_only=True)
                        else:
                            await self.broker.subscribe(self.ctx, [symbol])
                        successful.append(symbol)
                    except Exception as exc:
                        self.subscription_errors[symbol] = str(exc)
            subscribed.update(successful)
            for symbol in successful:
                self.subscription_errors.pop(symbol, None)
            if successful:
                self.connected_at = time.monotonic()
                try:
                    snapshot_ok = await self._take_snapshots(successful) or snapshot_ok
                except TimeoutError as exc:
                    if not quote_only:
                        raise
                    for symbol in successful:
                        self.errors[symbol] = str(exc)
        return snapshot_ok

    async def _take_snapshots(self, symbols):
        snapshot_ok = False
        for start in range(0, len(symbols), 500):
            chunk = symbols[start:start + 500]
            try:
                snapshot_ok = await self._snapshot(self.ctx, chunk) or snapshot_ok
            except TimeoutError:
                raise
            except Exception:
                for symbol in chunk:
                    try:
                        snapshot_ok = await self._snapshot(self.ctx, [symbol]) or snapshot_ok
                    except Exception as exc:
                        self.errors[symbol] = str(exc)
        return snapshot_ok

    async def update_candles(self):
        if self.on_candle is None:
            return
        wanted = {(symbol, tf) for symbol in self.symbols for tf in PHASES}
        order = ('5m', '1d', *PHASES[2:])
        priority = self.candle_priority or (lambda key: (order.index(key[1]), key[0]))
        pending = wanted - self.candle_subscribed | (wanted & self.candle_refresh)
        while pending:
            key = min(pending, key=priority)
            pending.remove(key)
            symbol, tf = key
            if symbol not in self.symbols:
                continue
            try:
                if key in self.candle_subscribed or key in self.candle_errors:
                    await self.broker.unsubscribe_candles(self.ctx, symbol, tf)
                    self.candle_subscribed.discard(key)
                # Retain the application view while the SDK acquires a new seed.
                # Buffer pushes generated after that seed so they win the initial snapshot.
                self.initializing[key] = {}
                rows = await self.broker.subscribe_candles(self.ctx, symbol, tf)
                seeded = {sdk_timestamp(row.timestamp): row for row in rows}
                seeded.update(self.initializing.pop(key))
                self.candle_subscribed.add(key)
                if symbol in self.symbols and seeded:
                    self.on_candle(symbol, tf, list(seeded.values()), initial=True)
                self.candle_refresh.discard(key)
                self.candle_errors.pop(key, None)
            except Exception as exc:
                if symbol in self.symbols:
                    self.candle_errors[key] = str(exc)
            finally:
                self.initializing.pop(key, None)
            if self.changed.is_set():
                break

    async def update_subscriptions(self, *, candles=True):
        self.changed.clear()
        for symbol, tf in sorted(self.candle_subscribed):
            if symbol not in self.symbols:
                await self.broker.unsubscribe_candles(self.ctx, symbol, tf)
                self.candle_subscribed.discard((symbol, tf))
        removed = self.subscribed - set(self.symbols)
        if removed:
            await self.broker.unsubscribe(self.ctx, sorted(removed))
            self.subscribed.difference_update(removed)
        removed = self.quote_subscribed - set(self.extra_symbols)
        if removed:
            await self.broker.unsubscribe(self.ctx, sorted(removed), quote_only=True)
            self.quote_subscribed.difference_update(removed)
        snapshot_ok = await self._subscribe_missing(self.symbols)
        snapshot_ok = await self._subscribe_missing(self.extra_symbols, quote_only=True) or snapshot_ok
        if candles:
            await self.update_candles()
        return snapshot_ok

    def apply(self, symbol, event, snapshot=False, session_override=None):
        if symbol not in self.all_symbols:
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
            preserve_push = snapshot and previous and previous['timestamp'] == ts and previous['source'] == 'push'
            if preserve_push:
                price = previous['last_price']
            entry[session] = {'last_price': price, 'cumulative_volume': volume,
                              'timestamp': ts, 'trade_session': session,
                              'received_at': int(time.time()), 'source': 'push' if preserve_push or not snapshot else 'snapshot',
                              'trade_status': str(getattr(event, 'trade_status', 'Unknown')).split('.')[-1]}
            for field in ('prev_close', 'bid_price', 'ask_price'):
                value = getattr(event, field, (previous or {}).get(field))
                try:
                    value = float(value)
                    if math.isfinite(value) and value > 0:
                        entry[session][field] = value
                except (TypeError, ValueError, OverflowError):
                    pass
            same_day = previous and datetime.fromtimestamp(previous['timestamp'], ET).date() == datetime.fromtimestamp(ts, ET).date()
            for field in ('open', 'high', 'low'):
                previous_value = previous.get(field) if same_day else None
                value = previous_value if preserve_push else getattr(event, field, None)
                try:
                    value = float(value)
                    if math.isfinite(value) and value > 0:
                        entry[session][field] = value
                    elif previous_value is not None:
                        entry[session][field] = previous_value
                except (TypeError, ValueError, OverflowError):
                    if previous_value is not None:
                        entry[session][field] = previous_value
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
                'latest': max(sessions.values(), key=lambda value: value['timestamp'], default=None),
                'connection_health': self.connection_health,
                'regular_quote_age_seconds': now - regular['timestamp'] if regular else None,
                'current_regular_session': current and self.calendar.is_open(now),
                'error': self.subscription_errors.get(symbol) or self.errors.get(symbol)}

    async def _snapshot(self, ctx, symbols):
        rows = await self.broker.snapshot(ctx, symbols)
        for row in rows:
            self.apply(row.symbol, row, snapshot=True)
            for field, session in (('pre_market_quote', 'Pre'), ('post_market_quote', 'Post'),
                                   ('overnight_quote', 'Overnight')):
                extended = getattr(row, field, None)
                if extended is not None:
                    event = SimpleNamespace(timestamp=extended.timestamp, last_done=extended.last_done,
                                            volume=extended.volume, trade_session=session)
                    # Snapshot extended values must retain their actual session.
                    self.apply(row.symbol, event, snapshot=True, session_override=session)

        return bool(rows)

    async def connect(self):
        self.generation += 1
        if self.on_reset:
            self.on_reset()
        generation = self.generation
        loop = asyncio.get_running_loop()
        self.ctx = ctx = self.broker.context()
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
        if self.on_candle:
            def candle_callback(symbol, event):
                def deliver():
                    if generation != self.generation or symbol not in self.symbols:
                        return
                    tf = next(tf for tf, period in SDK_PERIODS.items() if period == event.period)
                    key = symbol, tf
                    try:
                        if key in self.initializing:
                            self.initializing[key][sdk_timestamp(event.candlestick.timestamp)] = event.candlestick
                        elif self.on_candle(symbol, tf, [event.candlestick]):
                            self.candle_errors.pop(key, None)
                    except (AttributeError, ValueError, TypeError, OverflowError) as exc:
                        self.candle_errors[key] = str(exc)
                try:
                    loop.call_soon_threadsafe(deliver)
                except RuntimeError:
                    pass
            ctx.set_on_candlestick(candle_callback)
        snapshot_ok = await self.update_subscriptions(candles=False)
        if self.symbols and not self.subscribed:
            raise RuntimeError('No Focus/Holdings symbols could be subscribed')
        if self.all_symbols and not snapshot_ok and self.last_push_monotonic < connect_started:
            raise RuntimeError('No quote snapshot or fresh push available after subscribe')
        self.connected_at = time.monotonic()
        self.connection_health = 'CONNECTED'
        if self.has_connected and self.on_reconnect:
            self.on_reconnect()
        self.has_connected = True
        await self.update_candles()
        log.info('Quote connected symbols=%d', len(self.subscribed | self.quote_subscribed))

    async def disconnect(self):
        self.generation += 1
        ctx, self.ctx = self.ctx, None
        if ctx is not None:
            ctx.set_on_quote(lambda *_: None)
            if self.on_candle:
                ctx.set_on_candlestick(lambda *_: None)
            try:
                for symbol, tf in sorted(self.candle_subscribed | self.candle_errors.keys()):
                    await self.broker.unsubscribe_candles(ctx, symbol, tf)
                if self.subscribed:
                    await self.broker.unsubscribe(ctx, sorted(self.subscribed))
                if self.quote_subscribed:
                    await self.broker.unsubscribe(ctx, sorted(self.quote_subscribed), quote_only=True)
            except Exception as exc:
                log.warning('Quote cleanup failed; dropping SDK context: %s', exc)
                self.broker.close()
        self.candle_subscribed.clear()
        self.subscribed.clear()
        self.quote_subscribed.clear()
        self.candle_refresh.clear()
        self.initializing.clear()

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
                            await self.update_subscriptions()
                        now = int(time.time())
                        if self.all_symbols and self.calendar.is_open(now):
                            if time.monotonic() - max(self.last_push_monotonic, self.connected_at) > self.stale_seconds:
                                raise TimeoutError('No universe quote push; reconnecting stale connection')
                        self.connection_health = 'CONNECTED'
                        if time.monotonic() - last_snapshot >= 30:
                            await self.update_subscriptions()
                            await self._take_snapshots(self.all_symbols)
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

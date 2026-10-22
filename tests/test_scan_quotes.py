import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from data_service.calendar import ET, PHASES
from data_service.quotes import QuoteService
from data_service.workbench import Workbench
from test_data_service import cal


class Broker:
    def __init__(self):
        self.context_calls = 0
        self.calls = []
        self.types = {}

    def context(self):
        self.context_calls += 1
        return self

    def set_on_quote(self, callback): self.on_quote = callback
    def set_on_candlestick(self, callback): self.on_candle = callback
    def check(self, symbols): pass
    def close(self): pass

    async def subscribe(self, ctx, symbols, *, quote_only=False):
        self.calls.append(('subscribe', tuple(symbols), quote_only))
        for symbol in symbols:
            self.types.setdefault(symbol, set()).update({'quote'} if quote_only else {'quote', 'trade'})

    async def unsubscribe(self, ctx, symbols, *, quote_only=False):
        self.calls.append(('unsubscribe', tuple(symbols), quote_only))
        for symbol in symbols:
            self.types[symbol].difference_update({'quote'} if quote_only else {'quote', 'trade'})

    async def snapshot(self, ctx, symbols):
        return [SimpleNamespace(symbol=s, timestamp=datetime.now(ET), last_done=10, volume=100) for s in symbols]

    async def subscribe_candles(self, ctx, symbol, timeframe):
        self.calls.append(('candle', symbol, timeframe))
        return []

    async def unsubscribe_candles(self, ctx, symbol, timeframe):
        self.calls.append(('remove_candle', symbol, timeframe))


def test_regular_quote_retains_native_ohl_only_within_same_day(cal):
    quotes = QuoteService(Broker(), ['TEST.US'], cal)
    stamp = datetime.now(ET) - timedelta(days=1)
    def event(**fields):
        return SimpleNamespace(timestamp=stamp, last_done=11, volume=100,
                               trade_session='Intraday', **fields)
    quotes.apply('TEST.US', event(open=10, high=12, low=9))
    quotes.apply('TEST.US', event(open=0, high=0, low=0))
    assert quotes.values['TEST.US']['Intraday']['high'] == 12
    quotes.apply('TEST.US', event(open=8, high=20, low=7), snapshot=True)
    assert quotes.values['TEST.US']['Intraday']['high'] == 12
    stamp += timedelta(days=1)
    quotes.apply('TEST.US', event(open=0, high=0, low=0))
    assert 'high' not in quotes.values['TEST.US']['Intraday']


@pytest.mark.parametrize('clock, expected', [
    ('2026-10-16T03:59:59-04:00', None),
    ('2026-10-16T04:00:00-04:00', 'Pre'),
    ('2026-10-16T09:29:59-04:00', 'Pre'),
    ('2026-10-16T09:30:00-04:00', 'Intraday'),
    ('2026-10-16T15:59:59-04:00', 'Intraday'),
    ('2026-10-16T16:00:00-04:00', 'Post'),
    ('2026-10-16T19:59:59-04:00', 'Post'),
    ('2026-10-16T20:00:00-04:00', None),
    ('2026-10-17T10:00:00-04:00', None),
    ('2026-11-26T10:00:00-05:00', None),
    ('2026-11-27T12:59:59-05:00', 'Intraday'),
    ('2026-11-27T13:00:00-05:00', 'Post'),
    ('2026-10-30T13:30:00+00:00', 'Intraday'),
    ('2026-11-02T14:29:59+00:00', 'Pre'),
    ('2026-11-02T14:30:00+00:00', 'Intraday'),
])
def test_scan_quote_selects_only_current_session(cal, clock, expected):
    local = datetime.fromisoformat(clock).astimezone(ET)
    now = int(local.timestamp())
    quotes = QuoteService(Broker(), ['SCAN.US'], cal)
    closed_hour = 13 if local.date().isoformat() == '2026-11-27' else 16
    values = {name: {'last_price': price, 'timestamp': int(local.replace(hour=hour, minute=minute,
              second=0, microsecond=0).timestamp()), 'trade_session': name}
              for name, price, hour, minute in [('Pre', 10, 4, 0), ('Intraday', 11, 9, 30),
                                                ('Post', 12, closed_hour, 0)]}
    quotes.values['SCAN.US'] = values
    original = deepcopy(values)
    app = Workbench.__new__(Workbench)
    app.calendar, app.mock = cal, False
    app.workspace = SimpleNamespace(date='2026-10-15')
    app.selected_date = app.workspace.date
    app.monitor = SimpleNamespace(now=lambda: now, quotes=quotes)
    result = app.scan_quote('SCAN.US')
    assert result['regular'] == (values['Intraday'] if expected == 'Intraday' else None)
    assert result['extended'] == ({expected: values[expected]} if expected in ('Pre', 'Post') else {})
    assert values == original  # Scan filtering must not discard Monitor's cached sessions.
    if expected:
        values[expected]['timestamp'] -= int(timedelta(days=1).total_seconds())
        stale = app.scan_quote('SCAN.US')
        assert stale['regular'] is None and not stale['extended']
        del values[expected]
        missing = app.scan_quote('SCAN.US')
        assert missing['regular'] is None and not missing['extended']


def test_broker_scan_scope_allows_quote_but_rejects_trade_and_candles():
    from data_service.broker import Broker as LiveBroker, SubType
    broker = LiveBroker.__new__(LiveBroker)
    broker.allowed = frozenset({'CORE.US', 'SCAN.US'})
    broker.candle_allowed = frozenset({'CORE.US'})
    calls = []
    async def call(method, *args, **kwargs): calls.append(args)
    broker.call = call
    ctx = SimpleNamespace(subscribe=object())
    async def scenario():
        await broker.subscribe(ctx, ['SCAN.US'], quote_only=True)
        assert calls == [(['SCAN.US'], [SubType.Quote])]
        with pytest.raises(ValueError, match='Focus and Holdings'):
            await broker.subscribe(ctx, ['SCAN.US'])
        with pytest.raises(ValueError, match='Focus and Holdings'):
            await broker.candles('SCAN.US', '1d')
        with pytest.raises(ValueError, match='Focus and Holdings'):
            await broker.subscribe_candles(ctx, 'SCAN.US', '1d')
        assert len(calls) == 1
    asyncio.run(scenario())


def test_broker_rechecks_full_scope_while_symbol_remains_quote_only():
    from data_service.broker import Broker as LiveBroker
    async def scenario():
        gate = asyncio.Event()
        class Limiter:
            async def wait(self, background=False): await gate.wait()
        broker = LiveBroker.__new__(LiveBroker)
        broker.allowed = broker.candle_allowed = frozenset({'CORE.US'})
        broker.timeout, broker.secrets = 1, ()
        broker.limiter, broker.inflight = Limiter(), asyncio.Semaphore(5)
        calls = []
        async def candles(*args): calls.append(args)
        broker._context = SimpleNamespace(candlesticks=candles)
        task = asyncio.create_task(broker.candles('CORE.US', '1d'))
        await asyncio.sleep(0)
        broker.candle_allowed = frozenset()  # It moved from Focus to Scan-only while awaiting budget.
        gate.set()
        with pytest.raises(ValueError, match='Focus and Holdings'):
            await task
        assert not calls
    asyncio.run(scenario())


def test_scan_quote_batches_toggle_and_promote_without_reconnecting_or_expanding_candles(cal):
    async def scenario():
        broker = Broker()
        resets = []
        quotes = QuoteService(broker, ['CORE.US'], cal, on_candle=lambda *args, **kwargs: True,
                              on_reset=lambda: resets.append(True))
        extras = [f'SCAN{i}.US' for i in range(25)]
        quotes.set_symbols(['CORE.US'], ['CORE.US', *extras])
        await quotes.connect()
        assert broker.context_calls == 1 and resets == [True]
        assert len([c for c in broker.calls if c[0] == 'subscribe' and c[2]]) == 1
        assert quotes.quote_subscribed == set(extras)
        core_candles = {('CORE.US', tf) for tf in PHASES}
        assert quotes.candle_subscribed == core_candles
        assert set(quotes.values) == {'CORE.US', *extras}
        generation = quotes.generation

        count = len(broker.calls)
        quotes.recover()
        await quotes.update_subscriptions()
        assert quotes.candle_subscribed == core_candles and not quotes.candle_refresh
        assert broker.context_calls == 1 and quotes.generation == generation and resets == [True]
        assert all(c[0] in {'remove_candle', 'candle'} for c in broker.calls[count:])

        quotes.set_symbols(['CORE.US'])
        await quotes.update_subscriptions()
        assert not quotes.quote_subscribed
        assert broker.types['CORE.US'] == {'quote', 'trade'}
        assert quotes.candle_subscribed == core_candles
        quotes.set_symbols(['CORE.US'], extras)
        await quotes.update_subscriptions()
        assert quotes.quote_subscribed == set(extras)

        # Promotion starts Trade/candles; returning to Discover keeps only Quote.
        promoted = extras[0]
        quotes.set_symbols(['CORE.US', promoted], extras)
        await quotes.update_subscriptions()
        assert broker.types[promoted] == {'quote', 'trade'}
        assert promoted not in quotes.quote_subscribed
        assert quotes.candle_subscribed == core_candles | {(promoted, tf) for tf in PHASES}
        quotes.set_symbols(['CORE.US'], extras)
        await quotes.update_subscriptions()
        assert broker.types[promoted] == {'quote'}
        assert quotes.candle_subscribed == core_candles
        assert broker.context_calls == 1 and quotes.generation == generation and resets == [True]
        assert not any(c[0] == 'unsubscribe' and 'CORE.US' in c[1] for c in broker.calls)
        await quotes.disconnect()
        assert not any(broker.types.values())
    asyncio.run(scenario())


def test_unavailable_scan_symbol_does_not_block_other_quotes_or_monitor(cal):
    async def scenario():
        broker = Broker()
        original = broker.subscribe
        async def subscribe(ctx, symbols, *, quote_only=False):
            if quote_only and 'BAD.US' in symbols:
                raise RuntimeError('Symbol unavailable')
            await original(ctx, symbols, quote_only=quote_only)
        broker.subscribe = subscribe
        quotes = QuoteService(broker, ['CORE.US'], cal, on_candle=lambda *args, **kwargs: True)
        quotes.set_symbols(['CORE.US'], ['BAD.US', 'GOOD.US'])
        await quotes.connect()
        assert quotes.connection_health == 'CONNECTED' and broker.context_calls == 1
        assert quotes.subscribed == {'CORE.US'} and quotes.quote_subscribed == {'GOOD.US'}
        assert quotes.subscription_errors == {'BAD.US': 'Symbol unavailable'}
        assert quotes.candle_subscribed == {('CORE.US', tf) for tf in PHASES}
        await quotes.disconnect()
    asyncio.run(scenario())

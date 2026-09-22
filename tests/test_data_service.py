import asyncio
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_service.calendar import ET, PHASES, TradingCalendar
from data_service.config import Ticker, load_tickers
from data_service.downloader import BarDownloader
from data_service.quotes import QuoteService
from data_service.service import DataService
from data_service.store import Bar, BarStore
from data_service.validator import DataValidator


@pytest.fixture(scope='module')
def cal():
    return TradingCalendar(date(2026, 9, 19))


@pytest.fixture
def store(tmp_path, cal):
    value = BarStore(tmp_path / 'bars.sqlite3', cal, {'PAYS.US', 'BLSH.US'})
    yield value
    value.close()


def at(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=ET).timestamp())


def bar(ts, tf='5m', symbol='PAYS.US', volume=10):
    return Bar(symbol, tf, ts, 10, 12, 9, 11, volume)


def raw(ts, session='TradeSession.Intraday', volume=10):
    return SimpleNamespace(timestamp=datetime.fromtimestamp(ts, ET), trade_session=session,
                           open=10, high=12, low=9, close=11, volume=volume)


def test_tickers_status_authoritative_and_reload(tmp_path):
    path = tmp_path / 'workspace.json'
    data = {'statuses': {'PAYS': {'status': 'focus'}, 'BLSH': {'status': 'wait'},
                         'HIDDEN': {'status': 'hidden'}},
            'orders': {'focus': ['HIDDEN', 'UNKNOWN', 'PAYS']}, 'carried': ['CARRIED']}
    path.write_text(json.dumps(data))
    assert [t.symbol for t in load_tickers(path)] == ['PAYS.US', 'BLSH.US']
    with pytest.raises(ValueError, match='outside focus/wait'):
        load_tickers(path, ['HIDDEN'])
    data['statuses']['PAYS']['status'] = 'hidden'
    path.write_text(json.dumps(data))
    assert [t.symbol for t in load_tickers(path)] == ['BLSH.US']


def test_calendar_holiday_early_close_dst_hour_alignment(cal):
    assert not cal.grid(date(2026, 9, 7), '5m')
    assert len(cal.grid(date(2025, 11, 28), '5m')) == 42
    assert len(cal.grid(date(2026, 9, 18), '5m')) == 78
    hours = cal.grid(date(2026, 9, 18), '1h')
    assert hours[0] == (at('2026-09-18T09:30'), at('2026-09-18T10:30'))
    assert hours[-1] == (at('2026-09-18T15:30'), at('2026-09-18T16:00'))
    before = datetime.fromtimestamp(cal.session(date(2026, 3, 6))[0], ET)
    after = datetime.fromtimestamp(cal.session(date(2026, 3, 9))[0], ET)
    assert before.utcoffset() != after.utcoffset()
    assert cal.bar_end(at('2026-09-18T00:00'), '1d') == at('2026-09-18T16:00')


def test_store_closed_only_upsert_and_whitelist(store):
    ts = at('2026-09-18T09:30')
    with pytest.raises(ValueError, match='Forming'):
        store.upsert([bar(ts)], ts + 299)
    with pytest.raises(ValueError, match='outside focus/wait'):
        store.upsert([bar(ts, symbol='NO.US')], ts + 300)
    store.upsert([bar(ts, volume=10)], ts + 300)
    store.upsert([bar(ts, volume=99)], ts + 300)
    assert len(store.bars('PAYS.US', '5m')) == 1
    assert store.bars('PAYS.US', '5m')[0].volume == 99
    assert store.db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'


def install_batch(store, cal, now, symbol='PAYS.US', tf='5m', run='run', count=80):
    target = cal.latest_closed(tf, now)
    days = cal.completed_days(now, 100) + [datetime.fromtimestamp(now, ET).date()]
    times = sorted(set(ts for d in days for ts, end in cal.grid(d, tf) if end <= now))[-count:]
    rows = [bar(ts, tf, symbol) for ts in times]
    store.upsert(rows, now, {'symbol': symbol, 'timeframe': tf, 'run_id': run, 'as_of': now,
                            'returned_count': len(rows), 'window_start': times[0], 'rejected': []})
    return rows


def test_quote_is_cumulative_separated_and_monotonic(cal):
    class Fake:
        def check(self, symbols):
            assert symbols == ['PAYS.US']
    service = QuoteService(Fake(), ['PAYS.US'], cal)
    ts = int(time.time()) - 3
    def quote(t, volume, session='TradeSession.Intraday'):
        return SimpleNamespace(timestamp=datetime.fromtimestamp(t, ET), last_done=10,
                               volume=volume, trade_session=session)
    service.apply('PAYS.US', quote(ts, 100))
    service.apply('PAYS.US', quote(ts + 1, 120))
    service.apply('PAYS.US', quote(ts - 1, 999))
    service.apply('PAYS.US', quote(ts + 2, 30, 'TradeSession.Post'))
    assert service.values['PAYS.US']['Intraday']['cumulative_volume'] == 120
    assert service.values['PAYS.US']['Post']['cumulative_volume'] == 30
    service.apply('PAYS.US', quote(ts + 1, 119), snapshot=True)
    assert service.values['PAYS.US']['Intraday']['cumulative_volume'] == 119


def test_api_blocks_nonuniverse_and_returns_lightweight_chart_rows(tmp_path, cal):
    service = DataService([Ticker('PAYS.US', 'PAYS', 'focus')], tmp_path, calendar=cal)
    try:
        with pytest.raises(ValueError, match='outside focus/wait'):
            asyncio.run(service.api('/v1/bars', {'symbol': ['AAPL.US']}))
        ts = at('2026-09-17T09:30')
        service.store.upsert([bar(ts)], ts + 300)
        result = asyncio.run(service.api('/v1/bars', {'symbol': ['PAYS.US']}))
        assert result['bars'][0]['time'] == ts
        assert result['closed_only']
    finally:
        service.store.close()


def test_reconnect_restores_snapshot_and_ignores_old_connection(cal):
    class Context:
        def set_on_quote(self, callback):
            self.callback = callback
    class Fake:
        generation = 0
        subscribed = []
        def context(self):
            self.generation += 1
            return Context()
        async def subscribe(self, ctx, symbols):
            self.subscribed.append(tuple(symbols))
        async def snapshot(self, ctx, symbols):
            return [SimpleNamespace(symbol='PAYS.US', timestamp=datetime.now(ET),
                                    last_done=10, volume=self.generation * 100)]
        async def unsubscribe(self, ctx, symbols):
            pass
    async def scenario():
        fake = Fake()
        recoveries = []
        quotes = QuoteService(fake, ['PAYS.US'], cal, on_reconnect=lambda: recoveries.append(True))
        await quotes.connect()
        assert not recoveries
        old_callback = quotes.ctx.callback
        assert quotes.values['PAYS.US']['Intraday']['cumulative_volume'] == 100
        await quotes.disconnect()
        await quotes.connect()
        old_callback('PAYS.US', SimpleNamespace(timestamp=datetime.now(ET), last_done=10,
                                                volume=999, trade_session='TradeSession.Intraday'))
        await asyncio.sleep(0)
        assert quotes.values['PAYS.US']['Intraday']['cumulative_volume'] == 200
        assert fake.subscribed == [('PAYS.US',), ('PAYS.US',)]
        assert recoveries == [True]
        await quotes.disconnect()
    asyncio.run(scenario())


def test_snapshot_failure_does_not_claim_live(cal):
    class Context:
        def set_on_quote(self, callback):
            pass
    class Fake:
        def context(self):
            return Context()
        async def subscribe(self, ctx, symbols):
            pass
        async def snapshot(self, ctx, symbols):
            raise RuntimeError('snapshot failed')
    quotes = QuoteService(Fake(), ['PAYS.US'], cal)
    with pytest.raises(RuntimeError, match='No quote snapshot'):
        asyncio.run(quotes.connect())
    assert quotes.connection_health == 'CONNECTING'

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


def test_downloader_filters_forming_and_extended_reports_invalid(store, cal):
    ts = at('2026-09-18T09:30')
    class Fake:
        async def candles(self, *args):
            return [raw(ts), raw(ts + 300), raw(ts + 600, 'TradeSession.Pre')]
    result = asyncio.run(BarDownloader(Fake(), store, cal).fetch('PAYS.US', '5m', run_id='run', now=ts + 301))
    assert result['forming_count'] == 1
    assert len(result['rejected']) == 1
    assert [b.ts for b in store.bars('PAYS.US', '5m')] == [ts]


def seed(store, cal, now, days=300, symbol='PAYS.US', exhausted=False):
    dates = cal.completed_days(now, days)
    daily = [bar(cal.grid(d, '1d')[0][0], '1d', symbol) for d in dates]
    five = [bar(ts, '5m', symbol) for d in dates[-12:] for ts, _ in cal.grid(d, '5m')]
    store.upsert(daily + five, now)
    if exhausted:
        store.set_metadata(symbol, {'history_exhausted': True, 'first_daily_ts': daily[0].ts})
    return daily, five


def test_ready_and_deleted_json_rebuild_and_revoke(store, cal, tmp_path):
    now = at('2026-09-18T12:00')
    daily, five = seed(store, cal, now)
    path = tmp_path / 'readiness.json'
    validator = DataValidator(store, cal, path)
    state = validator.validate('PAYS.US', now)
    assert state['ready'] and state['alert_eligible']
    assert state['ready_through'] == '2026-09-17'
    validator.save()
    path.write_text('corrupt')
    assert DataValidator(store, cal, path).validate('PAYS.US', now)['ready']
    store.db.execute('DELETE FROM bars WHERE symbol=? AND timeframe=? AND ts=?', ('PAYS.US', '5m', five[10].ts))
    state = validator.validate('PAYS.US', now)
    assert not state['ready'] and not state['alert_eligible']
    assert five[10].ts in state['ready_checks'][1]['missing']


def test_short_history_requires_boundary_proof_then_degrades(store, cal, tmp_path):
    now = at('2026-09-18T12:00')
    daily, _ = seed(store, cal, now, days=20, symbol='BLSH.US')
    validator = DataValidator(store, cal, tmp_path / 'ready.json')
    assert not validator.validate('BLSH.US', now)['alert_eligible']
    store.set_metadata('BLSH.US', {'history_exhausted': True, 'first_daily_ts': daily[0].ts})
    state = validator.validate('BLSH.US', now)
    assert state['degraded_ready'] and state['alert_eligible'] and not state['ready']
    assert state['available_daily_days'] == 20


def test_full_ready_truncated_first_day_and_manifest_isolation(store, cal, tmp_path):
    now = at('2026-09-18T15:19')
    for tf in PHASES:
        start = cal.grid(date(2026, 9, 17), tf)[0][0]
        expected = cal.expected(tf, start, cal.latest_closed(tf, now), now)
        if tf != '1d':
            expected = expected[2:]
        batch = {'symbol': 'PAYS.US', 'timeframe': tf, 'run_id': 'run', 'as_of': now,
                 'returned_closed_ts': expected, 'rejected': []}
        store.upsert([bar(ts, tf) for ts in expected], now, batch)
    validator = DataValidator(store, cal, tmp_path / 'ready.json')
    assert validator.validate('PAYS.US', now, 'run')['full_ready']
    assert not validator.validate('PAYS.US', now, 'different')['full_ready']
    assert validator.validate('PAYS.US', now)['full_ready']
    store.db.execute("DELETE FROM bars WHERE timeframe='15m' AND ts=?", (at('2026-09-18T11:00'),))
    assert not validator.validate('PAYS.US', now)['full_ready']


def test_1000_window_prefix_repair(store, cal):
    now = at('2026-09-18T15:19')
    days = cal.completed_days(now, 12)
    expected = [ts for day in days for ts, _ in cal.grid(day, '5m')]
    store.upsert([bar(ts) for ts in expected[7:]], now)
    class Fake:
        calls = []
        async def candles(self, symbol, tf, count, before=None):
            self.calls.append((symbol, tf, count, before))
            return [raw(ts) for ts in expected[:7]]
    broker = Fake()
    asyncio.run(BarDownloader(broker, store, cal).repair_ready_window('PAYS.US', now))
    assert len(store.bars('PAYS.US', '5m')) == 936
    assert broker.calls[0][3] == expected[7] - 60


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


def test_failed_ticker_does_not_stop_phases_and_daily_phase_first(tmp_path, cal):
    class Fake:
        calls = []
        async def candles(self, symbol, tf, count=1000, before=None):
            self.calls.append((symbol, tf))
            if symbol == 'BLSH.US':
                raise RuntimeError('upstream error')
            return [raw(cal.latest_closed(tf, int(time.time())))]
    fake = Fake()
    service = DataService([Ticker('PAYS.US','PAYS','focus'), Ticker('BLSH.US','BLSH','wait')], tmp_path, fake, cal)
    try:
        asyncio.run(service.reconcile())
        assert service.initialized
        assert ('PAYS.US', '1h') in fake.calls
        first_five = next(i for i, (_, tf) in enumerate(fake.calls) if tf == '5m')
        assert ('BLSH.US', '1d') in fake.calls[:first_five]
        assert 'BLSH.US/1d' in service.errors
    finally:
        service.store.close()


def test_resume_after_multiple_boundaries_uses_refresh(tmp_path, cal):
    now = int(time.time())
    target = cal.latest_closed('5m', now)
    day = datetime.fromtimestamp(target, ET).date()
    grid = [ts for ts, end in cal.grid(day, '5m') if end <= now]
    if len(grid) < 4:
        day = cal.completed_days(now, 1)[-1]
        grid = [ts for ts, _ in cal.grid(day, '5m')]
        target = grid[-1]
    class Fake:
        calls = []
        async def candles(self, symbol, tf, count=1000, before=None):
            self.calls.append(count)
            return [raw(ts) for ts in grid[-4:]]
    fake = Fake()
    service = DataService([Ticker('PAYS.US','PAYS','focus')], tmp_path, fake, cal)
    try:
        service.store.upsert([bar(grid[-4])], now)
        asyncio.run(service.update_bar('PAYS.US', '5m', target))
        assert fake.calls == [1000]
        assert len(service.store.bars('PAYS.US', '5m')) == 4
    finally:
        service.store.close()


def test_rejected_revision_prevents_old_valid_row_from_passing(store, cal, tmp_path):
    now = at('2026-09-18T12:00')
    _, five = seed(store, cal, now)
    batch = {'symbol':'PAYS.US','timeframe':'5m','run_id':'r','as_of':now,
             'returned_closed_ts':[b.ts for b in five],
             'rejected':[{'ts':five[0].ts,'error':'Invalid OHLC range'}]}
    store.upsert([], now, batch)
    state = DataValidator(store, cal, tmp_path / 'ready.json').validate('PAYS.US', now)
    assert not state['alert_eligible']


def test_ready_expires_at_new_market_close(store, cal, tmp_path):
    now = at('2026-09-18T12:00')
    seed(store, cal, now)
    validator = DataValidator(store, cal, tmp_path / 'ready.json')
    assert validator.validate('PAYS.US', now)['ready']
    assert not validator.validate('PAYS.US', at('2026-09-18T16:00'))['ready']


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
        quotes = QuoteService(fake, ['PAYS.US'], cal)
        await quotes.connect()
        old_callback = quotes.ctx.callback
        assert quotes.values['PAYS.US']['Intraday']['cumulative_volume'] == 100
        await quotes.disconnect()
        await quotes.connect()
        old_callback('PAYS.US', SimpleNamespace(timestamp=datetime.now(ET), last_done=10,
                                                volume=999, trade_session='TradeSession.Intraday'))
        await asyncio.sleep(0)
        assert quotes.values['PAYS.US']['Intraday']['cumulative_volume'] == 200
        assert fake.subscribed == [('PAYS.US',), ('PAYS.US',)]
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


def test_offline_full_ready_cannot_mix_initialization_runs(store, cal, tmp_path):
    now = at('2026-09-18T15:19')
    for tf in PHASES:
        ts = cal.latest_closed(tf, now)
        batch = {'symbol':'PAYS.US','timeframe':tf,'run_id':'old','as_of':now,
                 'returned_closed_ts':[ts], 'rejected':[]}
        store.upsert([bar(ts,tf)],now,batch)
    newer = store.batch('PAYS.US','1d')
    newer.update(run_id='new',as_of=now+1)
    store.upsert([],now+1,newer)
    state=DataValidator(store,cal,tmp_path/'ready.json').validate('PAYS.US',now+1)
    assert not state['full_ready']

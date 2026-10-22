"""Current-window sync, budget isolation and retained official OHLC regressions."""
import asyncio
import json
import time

import pytest

from data_service.broker import Broker, RateLimiter
from data_service.calendar import PHASES
from data_service.config import Ticker
from data_service.downloader import BarDownloader
from data_service.service import DataService
from data_service.validator import DataValidator
from test_data_service import cal, store, at, bar, raw, install_batch


@pytest.mark.parametrize('prices', [(6.96, 7.27, 6.98, 7.18), (37.57, 37.19, 36, 36.37), (13, 9, 12, 11)])
def test_range_contradiction_is_retained_logged_and_never_retried(tmp_path, cal, prices):
    now = at('2026-09-18T09:35:02')
    ts = now - 302
    item = raw(ts)
    item.open, item.high, item.low, item.close = prices
    class Fake:
        calls = []
        async def candles(self, symbol, tf, count, **kwargs):
            self.calls.append(count)
            return [item, raw(ts + 300)]
    broker = Fake()
    service = DataService([Ticker('PAYS.US', 'PAYS', 'focus')], tmp_path, broker, cal, lambda: now)
    try:
        state = service.sync['PAYS.US', '5m']
        asyncio.run(service._execute(('PAYS.US', '5m')))
        assert state.complete and not state.pending and not state.error
        assert broker.calls == [1000]
        saved = service.store.bars('PAYS.US', '5m')[0]
        assert (saved.open, saved.high, saved.low, saved.close) == prices
        assert service.validator.check('PAYS.US', '5m', now)['complete']
        assert not service.status('PAYS.US', now)['errors']
        downloader = service.downloader
        asyncio.run(downloader.fetch('PAYS.US', '5m'))
        logs = [json.loads(line) for line in (tmp_path / 'invalid_ohlc.jsonl').read_text().splitlines()]
        assert len(logs) == 2  # Append only: repeat fetch is intentionally not deduplicated.
        assert logs[0]['start'] == ts and logs[0]['end'] == ts + 300
        assert logs[0]['fetched_at'] == now and logs[0]['session'] == 'Intraday'
        assert logs[0]['ohlcv']['open'] == str(prices[0])
        assert not (tmp_path / 'data_ready.json').exists()
    finally:
        service.store.close()


@pytest.mark.parametrize('kind', ['nan', 'negative_volume', 'duplicate', 'extended'])
def test_unplottable_response_preserves_old_window(store, cal, kind):
    ts = at('2026-09-18T09:30'); now = ts + 301
    store.upsert([bar(ts)], now)
    item = raw(ts)
    if kind == 'nan': item.open = float('nan')
    if kind == 'negative_volume': item.volume = -1
    if kind == 'extended': item.trade_session = 'Pre'
    class Fake:
        async def candles(self, *args, **kwargs): return [item, item] if kind == 'duplicate' else [item]
    with pytest.raises(ValueError):
        asyncio.run(BarDownloader(Fake(), store, cal, lambda: now).fetch('PAYS.US', '5m'))
    assert store.bars('PAYS.US', '5m') == [bar(ts)]
    assert not DataValidator(store, cal).check('PAYS.US', '5m', now)['complete']
    assert not (store.path.parent / 'invalid_ohlc.jsonl').exists()


def test_full_refresh_forgets_old_gap_and_normal_two_does_not_flip_readiness(tmp_path, cal):
    now = [at('2026-09-18T10:00:02')]
    class Fake:
        calls = []
        async def candles(self, symbol, tf, count, **kwargs):
            self.calls.append(count)
            target = cal.latest_closed(tf, now[0])
            return [raw(target), raw(target + 300)]
    broker = Fake(); service = DataService([Ticker('PAYS.US','PAYS','focus')], tmp_path, broker, cal, lambda: now[0])
    key = ('PAYS.US','5m')
    try:
        old = at('2025-09-18T09:30')
        service.store.upsert([bar(old)], now[0])
        asyncio.run(service._execute(key))
        assert broker.calls == [1000] and service.sync[key].complete
        assert len(service.store.window(*key)) == 1  # No traversal back to the old row.
        now[0] = at('2026-09-18T10:05:02')
        service._schedule(now[0])
        assert not service.sync[key].refresh and service.sync[key].complete
        asyncio.run(service._execute(key))
        assert broker.calls == [1000, 2]
        now[0] = at('2026-09-18T10:20:02')
        service._schedule(now[0])
        assert service.sync[key].refresh
        asyncio.run(service._execute(key))
        assert broker.calls == [1000, 2, 1000]
        assert service.sync[key].complete
    finally: service.store.close()


def test_retry_rounds_are_bounded_until_next_five_minute_boundary(tmp_path, cal):
    now = [at('2026-09-18T10:01')]
    class Fake:
        fail = True
        calls = []
        async def candles(self, symbol, tf, count, **kwargs):
            self.calls.append(count)
            if self.fail: raise TimeoutError('Request failed')
            return [raw(cal.latest_closed(tf, now[0]))]
    broker = Fake(); service = DataService([Ticker('PAYS.US','PAYS','focus')],tmp_path,broker,cal,lambda:now[0])
    key = ('PAYS.US','5m'); state = service.sync[key]
    try:
        for i in range(4):
            asyncio.run(service._execute(key))
            assert state.alert == (i == 3)
        assert broker.calls == [1000]*4
        assert state.due == at('2026-09-18T10:05:02')
        service._schedule(at('2026-09-18T10:04:59'))
        assert state.due == at('2026-09-18T10:05:02')
        now[0] = int(state.due)
        for _ in range(3): asyncio.run(service._execute(key))
        assert len(broker.calls) == 7 and state.due == at('2026-09-18T10:10:02')
        now[0] = int(state.due); broker.fail = False
        asyncio.run(service._execute(key))
        assert state.complete and not state.alert and not service.status(key[0],now[0])['errors']
    finally: service.store.close()


def test_missing_latest_closed_target_triggers_full_retry(tmp_path, cal):
    now = at('2026-09-18T09:45:02'); start = at('2026-09-18T09:30')
    class Fake:
        calls = []
        async def candles(self, symbol, tf, count, **kwargs):
            self.calls.append(count)
            return [raw(start), raw(start+300)]
    broker=Fake(); service=DataService([Ticker('PAYS.US','PAYS','focus')],tmp_path,broker,cal,lambda:now)
    try:
        key=('PAYS.US','5m')
        asyncio.run(service._execute(key))
        assert 'Missing latest closed' in service.sync[key].error
        assert service.sync[key].refresh and not service.sync[key].alert
        assert service.validator.check(*key,now)['missing'] == [start+600]
    finally: service.store.close()


def test_recovery_reuses_successful_inflight_history_request(tmp_path, cal):
    now=at('2026-09-18T10:01')
    class Fake:
        async def candles(self, symbol, tf, count, **kwargs):
            service.recover()
            return [raw(cal.latest_closed(tf,now))]
    service=DataService([Ticker('PAYS.US','PAYS','focus')],tmp_path,Fake(),cal,lambda:now)
    try:
        asyncio.run(service._execute(('PAYS.US','5m')))
        state=service.sync['PAYS.US','5m']
        assert not state.pending and not state.refresh and state.complete
    finally: service.store.close()


def test_partial_and_full_status_and_no_redundant_price_revision(tmp_path, cal):
    now=at('2026-09-18T10:01')
    service=DataService([Ticker('PAYS.US','PAYS','focus')],tmp_path,object(),cal,lambda:now)
    try:
        assert service.status('PAYS.US',now)['stage']=='loading'
        for tf in ('1d','5m'): service.sync['PAYS.US',tf].complete=True
        assert service.status('PAYS.US',now)['stage']=='basic'
        for state in service.sync.values(): state.complete=True
        assert service.status('PAYS.US',now)['stage']=='full'
        rows=install_batch(service.store,cal,now)
        rev=service.store.revisions['PAYS.US','5m']
        service.store.upsert(rows,now)
        assert service.store.revisions['PAYS.US','5m']==rev
    finally: service.store.close()


def test_opening_does_not_reset_stream_or_loaded_windows(tmp_path, cal):
    now = [at('2026-09-18T09:29')]
    service = DataService([Ticker('PAYS.US', 'PAYS', 'focus')], tmp_path, object(), cal, lambda: now[0])
    try:
        for tf, state in ((key[1], state) for key, state in service.sync.items()):
            state.pending = state.refresh = False
            state.complete = True
            state.target = cal.latest_closed(tf, now[0])
        now[0] = at('2026-09-18T09:30')
        service._schedule(now[0])
        assert not service.quotes.candle_refresh and not service.quotes.changed.is_set()
        assert all(state.complete and not state.pending for state in service.sync.values())
    finally:
        service.store.close()


@pytest.mark.parametrize('restart, pending, refresh', [
    ('2026-09-18T10:04:59', (), ()),
    ('2026-09-18T10:05:02', ('5m',), ()),
    ('2026-09-18T10:20:02', ('5m', '15m'), ('5m',)),
    ('2026-09-18T10:30:02', ('5m', '15m', '30m', '1h'), ('5m', '15m')),
])
def test_restart_restores_each_official_window_and_only_schedules_missing_boundaries(tmp_path, cal, restart, pending, refresh):
    initial = at('2026-09-18T10:01')
    service = DataService([Ticker('PAYS.US', 'PAYS', 'focus')], tmp_path, object(), cal, lambda: initial)
    for tf in PHASES:
        install_batch(service.store, cal, initial, tf=tf)
    service.store.close()
    service = DataService([Ticker('PAYS.US', 'PAYS', 'focus')], tmp_path, object(), cal, lambda: at(restart))
    try:
        assert all(state.complete for state in service.sync.values())
        assert {tf for (_, tf), state in service.sync.items() if state.pending} == set(pending)
        assert {tf for (_, tf), state in service.sync.items() if state.refresh} == set(refresh)
        # A newer SDK provisional bar cannot advance the official repair watermark.
        service.charts.apply_candle('PAYS.US', '5m', {'time': cal.latest_closed('5m', at(restart)),
            'open': 10, 'high': 12, 'low': 9, 'close': 11, 'volume': 20})
        assert service.cached_state('PAYS.US', '5m').target == cal.latest_closed('5m', initial)
        service.recover()
        assert {tf for (_, tf), state in service.sync.items() if state.pending} == set(pending)
    finally:
        service.store.close()


def test_midnight_preload_runs_without_unlock_and_no_extra_preopen_refresh(tmp_path, cal):
    now = [at('2026-09-17T23:59:59')]
    service = DataService([Ticker('PAYS.US', 'PAYS', 'focus')], tmp_path, object(), cal, lambda: now[0])
    try:
        for tf in PHASES:
            install_batch(service.store, cal, now[0], tf=tf)
            service.sync['PAYS.US', tf] = service.cached_state('PAYS.US', tf)
        now[0] = at('2026-09-18T00:00:00')
        service._schedule(now[0])
        assert all(state.pending and state.refresh and not state.complete for state in service.sync.values())
        for tf in PHASES:
            install_batch(service.store, cal, now[0], tf=tf)
            service.sync['PAYS.US', tf] = service.cached_state('PAYS.US', tf)
        now[0] = at('2026-09-18T09:25')
        service._schedule(now[0])
        assert all(state.complete and not state.pending for state in service.sync.values())
        now[0] = at('2026-09-18T16:00:02')
        for tf in PHASES:
            install_batch(service.store, cal, now[0], tf=tf)
            service.sync['PAYS.US', tf] = service.cached_state('PAYS.US', tf)
        for stamp in ('2026-09-19T10:00', '2026-09-20T10:00'):
            now[0] = at(stamp)
            service._schedule(now[0])
            assert service.session[0] == '2026-09-18'
            assert all(state.complete and not state.pending for state in service.sync.values())
        now[0] = at('2026-09-21T00:00')
        service._schedule(now[0])
        assert all(state.refresh and state.pending and not state.complete for state in service.sync.values())
        assert service.store.latest('PAYS.US', '5m') == at('2026-09-18T15:55')
    finally:
        service.store.close()


def test_reserved_rate_and_concurrency_admit_two_interactive_requests():
    async def scenario():
        limiter=RateLimiter(10,.08)
        for _ in range(8): await limiter.wait(background=True)
        waiting=asyncio.create_task(limiter.wait(background=True))
        await asyncio.sleep(0)
        await asyncio.wait_for(asyncio.gather(limiter.wait(),limiter.wait()),.03)
        assert not waiting.done()
        await waiting
        broker=object.__new__(Broker)
        broker.timeout,broker.secrets=2,()
        broker.limiter,broker.inflight,broker.background=RateLimiter(),asyncio.Semaphore(5),asyncio.Semaphore(3)
        gate=asyncio.Event(); started=[]
        async def method(label):
            started.append(label)
            await gate.wait()
        tasks=[asyncio.create_task(broker.call(method,'bg',background=True)) for _ in range(8)]
        await asyncio.sleep(.01)
        assert started==['bg']*3
        tasks += [asyncio.create_task(broker.call(method,'selected')) for _ in range(2)]
        await asyncio.sleep(.01)
        assert started.count('selected')==2 and len(started)==5
        gate.set(); await asyncio.gather(*tasks)
    asyncio.run(scenario())


def test_scheduler_selection_priority_and_bad_symbol_isolation(tmp_path,cal):
    now=at('2026-09-18T10:01')
    class Fake:
        calls=[]
        active=maximum=0
        async def candles(self,symbol,tf,count,**kwargs):
            self.calls.append((symbol,tf)); self.active+=1; self.maximum=max(self.maximum,self.active)
            try:
                await asyncio.sleep(.005)
                if symbol=='BLSH.US': raise TimeoutError('unavailable')
                return [raw(cal.latest_closed(tf,now))]
            finally: self.active-=1
    broker=Fake();service=DataService([Ticker('PAYS.US','PAYS','focus'),Ticker('BLSH.US','BLSH','wait')],tmp_path,broker,cal,lambda:now)
    for state in service.sync.values(): state.limit=1
    try:
        asyncio.run(asyncio.wait_for(service.reconcile(),2))
        assert broker.calls[:2]==[('PAYS.US','5m'),('PAYS.US','1d')]
        assert broker.maximum==5
        assert service.status('PAYS.US',now)['stage']=='full'
        assert len(service.status('BLSH.US',now)['errors'])==len(PHASES)
        service.recover()
        service.select('BLSH.US','2h')
        assert not service.sync['PAYS.US', '5m'].pending
        assert service.priority(('BLSH.US','5m'))<service.priority(('BLSH.US','15m'))
    finally: service.store.close()


def test_historical_gaps_inside_recent_response_are_accepted(tmp_path, cal):
    now = at('2026-09-18T09:45:02'); start = at('2026-09-18T09:30')
    class Fake:
        async def candles(self, *args, **kwargs): return [raw(start), raw(start+600)]
    service = DataService([Ticker('PAYS.US','PAYS','focus')], tmp_path, Fake(), cal, lambda:now)
    try:
        key = ('PAYS.US','5m')
        asyncio.run(service._execute(key))
        assert service.sync[key].complete and not service.sync[key].pending
        assert service.validator.check(*key, now)['missing'] == []
    finally: service.store.close()

import asyncio
import json
import sqlite3
import time
from datetime import datetime
from types import SimpleNamespace

import pytest
from aiohttp import ClientSession, web

from data_service.calendar import PHASES
from data_service.charts import ChartCache
from data_service.config import Ticker
from data_service.downloader import BarDownloader
from data_service.http_api import create_app
from data_service.indicators import series, preview, daily_summary
from data_service.service import DataService, Job
from data_service.store import BarStore, Bar
from data_service.broker import RateLimiter
from test_data_service import cal, store, at, bar, raw, install_batch


def quote(ts, price=11, volume=100, session='Intraday'):
    return {'timestamp': ts, 'last_price': price, 'cumulative_volume': volume, 'trade_session': session}


def test_active_five_restart_boundary_and_official_replacement(store, cal):
    cache = ChartCache(store, cal)
    now = at('2026-09-18T10:03')
    start = at('2026-09-18T10:00')
    cache.apply_quote('PAYS.US', quote(now, 15))
    cache.apply_quote('PAYS.US', quote(now + 1, 17))
    cache.apply_quote('PAYS.US', quote(now + 2, 14))
    active, _ = cache.forming('PAYS.US', '5m', now + 2)
    assert (active['open'], active['high'], active['low'], active['close']) == (15, 17, 14, 14)
    assert not store.bars('PAYS.US', '5m')
    assert cache.forming('PAYS.US', '5m', start + 300)[0] is None
    store.upsert([bar(start)], start + 301)
    cache.apply_quote('PAYS.US', quote(start + 301, 20))
    view = cache.chart('PAYS.US', '5m', start + 301)
    assert view['bars'][-1]['open'] == 10
    assert view['active']['time'] == start + 300 and view['active']['open'] == 20
    cache.apply_quote('PAYS.US', quote(start + 302, 500, session='Post'))
    assert cache.forming('PAYS.US', '5m', start + 302)[0]['close'] == 20
    assert cache.forming('PAYS.US', '5m', at('2026-09-18T16:00'))[0] is None


def test_larger_candle_rebuilds_from_official_five(store, cal):
    cache = ChartCache(store, cal)
    now = at('2026-09-18T10:13')
    opened = at('2026-09-18T10:00')
    cache.apply_quote('PAYS.US', quote(now, 20))
    assert cache.forming('PAYS.US', '15m', now)[0]['open'] == 20
    store.upsert([Bar('PAYS.US', '5m', opened, 10, 30, 8, 25, 20),
                  Bar('PAYS.US', '5m', opened + 300, 25, 26, 18, 19, 30)], now)
    active, _ = cache.forming('PAYS.US', '15m', now)
    assert (active['open'], active['high'], active['low'], active['close']) == (10, 30, 8, 20)
    daily, _ = cache.forming('PAYS.US', '1d', now)
    assert daily['volume'] == 100


def test_volume_waits_for_whole_prefix_and_never_fakes_zero(store, cal):
    cache = ChartCache(store, cal)
    now = at('2026-09-18T09:41')
    opened = at('2026-09-18T09:30')
    cache.apply_quote('PAYS.US', quote(now, volume=100))
    store.upsert([bar(opened, volume=20)], now)
    assert cache.forming('PAYS.US', '5m', now)[0]['volume'] is None
    store.upsert([bar(opened + 300, volume=30)], now)
    assert cache.forming('PAYS.US', '5m', now)[0]['volume'] == 50
    cache.apply_quote('PAYS.US', quote(now + 1, volume=40))
    active, warnings = cache.forming('PAYS.US', '5m', now + 1)
    assert active['volume'] is None and warnings
    cache.apply_quote('PAYS.US', quote(at('2026-09-21T09:31'), volume=17))
    assert cache.forming('PAYS.US', '5m', at('2026-09-21T09:31'))[0]['volume'] == 17


def test_live_ema_uses_closed_anchor_and_sma_requires_50():
    rows = [{'time': i, 'close': float(i)} for i in range(1, 50)]
    base = series(rows)
    assert base['series']['sma50'] == []
    active = {'time': 50, 'close': 50}
    first = preview(base, active)
    for _ in range(100):
        assert preview(base, active) == first
    assert first['sma50']['value'] == 25.5
    assert first['ema10']['value'] == pytest.approx(series(rows + [active])['ema'][10])
    assert len(series(rows)['series']['ema10']) == 40


def test_turnover_migration_and_indicator_invalidation(tmp_path, cal):
    path = tmp_path / 'old.sqlite3'
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE bars(symbol TEXT, timeframe TEXT, ts INTEGER, open REAL, high REAL, low REAL, close REAL, volume INTEGER, PRIMARY KEY(symbol,timeframe,ts))')
    db.close()
    store = BarStore(path, cal, {'PAYS.US'})
    try:
        now = at('2026-09-18T12:00')
        days = cal.completed_days(now, 20)
        rows = [Bar('PAYS.US', '1d', cal.grid(d, '1d')[0][0], 10, 12, 8, 11, 100, 1234) for d in days]
        store.upsert(rows, now)
        cache = ChartCache(store, cal)
        assert cache.summary('PAYS.US', now)['adv20'] == 1234
        assert cache.summary('PAYS.US', now)['adr20'] == 50
        before = cache.closed('PAYS.US', '1d')[2]['ema'][10]
        old = rows[-1]
        store.upsert([Bar(old.symbol, old.timeframe, old.ts, 10, 21, 8, 20, 100, None)], now)
        assert cache.closed('PAYS.US', '1d')[2]['ema'][10] != before
        assert cache.summary('PAYS.US', now)['estimated']
    finally:
        store.close()


def test_summary_does_not_fill_missing_day_with_older_data(store, cal):
    now = at('2026-09-18T12:00')
    days = cal.completed_days(now, 21)
    rows = [bar(cal.grid(d, '1d')[0][0], '1d') for d in days if d != days[-3]]
    assert daily_summary(rows, cal, now)['samples'] == 19


def test_bad_turnover_falls_back_without_rejecting_valid_ohlc(store, cal):
    ts = at('2026-09-18T09:30')
    class Fake:
        async def candles(self, *args):
            return [SimpleNamespace(**vars(raw(ts)), turnover=float('nan'))]
    batch = asyncio.run(BarDownloader(Fake(), store, cal).fetch('PAYS.US', '5m', now=ts + 300))
    assert not batch['rejected']
    assert store.bars('PAYS.US', '5m')[0].turnover is None


def test_priority_tracks_selection_and_deadlines(tmp_path, cal):
    service = DataService([Ticker('PAYS.US','PAYS','focus'), Ticker('BLSH.US','BLSH','wait')], tmp_path, calendar=cal)
    try:
        service.select('BLSH.US', '1h')
        jobs = [Job('PAYS.US','5m',True), Job('BLSH.US','1h',True), Job('PAYS.US','15m',False)]
        assert sorted(jobs, key=service.priority) == [jobs[2], jobs[1], jobs[0]]
        with pytest.raises(ValueError):
            service.select('NO.US', '5m')
    finally:
        service.store.close()


def test_global_limiter_rolling_window():
    async def scenario():
        limiter = RateLimiter(limit=3, window=0.03)
        times = []
        async def call():
            await limiter.wait()
            times.append(time.monotonic())
        await asyncio.gather(*(call() for _ in range(9)))
        assert times[3] - times[0] >= 0.029
        assert times[6] - times[3] >= 0.029
    asyncio.run(scenario())


def test_concurrent_history_cap_and_no_global_phase_barrier(tmp_path, cal, monkeypatch):
    monkeypatch.setattr('data_service.service.RETRY_DELAYS', ())
    class Fake:
        active = 0
        maximum = 0
        async def candles(self, symbol, tf, count=1000, before=None):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                await asyncio.sleep(0.005)
                if before is not None:
                    return []
                return [raw(cal.latest_closed(tf, int(time.time())))]
            finally:
                self.active -= 1
    fake = Fake()
    service = DataService([Ticker('PAYS.US','PAYS','focus'), Ticker('BLSH.US','BLSH','wait')], tmp_path, fake, cal)
    try:
        asyncio.run(service.reconcile())
        assert fake.maximum == 5
        assert service.initialized
    finally:
        service.store.close()


def test_lag_warning_from_close_time_after_initial_load(tmp_path, cal):
    service = DataService([Ticker('PAYS.US','PAYS','focus')], tmp_path, calendar=cal)
    try:
        now = at('2026-09-18T10:04')
        for tf in PHASES:
            install_batch(service.store, cal, now, tf=tf)
        assert service.status('PAYS.US', now)['ready']
        assert not any('延迟' in w for w in service.status('PAYS.US', at('2026-09-18T10:05:14'))['warnings'])
        late = service.status('PAYS.US', at('2026-09-18T10:05:16'))
        assert any('5m: 官方' in w for w in late['warnings'])
        assert not late['ready']
        service.store.upsert([bar(at('2026-09-18T10:00'))], at('2026-09-18T10:05:17'))
        assert not any('5m: 官方' in w for w in service.status('PAYS.US', at('2026-09-18T10:05:17'))['warnings'])
    finally:
        service.store.close()


def test_http_ws_snapshot_switch_origin_and_reconnect(tmp_path, cal):
    service = DataService([Ticker('PAYS.US','PAYS','focus'), Ticker('BLSH.US','BLSH','wait')], tmp_path, calendar=cal)
    async def scenario():
        runner = web.AppRunner(create_app(service))
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        try:
            async with ClientSession() as client:
                async with client.get(base + '/') as response:
                    assert response.status == 200 and 'Market Monitor' in await response.text()
                async with client.get(base + '/v1/chart?symbol=NO.US') as response:
                    assert response.status == 400
                async with client.get(base + '/v1/chart?symbol=PAYS.US&timeframe=5m') as response:
                    payload = await response.json()
                    assert 'indicators' in payload['charts']['1d']
                async with client.get(base + '/v1/stream', headers={'Origin':'https://untrusted.example'}) as response:
                    assert response.status == 403
                async with client.ws_connect(base + '/v1/stream') as ws:
                    initial = await ws.receive_json(timeout=2)
                    assert 'bars' in initial['charts']['5m']
                    await ws.send_json({'type':'select','symbol':'BLSH.US','timeframe':'1h','request_id':12})
                    while True:
                        message = await ws.receive_json(timeout=2)
                        if message['request_id'] == 12:
                            break
                    assert message['symbol'] == 'BLSH.US' and 'bars' in message['charts']['1h']
                    message = await ws.receive_json(timeout=2)
                    assert 'bars' not in message['charts']['1h']
                async with client.ws_connect(base + '/v1/stream') as ws:
                    message = await ws.receive_json(timeout=2)
                    assert 'bars' in message['charts']['1h']
        finally:
            await runner.cleanup()
    try:
        asyncio.run(scenario())
    finally:
        service.store.close()


def test_rejected_prefix_cannot_supply_live_volume(store, cal):
    now = at('2026-09-18T09:41')
    rows = install_batch(store, cal, now, count=2)
    batch = store.batch('PAYS.US', '5m')
    batch['rejected'] = [{'ts': rows[0].ts, 'error':'official revision invalid'}]
    store.upsert([], now, batch)
    cache = ChartCache(store, cal)
    cache.apply_quote('PAYS.US', quote(now))
    assert cache.forming('PAYS.US', '5m', now)[0]['volume'] is None


def test_snapshot_restores_extended_sessions_without_fake_pushes(cal):
    from data_service.quotes import QuoteService
    now = int(time.time()) - 3
    class Fake:
        async def snapshot(self, ctx, symbols):
            return [SimpleNamespace(symbol='PAYS.US', timestamp=datetime.fromtimestamp(now),
                     last_done=11, volume=100,
                     post_market_quote=SimpleNamespace(timestamp=datetime.fromtimestamp(now+1), last_done=12, volume=7),
                     pre_market_quote=None)]
    q = QuoteService(Fake(), ['PAYS.US'], cal)
    asyncio.run(q._snapshot(None, ['PAYS.US']))
    assert q.values['PAYS.US']['Post']['last_price'] == 12
    assert q.values['PAYS.US']['Intraday']['cumulative_volume'] == 100
    assert q.push_count == 0


def test_incremental_valid_revision_clears_rejection(store, cal):
    now = at('2026-09-18T09:41')
    rows = install_batch(store, cal, now, count=2)
    batch = store.batch('PAYS.US', '5m')
    batch['rejected'] = [{'ts': rows[0].ts, 'error':'invalid'}]
    store.upsert([], now, batch)
    class Fake:
        async def candles(self, *args): return [raw(rows[0].ts)]
    asyncio.run(BarDownloader(Fake(), store, cal).fetch('PAYS.US', '5m', count=2, now=now))
    assert store.batch('PAYS.US', '5m')['rejected'] == []


def test_broker_request_budget_shared_by_all_callers():
    from data_service.broker import Broker
    async def scenario():
        broker = object.__new__(Broker)
        broker.timeout, broker.secrets = 1, ()
        broker.limiter, broker.inflight = RateLimiter(10, 0.04), asyncio.Semaphore(5)
        active = maximum = 0
        started = []
        async def method():
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            started.append(time.monotonic())
            await asyncio.sleep(0.005)
            active -= 1
        await asyncio.gather(*(broker.call(method) for _ in range(25)))
        assert maximum == 5
        assert all(started[i + 10] - started[i] >= 0.039 for i in range(15))
    asyncio.run(scenario())


def test_recent_window_gap_uses_history_prefix(tmp_path, cal, monkeypatch):
    now = at('2026-09-18T10:00')
    monkeypatch.setattr('data_service.service.time.time', lambda: now)
    opened = at('2026-09-18T09:30')
    class Fake:
        calls = []
        async def candles(self, symbol, tf, count=1000, before=None):
            self.calls.append((count,before))
            times = [opened+1200, opened+1500] if before is None else [opened+300,opened+600,opened+900]
            return [raw(t) for t in times]
    fake = Fake()
    service = DataService([Ticker('PAYS.US','PAYS','focus')], tmp_path, fake, cal)
    try:
        service.store.upsert([bar(opened)], now)
        asyncio.run(service.update_bar('PAYS.US','5m',opened+1500))
        assert fake.calls == [(1000,None),(3,opened+1140)]
        assert len(service.store.bars('PAYS.US','5m')) == 6
    finally:
        service.store.close()


def test_lag_warning_does_not_reset_at_next_boundary(tmp_path, cal):
    service = DataService([Ticker('PAYS.US','PAYS','focus')], tmp_path, calendar=cal)
    try:
        now = at('2026-09-18T10:04')
        for tf in PHASES:
            install_batch(service.store, cal, now, tf=tf)
        service.status('PAYS.US', now)
        service.status('PAYS.US', at('2026-09-18T10:05:16'))
        assert any('5m: 官方' in w for w in service.status('PAYS.US', at('2026-09-18T10:10:01'))['warnings'])
    finally:
        service.store.close()


def test_exhausted_initial_sync_recovers_without_new_boundary(tmp_path, cal, monkeypatch):
    now = at('2026-09-18T10:04')
    monkeypatch.setattr('data_service.service.time.time', lambda: now)
    class RecoveringBroker:
        offline = True
        async def candles(self, symbol, tf, count=1000, before=None):
            if self.offline:
                raise TimeoutError('offline')
            return [raw(cal.latest_closed(tf, now))]
    broker = RecoveringBroker()
    service = DataService([Ticker('PAYS.US','PAYS','focus')], tmp_path, broker, cal)
    key = ('PAYS.US', '5m')
    try:
        service.initial_done = {(key[0], tf) for tf in PHASES}
        job = Job(*key, initial=True, attempt=4)
        service.jobs[key] = job
        asyncio.run(service._execute(key, job))
        service._schedule(now + 29)
        assert key not in service.jobs
        service._schedule(now + 30, initial_only=True)
        assert key not in service.jobs  # One-shot reconcile remains bounded.
        service._schedule(now + 30)
        assert service.jobs[key].initial  # Must establish this run's batch evidence.
        broker.offline = False
        asyncio.run(service._execute(key, service.jobs[key]))
        assert service.validate(key[0], now)['timeframes']['5m']['loaded']
        assert key not in service.retry_pairs
        assert key not in service.retry_after
    finally:
        service.store.close()

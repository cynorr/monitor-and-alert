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
from data_service.service import DataService
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
    active = cache.forming('PAYS.US', '5m', now + 2)
    assert (active['open'], active['high'], active['low'], active['close']) == (15, 17, 14, 14)
    assert not store.bars('PAYS.US', '5m')
    assert cache.forming('PAYS.US', '5m', start + 300) is None
    store.upsert([bar(start)], start + 301)
    cache.apply_quote('PAYS.US', quote(start + 301, 20))
    view = cache.chart('PAYS.US', '5m', start + 301)
    assert view['bars'][-1]['open'] == 10
    assert view['active']['time'] == start + 300 and view['active']['open'] == 20
    cache.apply_quote('PAYS.US', quote(start + 302, 500, session='Post'))
    assert cache.forming('PAYS.US', '5m', start + 302)['close'] == 20
    assert cache.forming('PAYS.US', '5m', at('2026-09-18T16:00')) is None


def test_larger_candle_rebuilds_from_official_five(store, cal):
    cache = ChartCache(store, cal)
    now = at('2026-09-18T10:13')
    opened = at('2026-09-18T10:00')
    cache.apply_quote('PAYS.US', quote(now, 20))
    assert cache.forming('PAYS.US', '15m', now)['open'] == 20
    store.upsert([Bar('PAYS.US', '5m', opened, 10, 30, 8, 25, 20),
                  Bar('PAYS.US', '5m', opened + 300, 25, 26, 18, 19, 30)], now)
    active = cache.forming('PAYS.US', '15m', now)
    assert (active['open'], active['high'], active['low'], active['close']) == (10, 30, 8, 20)
    daily = cache.forming('PAYS.US', '1d', now)
    assert daily['volume'] == 100


def test_volume_waits_for_whole_prefix_and_never_fakes_zero(store, cal):
    cache = ChartCache(store, cal)
    now = at('2026-09-18T09:41')
    opened = at('2026-09-18T09:30')
    cache.apply_quote('PAYS.US', quote(now, volume=100))
    store.upsert([bar(opened, volume=20)], now)
    assert cache.forming('PAYS.US', '5m', now)['volume'] is None
    store.upsert([bar(opened + 300, volume=30)], now)
    assert cache.forming('PAYS.US', '5m', now)['volume'] == 50
    cache.apply_quote('PAYS.US', quote(now + 1, volume=40))
    active = cache.forming('PAYS.US', '5m', now + 1)
    assert active['volume'] is None
    cache.apply_quote('PAYS.US', quote(at('2026-09-21T09:31'), volume=17))
    assert cache.forming('PAYS.US', '5m', at('2026-09-21T09:31'))['volume'] == 17


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
        async def candles(self, *args, **kwargs):
            return [SimpleNamespace(**vars(raw(ts)), turnover=float('nan'))]
    batch = asyncio.run(BarDownloader(Fake(), store, cal, clock=lambda: ts + 300).fetch('PAYS.US', '5m'))
    assert not batch['rejected']
    assert store.bars('PAYS.US', '5m')[0].turnover is None


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
                    assert response.status == 200 and '<title>Charts</title>' in await response.text()
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
    assert cache.forming('PAYS.US', '5m', now)['volume'] is None


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
        async def candles(self, *args, **kwargs): return [raw(rows[0].ts)]
    asyncio.run(BarDownloader(Fake(), store, cal, clock=lambda: now).fetch('PAYS.US', '5m', count=2))
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

import asyncio
from datetime import datetime

import pytest
from aiohttp import ClientSession, web

from data_service.calendar import ET, PHASES
from data_service.config import Ticker
from simulator.market import Market, SessionClock
from simulator.server import create_simulation
from test_data_service import cal, at


def test_simulated_periods_and_quotes_share_ohlcv(cal):
    now = at('2026-09-18T11:13')
    market = Market(['PAYS.US'], cal, lambda: now)
    start = at('2026-09-18T10:30')
    five = [market.bar('PAYS.US', '5m', start + i * 300) for i in range(6)]
    half = market.bar('PAYS.US', '30m', start)
    assert half.open == five[0].open and half.close == five[-1].close
    assert half.high == max(b.high for b in five) and half.low == min(b.low for b in five)
    assert half.volume == sum(b.volume for b in five)
    assert half.turnover == pytest.approx(sum(b.turnover for b in five))
    raw = market.quote('PAYS.US', now)
    opened = at('2026-09-18T09:30')
    prefix = sum(market.bar('PAYS.US', '5m', t).volume for t in range(opened, at('2026-09-18T11:10'), 300))
    partial = market.segment('PAYS.US', datetime.fromtimestamp(now, ET).date(), at('2026-09-18T11:10'), now)
    assert raw['volume'] - prefix == partial[4]
    assert float(raw['last_done']) == pytest.approx(partial[3], abs=1e-6)


def test_simulator_returns_1000_closed_bars_all_periods(cal):
    now = at('2026-09-18T13:44:45')
    market = Market(['PAYS.US'], cal, lambda: now)
    async def scenario():
        for tf in PHASES:
            bars = await market.candles('PAYS.US', tf)
            assert len(bars) == 1000
            times = [int(b.timestamp.timestamp()) for b in bars]
            assert times == sorted(set(times))
            assert times[-1] == cal.latest_closed(tf, now)
            assert all(cal.bar_end(t, tf) <= now for t in times)
        with pytest.raises(ValueError):
            await market.candles('NOT_ALLOWED.US', '5m')
    asyncio.run(scenario())


def test_actual_scheduler_crosses_boundaries_and_rollover(tmp_path, cal):
    now = [at('2026-09-18T13:44:45')]
    service = create_simulation([Ticker('PAYS.US','PAYS','focus')], tmp_path, cal, lambda: now[0])
    async def wait_ready():
        for _ in range(500):
            state = service.validate('PAYS.US')
            if all(c['complete'] for c in state.values()):
                return state
            await asyncio.sleep(.01)
        raise AssertionError(state)
    async def scenario():
        await service.reconcile()
        assert all(c['complete'] for c in service.validate('PAYS.US').values())
        task = asyncio.create_task(service.scheduler())
        try:
            for moment in ['2026-09-18T13:45:03','2026-09-18T14:00:03','2026-09-18T14:30:03','2026-09-21T09:35:03']:
                now[0] = at(moment)
                service.quotes.tick()
                state = await wait_ready()
                assert all(not c['errors'] for c in state.values())
                quote = service.quote('PAYS.US', now[0])['regular']
                assert quote['prev_close'] > 0
                for tf in PHASES:
                    view = service.charts.chart('PAYS.US', tf, now[0])
                    assert view['bars'][-1]['time'] == cal.latest_closed(tf, now[0])
                    assert view['active'] is not None and view['active']['volume'] >= 0
                view = service.view('PAYS.US', '5m')
                assert view['mode'] == 'simulation' and not view['status']['errors']
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    try:
        asyncio.run(scenario())
    finally:
        service.store.close()


def test_clock_skips_weekend_and_early_close(cal):
    clock = SessionClock(cal, at('2026-09-18T15:59:50'))
    clock.advance(20)
    assert clock.value == at('2026-09-21T09:30:10')
    clock = SessionClock(cal, at('2026-11-27T12:59:50'))
    clock.advance(20)
    assert clock.value == at('2026-11-30T09:30:10')
    clock.advance(6.5*3600)
    assert clock.value == at('2026-12-01T09:30:10')


def test_change_baseline_remains_previous_day_after_daily_close(tmp_path, cal):
    now = [at('2026-09-18T15:59:50')]
    service = create_simulation([Ticker('PAYS.US','PAYS','focus')], tmp_path, cal, lambda: now[0])
    try:
        now[0] = at('2026-09-18T16:01')
        asyncio.run(service.reconcile())
        rows = service.store.bars('PAYS.US','1d',limit=2)
        assert rows[-1].ts == at('2026-09-18T00:00')
        quote = service.quote('PAYS.US',now[0])['regular']
        assert quote['prev_close'] == rows[0].close
        assert quote['prev_close'] != rows[-1].close
        assert quote['bid_price'] < quote['last_price'] < quote['ask_price']
    finally:
        service.store.close()

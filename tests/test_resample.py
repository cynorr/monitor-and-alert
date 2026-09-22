from dataclasses import replace
from datetime import date

import pytest

from data_service.charts import ChartCache, bar_row
from data_service.resample import resample
from test_data_service import cal, store, at, bar


@pytest.mark.parametrize('day', [date(2026,9,18), date(2026,11,27), date(2026,3,9)])
@pytest.mark.parametrize('tf', ['15m','30m','1h','2h','4h'])
def test_all_periods_share_session_alignment_and_exact_totals(cal,day,tf):
    grid=cal.grid(day,'5m'); end=cal.session(day)[1]
    rows=[bar_row(replace(bar(ts),open=10+i,high=12+i,low=9+i,close=11+i,volume=i+1,turnover=float(100+i))) for i,(ts,_) in enumerate(grid)]
    converted=resample(rows,tf,cal,end)
    assert [r['time'] for r in converted]==[ts for ts,_ in cal.grid(day,tf)]
    assert sum(r['volume'] for r in converted)==sum(r['volume'] for r in rows)
    assert sum(r['turnover'] for r in converted)==sum(r['turnover'] for r in rows)
    assert converted[0]['open']==rows[0]['open'] and converted[-1]['close']==rows[-1]['close']
    assert max(r['high'] for r in converted)==max(r['high'] for r in rows)
    assert min(r['low'] for r in converted)==min(r['low'] for r in rows)


def test_missing_base_bar_and_partial_window_never_create_complete_bucket(cal):
    opened=at('2026-09-18T09:30'); now=opened+1800
    rows=[bar_row(bar(opened+i*300)) for i in range(6)]
    assert len(resample(rows,'15m',cal,now))==2
    assert [r['time'] for r in resample(rows[1:],'15m',cal,now)]==[opened+900]
    assert [r['time'] for r in resample(rows[:1]+rows[2:],'15m',cal,now)]==[opened+900]
    assert len(resample(rows,'15m',cal,opened+1200))==1


def test_five_fallback_is_replaced_by_official_without_waiting_for_close(store,cal):
    opened=at('2026-09-18T09:30'); now=opened+1801
    rows=[bar(opened+i*300) for i in range(6)]
    store.upsert(rows,now)
    cache=ChartCache(store,cal)
    first=cache.chart('PAYS.US','15m',now)
    assert len(first['bars'])==2
    assert not store.bars('PAYS.US','15m')
    store.upsert([replace(bar(opened,'15m'),close=99,high=100)],now)
    changed=cache.chart('PAYS.US','15m',now,known_revision=first['revision'])
    assert changed['bars'][0]['close']==99
    assert changed['bars'][1]['time']==opened+900  # Still fill a missing official timestamp.
    assert changed['revision']!=first['revision']
    assert 'bars' not in cache.chart('PAYS.US','15m',now,known_revision=changed['revision'])


def test_two_and_four_hours_depend_only_on_five_minute_data(store,cal):
    opened=at('2026-09-18T09:30'); now=at('2026-09-18T16:00')
    store.upsert([bar(ts) for ts,_ in cal.grid(date(2026,9,18),'5m')],now)
    cache=ChartCache(store,cal)
    before={tf:cache.chart('PAYS.US',tf,now) for tf in ('2h','4h')}
    store.upsert([replace(bar(opened,'1h'),close=999,high=1000)],now)
    for tf in ('2h','4h'):
        assert cache.chart('PAYS.US',tf,now)==before[tf]
        assert not store.bars('PAYS.US',tf)
    store.upsert([replace(bar(opened),high=21)],now)
    assert cache.chart('PAYS.US','4h',now)['bars'][0]['high']==21

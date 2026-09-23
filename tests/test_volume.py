"""Active volume must not absorb the Quote / candle day-total discrepancy."""
from dataclasses import replace
from datetime import date

import pytest

from data_service.charts import ChartCache
from data_service.config import Ticker
from data_service.service import DataService
from test_charts import quote
from test_data_service import at, bar, cal, store


def test_large_day_offset_does_not_leak_into_active_volume(store, cal):
    cache = ChartCache(store, cal)
    start = at('2026-09-22T14:15')
    cache.apply_quote('PAYS.US', quote(start-1, volume=18_456_445))
    assert cache.forming('PAYS.US','5m',start-1)['volume'] is None
    cache.apply_quote('PAYS.US', quote(start+1, volume=18_456_600))
    assert cache.forming('PAYS.US','5m',start+1)['volume'] == 155
    cache.apply_quote('PAYS.US', quote(start+2, volume=18_456_700))
    assert cache.forming('PAYS.US','5m',start+2)['volume'] == 255
    assert cache.forming('PAYS.US','1d',start+2)['volume'] == 18_456_700


def test_largest_available_official_intervals_cover_once_and_cache(store, cal, monkeypatch):
    start = at('2026-09-18T09:30'); end = at('2026-09-18T11:20'); now=end+60
    cache=ChartCache(store,cal)
    rows=[replace(bar(start+i*300),volume=999) for i in range(22)]
    rows += [bar(start,'1h',volume=600),bar(start+3600,'30m',volume=300),
             bar(start+5400,'15m',volume=150),bar(start+6300,'5m',volume=50)]
    store.upsert(rows,now)
    # Larger bar which extends into the active part cannot be subtracted/added.
    store.upsert([bar(start+3600,'1h',volume=5000)],start+7200)
    assert cache.closed_volume('PAYS.US','2h',start,end)==1100
    # No database work for repeated quotes/rendering with unchanged historical inputs.
    read=store.bars
    def forbidden(*args,**kwargs): raise AssertionError('Unchanged prefix was read again')
    monkeypatch.setattr(store,'bars',forbidden)
    for _ in range(100): assert cache.closed_volume('PAYS.US','2h',start,end)==1100
    monkeypatch.setattr(store,'bars',read)
    store.upsert([bar(start,'1h',volume=700)],now)
    assert cache.closed_volume('PAYS.US','2h',start,end)==1200


def test_coarse_bars_cover_missing_five_and_late_rows_repair_cache(store,cal):
    start=at('2026-09-18T09:30'); end=start+3900
    cache=ChartCache(store,cal)
    store.upsert([bar(start,'1h',volume=600)],end+1)
    assert cache.closed_volume('PAYS.US','2h',start,end) is None
    store.upsert([bar(start+3600,'5m',volume=50)],end+1)
    assert cache.closed_volume('PAYS.US','2h',start,end)==650
    cache.apply_quote('PAYS.US',quote(end-1,volume=1_000_000))
    cache.apply_quote('PAYS.US',quote(end+1,volume=1_000_007))
    assert cache.forming('PAYS.US','2h',end+1)['volume']==657
    # A rejected official revision invalidates the scalar as well.
    store.upsert([],end+1,{'symbol':'PAYS.US','timeframe':'1h','as_of':end+1,
                         'rejected':[{'ts':start,'error':'unusable'}]})
    assert cache.closed_volume('PAYS.US','2h',start,end) is None


@pytest.mark.parametrize('tf',['5m','15m','30m','1h','2h','4h'])
def test_each_active_period_uses_only_its_own_completed_part(store,cal,tf):
    now=at('2026-09-18T14:16'); five=cal.active_start('5m',now); start=cal.active_start(tf,now)
    store.upsert([bar(ts,volume=10) for ts,end in cal.grid(date(2026,9,18),'5m') if end<=five],now)
    cache=ChartCache(store,cal)
    cache.apply_quote('PAYS.US',quote(five-1,volume=999_000))
    cache.apply_quote('PAYS.US',quote(now,volume=999_007))
    assert cache.forming('PAYS.US',tf,now)['volume']==(five-start)//300*10+7


def test_recovery_and_skipped_bucket_do_not_attribute_gap_to_last_bar(tmp_path,cal):
    start=at('2026-09-18T10:00')
    service=DataService([Ticker('PAYS.US','PAYS','focus')],tmp_path,calendar=cal)
    cache=service.charts
    try:
        cache.apply_quote('PAYS.US',quote(start-1,volume=1000))
        cache.apply_quote('PAYS.US',quote(start+1,volume=1010))
        assert cache.forming('PAYS.US','5m',start+1)['volume']==10
        service.recover()
        assert cache.forming('PAYS.US','5m',start+1) is None
        cache.apply_quote('PAYS.US',quote(start+100,volume=1500))
        assert cache.forming('PAYS.US','5m',start+100)['volume'] is None
        cache.apply_quote('PAYS.US',quote(start+301,volume=1510))
        assert cache.forming('PAYS.US','5m',start+301)['volume']==10
        cache.apply_quote('PAYS.US',quote(start+901,volume=4000))
        assert cache.forming('PAYS.US','5m',start+901)['volume'] is None
    finally: service.store.close()

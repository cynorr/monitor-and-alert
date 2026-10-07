"""Optional feed processing, date replacement, scheduling and failure isolation."""
import asyncio
from datetime import datetime, timedelta
import json
import sqlite3

import pytest

from data_service.additional_info import AdditionalInfo
from data_service.additional_info.nasdaq import company_name, parse_companies, parse_earnings, SCREENER, EARNINGS, RequestFailure
from data_service.additional_info.service import ET, stamp, dates


def payload(*rows):
    return {'data': {'rows': list(rows)}, 'status': {'rCode': 200}}


def company(name='XYZ Inc. Class A Common Stock', cap='$1,200,000'):
    return payload({'symbol': 'XYZ', 'name': name, 'sector': 'Technology', 'industry': 'Semiconductors',
                    'marketCap': cap, 'country': 'USA', 'ipoyear': '1999'})


def event(symbol='XYZ', eps=None, period='Aug/2026'):
    return {'symbol': symbol, 'eps': eps, 'epsForecast': '1.10', 'fiscalQuarterEnding': period,
            'lastYearRptDt': '10/09/2025', 'time': 'time-after-hours'}


@pytest.mark.parametrize('raw,expected', [
    ('Apple Inc. Common Stock', 'Apple Inc.'),
    ('Alphabet Inc. Class A Common Stock', 'Alphabet Inc.'),
    ('CBRE Group Inc Common Stock Class A', 'CBRE Group Inc'),
    ('Brookfield Wealth Solutions Ltd. Class A Exchangeable Limited Voting Shares', 'Brookfield Wealth Solutions Ltd.'),
    ('Iron Mountain Incorporated (Delaware)Common Stock REIT', 'Iron Mountain Incorporated (Delaware)'),
    ('LyondellBasell Industries NV Ordinary Shares Class A (Netherlands)', 'LyondellBasell Industries NV'),
    ('Costamare Inc. Common Stock $0.0001 par value', 'Costamare Inc.'),
    ('Biodexa Pharmaceuticals plc American Depositary Shs', 'Biodexa Pharmaceuticals plc'),
    ('Polestar Automotive Holding UK PLC Class A ADS', 'Polestar Automotive Holding UK PLC'),
    ('Gabelli Multi-Media Trust Inc. (The) 5.125% Series E Cumulative Preferred Stock', 'Gabelli Multi-Media Trust Inc. (The)'),
    ('Opendoor Technologies Inc Series A Warrants each whole warrant exercisable to purchase Common Stock', 'Opendoor Technologies Inc'),
    ('DeFi Development Corp. Variable Rate Series C Perpetual Preferred Stock', 'DeFi Development Corp.'),
    ('Flying Class Software Inc.', 'Flying Class Software Inc.'),
    ('Alpha-Beta Co.', 'Alpha-Beta Co.'), (None, None),
])
def test_python_name_processing(raw, expected):
    assert company_name(raw) == expected


def test_company_table_keeps_raw_fields_and_rejects_incomplete_replacement():
    value = parse_companies(company())['XYZ.US']
    assert value['market_cap'] == '1200000' and value['raw_name'].endswith('Common Stock')
    assert value['raw']['country'] == 'USA' and value['company_name'] == 'XYZ Inc.'
    assert parse_companies(company(cap='0'))['XYZ.US']['market_cap'] is None
    assert parse_companies(company(cap='NaN'))['XYZ.US']['market_cap'] is None
    with pytest.raises(ValueError):
        parse_companies(payload({'symbol': 'XYZ', 'name': 'XYZ'}))
    with pytest.raises(ValueError):
        parse_companies(payload())
    rows = company()['data']['rows'] + [{**company()['data']['rows'][0], 'symbol': 'BRK/B'}]
    assert set(parse_companies(payload(*rows))) == {'XYZ.US'}


def test_actual_eps_zero_negative_and_future_estimates_use_calendar_date():
    rows = parse_earnings(payload(event(eps='0'), event('OTHER', eps='(1.20)'), event('FUTURE')), '2026-10-07')
    assert [row['reported'] for row in rows] == [True, True, False]
    assert all(row['date'] == '2026-10-07' for row in rows)
    assert rows[0]['raw']['lastYearRptDt'] == '10/09/2025'
    assert parse_earnings({'data': None, 'status': {'rCode': 200}}, '2026-10-04') == []
    with pytest.raises(ValueError):
        parse_earnings({'data': None, 'status': {'rCode': 500}}, '2026-10-04')


def test_successful_date_replacement_preserves_history_and_failure_keeps_last_good(tmp_path):
    clock = datetime(2026, 10, 7, 10, tzinfo=ET).timestamp()
    app = AdditionalInfo(tmp_path, now=lambda: clock)
    responses = {SCREENER: company(), EARNINGS + '2026-10-01': payload(event(eps='2.50')),
                 EARNINGS + '2026-10-10': payload(event())}
    async def fetch(url): return responses[url]
    async def run():
        await app.refresh(fetch, earnings_dates=['2026-10-01', '2026-10-10'])
        before = app.info('XYZ.US')
        assert before['earnings']['last']['date'] == '2026-10-01'
        assert before['earnings']['next']['date'] == '2026-10-10'
        async def failed(url): raise RequestFailure('Nasdaq HTTP 503')
        await app.refresh(failed, force=True, earnings_dates=['2026-10-10'])
        assert app.info('XYZ.US') == before
        assert app.state()['errors']['companies'] and app.state()['errors']['earnings']
        responses[EARNINGS + '2026-10-10'] = payload()
        await app.refresh(fetch, force=True, earnings_dates=['2026-10-10'])
        assert app.info('XYZ.US')['earnings']['next'] is None
        assert app.info('XYZ.US')['earnings']['last'] == before['earnings']['last']
        restored = AdditionalInfo(tmp_path, now=lambda: clock)
        await restored.load()
        assert restored.info('XYZ.US') == app.info('XYZ.US')
        assert restored.events['XYZ.US'][0]['raw']['eps'] == '2.50'
        with sqlite3.connect(restored.store.path) as db:
            raw = json.loads(db.execute('SELECT payload FROM earnings_days WHERE date=?', ('2026-10-10',)).fetchone()[0])
            assert raw == payload()
    asyncio.run(run())


def test_bootstrap_resume_daily_and_weekly_windows_freeze_old_history(tmp_path):
    day = datetime(2026, 10, 7, 10, tzinfo=ET)
    app = AdditionalInfo(tmp_path, now=lambda: day.timestamp())
    planned, weekly = app.plan()
    assert len(planned) == 241 and len(set(planned)) == 241 and weekly
    assert planned[:53] == dates(day.date() - timedelta(days=7), day.date() + timedelta(days=45))
    app.days[planned[0]] = stamp(day.timestamp())
    assert planned[0] not in app.plan()[0]
    app.days = {key: stamp(day.timestamp()) for key in planned}
    app.metadata['earnings_weekly_at'] = stamp(day.timestamp())
    assert app.plan() == ([], False)
    day += timedelta(days=1)
    planned, weekly = app.plan()
    assert len(planned) == 53 and not weekly
    assert min(planned) == '2026-10-01' and max(planned) == '2026-11-22'
    assert min(app.days) not in planned
    day += timedelta(days=6)
    planned, weekly = app.plan()
    assert weekly and max(planned) == '2027-02-11'


def test_cache_missing_and_corrupt_is_optional_and_mock_does_not_connect(tmp_path, monkeypatch):
    async def run():
        app = AdditionalInfo(tmp_path, enabled=False)
        class NoNetwork:
            def __init__(self): pytest.fail('Mock must not create a Nasdaq session')
        monkeypatch.setattr('data_service.additional_info.service.Nasdaq', NoNetwork)
        await app.run()
        assert app.info('MISSING.US')['company_name'] is None
        assert app.info('MISSING.US')['earnings'] == {'last': None, 'next': None}
        app.store.path.write_text('bad sqlite')
        app = AdditionalInfo(tmp_path, enabled=False)
        await app.run()
        assert app.state()['errors']['cache']
        assert app.info('MISSING.US')['market_cap'] is None
        with pytest.raises(ValueError, match='disabled'):
            app.request_refresh()
    asyncio.run(run())


def test_memory_reads_and_refresh_request_do_not_download_or_read_sqlite(tmp_path, monkeypatch):
    app = AdditionalInfo(tmp_path)
    monkeypatch.setattr(app.store, 'load', lambda: pytest.fail('Memory read touched SQLite'))
    assert app.info('MISSING.US')['sector'] is None
    assert app.request_refresh()['running'] and app.wakeup.is_set()
    with pytest.raises(ValueError, match='already running'):
        app.request_refresh()

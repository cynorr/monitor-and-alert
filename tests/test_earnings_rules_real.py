"""Earnings classification against installed real Scan and Nasdaq cache data."""
import asyncio
from contextlib import closing
from copy import deepcopy
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3

import pytest

from data_service.additional_info import AdditionalInfo
from data_service.additional_info.nasdaq import EARNINGS, parse_earnings
from data_service.additional_info.service import ET
from data_service.features.events import days_to_earnings
from data_service.list_rules import matched_tags
from data_service.workbench import Workbench
from data_service.workspace import Workspace

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'


@pytest.fixture(scope='module')
def real_data():
    folder = sorted((RUNTIME / 'days').glob('*/scan.json'))[-1].parent
    snapshot = json.loads((folder / 'scan.json').read_text())
    preferences = json.loads((RUNTIME / 'preferences.json').read_text())
    preferences['tags'] = [tag for tag in preferences['tags'] if tag['role'] != 'earnings'] + [
        {'id': 'earnings', 'name': 'In 14 Days', 'role': 'earnings',
         'filters': {'days_to_earnings': {'min': 0, 'max': 14}}}]
    today = datetime.now(ET).date()
    symbols = {row['symbol'] for row in snapshot['rows'] if row['candidate']}
    with closing(sqlite3.connect((RUNTIME / 'additional-info/info.sqlite3').resolve().as_uri() + '?mode=ro', uri=True)) as db:
        pages = [(day, json.loads(payload)) for day, payload in db.execute(
            'SELECT date, payload FROM earnings_days WHERE date BETWEEN ? AND ?',
            (today.isoformat(), (today + timedelta(days=14)).isoformat()))]
    page = max(pages, key=lambda item: sum(event['symbol'] in symbols and not event['reported']
                                         for event in parse_earnings(item[1], item[0])))
    return folder, snapshot, preferences, today, page


def create_app(tmp_path, real_data, *, cache=None, now=None):
    folder, snapshot, preferences, _, _ = real_data
    target = tmp_path / 'days' / snapshot['date']
    target.mkdir(parents=True)
    for name in ('scan.json', 'workspace.json'):
        (target / name).write_bytes((folder / name).read_bytes())
    (tmp_path / 'preferences.json').write_text(json.dumps(preferences))
    options = {'now': now} if now is not None else {}
    info = AdditionalInfo(cache or tmp_path / 'additional-info', enabled=False, **options)
    def no_broker(*_):
        raise AssertionError('Local earnings classification must not start a broker')
    return Workbench(Workspace(root=target.parent), tmp_path, RUNTIME / 'massive/daily.sqlite3',
                     no_broker, additional_info=info)


def test_calendar_boundaries_and_missing_use_real_report_date(real_data):
    report_date = date.fromisoformat(real_data[4][0])
    assert days_to_earnings(report_date.isoformat(), report_date) == 0
    assert days_to_earnings(report_date.isoformat(), report_date - timedelta(days=14)) == 14
    assert days_to_earnings(report_date.isoformat(), report_date - timedelta(days=15)) == 15
    assert days_to_earnings(None, real_data[3]) is None


def test_real_cache_load_classifies_with_highest_priority_and_keeps_raw_scan(tmp_path, real_data):
    app = create_app(tmp_path, real_data, cache=RUNTIME / 'additional-info')
    before = deepcopy(app.workspace.data)
    raw = deepcopy(app.snapshot(app.workspace.date))
    scan_bytes = (app.workspace.path.parent / 'scan.json').read_bytes()
    async def run():
        try:
            await app.additional.load()
            enriched = app.list_snapshot(app.workspace.date)
            rows = {row['symbol'].removesuffix('.US'): row for row in enriched['rows']}
            states = app.workspace.data['statuses']
            earnings = {ticker for ticker, state in states.items() if state.get('section') == 'earnings'}
            assert earnings
            overlaps = 0
            missing = 0
            for ticker, state in states.items():
                row = rows.get(ticker, {})
                if state.get('section') == 'hidden':
                    assert state['excluded_at'] == before['statuses'][ticker]['excluded_at']
                elif state['status'] == 'excluded' and 'earnings' in state['tags']:
                    assert state['section'] == 'earnings' and row['candidate']
                    roles = {tag['role'] for tag in matched_tags(row, app.preferences['tags'])}
                    overlaps += bool(roles & {'broken', 'extended', 'under50'})
                if row.get('days_to_earnings') is None and ticker in before['statuses']:
                    missing += 1
                    assert state == before['statuses'][ticker]
            assert missing and overlaps
            assert app.snapshot(app.workspace.date) == raw
            assert (app.workspace.path.parent / 'scan.json').read_bytes() == scan_bytes
            assert all('days_to_earnings' not in row for row in raw['rows'])
            saved = json.loads(app.workspace.path.read_text())
            assert all(state['section'] == 'hidden' for state in saved['statuses'].values()
                       if state.get('status') == 'excluded')
        finally:
            await app.close()
    asyncio.run(run())


def test_real_daily_response_commit_reclassifies_without_network_or_bar_rebuild(tmp_path, real_data):
    app = create_app(tmp_path, real_data)
    day, payload = real_data[4]
    initial = app.snapshot(app.workspace.date)
    async def read_cached_response(url):
        assert url == EARNINGS + day
        return payload
    async def run():
        try:
            assert all(row['days_to_earnings'] is None for row in app.scan_board())
            await app.additional.refresh(read_cached_response, companies=False, earnings_dates=[day])
            assert app.additional.days[day]
            rows = app.scan_board()
            assert any(row['section'] == 'earnings' for row in rows)
            expected_days = (date.fromisoformat(day) - real_data[3]).days
            assert all(row['days_to_earnings'] == expected_days for row in rows if row['section'] == 'earnings')
            assert app.snapshot(app.workspace.date) is initial
            before = deepcopy(app.workspace.data)
            await app.additional.load()
            assert app.workspace.data == before
        finally:
            await app.close()
    asyncio.run(run())


def test_et_day_change_updates_real_cached_report_without_fetching(tmp_path, real_data):
    day, payload = real_data[4]
    report = date.fromisoformat(day)
    first = report - timedelta(days=15)
    clock = [datetime.combine(first, datetime.min.time(), ET).timestamp()]
    app = create_app(tmp_path, real_data, now=lambda: clock[0])
    async def read_cached_response(url):
        assert url == EARNINGS + day
        return payload
    async def run():
        task = None
        try:
            await app.additional.refresh(read_cached_response, companies=False, earnings_dates=[day])
            rows = app.scan_board()
            observed = {row['symbol'] for row in rows if row['days_to_earnings'] == 15}
            assert observed and not any(row['section'] == 'earnings' for row in rows)
            revision = app.additional.revision
            clock[0] += 86400
            task = asyncio.create_task(app.run())
            await asyncio.sleep(.25)
            assert app.earnings_day == first + timedelta(days=1)
            rows = [row for row in app.scan_board() if row['symbol'] in observed]
            assert rows and all(row['days_to_earnings'] == 14 for row in rows)
            assert any(row['section'] == 'earnings' for row in rows)
            assert app.additional.revision == revision
        finally:
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await app.close()
    asyncio.run(run())

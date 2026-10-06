"""Keep successful unadjusted daily responses without changing existing raw files."""
from __future__ import annotations

import asyncio
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..calendar import ET
from ..store import atomic_json

BASE_URL = 'https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks'
HISTORY_YEARS = 2
REPAIR_DAYS = 14


def shift_year(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def mature_date(now=None):
    value = datetime.now(ET) if now is None else datetime.fromtimestamp(now, ET)
    return value.date() - timedelta(days=value.hour < 18)


def target_date(calendar, now=None):
    end = mature_date(now)
    sessions = calendar.days(end - timedelta(days=15), end)
    if not sessions:
        raise ValueError('No completed trading date in the recent calendar')
    return sessions[-1]


def check_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'Invalid daily {name}')


def check_data(data, day):
    if not isinstance(data, dict) or data.get('status') != 'OK' or data.get('adjusted') is not False:
        raise ValueError('Expected successful unadjusted Massive daily data')
    rows = data.get('results')
    count = data.get('resultsCount')
    if not isinstance(rows, list) or isinstance(count, bool) or not isinstance(count, int) or count != len(rows):
        raise ValueError('Daily result count does not match its rows')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not {'T', 'o', 'h', 'l', 'c', 'v', 't'} <= row.keys():
            raise ValueError('A daily row is missing required fields')
        symbol = row['T']
        if not isinstance(symbol, str) or not symbol or symbol != symbol.strip() or symbol in seen:
            raise ValueError('Invalid or duplicate daily ticker')
        if row.get('otc') is True:
            raise ValueError('OTC data was returned unexpectedly')
        seen.add(symbol)
        for key in ('o', 'h', 'l', 'c', 'v'):
            check_number(row[key], key)
        if any(row[key] <= 0 for key in ('o', 'h', 'l', 'c')) or row['v'] < 0:
            raise ValueError('Daily OHLC must be positive and volume nonnegative')
        if isinstance(row['t'], bool) or not isinstance(row['t'], int):
            raise ValueError('Invalid daily timestamp')
        row_day = datetime.fromtimestamp(row['t'] / 1000, timezone.utc).astimezone(ET).date()
        if row_day != day:
            raise ValueError('Daily timestamp does not match its trading date')
        if row.get('vw') is not None:
            check_number(row['vw'], 'vw')
        if row.get('n') is not None and (isinstance(row['n'], bool) or not isinstance(row['n'], int) or row['n'] < 0):
            raise ValueError('Invalid daily transaction count')
    return rows


def read_day(path, day):
    data = json.loads(Path(path).read_bytes())
    rows = check_data(data, day)
    if not rows:
        raise ValueError('Saved daily response is empty')
    return rows


async def update(directory, target, calendar, fetch_json):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    existing = [date.fromisoformat(path.stem) for path in directory.glob('????-??-??.json')]
    if existing and max(existing) > target:
        raise ValueError('Local daily data is later than the mature trading date')
    start = shift_year(target, -HISTORY_YEARS)
    if existing:
        start = max(start, max(existing) - timedelta(days=REPAIR_DAYS))
    for day in reversed(calendar.days(start, target)):
        path = directory / f'{day.isoformat()}.json'
        if path.exists():
            await asyncio.to_thread(read_day, path, day)
            continue
        data = await fetch_json(f'{BASE_URL}/{day.isoformat()}?adjusted=false&include_otc=false')
        if not await asyncio.to_thread(check_data, data, day):
            raise ValueError('Massive returned no data for an expected trading date')
        await asyncio.to_thread(atomic_json, path, data)
    await asyncio.to_thread(read_day, directory / f'{target.isoformat()}.json', target)
    return target.isoformat()

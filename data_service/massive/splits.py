"""Replace the latest two-year split window while retaining older local history."""
from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .daily import shift_year
from ..store import atomic_json

BASE_URL = 'https://api.massive.com/stocks/v1/splits'
FIELDS = {'id', 'ticker', 'execution_date', 'adjustment_type', 'split_from', 'split_to'}


def check_rows(rows, start, end):
    if not isinstance(rows, list):
        raise ValueError('Split results must be a list')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not FIELDS <= row.keys():
            raise ValueError('A split row is missing required fields')
        if not isinstance(row['id'], str) or not row['id'] or row['id'] in seen:
            raise ValueError('Invalid or duplicate split id')
        seen.add(row['id'])
        if not isinstance(row['ticker'], str) or not row['ticker'] or row['ticker'] != row['ticker'].strip():
            raise ValueError('Invalid split ticker')
        if not start <= date.fromisoformat(row['execution_date']) <= end:
            raise ValueError('Split date is outside its declared coverage')
        for key in ('split_from', 'split_to'):
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError('Split ratios must be finite positive numbers')
    return sorted(rows, key=lambda row: (row['execution_date'], row['ticker'], row['id']))


def read_existing(path):
    if not Path(path).exists():
        return None
    data = json.loads(Path(path).read_bytes())
    if not isinstance(data, dict) or data.get('status') != 'OK':
        raise ValueError('Invalid local split snapshot')
    start, end = (date.fromisoformat(data[key]) for key in ('start_date', 'end_date'))
    if start > end or data.get('resultsCount') != len(data.get('results', [])):
        raise ValueError('Invalid local split coverage or result count')
    rows = check_rows(data['results'], start, end)
    return {'start_date': start, 'end_date': end, 'results': rows}


def merge(existing, fresh, refresh_start, target):
    start, old = refresh_start, []
    if existing is not None:
        if existing['end_date'] < refresh_start - timedelta(days=1):
            raise ValueError('Local split coverage cannot join the latest two-year window')
        start = min(existing['start_date'], refresh_start)
        old = [row for row in existing['results'] if date.fromisoformat(row['execution_date']) < refresh_start]
    rows = check_rows(old + fresh, start, target)
    return {'status': 'OK', 'start_date': start.isoformat(), 'end_date': target.isoformat(),
            'resultsCount': len(rows), 'results': rows}


async def update(path, target, fetch_json):
    existing = read_existing(path)
    start = shift_year(target, -2)
    query = urlencode({'execution_date.gte': start.isoformat(), 'execution_date.lte': target.isoformat(),
                       'limit': 5000, 'sort': 'execution_date.asc'})
    url, rows, seen = f'{BASE_URL}?{query}', [], set()
    while url:
        parts = urlsplit(url)
        if parts.scheme != 'https' or parts.hostname != 'api.massive.com' or parts.path != '/stocks/v1/splits' or url in seen:
            raise ValueError('Invalid or repeated Massive split page')
        seen.add(url)
        data = await fetch_json(url)
        if not isinstance(data, dict) or data.get('status') != 'OK':
            raise ValueError('Massive split response is unsuccessful')
        rows.extend(check_rows(data.get('results', []), start, target))
        url = data.get('next_url')
        if url is not None and not isinstance(url, str):
            raise ValueError('Invalid Massive split next page')
    result = merge(existing, rows, start, target)
    atomic_json(Path(path), result)
    return result

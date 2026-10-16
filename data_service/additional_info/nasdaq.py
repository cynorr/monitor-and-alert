"""The two public Nasdaq website feeds and their Python field processing."""
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
import re
import time

import aiohttp

from ..network import create_session, proxy_url

SCREENER = 'https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true'
EARNINGS = 'https://api.nasdaq.com/api/calendar/earnings?date='
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json',
           'Origin': 'https://www.nasdaq.com', 'Referer': 'https://www.nasdaq.com/'}
TICKER = re.compile(r'[A-Z][A-Z0-9.-]{0,19}')
# Recognized security markers begin a suffix, including attributes following it.
# Do not split on arbitrary hyphens: those can be part of the company name.
SECURITY_SUFFIX = re.compile(
    r'(?:\s+(?:-\s*)?|(?<=[.)]))'
    r'(?:Class\s+[A-Z0-9][A-Z0-9-]{0,3}\b|(?:Voting\s+)?Common\s+(?:Stock|Shares?)\b|(?:Voting\s+)?Ordinary\s+Shares?\b|'
    r'(?:Subordinate|Multiple|Non[- ]?)\s*Voting\s+Shares?\b|'
    r'(?:American\s+)?Deposit(?:ary|ory)\s+(?:Shares?|Shs?|Receipts?)\b|'
    r'ADS\b|ADR\b|(?:Series\s+[A-Z0-9-]+\s+)?(?:Warrants?|Units?|Rights)\b).*$', re.I)
COUPON_SUFFIX = re.compile(r'\s+\d+(?:\.\d+)?(?:\s+\d+/\d+)?%\s+.*\b(?:Preferred|Notes)\b.*$', re.I)
RATE_SUFFIX = re.compile(r'\s+(?:Fixed[- ]Rate|Fixed[- ]to[- ]Floating|Floating\s+Rate|Variable\s+Rate)\b.*\b(?:Preferred|Notes)\b.*$', re.I)
PREFERRED_NOTES = re.compile(
    r'^(.*\b(?:Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.?|plc|Ltd\.?|Limited|Trust|L\.?P\.?))'
    r'((?:\s+\(The\))?)\s+(?:-\s*)?.*\b(?:Preferred|Notes)\b.*$', re.I)


class RequestFailure(RuntimeError):
    """A public-feed network failure without arbitrary upstream response text."""


def text(value):
    if not isinstance(value, str):
        return None
    value = ' '.join(value.split())
    return value if value and value.upper() not in {'N/A', 'NA', '--', 'NAN'} else None


def company_name(raw):
    """Strip recognized security suffixes, keeping the company's legal name."""
    value = text(raw)
    if value is None:
        return None
    preferred = PREFERRED_NOTES.fullmatch(value)
    if preferred:
        value = preferred[1] + preferred[2]
    value = COUPON_SUFFIX.sub('', value)
    value = RATE_SUFFIX.sub('', value)
    value = SECURITY_SUFFIX.sub('', value)
    return value.rstrip(' -') or None


def symbol(raw):
    ticker = text(raw)
    return ticker + '.US' if ticker and TICKER.fullmatch(ticker) and not ticker.endswith('.US') else None


def number(raw):
    """A raw financial number, including dollar signs and negative parentheses."""
    value = text(raw) if isinstance(raw, str) else str(raw) if isinstance(raw, (int, float)) else None
    if value is None:
        return None
    value = value.replace('$', '').replace(',', '')
    if value.startswith('(') and value.endswith(')'):
        value = '-' + value[1:-1]
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def rows(payload, *, empty=False):
    if not isinstance(payload, dict):
        raise ValueError('Nasdaq response must be an object')
    status = payload.get('status') or {}
    if not isinstance(status, dict) or status.get('rCode', 200) != 200:
        raise ValueError('Nasdaq response has an unsuccessful status')
    data = payload.get('data')
    if data is None and empty:
        return []
    if not isinstance(data, dict) or 'rows' not in data:
        raise ValueError('Nasdaq response is missing data.rows')
    result = data['rows']
    if result is None and empty:
        return []
    if not isinstance(result, list) or (not empty and not result):
        raise ValueError('Nasdaq rows are empty or malformed')
    if not all(isinstance(row, dict) and isinstance(row.get('symbol'), str) for row in result):
        raise ValueError('Nasdaq row is missing a symbol')
    return result


def parse_companies(payload):
    result = {}
    for row in rows(payload):
        if not {'name', 'sector', 'industry', 'marketCap'} <= row.keys():
            raise ValueError('Nasdaq Screener is missing company columns')
        key = symbol(row['symbol'])
        if key is None:
            continue
        if key in result:
            raise ValueError('Duplicate Nasdaq Screener symbol')
        cap = number(row['marketCap'])
        result[key] = {'company_name': company_name(row['name']), 'raw_name': row['name'],
                       'sector': text(row['sector']), 'industry': text(row['industry']),
                       'market_cap': format(cap, 'f') if cap is not None and cap > 0 else None,
                       'raw': row}
    if not result:
        raise ValueError('Nasdaq Screener has no supported US symbols')
    return result


def parse_earnings(payload, day):
    result, seen = [], set()
    for row in rows(payload, empty=True):
        key = symbol(row['symbol'])
        if key is None:
            continue
        period = text(row.get('fiscalQuarterEnding'))
        identity = key, period
        if identity in seen:
            raise ValueError('Duplicate Nasdaq earnings event')
        seen.add(identity)
        result.append({'symbol': key, 'date': day, 'session': text(row.get('time')),
                       'fiscal_period': period, 'reported': number(row.get('eps')) is not None, 'raw': row})
    return result


class Nasdaq:
    """One session, serial requests and bounded retries; no API credentials."""
    def __init__(self):
        self.session = None
        self.started = 0.0

    async def __aenter__(self):
        self.session = create_session(30)
        return self

    async def __aexit__(self, *_):
        await self.session.close()

    async def fetch(self, url):
        for attempt in range(4):
            await asyncio.sleep(max(0, self.started + 1 - time.monotonic()))
            self.started = time.monotonic()
            try:
                async with self.session.get(url, proxy=proxy_url(), headers=HEADERS) as response:
                    if response.status != 200:
                        raise RequestFailure(f'Nasdaq HTTP {response.status}')
                    try:
                        return await response.json(content_type=None)
                    except ValueError:
                        raise ValueError('Nasdaq returned invalid JSON') from None
            except (aiohttp.ClientError, TimeoutError, RequestFailure) as error:
                if attempt == 3:
                    message = str(error) if isinstance(error, RequestFailure) else type(error).__name__
                    raise RequestFailure(f'Nasdaq request failed ({message})') from None
                await asyncio.sleep((2, 5, 10)[attempt])

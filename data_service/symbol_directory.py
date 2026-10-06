"""Free Nasdaq Trader ETF classifications and names, independent of Massive."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

import aiohttp

from .network import create_session, proxy_url
from .store import atomic_json

SOURCES = {
    'nasdaqlisted.txt': 'https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt',
    'otherlisted.txt': 'https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt',
}
REQUEST_TIMEOUT = 30


class RequestFailure(RuntimeError):
    """A request error without a proxy URL or upstream response body."""


def make_snapshot(symbols, *, sources=None, updated_at=None):
    """Create the plain cache; offline mocks can supply their own symbols."""
    return {'symbols': symbols, 'updated_at': updated_at or datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'sources': sources or {}}


def read_directory(path):
    """Read the local cache. Missing classification cannot confirm a non-ETF."""
    try:
        snapshot = json.loads(Path(path).read_bytes())
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get('symbols'), dict):
            raise ValueError('Missing symbols map')
        return snapshot
    except (OSError, ValueError):
        raise ValueError('Symbol directory is missing or corrupt; run scripts/pull_symbol_directory.py') from None


def parse_text(text, filename):
    """Read primary symbols and ETF flags from a complete official text file."""
    lines = text.removeprefix('\ufeff').splitlines()
    if len(lines) < 3:
        raise ValueError('Nasdaq directory is empty or incomplete')
    columns = lines[0].split('|')
    ticker_column = 'Symbol' if filename == 'nasdaqlisted.txt' else 'ACT Symbol'
    if len(set(columns)) != len(columns) or not {ticker_column, 'Security Name', 'ETF'} <= set(columns):
        raise ValueError('Nasdaq directory is missing required columns')
    footer = lines[-1].split('|')
    # otherlisted has six trailing delimiters despite its eight-column header.
    footer_sizes = {len(columns)}
    if filename == 'otherlisted.txt':
        footer_sizes.add(len(columns) - 1)
    if (not footer[0].startswith('File Creation Time: ') or len(footer) not in footer_sizes
            or any(footer[1:])):
        raise ValueError('Nasdaq directory is missing a complete File Creation Time footer')
    creation_time = footer[0].removeprefix('File Creation Time: ')
    datetime.strptime(creation_time, '%m%d%Y%H:%M')
    symbols = {}
    for line in lines[1:-1]:
        fields = line.split('|')
        if len(fields) != len(columns):
            raise ValueError('Nasdaq directory row does not match its header')
        row = dict(zip(columns, fields))
        ticker = row[ticker_column]
        if not ticker or ticker != ticker.strip() or ticker + '.US' in symbols:
            raise ValueError('Invalid or duplicate Nasdaq directory ticker')
        if row['ETF'] not in {'Y', 'N'}:
            raise ValueError('Nasdaq directory ETF must be Y or N')
        symbols[ticker + '.US'] = {'name': row['Security Name'].strip() or None, 'etf': row['ETF'] == 'Y'}
    return symbols, {'url': SOURCES[filename], 'creation_time': creation_time, 'row_count': len(symbols)}


def combine(nasdaq_text, other_text, *, updated_at=None):
    """Combine Nasdaq Symbol and otherlisted ACT Symbol without protocol aliases."""
    symbols, metadata = {}, {}
    for filename, text in zip(SOURCES, (nasdaq_text, other_text)):
        entries, metadata[filename] = parse_text(text, filename)
        if symbols.keys() & entries.keys():
            raise ValueError('Duplicate ticker across Nasdaq directory sources')
        symbols.update(entries)
    return make_snapshot(symbols, sources={'files': metadata}, updated_at=updated_at)


async def update(path, fetch_text=None):
    """Fetch each free file once; publish only after both have parsed successfully."""
    if fetch_text is None:
        async with create_session(REQUEST_TIMEOUT) as session:
            async def fetch(url):
                try:
                    async with session.get(url, proxy=proxy_url()) as response:
                        if response.status != 200:
                            raise RequestFailure(f'Nasdaq directory HTTP {response.status}')
                        return (await response.read()).decode('utf-8-sig')
                except (aiohttp.ClientError, TimeoutError) as error:
                    raise RequestFailure(f'Nasdaq directory request failed ({type(error).__name__})') from None
            return await update(path, fetch)
    texts = [await fetch_text(url) for url in SOURCES.values()]
    snapshot = combine(*texts)
    await asyncio.to_thread(atomic_json, Path(path), snapshot)
    return snapshot

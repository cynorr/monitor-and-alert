"""Refresh optional Nasdaq info without market-data or broker credentials."""
import argparse
import asyncio
from datetime import date
import fcntl
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_service.additional_info import AdditionalInfo
from data_service.additional_info.nasdaq import Nasdaq
from data_service.additional_info.service import dates
from data_service.paths import RuntimePaths


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=Path('runtime'))
    parser.add_argument('--force', action='store_true', help='Refresh current daily/weekly windows even if already fetched')
    parser.add_argument('--companies-only', action='store_true', help='One company-table refresh, no earnings requests')
    parser.add_argument('--earnings-start', type=date.fromisoformat, help='Bounded earnings validation start date')
    parser.add_argument('--earnings-end', type=date.fromisoformat, help='Bounded earnings validation end date')
    args = parser.parse_args(argv)
    if bool(args.earnings_start) != bool(args.earnings_end):
        parser.error('--earnings-start and --earnings-end must be provided together')
    if args.earnings_start and (args.earnings_start > args.earnings_end or args.companies_only):
        parser.error('Use a valid earnings range or --companies-only')
    planned = [] if args.companies_only else dates(args.earnings_start, args.earnings_end) if args.earnings_start else None
    async def refresh():
        service = AdditionalInfo(RuntimePaths(args.runtime).additional_info_dir)
        await service.load()
        async with Nasdaq() as source:
            await service.refresh(source.fetch, force=args.force, earnings_dates=planned)
        return service.state()
    try:
        args.runtime.mkdir(parents=True, exist_ok=True)
        with (args.runtime / 'service.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('Service is running; use POST /v1/additional-info with {"action":"refresh"}') from None
            state = asyncio.run(refresh())
        print(json.dumps(state, indent=2))
        return 2 if any(state['errors'].values()) else 0
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f'Additional info refresh failed: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

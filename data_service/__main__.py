from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import logging
import re
import sqlite3
from pathlib import Path

from .config import load_tickers
from .store import atomic_json
from .workspace import Workspace, resolve_latest_workspace


def parser():
    result = argparse.ArgumentParser(description='Scan and Monitor workbench')
    result.add_argument('command', choices=('universe', 'serve', 'reconcile', 'verify', 'scan'))
    result.add_argument('--workspace', type=Path, help='Pin a workspace file instead of following the latest Scan day')
    result.add_argument('--credentials', type=Path, default=Path('longbridge-token.txt'))
    result.add_argument('--holdings-credentials', type=Path, default=Path('snaptrade-token.txt'))
    result.add_argument('--holdings-rules', type=Path, help='Buy/sell rules; defaults to runtime/holdings')
    result.add_argument('--runtime', type=Path, default=Path('runtime'))
    result.add_argument('--mode', choices=('monitor','scan'), default='monitor')
    result.add_argument('--daily-db', type=Path, help='Read-only upstream daily SQLite; defaults to runtime/daily.sqlite3')
    result.add_argument('--date', help='Completed trading date; scan defaults to upstream metadata.completed_date')
    result.add_argument('--mock-scan', action='store_true', help='Label the explicitly supplied daily data as synthetic')
    result.add_argument('--symbols', nargs='+', help='Optional SUBSET of current focus/wait tickers')
    result.add_argument('--region', choices=('cn', 'global'), default='cn')
    result.add_argument('--port', type=int, default=8765)
    result.add_argument('--cors-origin', help='Optional exact origin of local frontend')
    result.add_argument('--duration', type=float, help='Stop serve after this many seconds (smoke tests)')
    return result


async def run(args, tickers):
    from .broker import Broker
    from .http_api import start_http
    from .service import DataService

    if args.command == 'serve':
        from .workbench import Workbench
        def holdings_factory():
            from .config import read_snaptrade_credentials
            from .holdings import Holdings
            from .snaptrade import SnapTrade
            return Holdings(SnapTrade(*read_snaptrade_credentials(args.holdings_credentials),
                                      args.runtime / 'holdings' / 'latest.json'),
                            args.holdings_rules or args.runtime / 'holdings')
        workspace = Workspace(args.workspace, root=args.days)
        service = Workbench(workspace, args.runtime, args.daily_db,
                            lambda allowed: Broker(args.credentials, allowed, args.runtime, args.region),
                            mock=args.mock_scan, only=args.symbols,
                            holdings_factory=holdings_factory if args.holdings_credentials.exists() else None)
        server = None
        try:
            if args.mode == 'monitor':
                await service.switch_mode('monitor')
            else:
                service.snapshot()
            workspace.start_watcher()
            server = await start_http(service, args.port, args.cors_origin)
            print(f'{args.mode.upper()}: http://127.0.0.1:{args.port}/', flush=True)
            if args.duration:
                try:
                    await asyncio.wait_for(service.run(), args.duration)
                except TimeoutError:
                    pass
            else:
                await service.run()
            if service.monitor:
                summary = {s: service.monitor.validate(s) for s in service.monitor.symbols}
                atomic_json(args.runtime / 'last_run_report.json', {'health': await service.api('/health', {}), 'readiness': summary})
                return 0 if summary and all(c['complete'] for s in summary.values() for c in s.values()) else 2
            return 0
        finally:
            workspace.stop_watcher()
            if server:
                await server.cleanup()
            await service.close()

    broker = None if args.command == 'verify' else Broker(args.credentials, {t.symbol for t in tickers}, args.runtime, args.region)
    service = DataService(tickers, args.runtime, broker)
    try:
        if args.command == 'verify':
            for symbol in service.symbols:
                service.validate(symbol)
        elif args.command == 'reconcile':
            await service.reconcile()
        summary = {s: service.validate(s) for s in service.symbols}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary and all(c['complete'] for s in summary.values() for c in s.values()) else 2
    finally:
        service.store.close()
        if broker:
            broker.close()


def main():
    args = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    try:
        args.daily_db = args.daily_db or args.runtime / 'daily.sqlite3'
        args.days = args.workspace.parent.parent if args.workspace and re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.workspace.parent.name) else args.runtime / 'days'
        if args.command == 'scan':
            from .calendar import TradingCalendar
            from .scan import build_day, publish_day, latest_completed_date
            args.date = args.date or latest_completed_date(args.daily_db)
            args.runtime.mkdir(parents=True, exist_ok=True)
            with (args.runtime / 'service.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('A service already uses this runtime; generate through POST /v1/scan') from None
                snapshot = build_day(args.daily_db, args.date, TradingCalendar(),
                                     log_path=args.runtime / 'invalid_ohlc.jsonl', mock=args.mock_scan)
                publish_day(args.days, snapshot)
            print(f"{snapshot['date']}: {sum(row['candidate'] for row in snapshot['rows'])} candidates")
            return 0
        path = args.workspace or resolve_latest_workspace(args.days)
        tickers = load_tickers(path, args.symbols, allow_empty=args.command == 'serve')
        if args.command == 'universe':
            print(json.dumps([{'symbol': t.symbol, 'status': t.status} for t in tickers], indent=2))
            return 0
        if args.duration is not None and args.duration <= 0:
            raise ValueError('duration must be positive')
        args.runtime.mkdir(parents=True, exist_ok=True)
        with (args.runtime / 'service.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('A service already uses this runtime directory') from None
            logging.info('Service start symbols=%d workspace=%s', len(tickers), path.resolve())
            return asyncio.run(run(args, tickers))
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        logging.error('%s', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

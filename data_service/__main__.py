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
from .paths import RuntimePaths
from .store import atomic_json
from .workspace import Workspace, resolve_latest_workspace


def parser():
    result = argparse.ArgumentParser(description='Scan and Monitor workbench')
    result.add_argument('command', choices=('universe', 'serve', 'reconcile', 'verify', 'scan', 'massive'))
    result.add_argument('--workspace', type=Path, help='Pin a workspace file instead of following the latest Scan day')
    result.add_argument('--credentials', type=Path, default=Path('longbridge-token.txt'))
    result.add_argument('--holdings-credentials', type=Path, default=Path('snaptrade-token.txt'))
    result.add_argument('--massive-credentials', type=Path, default=Path('massive-token.txt'))
    result.add_argument('--holdings-rules', type=Path, help='Buy/sell rules; defaults to runtime/holdings')
    result.add_argument('--runtime', type=Path, default=Path('runtime'))
    result.add_argument('--mode', choices=('monitor','scan'), default='monitor')
    result.add_argument('--daily-db', type=Path, help='Read-only external daily SQLite; disables the built-in Massive pipeline')
    result.add_argument('--date', help='Completed trading date; scan defaults to upstream metadata.completed_date')
    result.add_argument('--force', action='store_true', help='Force the Massive splits/bars/features refresh; existing raw daily files are kept')
    result.add_argument('--mock-scan', action='store_true', help='Label the explicitly supplied daily data as synthetic')
    result.add_argument('--symbols', nargs='+', help='Optional SUBSET of current focus/wait tickers')
    result.add_argument('--region', choices=('cn', 'global'), default='cn')
    result.add_argument('--port', type=int, default=8765)
    result.add_argument('--cors-origin', help='Optional exact origin of local frontend')
    result.add_argument('--duration', type=float, help='Stop serve after this many seconds (smoke tests)')
    return result


async def run(args, tickers, notifier=None):
    from .broker import Broker
    from .http_api import start_http
    from .service import DataService

    if args.command == 'serve':
        from .workbench import Workbench
        paths = RuntimePaths(args.runtime)
        pipeline = None
        if not args.external_daily_db and not args.mock_scan and args.symbols is None:
            from .pipeline import MassivePipeline
            pipeline = MassivePipeline(paths, credentials=args.massive_credentials)
        def holdings_factory():
            from .config import read_snaptrade_credentials
            from .holdings import Holdings
            from .snaptrade import SnapTrade
            return Holdings(SnapTrade(*read_snaptrade_credentials(args.holdings_credentials),
                                      paths.holdings_dir / 'latest.json'),
                            args.holdings_rules or paths.holdings_dir)
        workspace = Workspace(args.workspace, root=args.days)
        service = Workbench(workspace, args.runtime, args.daily_db,
                            lambda allowed: Broker(args.credentials, allowed, args.runtime, args.region),
                            mock=args.mock_scan, only=args.symbols,
                            holdings_factory=holdings_factory if args.holdings_credentials.exists() else None,
                            pipeline=pipeline, bars_path=paths.bars_db, notifier=notifier)
        if notifier:
            notifier.bind(service.alerts, asyncio.get_running_loop())
        server = None
        try:
            service.mode = args.mode
            workspace.start_watcher()
            server = await start_http(service, args.port, args.cors_origin)
            if notifier:
                notifier.open_workbench()
            await service.start_background()
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
    service = DataService(tickers, args.runtime, broker, bars_path=RuntimePaths(args.runtime).bars_db)
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


def main(argv=None, *, notifier=None):
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    try:
        paths = RuntimePaths(args.runtime)
        args.external_daily_db = args.daily_db is not None
        args.daily_db = args.daily_db or (args.runtime / 'daily.sqlite3' if args.mock_scan else paths.daily_db)
        args.days = args.workspace.parent.parent if args.workspace and re.fullmatch(r'\d{4}-\d{2}-\d{2}', args.workspace.parent.name) else args.runtime / 'days'
        if args.command == 'massive':
            if args.mock_scan or args.symbols or args.external_daily_db:
                raise ValueError('massive requires its own runtime without --mock-scan, --symbols or --daily-db')
            from .pipeline import MassivePipeline
            args.runtime.mkdir(parents=True, exist_ok=True)
            with (args.runtime / 'service.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('Stop the service before running the Massive command') from None
                async def prepare():
                    pipeline = MassivePipeline(paths, credentials=args.massive_credentials)
                    try:
                        await pipeline.run(force=args.force)
                        return pipeline.state()
                    finally:
                        await pipeline.close()
                state = asyncio.run(prepare())
            print(json.dumps(state, ensure_ascii=False, indent=2))
            return 0 if state['ready'] else 2
        if args.command == 'scan':
            from .calendar import TradingCalendar
            from .scan import build_day, publish_day, latest_completed_date, workspace_scope
            args.date = args.date or latest_completed_date(args.daily_db)
            args.runtime.mkdir(parents=True, exist_ok=True)
            with (args.runtime / 'service.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError('Stop the service before rebuilding a Scan date') from None
                tracked = workspace_scope(args.days, args.date)
                snapshot = build_day(args.daily_db, args.date, TradingCalendar(),
                                     log_path=args.runtime / 'invalid_ohlc.jsonl', mock=args.mock_scan,
                                     tracked_tickers=tracked,
                                     directory_path=paths.symbol_directory)
                if not args.external_daily_db and not args.mock_scan:
                    from .massive.build import metadata
                    from .pipeline import updated_at
                    snapshot.update(input_revision=metadata(args.daily_db)['input_revision'], updated_at=updated_at())
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
            return asyncio.run(run(args, tickers, notifier))
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        logging.error('%s', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

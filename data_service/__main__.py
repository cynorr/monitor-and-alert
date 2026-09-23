from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import logging
from pathlib import Path

from .config import load_tickers
from .store import atomic_json
from .workspace import Workspace, resolve_latest_workspace


def parser():
    result = argparse.ArgumentParser(description='Whitelist-only Longbridge data service')
    result.add_argument('command', choices=('universe', 'serve', 'reconcile', 'verify'))
    result.add_argument('--workspace', type=Path, help='Pin a workspace file instead of following the latest Scan day')
    result.add_argument('--credentials', type=Path, default=Path('longbridge-token.txt'))
    result.add_argument('--runtime', type=Path, default=Path('runtime'))
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

    broker = None if args.command == 'verify' else Broker(args.credentials, {t.symbol for t in tickers}, args.runtime, args.region)
    service = DataService(tickers, args.runtime, broker)
    workspace = Workspace(args.workspace) if args.command == 'serve' else None
    if workspace:
        service.attach_workspace(workspace, args.symbols)
    server = None
    try:
        if args.command == 'verify':
            for symbol in service.symbols:
                service.validate(symbol)
        elif args.command == 'reconcile':
            await service.reconcile()
        else:
            workspace.start_watcher()
            server = await start_http(service, args.port, args.cors_origin)
            print(f'LIVE: http://127.0.0.1:{args.port}/ | Longbridge real data | '
                  f'database: {args.runtime.resolve() / "bars.sqlite3"}', flush=True)
            if args.duration:
                try:
                    await asyncio.wait_for(service.run(), args.duration)
                except TimeoutError:
                    pass
            else:
                await service.run()
        summary = {s: service.validate(s) for s in service.symbols}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.command == 'serve':
            report = {'health': await service.api('/health', {}), 'readiness': summary,
                      'quotes': await service.api('/v1/quotes', {})}
            atomic_json(args.runtime / 'last_run_report.json', report)
        return 0 if summary and all(c['complete'] for s in summary.values() for c in s.values()) else 2
    finally:
        if workspace:
            workspace.stop_watcher()
        if server:
            await server.cleanup()
        service.store.close()


def main():
    args = parser().parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    try:
        path = args.workspace or resolve_latest_workspace()
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
    except (ValueError, OSError) as exc:
        logging.error('%s', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

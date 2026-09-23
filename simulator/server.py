"""One-command, isolated chart simulation with Quote and closed-bar scheduling."""
import argparse
import asyncio
import logging
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_service.calendar import TradingCalendar, ET
from data_service.config import load_tickers
from data_service.http_api import start_http
from data_service.service import DataService
from data_service.workspace import Workspace
from simulator.market import Market, SessionClock, SimulatedQuotes, default_start

ROOT = Path(__file__).resolve().parents[1]


def create_simulation(tickers, runtime, calendar, clock):
    market = Market([t.symbol for t in tickers], calendar, clock)
    service = DataService(tickers, runtime, market, calendar, clock=clock)
    service.mode = 'simulation'
    service.quotes = SimulatedQuotes(market, service.charts)
    return service


def parser():
    result = argparse.ArgumentParser(description='Offline chart and Quote simulator')
    result.add_argument('--workspace', type=Path, default=ROOT/'workspace.json')
    result.add_argument('--symbols', nargs='+', help='Optional subset of workspace focus/wait')
    result.add_argument('--port', type=int, default=18765)
    result.add_argument('--speed', type=float, default=1, help='Trading seconds per real second')
    result.add_argument('--start', help='Regular-session start in ET, e.g. 2026-09-18T13:44:45')
    return result


async def main(args=None):
    args = args or parser().parse_args()
    calendar = TradingCalendar()
    start = int(datetime.fromisoformat(args.start).replace(tzinfo=ET).timestamp()) if args.start else default_start(calendar)
    clock = SessionClock(calendar, start, args.speed)
    tickers = load_tickers(args.workspace, args.symbols, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix='chart-simulator-') as folder:
        service = create_simulation(tickers, Path(folder), calendar, clock)
        path = Path(folder) / 'workspace.json'
        shutil.copyfile(args.workspace, path)
        workspace = Workspace(path)
        service.attach_workspace(workspace, args.symbols)
        runner = None
        try:
            workspace.start_watcher()
            runner = await start_http(service, args.port)
            print(f'SIMULATION: http://127.0.0.1:{args.port}', flush=True)
            print(f'{len(tickers)} focus/wait symbols | {args.speed:g}x exchange time | temporary database | no broker', flush=True)
            await service.run()
        finally:
            workspace.stop_watcher()
            if runner:
                await runner.cleanup()
            service.store.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

"""One-command, isolated chart simulation with Quote and closed-bar scheduling."""
import argparse
import asyncio
import logging
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiohttp import web
from data_service.calendar import TradingCalendar, ET
from data_service.config import load_tickers
from data_service.http_api import create_app
from data_service.service import DataService
from simulator.market import Market, SessionClock, SimulatedQuotes, default_start

ROOT = Path(__file__).resolve().parents[1]


def create_simulation(tickers, runtime, calendar, clock):
    market = Market([t.symbol for t in tickers], calendar, clock)
    service = DataService(tickers, runtime, market, calendar, clock=clock)
    service.mode = 'simulation'
    service.quotes = SimulatedQuotes(market, service.charts)
    return service


def quote_app(service):
    app = web.Application()
    sockets = set()
    async def connected(request):
        ws = web.WebSocketResponse(heartbeat=10)
        await ws.prepare(request)
        sockets.add(ws)
        async def publish():
            try:
                while not ws.closed:
                    for quote in list(service.quotes.raw.values()):
                        await ws.send_json(quote)
                    await asyncio.sleep(1)
            except (ConnectionError, RuntimeError):
                await ws.close()
        sender = asyncio.create_task(publish())
        try:
            async for _ in ws:
                pass
        finally:
            sockets.discard(ws)
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
        return ws
    async def shutdown(_app):
        await asyncio.gather(*(ws.close(code=1001) for ws in list(sockets)))
    app.on_shutdown.append(shutdown)
    app.router.add_get('/', connected)
    return app


def parser():
    result = argparse.ArgumentParser(description='Offline chart and Quote simulator')
    result.add_argument('--workspace', type=Path, default=ROOT/'workspace.json')
    result.add_argument('--symbols', nargs='+', help='Optional subset of workspace focus/wait')
    result.add_argument('--port', type=int, default=18765)
    result.add_argument('--quote-port', type=int, default=18766)
    result.add_argument('--speed', type=float, default=1, help='Trading seconds per real second')
    result.add_argument('--start', help='Regular-session start in ET, e.g. 2026-09-18T13:44:45')
    return result


async def main(args=None):
    args = args or parser().parse_args()
    calendar = TradingCalendar()
    start = int(datetime.fromisoformat(args.start).replace(tzinfo=ET).timestamp()) if args.start else default_start(calendar)
    clock = SessionClock(calendar, start, args.speed)
    tickers = load_tickers(args.workspace, args.symbols)
    with tempfile.TemporaryDirectory(prefix='chart-simulator-') as folder:
        service = create_simulation(tickers, Path(folder), calendar, clock)
        runners = [web.AppRunner(create_app(service)), web.AppRunner(quote_app(service))]
        try:
            for runner, port in zip(runners, [args.port, args.quote_port]):
                await runner.setup()
                await web.TCPSite(runner, '127.0.0.1', port).start()
            print(f'SIMULATION: http://127.0.0.1:{args.port} | Quote ws://127.0.0.1:{args.quote_port}', flush=True)
            print(f'{len(tickers)} focus/wait symbols | {args.speed:g}x exchange time | temporary database | no broker', flush=True)
            await service.run()
        finally:
            for runner in runners:
                await runner.cleanup()
            service.store.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

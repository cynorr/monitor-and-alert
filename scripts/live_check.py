"""Explicit, bounded Longbridge check using one context and a temporary database."""
import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

from aiohttp import ClientSession

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_service.broker import Broker
from data_service.config import load_tickers
from data_service.http_api import start_http
from data_service.service import DataService
from data_service.store import atomic_json


async def run(args):
    tickers = load_tickers(ROOT / 'workspace.json', args.symbols)
    runtime = Path(tempfile.mkdtemp(prefix='longbridge-check-'))
    requests = []
    class ObservedBroker(Broker):
        async def candles(self, symbol, timeframe, count=1000, *, background=False):
            started = time.monotonic()
            rows = await super().candles(symbol, timeframe, count, background=background)
            requests.append({'symbol': symbol, 'timeframe': timeframe, 'count': count,
                             'returned': len(rows), 'seconds': round(time.monotonic() - started, 3)})
            return rows
    broker = ObservedBroker(ROOT / 'longbridge-token.txt', {t.symbol for t in tickers}, runtime)
    service = DataService(tickers, runtime, broker)
    runner = await start_http(service, args.port)
    task = asyncio.create_task(service.run())
    counts = {'messages': 0, 'history_snapshots': 0}
    print(f'LIVE CHECK http://127.0.0.1:{args.port}/ | runtime: {runtime}', flush=True)
    try:
        async with ClientSession() as client:
            async with client.ws_connect(f'http://127.0.0.1:{args.port}/v1/stream') as ws:
                await ws.send_json({'type': 'select', 'symbol': tickers[0].symbol,
                                    'timeframe': '4h', 'request_id': 1})
                deadline = time.monotonic() + args.duration
                while time.monotonic() < deadline:
                    if task.done(): task.result()
                    view = await ws.receive_json(timeout=15)
                    if view.get('request_id') == 1:
                        counts['messages'] += 1
                        counts['history_snapshots'] += int('bars' in view['charts']['4h'])
            async with client.ws_connect(f'http://127.0.0.1:{args.port}/v1/stream') as ws:
                view = await ws.receive_json(timeout=10)
                counts['reconnect_snapshot'] = 'bars' in view['charts'][view['timeframe']]
        report = {'tested_at': int(time.time()), 'symbols': service.symbols,
                  'market_open': service.calendar.is_open(int(time.time())),
                  'health': await service.api('/health', {}),
                  'readiness': await service.api('/v1/readiness', {}),
                  'stream': counts, 'requests': requests}
        atomic_json(runtime / 'report.json', report)
        print(json.dumps({'report': str(runtime / 'report.json'), 'market_open': report['market_open'],
                          'health': report['health'], 'stream': counts, 'requests': len(requests)}), flush=True)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runner.cleanup()
        service.store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbols', nargs='+', required=True, help='Subset of current workspace focus/wait')
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--port', type=int, default=28766)
    args = parser.parse_args()
    if not 0 < args.duration <= 600:
        parser.error('duration must be in (0, 600] seconds')
    asyncio.run(asyncio.wait_for(run(args), args.duration + 45))

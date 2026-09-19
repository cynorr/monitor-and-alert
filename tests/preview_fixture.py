"""Explicit offline browser fixture. Synthetic data, temporary DB, no credentials or SDK.
Run: .venv/bin/python tests/preview_fixture.py
"""
import asyncio
import math
import random
import sys
import tempfile
from datetime import datetime, date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aiohttp import web
from data_service.calendar import TradingCalendar, ET, PHASES
from data_service.config import Ticker
from data_service.http_api import create_app, UI_ROOT
from data_service.service import DataService
from data_service.store import Bar


async def main():
    clock = [int(datetime(2026, 9, 18, 13, 42, tzinfo=ET).timestamp())]
    cal = TradingCalendar(date(2026, 9, 19))
    symbols = ['DEMO', 'ALFA', 'BETA', 'GAMMA', 'TEST']
    with tempfile.TemporaryDirectory(prefix='monitor-offline-preview-') as runtime:
        service = DataService([Ticker(s + '.US', s, 'focus' if i < 3 else 'wait')
                               for i, s in enumerate(symbols)], Path(runtime), calendar=cal)
        rng = random.Random(23)
        for i, symbol in enumerate(service.symbols):
            for tf in PHASES:
                days = cal.completed_days(clock[0], 1050 if tf == '1d' else 40) + [date(2026, 9, 18)]
                times = sorted({ts for d in days for ts, end in cal.grid(d, tf) if end <= clock[0]})[-1000:]
                rows = []
                previous = 80 + i * 45
                for j, ts in enumerate(times):
                    base = 80 + i * 45 + j * 0.12 + math.sin(j / 14) * 3 + math.sin(j / 59) * 7
                    close = base + rng.uniform(-1.5, 1.5)
                    volume = rng.randint(15000, 2000000 if tf == '1d' else 180000)
                    rows.append(Bar(symbol, tf, ts, previous, max(previous, close) + rng.random() * 1.5,
                                    min(previous, close) - rng.random() * 1.5, close, volume, volume * (previous + close) / 2))
                    previous = close
                service.store.upsert(rows, clock[0], {'symbol':symbol,'timeframe':tf,'run_id':service.run_id,
                    'as_of':clock[0],'returned_count':1000,'returned_closed_ts':times,'rejected':[]})
        class Quotes:
            def __init__(self): self.values = {}
            def output(self, symbol, now):
                return {'symbol':symbol,'regular':self.values.get(symbol),'extended':{},'connection_health':'LIVE','error':None}
        quotes = Quotes()
        service.quotes = quotes
        service.initialized, service.phase = True, 'running'
        @web.middleware
        async def label(request, handler):
            if request.path == '/':
                return web.Response(text=(UI_ROOT / 'index.html').read_text().replace('个人行情工作台','离线测试 · 合成数据'),content_type='text/html')
            return await handler(request)
        app = create_app(service)
        app.middlewares.insert(0, label)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 18765)
        await site.start()
        print('OFFLINE SYNTHETIC browser fixture: http://127.0.0.1:18765', flush=True)
        try:
            with patch('data_service.service.time.time', lambda: clock[0]):
                while True:
                    for i, symbol in enumerate(service.symbols):
                        price = 201 + i * 45 + math.sin(clock[0] / 12) * 0.8
                        opened = cal.session(date(2026,9,18))[0]
                        prefix = sum(b.volume for b in service.store.bars(symbol, '5m', opened))
                        q = {'last_price':price,'timestamp':clock[0],'trade_session':'Intraday','cumulative_volume':prefix+34000,'source':'fixture'}
                        quotes.values[symbol] = q
                        service.charts.apply_quote(symbol, q)
                    await asyncio.sleep(1)
                    clock[0] += 1
        finally:
            await runner.cleanup()
            service.store.close()


if __name__ == '__main__':
    try: asyncio.run(main())
    except KeyboardInterrupt: pass

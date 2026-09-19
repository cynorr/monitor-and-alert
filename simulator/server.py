"""Intraday-only Quote generator. Connect a WebSocket client to receive JSON."""
import asyncio
import json
import random
import time
from pathlib import Path

from websockets.asyncio.server import broadcast, serve

WORKSPACE = Path(__file__).resolve().parents[1] / 'workspace.json'
HOST, PORT = '127.0.0.1', 18766


def load_symbols():
    workspace = json.loads(WORKSPACE.read_text())
    return list(dict.fromkeys(
        ticker if ticker.endswith('.US') else ticker + '.US'
        for ticker, entry in workspace['statuses'].items()
        if entry['status'] in ('focus', 'wait')
    ))


class Market:
    def __init__(self, symbols):
        self.random = random.Random(7)
        self.quotes = {}
        self.settings = {}
        for index, symbol in enumerate(symbols):
            price = self.random.randrange(500, 15000) * 10
            self.settings[symbol] = (price, (1, -1, 0)[index % 3], self.random.randint(10, 800))
            self.quotes[symbol] = {
                'symbol': symbol, 'sequence': 0, 'last_done': f'{price / 1000:.3f}',
                'open': f'{price / 1000:.3f}', 'high': f'{price / 1000:.3f}',
                'low': f'{price / 1000:.3f}', 'timestamp': int(time.time()),
                'volume': 0, 'turnover': '0.000', 'trade_status': 0,
                'trade_session': 0, 'current_volume': 0, 'current_turnover': '0.000', 'tag': 0,
            }

    def tick(self):
        now = int(time.time())
        for symbol, quote in self.quotes.items():
            anchor, direction, typical_volume = self.settings[symbol]
            price = float(quote['last_done'])
            change = direction * 0.00004 + self.random.gauss(0, 0.0002)
            price = round(min(anchor / 1000 * 1.3, max(anchor / 1000 * 0.7, price * (1 + change))), 3)
            volume = max(1, round(typical_volume * self.random.uniform(0.3, 1.7)))
            turnover = round(price * volume, 3)
            quote.update(
                sequence=quote['sequence'] + 1, timestamp=now, last_done=f'{price:.3f}',
                high=f"{max(float(quote['high']), price):.3f}",
                low=f"{min(float(quote['low']), price):.3f}",
                volume=quote['volume'] + volume,
                turnover=f"{float(quote['turnover']) + turnover:.3f}",
                current_volume=volume, current_turnover=f'{turnover:.3f}',
            )


async def main():
    market = Market(load_symbols())

    async def connected(socket):
        for quote in market.quotes.values():
            await socket.send(json.dumps(quote))
        await socket.wait_closed()

    async with serve(connected, HOST, PORT) as server:
        print(f'SIMULATION — ws://{HOST}:{PORT} — {len(market.quotes)} focus/wait symbols', flush=True)
        print('One Quote per symbol per second. Ctrl+C to stop.', flush=True)
        while True:
            market.tick()
            for quote in market.quotes.values():
                broadcast(server.connections, json.dumps(quote))
            await asyncio.sleep(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

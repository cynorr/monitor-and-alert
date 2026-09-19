"""Read-only broker recovery check using a subset of the current workspace."""
import asyncio
import fcntl
import json
import time
from pathlib import Path

from data_service.broker import Broker
from data_service.config import load_tickers
from data_service.service import DataService
from data_service.store import atomic_json


async def main():
    tickers = load_tickers(Path('workspace.json'), ['PAYS'])
    runtime = Path('runtime')
    broker = Broker(Path('longbridge-token.txt'), {t.symbol for t in tickers}, runtime)
    service = DataService(tickers, runtime, broker)
    quotes = service.quotes
    try:
        await quotes.connect()
        first = quotes.output('PAYS.US', int(time.time()))
        await quotes.disconnect()
        await quotes.connect()
        await asyncio.sleep(5)
        restored = quotes.output('PAYS.US', int(time.time()))
        assert first['regular'] and restored['regular']
        assert restored['regular']['timestamp'] >= first['regular']['timestamp']
        before = service.store.bars('PAYS.US', '5m', limit=1)[0].ts
        target = service.calendar.latest_closed('5m', int(time.time()))
        await service.update_bar('PAYS.US', '5m', target)
        after = service.store.bars('PAYS.US', '5m', limit=1)[0].ts
        assert after == target
        report = {'first': first, 'restored': restored, 'pushes': quotes.push_count,
                  'previous_last_5m': before, 'expected_last_closed_5m': target, 'actual_last_5m': after,
                  'closed_bar_update_ok': True, 'snapshot_recovery_ok': True}
        atomic_json(runtime / 'recovery-smoke.json', report)
        print(json.dumps(report, indent=2))
    finally:
        await quotes.disconnect()
        service.store.close()


if __name__ == '__main__':
    with Path('runtime/service.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(asyncio.wait_for(main(), 60))

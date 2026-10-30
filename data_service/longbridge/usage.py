"""One local symbol/account ledger; request paths only update memory."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
MONTH_ZONE = ZoneInfo('Asia/Hong_Kong')
SAVE_INTERVAL = 10
ACCOUNT_SWITCH_AT = 90
ACCOUNT_LIMIT = 100


def month_of(timestamp):
    return datetime.fromtimestamp(timestamp, MONTH_ZONE).strftime('%Y-%m')


def read_usage(path: Path):
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or any(
            not isinstance(row, dict) or not isinstance(row.get('account'), str)
            or not isinstance(row.get('last_access_at'), int)
            for row in data.values()
        ):
            raise ValueError('Expected symbol -> account / last_access_at')
        return data
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning('Could not read Longbridge usage; starting an empty ledger: %s', exc)
        return {}


class SymbolUsage:
    def __init__(self, path: Path, accounts):
        self.path, self.accounts = path, tuple(accounts)
        self.data = read_usage(path)
        self.dirty = False
        self.save_lock = asyncio.Lock()

    def counts(self, now=None):
        month = month_of(time.time() if now is None else now)
        counts = Counter(row['account'] for row in self.data.values()
                         if month_of(row['last_access_at']) == month)
        return {account: counts[account] for account in self.accounts}

    def access(self, symbol):
        now = int(time.time())
        previous = self.data.get(symbol)
        if (previous and previous['account'] in self.accounts
                and month_of(previous['last_access_at']) == month_of(now)):
            account = previous['account']
        else:
            counts = self.counts(now)
            account = next((account for limit in (ACCOUNT_SWITCH_AT, ACCOUNT_LIMIT)
                            for account in self.accounts if counts[account] < limit), None)
            if account is None:
                raise RuntimeError('All Longbridge accounts have reached the local monthly symbol limit')
        row = {'account': account, 'last_access_at': now}
        if row != previous:
            self.data[symbol] = row
            self.dirty = True
        return account

    def _write(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(payload)

    async def flush(self):
        async with self.save_lock:
            if not self.dirty:
                return
            payload = json.dumps(self.data, indent=2, ensure_ascii=False) + '\n'
            self.dirty = False
            write = asyncio.create_task(asyncio.to_thread(self._write, payload))
            # A cancelled caller must finish its writer before another snapshot writes.
            try:
                await asyncio.shield(write)
            except asyncio.CancelledError:
                try:
                    await write
                except OSError as exc:
                    self.dirty = True
                    log.warning('Could not save Longbridge usage: %s', exc)
                raise
            except OSError as exc:
                self.dirty = True
                log.warning('Could not save Longbridge usage: %s', exc)

    async def run(self):
        try:
            while True:
                await asyncio.sleep(SAVE_INTERVAL)
                await self.flush()
        finally:
            await self.flush()

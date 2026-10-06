"""SnapTrade acquisition only: signed GETs, account budget, one raw snapshot."""
from __future__ import annotations

import asyncio
import base64
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
from pathlib import Path
import time
from urllib.parse import urlencode

from .network import create_session, proxy_url
from .store import atomic_json


def now():
    return datetime.now(timezone.utc).isoformat()


def decimal_json(value):
    return json.loads(json.dumps(value, default=lambda n: format(n, 'f'), allow_nan=False))


class SnapTrade:
    def __init__(self, client_id, consumer_key, account_id, data_file: Path):
        self.client_id, self.consumer_key, self.account_id = client_id, consumer_key, account_id
        self.secrets = (client_id, consumer_key, account_id)
        self.data_file = data_file
        self.raw = None
        if data_file.exists():
            try:
                cached = json.loads(data_file.read_text(), parse_float=Decimal)
                if cached['account']['id'] == account_id:
                    self.raw = cached
            except (OSError, ValueError, KeyError, TypeError):
                pass  # A cache cannot prevent the immediate authoritative refresh.
        self.starts = deque()
        self.session = None

    async def get(self, resource, params=None):
        # All account endpoints, including transaction pages, share this budget.
        while True:
            current = time.monotonic()
            while self.starts and current - self.starts[0] >= 60.1:
                self.starts.popleft()
            if len(self.starts) < 10:
                break
            await asyncio.sleep(max(0, 60.1 - (current - self.starts[0])))
        self.starts.append(time.monotonic())
        query = urlencode({'clientId': self.client_id, 'timestamp': int(time.time()), **(params or {})})
        path = '/api/v1' + resource
        payload = json.dumps({'content': None, 'path': path, 'query': query},
                             sort_keys=True, separators=(',', ':')).encode()
        signature = base64.b64encode(hmac.new(self.consumer_key.encode(), payload, hashlib.sha256).digest()).decode()
        if self.session is None:
            self.session = create_session(30)
        async with self.session.get('https://api.snaptrade.com' + path + '?' + query,
                                    headers={'Signature': signature, 'Accept': 'application/json'},
                                    proxy=proxy_url()) as response:
            if response.status != 200:
                # Never expose signed request URLs or arbitrary upstream bodies.
                raise RuntimeError(f'SnapTrade HTTP {response.status}')
            return json.loads(await response.text(), parse_float=Decimal)

    async def refresh(self):
        path = '/accounts/' + self.account_id
        raw = dict(self.raw) if self.raw else {'source_timestamps': {}}
        raw['source_timestamps'] = dict(raw['source_timestamps'])
        timestamps = raw['source_timestamps']
        raw['positions'] = await self.get(path + '/positions/all')
        timestamps['positions'] = now()
        detail = await self.get(path)
        timestamps['account_total'] = now()
        raw['account'] = {'id': detail['id'], 'balance': detail['balance'],
                          'sync_status': {'transactions': detail['sync_status']['transactions']}}
        if detail['id'] != self.account_id:
            raise ValueError('SnapTrade returned a different account')
        balances = await self.get(path + '/balances')
        raw['cash'] = next(b['cash'] for b in balances if b['currency']['code'] == 'USD')
        timestamps['cash'] = now()
        through = detail['sync_status']['transactions']['last_successful_sync']
        if not self.raw or self.raw['activities_through'] != through:
            activities, offset = [], 0
            while True:
                page = await self.get(path + '/activities', {'offset': offset, 'limit': 1000})
                activities.extend(page['data'])
                offset += len(page['data'])
                if offset >= page['pagination']['total']:
                    break
                if not page['data']:
                    raise ValueError('SnapTrade activities page is incomplete')
            raw['activities'], raw['activities_through'] = activities, through
            timestamps['activities'] = now()
        raw['orders'] = await self.get(path + '/orders', {'state': 'executed', 'days': 90})
        timestamps['orders'] = now()
        raw['fetched_at'] = now()
        return raw

    def commit(self, raw):
        # Publish/cache only after holdings accounting has accepted the whole fetch.
        atomic_json(self.data_file, decimal_json(raw))
        self.data_file.chmod(0o600)
        self.raw = raw

    async def close(self):
        if self.session is not None:
            await self.session.close()
            self.session = None

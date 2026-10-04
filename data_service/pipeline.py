"""Prepare Massive raw data, adjusted bars, and Scan features once at startup."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import time

import aiohttp

from .calendar import TradingCalendar
from .massive import daily, splits, build
from .network import create_session, proxy_url, read_massive_token
from .scan import build_day, publish_day, workspace_scope
from .store import atomic_json

RETRY_DELAYS = (2, 5, 10)
REQUEST_INTERVAL = 15
STAGES = ('daily', 'splits', 'bars', 'features')


def updated_at(timestamp=None):
    return datetime.fromtimestamp(time.time() if timestamp is None else timestamp, timezone.utc).isoformat()


async def complete_thread(function, *args, **kwargs):
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class RequestFailure(Exception):
    """Safe request failure; carries no URL, request headers, or response body."""


class MassivePipeline:
    def __init__(self, paths, calendar=None, *, credentials=Path('massive-token.txt')):
        self.paths, self.calendar, self.credentials = paths, calendar or TradingCalendar(), Path(credentials)
        self.session, self._token, self._last_request = None, None, 0.0
        self._running = False
        self._data = {}
        self._hydrate()

    def _hydrate(self):
        target = daily.target_date(self.calendar)
        split_target = daily.mature_date()
        try:
            saved = json.loads(self.paths.pipeline_status.read_bytes())
        except (OSError, ValueError):
            saved = {}
        self._data = {'target_date': target.isoformat(), 'ready': False, 'running': False}
        for name in STAGES:
            previous = saved.get(name, {}) if isinstance(saved, dict) else {}
            if not isinstance(previous, dict):
                previous = {}
            self._data[name] = {'status': 'idle', 'target': split_target.isoformat() if name == 'splits' else target.isoformat(),
                                'updated_at': previous.get('updated_at'), 'error': None}
        self._data['bars']['input_revision'] = None
        self._data['features'].update(date=None, input_revision=None)
        try:
            raw_dates = [date.fromisoformat(path.stem) for path in self.paths.daily_dir.glob('????-??-??.json')]
            latest = max(raw_dates)
            if latest != target:
                raise ValueError('Daily target is not locally available')
            start = max(daily.shift_year(target, -2), latest - timedelta(days=daily.REPAIR_DAYS))
            for day in self.calendar.days(start, target):
                daily.read_day(self.paths.daily_dir / f'{day.isoformat()}.json', day)
            self._ready('daily', self.paths.daily_dir / f'{target.isoformat()}.json')
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            pass
        try:
            split_data = splits.read_existing(self.paths.splits_file)
            if split_data and split_data['end_date'] == split_target and split_data['start_date'] <= daily.shift_year(split_target, -2):
                self._ready('splits', self.paths.splits_file)
        except (OSError, ValueError, TypeError, KeyError, OverflowError):
            pass
        try:
            revision = build.input_revision(self.paths, target)
            meta = build.metadata(self.paths.daily_db)
            expected = {'completed_date': target.isoformat(), 'adjustment': 'split_adjusted',
                        'volume_rounding': 'half_up', 'source': 'massive_grouped_daily',
                        'session': 'massive_daily', 'input_revision': revision}
            if all(meta.get(key) == value for key, value in expected.items()):
                self._data['bars']['input_revision'] = revision
                self._ready('bars', self.paths.daily_db)
        except (OSError, ValueError, TypeError, KeyError, build.sqlite3.Error):
            pass
        for path in sorted(self.paths.days.glob('*/scan.json'), reverse=True):
            try:
                snapshot = json.loads(path.read_bytes())
                if not isinstance(snapshot, dict) or snapshot.get('date') != path.parent.name or not isinstance(snapshot.get('rows'), list) or snapshot.get('mock'):
                    continue
                self._data['features'].update(date=snapshot['date'], input_revision=snapshot.get('input_revision'),
                                               updated_at=snapshot.get('updated_at') or updated_at(path.stat().st_mtime))
                if (snapshot['date'] == target.isoformat() and snapshot.get('input_revision')
                        and snapshot['input_revision'] == self._data['bars']['input_revision']):
                    self._data['features']['status'] = 'ready'
                break
            except (OSError, ValueError, TypeError, KeyError):
                continue
        self._set_ready()

    def _ready(self, name, path=None):
        stage = self._data[name]
        stage.update(status='ready', error=None)
        if path is not None:
            stage['updated_at'] = updated_at(Path(path).stat().st_mtime)

    def _set_ready(self):
        self._data['ready'] = (all(self._data[name]['status'] == 'ready' for name in STAGES)
                              and self._data['features']['date'] == self._data['target_date']
                              and self._data['features']['input_revision'] == self._data['bars']['input_revision']
                              and not self._data.get('error'))
        self._data['running'] = self._running

    def state(self):
        self._set_ready()
        return deepcopy(self._data)

    def _save(self):
        self._data.pop('error', None)
        try:
            atomic_json(self.paths.pipeline_status, self.state())
        except OSError:
            self._data['error'] = 'Pipeline status could not be saved'
            return False
        return True

    async def _fetch_json(self, url):
        if self._token is None:
            try:
                self._token = read_massive_token(self.credentials)
            except (OSError, ValueError):
                raise RequestFailure('Massive credentials unavailable or invalid') from None
        if self.session is None or self.session.closed:
            self.session = create_session(60)
        delay = REQUEST_INTERVAL - (time.monotonic() - self._last_request)
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_request = time.monotonic()
        try:
            async with self.session.get(url, headers={'Authorization': f'Bearer {self._token}', 'Accept': 'application/json'},
                                        proxy=proxy_url()) as response:
                if response.status != 200:
                    raise RequestFailure(f'Massive HTTP {response.status}')
                body = await response.read()
            return await asyncio.to_thread(json.loads, body)
        except (aiohttp.ClientError, TimeoutError):
            raise RequestFailure('Massive network request failed') from None
        except (ValueError, UnicodeError):
            raise RequestFailure('Massive response is not valid JSON') from None

    async def _step(self, name, operation):
        stage = self._data[name]
        stage.update(status='running', error=None)
        if not self._save():
            stage.update(status='error', error=f'{name}: pipeline status could not be saved')
            return False, None
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                result = await operation()
            except asyncio.CancelledError:
                stage.update(status='idle', error=None)
                self._save()
                raise
            except Exception as exc:
                reason = str(exc) if isinstance(exc, RequestFailure) else f'{type(exc).__name__}: local data or preparation failed'
                stage['error'] = f'{name}: {reason}'
                if attempt < len(RETRY_DELAYS):
                    self._save()
                    try:
                        await asyncio.sleep(RETRY_DELAYS[attempt])
                    except asyncio.CancelledError:
                        stage.update(status='idle', error=None)
                        self._save()
                        raise
                    continue
                stage['status'] = 'error'
                self._save()
                return False, None
            stage.update(status='ready', updated_at=updated_at(), error=None)
            self._save()
            return True, result
        return False, None

    async def run(self, force=False, on_publish=None):
        if self._running:
            return None
        self._hydrate()
        if self._data['ready'] and not force:
            self._save()
            return None
        self._running = True
        target = date.fromisoformat(self._data['target_date'])
        split_target = date.fromisoformat(self._data['splits']['target'])
        snapshot = None
        try:
            if force:
                for name in STAGES:
                    self._data[name].update(status='idle', error=None)
            if self._data['daily']['status'] != 'ready':
                ok, _ = await self._step('daily', lambda: daily.update(self.paths.daily_dir, target, self.calendar, self._fetch_json))
                if not ok:
                    return None
                self._data['bars']['status'] = 'idle'
            if self._data['splits']['status'] != 'ready':
                ok, _ = await self._step('splits', lambda: splits.update(self.paths.splits_file, split_target, self._fetch_json))
                if not ok:
                    return None
                self._data['bars']['status'] = 'idle'
            if self._data['bars']['status'] != 'ready':
                async def build_bars():
                    return await complete_thread(build.build, self.paths, target, self.calendar)
                ok, result = await self._step('bars', build_bars)
                if not ok:
                    return None
                self._data['bars']['input_revision'] = result['input_revision']
            revision = self._data['bars']['input_revision']
            if (self._data['features']['status'] != 'ready' or self._data['features']['input_revision'] != revision):
                async def prepare_features():
                    tracked, hidden = workspace_scope(self.paths.days, target.isoformat())
                    result = await complete_thread(build_day, self.paths.daily_db, target.isoformat(), self.calendar,
                                                   log_path=self.paths.root / 'invalid_ohlc.jsonl',
                                                   tracked_tickers=tracked, hidden_tickers=hidden)
                    if await complete_thread(build.input_revision, self.paths, target) != revision:
                        raise ValueError('Massive inputs changed before feature publication')
                    result.update(input_revision=revision, updated_at=updated_at())
                    publish_day(self.paths.days, result)
                    return result
                ok, snapshot = await self._step('features', prepare_features)
                if not ok:
                    return None
                self._data['features'].update(date=snapshot['date'], input_revision=revision,
                                               updated_at=snapshot['updated_at'])
                if on_publish is not None:
                    try:
                        on_publish(snapshot)
                    except Exception:
                        self._data['features'].update(status='error', error='features: workspace update failed')
                        return None
            return snapshot
        finally:
            self._running = False
            self._save()

    async def close(self):
        if self.session is not None:
            await self.session.close()
            self.session = None

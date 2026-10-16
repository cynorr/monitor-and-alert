"""Independent SQLite/cache, daily refresh and weekly earnings lookahead."""
from __future__ import annotations

import asyncio
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sqlite3
import time
from zoneinfo import ZoneInfo

from .nasdaq import Nasdaq, SCREENER, EARNINGS, parse_companies, parse_earnings, RequestFailure

ET = ZoneInfo('America/New_York')
log = logging.getLogger(__name__)
SCHEMA = '''
CREATE TABLE IF NOT EXISTS companies (symbol TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS earnings_days (date TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
'''


def stamp(now):
    return datetime.fromtimestamp(now, timezone.utc).isoformat(timespec='seconds')


def local_day(value):
    return datetime.fromisoformat(value).astimezone(ET).date()


def dates(start, end):
    return [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)]


class Store:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        companies, days, events, metadata, day_symbols = {}, {}, {}, {}, {}
        if not self.path.exists():
            return companies, days, events, metadata, day_symbols
        with closing(sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            metadata = dict(db.execute('SELECT key, value FROM metadata'))
            companies = {key: json.loads(payload) for key, payload in db.execute('SELECT symbol, payload FROM companies')}
            for day, payload, updated in db.execute('SELECT date, payload, updated_at FROM earnings_days ORDER BY date'):
                rows = parse_earnings(json.loads(payload), day)
                days[day] = updated
                day_symbols[day] = {event['symbol'] for event in rows}
                for event in rows:
                    events.setdefault(event['symbol'], []).append(event)
        return companies, days, events, metadata, day_symbols

    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        db.executescript(SCHEMA)
        return db

    def companies(self, values, updated):
        with closing(self.connection()) as db, db:
            db.execute('DELETE FROM companies')
            db.executemany('INSERT INTO companies VALUES (?, ?)',
                           [(key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()])
            db.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?)', ('companies_updated_at', updated))

    def earnings(self, day, payload, updated):
        with closing(self.connection()) as db, db:
            db.execute('INSERT OR REPLACE INTO earnings_days VALUES (?, ?, ?)',
                       (day, json.dumps(payload, ensure_ascii=False), updated))

    def weekly(self, updated):
        with closing(self.connection()) as db, db:
            db.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?)', ('earnings_weekly_at', updated))


class AdditionalInfo:
    def __init__(self, directory, *, enabled=True, now=time.time):
        self.store = Store(Path(directory) / 'info.sqlite3')
        self.enabled, self.now = enabled, now
        self.companies, self.days, self.events, self.metadata = {}, {}, {}, {}
        self.day_symbols = {}
        self.revision = 0
        self.running = False
        self.errors = {'companies': None, 'earnings': None, 'cache': None}
        self.progress = None
        self.wakeup = asyncio.Event()
        self.force = False

    async def load(self):
        self.companies, self.days, self.events, self.metadata, self.day_symbols = await asyncio.to_thread(self.store.load)
        self.errors['cache'] = None
        self.revision += 1

    def state(self):
        return {'enabled': self.enabled, 'running': self.running or self.force, 'progress': self.progress,
                'companies_updated_at': self.metadata.get('companies_updated_at'),
                'earnings_updated_at': max(self.days.values(), default=None), 'errors': dict(self.errors)}

    def info(self, symbol):
        today = datetime.fromtimestamp(self.now(), ET).date().isoformat()
        company = self.companies.get(symbol, {})
        events = self.events.get(symbol, [])
        reported = [event for event in events if event['reported'] and event['date'] <= today]
        upcoming = [event for event in events if not event['reported'] and event['date'] >= today]
        def brief(event):
            return {key: event[key] for key in ('date', 'session', 'fiscal_period')} if event else None
        return {'symbol': symbol, **{key: company.get(key) for key in ('company_name', 'sector', 'industry', 'market_cap')},
                'earnings': {'last': brief(max(reported, key=lambda event: event['date'], default=None)),
                             'next': brief(min(upcoming, key=lambda event: event['date'], default=None))},
                'companies_updated_at': self.metadata.get('companies_updated_at'),
                'earnings_updated_at': max((self.days[event['date']] for event in events), default=None),
                'server_time': int(self.now())}

    def plan(self, *, force=False):
        today = datetime.fromtimestamp(self.now(), ET).date()
        recent = [day for day in dates(today - timedelta(days=7), today + timedelta(days=45))
                  if force or day not in self.days or local_day(self.days[day]) != today]
        history = [day for day in reversed(dates(today - timedelta(days=120), today - timedelta(days=8)))
                   if day not in self.days]
        weekly = self.metadata.get('earnings_weekly_at')
        weekly_due = force or not weekly or (today - local_day(weekly)).days >= 7
        far = [day for day in dates(today + timedelta(days=46), today + timedelta(days=120))
               if force or day not in self.days or (today - local_day(self.days[day])).days >= 7] if weekly_due else []
        return recent + history + far, weekly_due

    def request_refresh(self):
        if not self.enabled:
            raise ValueError('Additional info refresh is disabled for this session')
        if self.running or self.force:
            raise ValueError('Additional info refresh already running')
        self.force = True
        self.wakeup.set()
        return self.state()

    async def refresh(self, fetch, *, force=False, earnings_dates=None, companies=True):
        self.running = True
        try:
            today = datetime.fromtimestamp(self.now(), ET).date()
            updated = self.metadata.get('companies_updated_at')
            if companies and (force or not updated or local_day(updated) != today):
                self.progress = {'source': 'companies'}
                try:
                    values = await asyncio.to_thread(parse_companies, await fetch(SCREENER))
                    updated = stamp(self.now())
                    await asyncio.to_thread(self.store.companies, values, updated)
                    self.companies = values
                    self.metadata['companies_updated_at'] = updated
                    self.errors['companies'] = None
                    self.revision += 1
                except (RequestFailure, ValueError, OSError, sqlite3.Error) as error:
                    self.errors['companies'] = str(error)
                    log.warning('Additional company info: %s', error)
            planned, weekly_due = self.plan(force=force)
            planned = planned if earnings_dates is None else earnings_dates
            for index, day in enumerate(planned):
                self.progress = {'source': 'earnings', 'date': day, 'completed': index, 'total': len(planned)}
                try:
                    payload = await fetch(EARNINGS + day)
                    values = await asyncio.to_thread(parse_earnings, payload, day)
                    updated = stamp(self.now())
                    await asyncio.to_thread(self.store.earnings, day, payload, updated)
                except (RequestFailure, ValueError, OSError, sqlite3.Error) as error:
                    self.errors['earnings'] = f'{day}: {error}'
                    log.warning('Additional earnings info: %s', self.errors['earnings'])
                    break
                symbols = {event['symbol'] for event in values}
                for key in symbols | self.day_symbols.get(day, set()):
                    self.events[key] = [event for event in self.events.get(key, []) if event['date'] != day]
                for event in values:
                    self.events.setdefault(event['symbol'], []).append(event)
                self.days[day] = updated
                self.day_symbols[day] = symbols
                self.errors['earnings'] = None
                self.revision += 1
            else:
                if earnings_dates is None and weekly_due:
                    updated = stamp(self.now())
                    await asyncio.to_thread(self.store.weekly, updated)
                    self.metadata['earnings_weekly_at'] = updated
        finally:
            self.running = False
            self.progress = None

    async def run(self):
        while True:
            self.wakeup.clear()
            force, self.force = self.force, False
            try:
                if self.errors['cache'] or self.revision == 0:
                    await self.load()
                if not self.enabled:
                    return
                async with Nasdaq() as source:
                    await self.refresh(source.fetch, force=force)
            except (OSError, ValueError, sqlite3.Error) as error:
                self.errors['cache'] = str(error)
                log.warning('Additional info cache: %s', error)
            if not self.enabled:
                return
            now = datetime.fromtimestamp(self.now(), ET)
            midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), ET)
            try:
                await asyncio.wait_for(self.wakeup.wait(), max(1, midnight.timestamp() - self.now()))
            except TimeoutError:
                pass

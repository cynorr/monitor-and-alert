from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from .calendar import UTC, PHASES, TradingCalendar
from .store import BarStore, atomic_json

log = logging.getLogger(__name__)


class DataValidator:
    def __init__(self, store: BarStore, calendar: TradingCalendar, path: Path):
        self.store, self.calendar, self.path = store, calendar, path
        self.states: dict[str, dict] = {}
        self.cache: dict[tuple, tuple[tuple, dict]] = {}

    def check(self, symbol: str, tf: str, now: int, run_id: str | None) -> dict:
        target = self.calendar.latest_closed(tf, now)
        key = (symbol, tf)
        revision = self.store.revisions.get(key, 0)
        signature = (revision, target, run_id)
        if key in self.cache and self.cache[key][0] == signature:
            return self.cache[key][1]
        batch = self.store.batch(symbol, tf)
        rows = self.store.bars(symbol, tf, limit=1000)
        synced = bool(batch and batch['run_id'] == run_id)
        starts = batch['returned_closed_ts'] if batch else []
        rejected_starts = [r['ts'] for r in (batch or {}).get('rejected', [])
                           if r['ts'] is not None and r['ts'] <= target]
        bounds = starts + rejected_starts
        first = min(bounds) if bounds else (rows[0].ts if rows else target)
        # Only the current display window is required, including its partial first day.
        if len(rows) == 1000:
            first = max(first, rows[0].ts)
        expected = self.calendar.expected(tf, first, target, now)
        present, invalid = set(), []
        for row in rows:
            if row.ts < first:
                continue
            try:
                row.validate(self.calendar, now)
                present.add(row.ts)
            except ValueError as exc:
                invalid.append({'ts': row.ts, 'error': str(exc)})
        rejected = [r for r in (batch or {}).get('rejected', [])
                    if r['ts'] is None or first <= r['ts'] <= target]
        invalid += rejected
        missing = sorted(set(expected) - present)
        unexpected = sorted(present - set(expected))
        latest_ok = target in present and not any(r['ts'] in (target, None) for r in invalid)
        warnings = []
        if batch and batch.get('returned_count', len(starts)) < 1000:
            warnings.append(f'{tf}: Short history ({len(rows)} samples)')
        if missing:
            warnings.append(f'{tf}: {len(missing)} missing bars')
        if invalid or unexpected:
            warnings.append(f'{tf}: Invalid bar data')
        result = {'timeframe': tf, 'synced': synced, 'target': target,
                  'latest': max(present) if present else None,
                  'loaded': synced and latest_ok,
                  'ok': synced and latest_ok and not missing and not invalid and not unexpected,
                  'available_count': len(present), 'expected_count': len(expected),
                  'missing_count': len(missing), 'missing': missing[:100],
                  'invalid': invalid[:20], 'warnings': warnings,
                  'as_of': (batch or {}).get('as_of')}
        self.cache[key] = (signature, result)
        return result

    def validate(self, symbol: str, now: int, run_id: str | None = None) -> dict:
        if run_id is None:
            batches = [self.store.batch(symbol, tf) for tf in PHASES]
            batches = [b for b in batches if b]
            run_id = max(batches, key=lambda b: b['as_of'])['run_id'] if batches else None
        checks = {tf: self.check(symbol, tf, now, run_id) for tf in PHASES}
        ready = all(checks[tf]['ok'] for tf in ('1d', '5m'))
        full = all(c['ok'] for c in checks.values())
        state = {'schema_version': 2, 'ready': ready, 'full_ready': full,
                 'loaded': all(checks[tf]['loaded'] for tf in ('1d', '5m')),
                 'through': {tf: c['latest'] for tf, c in checks.items()},
                 'timeframes': checks, 'warnings': [w for c in checks.values() for w in c['warnings']],
                 'validated_at': datetime.fromtimestamp(now, UTC).isoformat()}
        self.states[symbol] = state
        return state

    def save(self):
        try:
            atomic_json(self.path, self.states)
        except OSError as exc:
            log.warning('Derived readiness JSON write failed: %s', exc)

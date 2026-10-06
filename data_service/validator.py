"""Cached checks of the current recent window; never downloads or writes status files."""
from __future__ import annotations

from .calendar import PHASES


class DataValidator:
    def __init__(self, store, calendar):
        self.store, self.calendar = store, calendar
        self.cache = {}

    def check(self, symbol, tf, now):
        target = self.calendar.latest_closed(tf, now)
        key = (symbol, tf)
        session = self.calendar.window_session(now)
        signature = (self.store.revisions.get(key, 0), target, session)
        if key in self.cache and self.cache[key][0] == signature:
            return self.cache[key][1]
        batch = self.store.batch(symbol, tf)
        rows = self.store.window(symbol, tf)
        present, errors = set(), []
        for row in rows:
            try:
                row.validate(self.calendar, now)
                present.add(row.ts)
            except ValueError as exc:
                errors.append(f'{row.ts}: {exc}')
        # Historical holes are accepted, including within the returned recent window.
        # Only the current closed target must exist; never bridge old gaps.
        missing = [] if target in present else [target]
        if batch and tuple(batch['session']) != session:
            errors.append('Waiting for current session refresh')
        if missing:
            errors.insert(0, f'Missing {len(missing)} bars; first timestamp {missing[0]}')
        result = {'complete': bool(batch) and not errors, 'target': target,
                  'latest': max(present) if present else None, 'count': len(present),
                  'missing': missing, 'errors': errors}
        self.cache[key] = (signature, result)
        return result

    def validate(self, symbol, now):
        return {tf: self.check(symbol, tf, now) for tf in PHASES}

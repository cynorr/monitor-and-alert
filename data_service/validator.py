from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from .calendar import ET, UTC, PHASES, TradingCalendar
from .store import BarStore, atomic_json

log = logging.getLogger(__name__)


class DataValidator:
    def __init__(self, store: BarStore, calendar: TradingCalendar, path: Path):
        self.store, self.calendar, self.path = store, calendar, path
        self.states: dict[str, dict] = {}

    def _check(self, symbol: str, timeframe: str, expected: list[int], now: int) -> dict:
        if not expected:
            return {'timeframe': timeframe, 'error': 'empty_validation_range'}
        bars = self.store.bars(symbol, timeframe, expected[0], expected[-1])
        present, invalid = set(), []
        for bar in bars:
            try:
                bar.validate(self.calendar, now)
                present.add(bar.ts)
            except ValueError as exc:
                invalid.append({'ts': bar.ts, 'error': str(exc)})
        missing = sorted(set(expected) - present)
        unexpected = sorted(present - set(expected))
        batch = self.store.batch(symbol, timeframe)
        if batch:
            expected_set = set(expected)
            invalid.extend(item for item in batch['rejected'] if item['ts'] in expected_set)
        return {'timeframe': timeframe, 'expected_count': len(expected), 'available_count': len(present),
                'missing_count': len(missing), 'missing': missing[:100],
                'unexpected': unexpected[:100], 'invalid': invalid[:100],
                'ok': not missing and not unexpected and not invalid}

    def validate(self, symbol: str, now: int, run_id: str | None = None) -> dict:
        days = self.calendar.completed_days(now, 300)
        through = days[-1].isoformat()
        daily = self.store.bars(symbol, '1d', end=self.calendar.grid(days[-1], '1d')[0][0])
        metadata = self.store.metadata(symbol)
        first = datetime.fromtimestamp(daily[0].ts, ET).date() if daily else None
        boundary_confirmed = bool(first and metadata.get('history_exhausted') and
                                  metadata.get('first_daily_ts') == daily[0].ts)
        limited = bool(first and first > days[0])
        used_days = [d for d in days if not limited or d >= first]
        daily_expected = [self.calendar.grid(d, '1d')[0][0] for d in used_days]
        five_days = [d for d in days[-12:] if not limited or d >= first]
        five_expected = [ts for d in five_days for ts, _ in self.calendar.grid(d, '5m')]
        checks = [self._check(symbol, '1d', daily_expected, now),
                  self._check(symbol, '5m', five_expected, now)]
        complete = all(c.get('ok') for c in checks)
        # A short response alone is not evidence of a newly listed security.
        degraded = complete and limited and boundary_confirmed
        ready = complete and not limited and len(used_days) == 300 and len(five_days) == 12
        full_checks = []
        batch_through = []
        batches = {tf: self.store.batch(symbol, tf) for tf in PHASES}
        if run_id is None:
            available_batches = [batch for batch in batches.values() if batch]
            if available_batches:
                run_id = max(available_batches, key=lambda b: b['as_of'])['run_id']
        for tf in PHASES:
            batch = batches[tf]
            if not batch or (run_id is not None and batch['run_id'] != run_id):
                full_checks.append({'timeframe': tf, 'ok': False, 'error': 'not_downloaded_this_run'})
                continue
            starts = batch['returned_closed_ts']
            if not starts or batch['rejected']:
                full_checks.append({'timeframe': tf, 'ok': False, 'error': 'empty_or_rejected_batch',
                                    'rejected': batch['rejected'][:10]})
                continue
            # The 1000-bar window may begin midway through a session.
            end = self.calendar.latest_closed(tf, batch['as_of'])
            expected = self.calendar.expected(tf, min(starts), end, batch['as_of'])
            check = self._check(symbol, tf, expected, now)
            check['returned_closed_count'] = len(starts)
            if not set(starts).issubset(expected):
                check.update(ok=False, error='invalid_returned_timestamp')
            full_checks.append(check)
            batch_through.append(self.calendar.completed_days(batch['as_of'], 1)[-1].isoformat())
        full_ready = all(c.get('ok') for c in full_checks)
        reasons = []
        if limited:
            reasons.append('available_history_only' if boundary_confirmed else 'history_boundary_unconfirmed')
        if not complete:
            reasons.append('missing_or_invalid_bars')
        state = {'ready': ready, 'ready_through': through if ready else None,
                 'degraded_ready': degraded, 'alert_eligible': ready or degraded,
                 'history_mode': 'available' if degraded else ('full' if ready else 'unavailable'),
                 'available_daily_days': checks[0].get('available_count', 0),
                 'required_daily_days': len(used_days), 'required_5m_days': len(five_days),
                 'available_5m_days': sum(
                     len(self.store.bars(symbol, '5m', self.calendar.grid(d, '5m')[0][0],
                                         self.calendar.grid(d, '5m')[-1][0])) == len(self.calendar.grid(d, '5m'))
                     for d in five_days),
                 'available_history_through': through if ready or degraded else None,
                 'history_start': first.isoformat() if first else None,
                 'full_ready': full_ready,
                 'full_ready_through': min(batch_through) if full_ready else None,
                 'validated_at': datetime.fromtimestamp(now, UTC).isoformat(),
                 'reasons': reasons, 'ready_checks': checks, 'full_checks': full_checks}
        old = self.states.get(symbol, {})
        self.states[symbol] = state
        if any(state[k] and not old.get(k) for k in ('ready', 'degraded_ready', 'full_ready')):
            log.info('Readiness %s ready=%s degraded=%s full=%s', symbol, ready, degraded, full_ready)
        return state

    def save(self) -> None:
        try:
            atomic_json(self.path, self.states)
        except OSError as exc:
            log.warning('Derived readiness JSON write failed; API state remains available: %s', exc)

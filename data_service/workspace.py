"""Three shared lists, synchronous JSON persistence and one file-event watcher."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import workspace_tickers

DAYS = Path(__file__).resolve().parents[1] / 'runtime' / 'days'
SECTIONS = ('focus',)
ORDERED_STATUSES = ('discover', 'focus', 'excluded')
WORKSPACE_VERSION = 3
HIDDEN_DAYS = 7
log = logging.getLogger(__name__)


def resolve_latest_workspace(root: Path = DAYS) -> Path:
    paths = [p / 'workspace.json' for p in root.iterdir()
             if p.is_dir() and re.fullmatch(r'\d{4}-\d{2}-\d{2}', p.name)
             and (p / 'workspace.json').is_file()]
    if not paths:
        raise ValueError(f'No dated workspace.json found in {root}')
    return max(paths)


def normalize_ticker(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Enter a US ticker')
    ticker = value.strip().upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,19}', ticker) or ticker.endswith(('.US', '.HK', '.SH', '.SZ', '.SG')):
        raise ValueError('Enter a US ticker without a market suffix')
    return ticker


def empty_workspace() -> dict[str, Any]:
    return {'version': WORKSPACE_VERSION, 'carried': [], 'statuses': {}, 'pinned': [],
            'orders': {status: [] for status in ORDERED_STATUSES}}


def _status_age(selected_date: str, status_at: str) -> int:
    return (date.fromisoformat(selected_date) - date.fromisoformat(status_at)).days


def is_hidden(state: dict, selected_date: str) -> bool:
    hidden = state.get('status') == 'hidden' or (state.get('status') == 'excluded' and state.get('section') == 'hidden')
    return hidden and _status_age(selected_date, state.get('excluded_at', state.get('status_at', selected_date))) < HIDDEN_DAYS


def _workspace_orders(workspace: dict) -> dict[str, list[str]]:
    statuses, stored = workspace.get('statuses', {}), workspace.get('orders', {})
    result = {}
    for status in ORDERED_STATUSES:
        members = {ticker for ticker, state in statuses.items() if state.get('status') == status}
        order = list(dict.fromkeys(ticker for ticker in stored.get(status, []) if ticker in members))
        order.extend(sorted(members - set(order)))
        result[status] = order
    return result


def migrate_workspace(data: dict, selected_date: str | None = None) -> dict:
    """Normalize legacy Focus/Wait/Hidden in memory; reads never write the file."""
    result = deepcopy(data)
    result['version'] = WORKSPACE_VERSION
    result.setdefault('carried', [])
    states = result.setdefault('statuses', {})
    old_orders = result.get('orders', {})
    result['orders'] = {'discover': list(old_orders.get('discover', result.get('discover_order', []))),
                        'focus': list(old_orders.get('focus', [])) + list(old_orders.get('wait', [])),
                        'excluded': list(old_orders.get('excluded', [])) + list(old_orders.get('hidden', []))}
    for state in states.values():
        status = state.get('status')
        if status == 'wait':
            state['status'] = 'focus'
        elif status == 'hidden':
            state.update(status='excluded', section='hidden')
        state.setdefault('section', 'unclassified' if state.get('status') != 'excluded' else 'hidden')
        state.setdefault('tags', [])
        if state.get('status') == 'excluded' and state['section'] == 'hidden':
            state.setdefault('excluded_at', state.get('status_at', selected_date or date.today().isoformat()))
        else:
            state.pop('excluded_at', None)
    result['orders'] = _workspace_orders(result)
    result['pinned'] = list(dict.fromkeys(ticker for ticker in result.get('pinned', []) if ticker in states))
    return result


def inherit_workspace(previous: dict | None, previous_candidates: set[str],
                      current_candidates: set[str], selected_date: str) -> dict:
    """Focus and exclusion survive candidate gaps; daily conclusions are recomputed."""
    if previous is None:
        return empty_workspace()
    result = migrate_workspace(previous, selected_date)
    result['pinned'] = []
    states = result['statuses']
    for ticker, state in list(states.items()):
        if state.get('status') == 'discover':
            del states[ticker]
            continue
        state['tags'] = []
        for key in ('manual_focus_date', 'manual_section_date', 'manual_tags_date', 'manual_tags'):
            state.pop(key, None)
    result['carried'] = sorted(ticker for ticker, state in states.items() if state.get('status') == 'focus')
    result['orders'] = _workspace_orders(result)
    return result


@dataclass(frozen=True)
class DayView:
    date: str
    candidates: frozenset[str]
    carried: frozenset[str]
    discover: tuple[str, ...]
    focus: tuple[str, ...]
    excluded: tuple[str, ...]
    new: frozenset[str]
    returned: frozenset[str]
    statuses: dict[str, dict[str, Any]]

    @property
    def tickers(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.discover) | set(self.focus) | set(self.excluded)))

    def as_dict(self) -> dict:
        return {'date': self.date, 'candidates': sorted(self.candidates), 'carried': sorted(self.carried),
                'lists': {'discover': list(self.discover), 'focus': list(self.focus), 'excluded': list(self.excluded)},
                'new': sorted(self.new), 'returned': sorted(self.returned), 'statuses': deepcopy(self.statuses)}


def derive_day_view(selected_date: str, candidates: set[str], previous_candidates: set[str], workspace: dict) -> DayView:
    data = migrate_workspace(workspace, selected_date)
    statuses = data['statuses']
    returned = set()
    for ticker, state in statuses.items():
        if state.get('manual_tags_date') != selected_date:
            state['manual_tags'] = []
        if state.get('released_at') == selected_date:
            returned.add(ticker)
    focus = {ticker for ticker, state in statuses.items() if state.get('status') == 'focus'}
    excluded = {ticker for ticker, state in statuses.items() if state.get('status') == 'excluded'}
    discover = candidates - focus - excluded
    for ticker in discover:
        statuses.setdefault(ticker, {'status': 'discover', 'section': 'unclassified', 'tags': []})
    for ticker, state in list(statuses.items()):
        if state.get('status') == 'discover' and ticker not in discover:
            del statuses[ticker]
    data['orders'] = _workspace_orders(data)
    return DayView(selected_date, frozenset(candidates), frozenset(data['carried']),
                   tuple(data['orders']['discover']), tuple(data['orders']['focus']), tuple(data['orders']['excluded']),
                   frozenset(candidates - previous_candidates), frozenset(returned), statuses)


class Workspace:
    def __init__(self, path: Path | None = None, *, root: Path = DAYS):
        self.root = root.resolve()
        self.follow_latest = path is None
        self.path = (path or resolve_latest_workspace(self.root)).resolve()
        self.data = migrate_workspace(json.loads(self.path.read_text()), self.date)
        self.on_change = lambda: None
        self.observer = None
        self.error = None

    @property
    def date(self):
        return self.path.parent.name if re.fullmatch(r'\d{4}-\d{2}-\d{2}', self.path.parent.name) else date.today().isoformat()

    def tickers(self):
        return workspace_tickers(self.data)

    def section(self, ticker):
        return self.data.get('statuses', {}).get(ticker, {}).get('status')

    def save(self, previous):
        # Existing direct synchronous persistence and rollback; no new queue or watcher.
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + '\n')
        except OSError:
            self.data = previous
            self.error = 'Could not save workspace'
            raise
        self.error = None
        self.on_change()

    def reclassify(self, snapshot, preferences):
        from .list_rules import apply_rules
        result = apply_rules(self.data, snapshot, preferences, self.date)
        if result == self.data:
            return False
        previous, self.data = self.data, result
        self.save(previous)
        return True

    def _remove_order(self, ticker):
        for order in self.data['orders'].values():
            order[:] = [item for item in order if item != ticker]

    def _focus(self, ticker, classification=None):
        self._unpin(ticker)
        state = self.data['statuses'].setdefault(ticker, {})
        for key in ('tags', 'manual_tags', 'manual_tags_date', 'manual_section_date', 'excluded_at', 'released_at'):
            state.pop(key, None)
        state.update(status='focus', section='unclassified', tags=[], status_at=self.date, manual_focus_date=self.date)
        state.update(classification or {})

    def add_ticker(self, ticker, section='focus', *, classification=None):
        if section not in ('focus', 'wait'):
            raise ValueError('Invalid list')
        if self.section(ticker) == 'focus':
            return self.keep_ticker(ticker)
        previous = deepcopy(self.data)
        self._remove_order(ticker)
        self.data['orders']['focus'].insert(0, ticker)
        self._focus(ticker, classification)
        self.save(previous)
        return True

    def keep_ticker(self, ticker):
        if self.section(ticker) != 'focus':
            raise ValueError('Ticker is not in Focus')
        if self.data['statuses'][ticker].get('manual_focus_date') == self.date:
            return False
        previous = deepcopy(self.data)
        self.data['statuses'][ticker]['manual_focus_date'] = self.date
        self.save(previous)
        return True

    def hide_ticker(self, ticker):
        if ticker not in self.data['statuses']:
            raise ValueError('Ticker is not in the workspace')
        previous = deepcopy(self.data)
        self._unpin(ticker)
        self._remove_order(ticker)
        state = self.data['statuses'][ticker]
        state.update(status='excluded', section='hidden', tags=[], status_at=self.date, excluded_at=self.date)
        for key in ('manual_focus_date', 'manual_section_date', 'manual_tags', 'manual_tags_date'):
            state.pop(key, None)
        self.data['orders']['excluded'].insert(0, ticker)
        self.save(previous)

    def move_ticker(self, ticker, section, index, list_name='focus'):
        if section in ('focus', 'wait'):
            list_name, section = 'focus', self.data['statuses'].get(ticker, {}).get('section', 'unclassified')
        if list_name not in ORDERED_STATUSES or not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ValueError('Invalid list position')
        if self.section(ticker) != list_name:
            raise ValueError('Ticker is not in this list')
        if list_name == 'excluded':
            raise ValueError('Excluded sections are assigned by rules')
        previous = deepcopy(self.data)
        self._remove_order(ticker)
        state = self.data['statuses'][ticker]
        state.update(section=section, manual_section_date=self.date)
        order = self.data['orders'][list_name]
        positions = [i for i, item in enumerate(order) if self.data['statuses'][item].get('section') == section]
        at = positions[index] if index < len(positions) else (positions[-1] + 1 if positions else 0)
        order.insert(at, ticker)
        self.save(previous)

    def move_members(self, tickers, source, target, candidates, previous_candidates, *, classifications=None):
        if source == target or source not in ORDERED_STATUSES or target not in ('discover', 'focus', 'hidden'):
            raise ValueError('Choose a different destination list')
        if not tickers or len(set(tickers)) != len(tickers):
            raise ValueError('Select unique tickers')
        view = derive_day_view(self.date, candidates, previous_candidates, self.data)
        if not set(tickers) <= set(view.as_dict()['lists'].get(source, [])):
            raise ValueError('Selection has changed; select again')
        if source == 'excluded' and target == 'discover' and any(
                self.data['statuses'][ticker].get('section') != 'hidden' for ticker in tickers):
            raise ValueError('Machine exclusions are released by scan rules')
        previous = deepcopy(self.data)
        for ticker in tickers:
            self._unpin(ticker)
            self._remove_order(ticker)
            if target == 'discover':
                self.data['statuses'].pop(ticker, None)
                if ticker in candidates:
                    self.data['statuses'][ticker] = {'status': 'discover', 'section': 'unclassified', 'tags': [], 'released_at': self.date}
            elif target == 'focus':
                self._focus(ticker, (classifications or {}).get(ticker))
            else:
                self.data['statuses'].setdefault(ticker, {}).update(status='excluded', section='hidden', tags=[], status_at=self.date, excluded_at=self.date)
                for key in ('manual_focus_date', 'manual_section_date', 'manual_tags', 'manual_tags_date'):
                    self.data['statuses'][ticker].pop(key, None)
        destination = 'excluded' if target == 'hidden' else target
        self.data['orders'][destination] = [ticker for ticker in tickers if ticker in self.data['statuses']] + self.data['orders'][destination]
        self.save(previous)

    def _unpin(self, ticker):
        self.data['pinned'] = [item for item in self.data['pinned'] if item != ticker]

    def pin_ticker(self, ticker, pinned):
        if ticker not in self.data['statuses'] or not isinstance(pinned, bool):
            raise ValueError('Choose a workspace ticker and pin state')
        if (ticker in self.data['pinned']) == pinned:
            return
        previous = deepcopy(self.data)
        self._unpin(ticker)
        if pinned:
            self.data['pinned'].insert(0, ticker)
        self.save(previous)

    def move_pin(self, ticker, index):
        if ticker not in self.data['pinned'] or not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ValueError('Choose a pinned ticker and position')
        previous = deepcopy(self.data)
        list_name = self.section(ticker)
        self._unpin(ticker)
        order = self.data['pinned']
        positions = [i for i, item in enumerate(order) if self.section(item) == list_name]
        at = positions[index] if index < len(positions) else (positions[-1] + 1 if positions else 0)
        order.insert(at, ticker)
        self.save(previous)

    def set_manual_tags(self, ticker, tag_ids):
        if ticker not in self.data['statuses'] or self.data['statuses'][ticker].get('section') == 'hidden':
            raise ValueError('Ticker is not available for tagging')
        if not isinstance(tag_ids, list) or any(not isinstance(tag, str) for tag in tag_ids) or len(set(tag_ids)) != len(tag_ids):
            raise ValueError('Use unique Tag IDs')
        previous = deepcopy(self.data)
        self.data['statuses'][ticker].update(manual_tags=tag_ids, manual_tags_date=self.date)
        self.save(previous)

    def reload(self):
        path = resolve_latest_workspace(self.root) if self.follow_latest else self.path
        path = max(path, self.path) if self.follow_latest else path
        selected_date = path.parent.name if re.fullmatch(r'\d{4}-\d{2}-\d{2}', path.parent.name) else date.today().isoformat()
        data = migrate_workspace(json.loads(path.read_text()), selected_date)
        if path != self.path or data != self.data or self.error:
            self.path, self.data, self.error = path, data, None
            self.on_change()

    def start_watcher(self):
        loop = asyncio.get_running_loop()
        workspace = self

        def reload():
            if workspace.observer is None:
                return
            try:
                workspace.reload()
            except (OSError, ValueError, KeyError, TypeError):
                workspace.error = 'Could not reload workspace'
                log.warning('Could not reload workspace: %s', workspace.path)

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                if event.event_type not in {'modified', 'created', 'moved', 'deleted', 'closed'}:
                    return
                paths = [Path(p) for p in (event.src_path, getattr(event, 'dest_path', '')) if p]
                if event.is_directory or any(p == workspace.path or p.name == 'workspace.json' for p in paths):
                    loop.call_soon_threadsafe(reload)

        self.observer = Observer()
        self.observer.schedule(Handler(), str(self.root if self.follow_latest else self.path.parent), recursive=True)
        self.observer.start()
        reload()  # Close the startup read/watch gap, without polling.

    def stop_watcher(self):
        observer, self.observer = self.observer, None
        if observer:
            observer.stop()
            observer.join()

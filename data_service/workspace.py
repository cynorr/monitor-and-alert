"""The shared Scan JSON and one filesystem-event watcher; writes are synchronous."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from datetime import date
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import workspace_tickers

DAYS = Path(__file__).resolve().parents[1] / 'runtime' / 'days'
SECTIONS = ('focus', 'wait')
ORDERED_STATUSES = ('focus', 'wait', 'hidden')
WORKSPACE_VERSION = 2
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
    return {
        "version": WORKSPACE_VERSION,
        "carried": [],
        "statuses": {},
        "orders": {status: [] for status in ORDERED_STATUSES},
    }

def _parse_date(value: str) -> date:
    return date.fromisoformat(value)

def _status_age(selected_date: str, status_at: str) -> int:
    return (
        _parse_date(selected_date)
        - _parse_date(status_at)
    ).days

def _workspace_orders(workspace: dict[str, Any]) -> dict[str, list[str]]:
    """Return complete, de-duplicated orders for all saved statuses."""

    statuses = workspace.get("statuses", {})
    stored = workspace.get("orders", {})
    result: dict[str, list[str]] = {}

    for status in ORDERED_STATUSES:
        members = {
            ticker
            for ticker, state in statuses.items()
            if state.get("status") == status
        }
        order: list[str] = []
        stored_order = (
            stored.get(status, [])
            if isinstance(stored, dict)
            else []
        )
        for ticker in stored_order:
            if ticker in members and ticker not in order:
                order.append(ticker)

        missing = members - set(order)
        order.extend(sorted(
            missing,
            key=lambda ticker: (
                statuses[ticker].get("status_at", ""),
                ticker,
            ),
            reverse=status != "hidden",
        ))
        result[status] = order

    return result

def _remove_from_orders(
    orders: dict[str, list[str]],
    ticker: str,
) -> None:
    for status in ORDERED_STATUSES:
        orders[status] = [item for item in orders[status] if item != ticker]

def inherit_workspace(
    previous: dict[str, Any] | None,
    previous_candidates: set[str],
    current_candidates: set[str],
    selected_date: str,
) -> dict[str, Any]:
    """Create a day once; later Pulls reuse it without re-inheritance."""

    if previous is None:
        return empty_workspace()

    previous_statuses = previous.get("statuses", {})
    focus_wait = {
        ticker: deepcopy(state)
        for ticker, state in previous_statuses.items()
        if state.get("status") in {"focus", "wait"}
    }
    inherited_hidden = {
        ticker: deepcopy(state)
        for ticker, state in previous_statuses.items()
        if (
            state.get("status") == "hidden"
            and ticker in previous_candidates
            and ticker in current_candidates
            and _status_age(selected_date, state["status_at"]) <= HIDDEN_DAYS
        )
    }

    inherited = {
        "version": WORKSPACE_VERSION,
        "carried": sorted(focus_wait),
        "statuses": {
            **focus_wait,
            **inherited_hidden,
        },
        "orders": deepcopy(previous.get("orders", {})),
    }
    inherited["orders"] = _workspace_orders(inherited)
    return inherited

@dataclass(frozen=True)
class DayView:
    date: str
    candidates: frozenset[str]
    carried: frozenset[str]
    discover: tuple[str, ...]
    focus: tuple[str, ...]
    wait: tuple[str, ...]
    hidden: tuple[str, ...]
    new: frozenset[str]
    returned: frozenset[str]
    statuses: dict[str, dict[str, str]]

    @property
    def tickers(self) -> tuple[str, ...]:
        return tuple(sorted(set().union(
            self.discover,
            self.focus,
            self.wait,
            self.hidden,
        )))

    def as_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "candidates": sorted(self.candidates),
            "carried": sorted(self.carried),
            "lists": {
                "discover": list(self.discover),
                "focus": list(self.focus),
                "wait": list(self.wait),
                "hidden": list(self.hidden),
            },
            "new": sorted(self.new),
            "returned": sorted(self.returned),
            "statuses": deepcopy(self.statuses),
        }

def derive_day_view(
    selected_date: str,
    candidates: set[str],
    previous_candidates: set[str],
    workspace: dict[str, Any],
) -> DayView:
    carried = set(workspace.get("carried", []))
    statuses = workspace.get("statuses", {})

    focus = {
        ticker
        for ticker, state in statuses.items()
        if state.get("status") == "focus"
    }
    wait = {
        ticker
        for ticker, state in statuses.items()
        if state.get("status") == "wait"
    }
    hidden_statuses = {
        ticker: _status_age(selected_date, state["status_at"])
        for ticker, state in statuses.items()
        if state.get("status") == "hidden"
    }

    hidden = {
        ticker
        for ticker, age in hidden_statuses.items()
        if age < HIDDEN_DAYS
    }
    returned = {
        ticker
        for ticker, age in hidden_statuses.items()
        if ticker in candidates and age == HIDDEN_DAYS
    }

    discover = (candidates | carried) - focus - wait
    discover -= hidden
    discover -= {
        ticker
        for ticker in hidden_statuses
        if ticker not in candidates
    }
    orders = _workspace_orders(workspace)

    return DayView(
        date=selected_date,
        candidates=frozenset(candidates),
        carried=frozenset(carried),
        discover=tuple(sorted(discover)),
        focus=tuple(ticker for ticker in orders["focus"] if ticker in focus),
        wait=tuple(ticker for ticker in orders["wait"] if ticker in wait),
        hidden=tuple(ticker for ticker in orders["hidden"] if ticker in hidden),
        new=frozenset(candidates - previous_candidates),
        returned=frozenset(returned),
        statuses=deepcopy(statuses),
    )


class Workspace:
    def __init__(self, path: Path | None = None, *, root: Path = DAYS):
        self.root = root.resolve()
        self.follow_latest = path is None
        self.path = (path or resolve_latest_workspace(self.root)).resolve()
        self.data = json.loads(self.path.read_text())
        self.on_change = lambda: None
        self.observer = None
        self.error = None

    @property
    def date(self):
        return self.path.parent.name if re.fullmatch(r'\d{4}-\d{2}-\d{2}', self.path.parent.name) else date.today().isoformat()

    def tickers(self):
        return workspace_tickers(self.data)

    def section(self, ticker):
        return next((t.status for t in self.tickers() if t.ticker == ticker), None)

    def save(self, previous):
        # Deliberately no lock, temporary file, replace, queue, or delayed persistence.
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + '\n')
        except OSError:
            self.data = previous
            self.error = 'Could not save workspace'
            raise
        self.error = None
        self.on_change()

    def add_ticker(self, ticker, section):
        if section not in SECTIONS:
            raise ValueError('Invalid section')
        if self.section(ticker):
            return False
        previous = deepcopy(self.data)
        for group in ORDERED_STATUSES:
            self.data.get('orders', {}).setdefault(group, [])[:] = [item for item in self.data.get('orders', {}).get(group, []) if item != ticker]
        self.data.setdefault('orders', {}).setdefault(section, []).insert(0, ticker)
        self.data['statuses'].setdefault(ticker, {}).update(status=section, status_at=self.date)
        self.save(previous)
        return True

    def delete_ticker(self, ticker):
        if not self.section(ticker):
            raise ValueError('Ticker is not in Focus or Wait')
        previous = deepcopy(self.data)
        for section in ORDERED_STATUSES:
            items = self.data.get('orders', {}).get(section, [])
            items[:] = [item for item in items if item != ticker]
        del self.data['statuses'][ticker]
        self.save(previous)

    def move_ticker(self, ticker, section, index):
        if section not in SECTIONS or not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ValueError('Invalid list position')
        source = self.section(ticker)
        if source is None:
            raise ValueError('Ticker is not in Focus or Wait')
        previous = deepcopy(self.data)
        orders = self.data.setdefault('orders', {})
        for group in SECTIONS:
            items = orders.setdefault(group, [])
            items[:] = [item for item in items if item != ticker]
        orders[section].insert(min(index, len(orders[section])), ticker)
        self.data['statuses'][ticker].update(status=section, status_at=self.date)
        self.save(previous)

    def move_members(self, tickers, source, target, candidates, previous_candidates):
        if source == target or target not in ('discover', *ORDERED_STATUSES):
            raise ValueError('Choose a different destination list')
        if not tickers or len(set(tickers)) != len(tickers):
            raise ValueError('Select unique tickers')
        view = derive_day_view(self.date, candidates, previous_candidates, self.data)
        if not set(tickers) <= set(view.as_dict()['lists'].get(source, [])):
            raise ValueError('Selection has changed; select again')
        previous = deepcopy(self.data)
        orders = _workspace_orders(self.data)
        moving = set(tickers)
        for group in orders:
            orders[group] = [ticker for ticker in orders[group] if ticker not in moving]
        priority = [ticker for ticker in self.data.get('discover_order', []) if ticker not in moving]
        if target == 'discover':
            self.data['discover_order'] = tickers + priority
            self.data['carried'] = sorted(set(self.data.get('carried', [])) | moving)
            for ticker in tickers:
                self.data['statuses'].pop(ticker, None)
        else:
            self.data['discover_order'] = priority
            orders[target] = tickers + orders[target]
            for ticker in tickers:
                self.data['statuses'].setdefault(ticker, {}).update(status=target, status_at=self.date)
        self.data['orders'] = orders
        self.save(previous)

    def reload(self):
        path = resolve_latest_workspace(self.root) if self.follow_latest else self.path
        # A removed/older day never sends an active session backwards.
        path = max(path, self.path) if self.follow_latest else path
        data = json.loads(path.read_text())
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

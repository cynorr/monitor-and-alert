"""The shared Scan JSON and one filesystem-event watcher; writes are synchronous."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from copy import deepcopy
from datetime import date
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import workspace_tickers

DAYS = Path.home() / 'qull-scan-workspace' / 'days'
SECTIONS = ('focus', 'wait')
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


class Workspace:
    def __init__(self, path: Path | None = None, *, root: Path = DAYS):
        self.root = root.resolve()
        self.follow_latest = path is None
        self.path = (path or resolve_latest_workspace(self.root)).resolve()
        self.data = json.loads(self.path.read_text())
        self.on_change = lambda: None
        self.observer = None
        self.error = None

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
        self.data.setdefault('orders', {}).setdefault(section, []).insert(0, ticker)
        self.data['statuses'].setdefault(ticker, {}).update(status=section, status_at=date.today().isoformat())
        self.save(previous)
        return True

    def delete_ticker(self, ticker):
        if not self.section(ticker):
            raise ValueError('Ticker is not in Focus or Wait')
        previous = deepcopy(self.data)
        for section in SECTIONS:
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
        self.data['statuses'][ticker].update(status=section, status_at=date.today().isoformat())
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

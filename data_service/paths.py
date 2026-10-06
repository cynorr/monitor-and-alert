"""Persistent paths below one runtime root."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path

    @property
    def daily_dir(self) -> Path:
        return self.root / 'massive' / 'daily'

    @property
    def splits_file(self) -> Path:
        return self.root / 'massive' / 'splits.json'

    @property
    def daily_db(self) -> Path:
        return self.root / 'massive' / 'daily.sqlite3'

    @property
    def bars_db(self) -> Path:
        return self.root / 'longbridge' / 'bars.sqlite3'

    @property
    def pipeline_status(self) -> Path:
        return self.root / 'pipeline-status.json'

    @property
    def symbol_directory(self) -> Path:
        return self.root / 'symbol-directory.json'

    @property
    def days(self) -> Path:
        return self.root / 'days'

    @property
    def holdings_dir(self) -> Path:
        return self.root / 'holdings'

    @property
    def alerts_db(self) -> Path:
        return self.root / 'alerts' / 'alerts.sqlite3'

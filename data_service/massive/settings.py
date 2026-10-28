"""Massive candidate configuration, local paths and API credentials."""
from dataclasses import dataclass
import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'massive.json'


@dataclass(frozen=True)
class ScanConfig:
    exclude_etfs: bool
    min_daily_bars: int
    adr20_min_pct: float
    adv20_min_usd: float
    rfl_top_n: int


def load_config(path=None):
    return ScanConfig(**json.loads(Path(path or CONFIG_PATH).read_text()))


def directory_for_database(path):
    parent = Path(path).parent
    return (parent.parent if parent.name == 'massive' else parent) / 'symbol-directory.json'


def read_massive_token(path: Path = Path('massive-token.txt')) -> str:
    token = os.environ.get('MASSIVE_API_KEY', '').strip()
    if not token:
        try:
            token = path.read_text().strip()
        except FileNotFoundError:
            pass
    if not token:
        raise ValueError('Massive credentials missing: set MASSIVE_API_KEY or create massive-token.txt')
    return token

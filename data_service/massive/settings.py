"""Massive candidate configuration, local paths and API credentials."""
from dataclasses import dataclass
import json
import os
from pathlib import Path

from ..config import DEFAULT_CREDENTIALS, credential_values

CONFIG_PATH = Path(__file__).resolve().parents[2] / 'config' / 'scan.json'


@dataclass(frozen=True)
class ScanConfig:
    exclude_etfs: bool
    minimum_daily_bars: int
    minimum_mdv20_usd: float
    minimum_adr20_percent: float
    close_price_above_usd: float
    momentum_top_n: int


def load_config(path=None):
    return ScanConfig(**json.loads(Path(path or CONFIG_PATH).read_text()))


def directory_for_database(path):
    parent = Path(path).parent
    return (parent.parent if parent.name == 'massive' else parent) / 'symbol-directory.json'


def read_massive_token(path: Path = DEFAULT_CREDENTIALS) -> str:
    token = os.environ.get('MASSIVE_API_KEY', '').strip()
    return token or credential_values(path, 'massive', 'api_key')[0]

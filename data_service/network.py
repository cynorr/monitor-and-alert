"""Shared HTTP sessions, explicit proxy configuration, and Massive credentials."""
import os
from pathlib import Path

import aiohttp


def proxy_url() -> str | None:
    return os.environ.get('MARKET_PROXY', 'http://127.0.0.1:7899').strip() or None


def create_session(timeout: float) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), trust_env=False)


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

"""Shared HTTP session creation and explicit proxy configuration."""
import os

import aiohttp


def proxy_url() -> str | None:
    return os.environ.get('MARKET_PROXY', 'http://127.0.0.1:7899').strip() or None


def create_session(timeout: float) -> aiohttp.ClientSession:
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), trust_env=False)

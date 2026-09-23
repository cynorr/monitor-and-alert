from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Ticker:
    symbol: str
    ticker: str
    status: str


def load_tickers(path: Path, only: list[str] | None = None, *, allow_empty=False) -> list[Ticker]:
    return workspace_tickers(json.loads(path.read_text()), only, allow_empty=allow_empty)


def workspace_tickers(data: dict, only: list[str] | None = None, *, allow_empty=True) -> list[Ticker]:
    statuses = data['statuses']
    if not isinstance(statuses, dict):
        raise ValueError('workspace.statuses must be an object')
    eligible = {}
    for ticker, entry in statuses.items():
        if not isinstance(entry, dict):
            raise ValueError(f'Invalid status record: {ticker}')
        if entry.get('status') not in {'focus', 'wait'}:
            continue
        if not re.fullmatch(r'[A-Z][A-Z0-9.-]{0,19}', ticker):
            raise ValueError(f'Unsupported US ticker: {ticker}')
        symbol = ticker if ticker.endswith('.US') else ticker + '.US'
        eligible[ticker] = Ticker(symbol, ticker, entry['status'])
    order = [t for group in ('focus', 'wait') for t in data.get('orders', {}).get(group, [])]
    order += list(eligible)
    result, seen = [], set()
    for ticker in order:
        item = eligible.get(ticker)
        if item and item.symbol not in seen:
            result.append(item)
            seen.add(item.symbol)
    if only:
        wanted = {s if s.endswith('.US') else s + '.US' for s in only}
        if wanted - seen:
            raise ValueError('Requested symbols outside focus/wait: ' + ', '.join(sorted(wanted - seen)))
        result = [item for item in result if item.symbol in wanted]
    if not result and not allow_empty:
        raise ValueError('No focus/wait tickers; refusing to connect')
    return result


def read_credentials(path: Path) -> tuple[str, str, str]:
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    if len(lines) != 6 or lines[::2] != ['App Key', 'App Secret', 'App Token']:
        raise ValueError('Expected App Key / App Secret / App Token labels, each followed by its value')
    return tuple(lines[1::2])


def redact(message: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        message = message.replace(secret, '[REDACTED]')
    return message

"""Routing and persistence using actual successful Longbridge batch metadata."""
import asyncio
import json
import sqlite3
import time
from pathlib import Path

import pytest

from data_service.longbridge.usage import SymbolUsage, month_of, read_usage

ROOT = Path(__file__).resolve().parents[1]


def test_real_monthly_symbols_share_one_account_mapping(tmp_path):
    path = ROOT / 'runtime/longbridge/bars.sqlite3'
    if not path.exists():
        pytest.skip('Requires the actual Longbridge cache')
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
        rows = db.execute("SELECT symbol,MAX(json_extract(payload,'$.as_of')) FROM batches "
                          "GROUP BY symbol ORDER BY symbol").fetchall()
    ledger = read_usage(ROOT / 'runtime/longbridge/usage.json')
    secondary = {symbol for symbol, row in ledger.items() if row['account'] != 'account_1'}
    rows = [(symbol, timestamp) for symbol, timestamp in rows
            if symbol not in secondary and month_of(timestamp) == month_of(time.time())]
    if len(rows) < 91:
        pytest.skip('Requires 91 actual same-month successful symbols')
    usage = SymbolUsage(tmp_path / 'usage.json', ['account_1', 'account_2'])
    usage.data = {symbol: {'account': 'account_1', 'last_access_at': timestamp}
                  for symbol, timestamp in rows[:89]}
    assert usage.access(rows[89][0]) == 'account_1'
    symbol = rows[90][0]
    assert {usage.access(symbol) for _ in range(6)} == {'account_2'}
    assert usage.counts() == {'account_1': 90, 'account_2': 1}

    async def save():
        await usage.flush()
        saved_at = usage.path.stat().st_mtime_ns
        await usage.flush()
        assert usage.path.stat().st_mtime_ns == saved_at
    asyncio.run(save())
    assert json.loads(usage.path.read_text()) == usage.data
    restored = SymbolUsage(usage.path, usage.accounts)
    assert restored.access(symbol) == 'account_2'
    assert restored.counts() == usage.counts()

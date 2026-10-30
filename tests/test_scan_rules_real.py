"""Core screening checks against the installed real daily database only."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path

import pytest

from data_service.calendar import TradingCalendar
from data_service.indicators import adr_mdv, daily_summary
from data_service.massive.settings import load_config
from data_service.preferences import CATALOG, validate_preferences
from data_service.scan import build_day, connect_daily, day_start, latest_completed_date, workspace_scope
from data_service.storage import read_bars

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'


@pytest.fixture(scope='module')
def real_scan():
    path = RUNTIME / 'massive/daily.sqlite3'
    if not path.exists():
        pytest.skip('Installed real Daily data is required')
    calendar = TradingCalendar()
    day = latest_completed_date(path)
    tracked = workspace_scope(RUNTIME / 'days', day)
    snapshot = build_day(path, day, calendar, tracked_tickers=tracked)
    return path, calendar, snapshot, tracked


def test_shared_mdv_and_adr_use_real_completed_turnover(real_scan):
    path, calendar, snapshot, _ = real_scan
    cutoff = day_start(calendar, snapshot['date'])
    symbols = [r['symbol'] for r in snapshot['rows'] if r['candidate']][:5]
    assert symbols
    with closing(connect_daily(path)) as db:
        for symbol in symbols:
            bars = read_bars(db, symbol, '1d', end=cutoff, limit=20)
            amounts = sorted(b.turnover for b in bars)
            assert len(amounts) == 20
            expected = (amounts[9] + amounts[10]) / 2
            metrics = adr_mdv({key: [getattr(b, key) for b in bars] for key in ('high', 'low', 'turnover')})
            summary = daily_summary(bars, calendar, calendar.bar_end(cutoff, '1d'))
            stored = next(r for r in snapshot['rows'] if r['symbol'] == symbol)
            assert metrics['mdv20'] == pytest.approx(expected)
            assert summary['mdv20'] == pytest.approx(expected)
            assert stored['mdv20'] == pytest.approx(expected)
            assert stored['adr20'] == pytest.approx(sum((b.high-b.low)/b.low*100 for b in bars)/20)


def test_ranks_use_all_real_eligible_stocks_before_tag_classification(real_scan):
    _, _, snapshot, _ = real_scan
    config = load_config()
    rows = snapshot['rows']
    expected_eligible = {r['symbol'] for r in rows if r['etf_pass'] and r['history_pass'] and
                         r['close'] > 5 and r['mdv20'] is not None and r['mdv20'] >= 15_000_000 and r['adr20'] >= 4}
    assert expected_eligible
    assert {r['symbol'] for r in rows if r['eligible']} == expected_eligible
    selected = set()
    for name in ('rfl1m', 'rfl3m', 'rfl6m'):
        ordered = sorted((r for r in rows if r['symbol'] in expected_eligible), key=lambda r: (-r[name], r['symbol']))
        for rank, row in enumerate(ordered, 1):
            assert row[name+'_rank'] == rank
        selected.update(r['symbol'] for r in ordered[:75])
    assert {r['symbol'] for r in rows if r['candidate']} == selected
    for row in rows:
        if row['symbol'] not in expected_eligible:
            assert all(row[n+'_rank'] is None for n in ('rfl1m', 'rfl3m', 'rfl6m'))
    assert config.minimum_daily_bars == 50 and config.momentum_top_n == 75
    assert any(not r['etf_pass'] for r in rows)
    assert any(not r['history_pass'] for r in rows)
    assert any(r['close'] <= 5 for r in rows)


def test_features_only_cover_real_candidates_and_retained_members(real_scan):
    _, _, snapshot, tracked = real_scan
    universe = {r['symbol'] for r in snapshot['rows']}
    expected = ({r['symbol'] for r in snapshot['rows'] if r['candidate']} | {t+'.US' for t in tracked}) & universe
    assert set(snapshot['feature_scope']) == expected
    assert all('extended_k' in r for r in snapshot['rows'] if r['candidate'])


def test_saved_real_tags_keep_shape_filters():
    preferences = json.loads((RUNTIME / 'preferences.json').read_text())
    assert len(CATALOG) == 36 and all(field['group'] != 'Market' for field in CATALOG)
    saved = validate_preferences(deepcopy(preferences))
    assert preferences['tags']
    for original, tag in zip(preferences['tags'], saved['tags']):
        assert tag['filters'] == original['filters']
        assert tag['filters'].keys() <= {field['key'] for field in CATALOG}

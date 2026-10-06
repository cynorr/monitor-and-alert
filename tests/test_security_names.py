"""Optional local symbol names must not affect chart availability or subscriptions."""
import asyncio

import pytest

from data_service.store import atomic_json
from data_service.symbol_directory import make_snapshot, read_directory
from data_service.workbench import Workbench
from data_service.workspace import Workspace


@pytest.fixture
def workbench(tmp_path):
    day = tmp_path / 'days' / '2026-09-30'
    day.mkdir(parents=True)
    atomic_json(day / 'workspace.json', {
        'version': 3, 'statuses': {'XYZ': {'status': 'excluded', 'section': 'review'}},
        'orders': {'discover': [], 'focus': [], 'excluded': ['XYZ']},
    })
    def no_broker(*_):
        pytest.fail('Name reads must not construct a broker')
    app = Workbench(Workspace(root=tmp_path / 'days'), tmp_path, tmp_path / 'daily.sqlite3', no_broker, mock=True)
    app.chart_cache[(app.workspace.date, 'XYZ.US')] = ({'revision': 1, 'bars': [], 'indicators': {}}, {})
    return app


def write_names(app, name):
    atomic_json(app.symbol_directory_path, make_snapshot({
        'XYZ.US': {'name': name, 'etf': False, 'test_issue': False},
    }))


def test_names_reload_after_local_update_without_rebuilding_chart(workbench, monkeypatch):
    app = workbench
    calls = []
    def counted_read(path):
        calls.append(path)
        return read_directory(path)
    monkeypatch.setattr('data_service.workbench.read_directory', counted_read)
    write_names(app, 'XYZ Holdings Inc. - Common Stock')
    first = app.view('XYZ.US', '5m')
    second = app.view('XYZ.US', '5m', {'1d': 1})
    assert first['security_name'] == second['security_name'] == 'XYZ Holdings Inc. - Common Stock'
    assert len(calls) == 1 and 'bars' not in second['charts']['1d']
    write_names(app, 'XYZ New Name - Common Stock')
    updated = app.view('XYZ.US', '5m', {'1d': 1})
    assert updated['security_name'] == 'XYZ New Name - Common Stock'
    assert len(calls) == 2 and 'bars' not in updated['charts']['1d']
    assert app.security_name('MISSING.US') is None


def test_missing_corrupt_or_empty_names_keep_charts_available(workbench):
    app = workbench
    assert app.view('XYZ.US', '5m')['security_name'] is None
    write_names(app, 'XYZ Inc.')
    assert app.view('XYZ.US', '5m')['security_name'] == 'XYZ Inc.'
    app.symbol_directory_path.write_text('{invalid json')
    assert app.view('XYZ.US', '5m')['security_name'] is None
    app.symbol_directory_path.unlink()
    assert app.view('XYZ.US', '5m')['security_name'] is None
    write_names(app, None)
    assert app.view('XYZ.US', '5m')['security_name'] is None


def test_scan_review_monitor_and_holdings_views_share_local_name(workbench):
    app = workbench
    write_names(app, 'XYZ & Company <Common Stock>')
    expected = 'XYZ & Company <Common Stock>'
    assert app.view('XYZ.US', '5m')['security_name'] == expected

    class LocalMonitor:
        def view(self, symbol, tf, revisions=None):
            return {'symbol': symbol, 'timeframe': tf, 'charts': {'1d': {}, tf: {}}, 'mode': 'monitor'}

        async def api(self, path, query):
            assert path == '/v1/chart'
            return self.view(query['symbol'][0], query.get('timeframe', ['5m'])[0])

    app.mode, app.monitor = 'monitor', LocalMonitor()
    review = app.view('XYZ.US', '5m')
    holding = app.view('XYZ.US', '5m', source='holdings')
    assert review['security_name'] == holding['security_name'] == expected
    assert review['read_only_daily'] and not holding.get('read_only_daily')
    app.workspace.data['statuses']['XYZ'] = {'status': 'focus', 'section': 'unclassified'}
    live = app.view('XYZ.US', '5m')
    http = asyncio.run(app.api('/v1/chart', {'symbol': ['XYZ.US'], 'timeframe': ['5m']}))
    assert live['security_name'] == http['security_name'] == expected

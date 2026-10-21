"""List regression checks using the installed real Daily snapshots and workspace."""
from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from data_service.list_rules import apply_rules, focus_classification, matched_tags, NEGATIVE_ROLES
from data_service.preferences import tag_role, validate_preferences
from data_service.scan import candidates, publish_day, workspace_scope
from data_service.workspace import Workspace, inherit_workspace, is_hidden, persistent_workspace

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'


@pytest.fixture(scope='module')
def real_data():
    files = sorted((RUNTIME / 'days').glob('*/scan.json'))
    if not files:
        pytest.skip('Real Scan data is required')
    folder = files[-1].parent
    return (json.loads((folder / 'workspace.json').read_text()),
            json.loads((folder / 'scan.json').read_text()),
            validate_preferences(json.loads((RUNTIME / 'preferences.json').read_text())))


@pytest.fixture
def saved_real_workspace(tmp_path, real_data):
    data, snapshot, preferences = real_data
    folder = tmp_path / 'days' / snapshot['date']
    folder.mkdir(parents=True)
    (folder / 'workspace.json').write_text(json.dumps(data))
    (folder / 'scan.json').write_text(json.dumps(snapshot))
    (tmp_path / 'preferences.json').write_text(json.dumps(preferences))
    ws = Workspace(folder / 'workspace.json', root=folder.parent)
    ws.reclassify(snapshot, preferences)
    return ws


def test_machine_exclusions_belong_only_to_current_real_candidates(real_data):
    data, snapshot, preferences = real_data
    before = deepcopy(data)
    result = apply_rules(data, snapshot, preferences)
    current = candidates(snapshot)
    for ticker, state in result['statuses'].items():
        if state['status'] == 'excluded' and state['section'] != 'hidden':
            assert ticker in current
    assert data == before
    assert apply_rules(result, snapshot, preferences) == result
    saved = persistent_workspace(result)
    assert all(s['section'] == 'hidden' for s in saved['statuses'].values() if s.get('status') == 'excluded')


def test_new_date_inherits_only_focus_and_unexpired_hidden(real_data):
    data, snapshot, _ = real_data
    day = (date.fromisoformat(snapshot['date']) + timedelta(days=1)).isoformat()
    inherited = inherit_workspace(data, day)
    expected = {t for t, s in data['statuses'].items() if s['status'] == 'focus' or is_hidden(s, day)}
    assert set(inherited['statuses']) == expected
    assert inherited['pinned'] == []
    assert all(not any(k in s for k in ('manual_focus_date', 'manual_discover_date', 'manual_tags'))
               for s in inherited['statuses'].values())


def test_real_focus_daily_elimination_keeps_candidate_scope(real_data):
    _, _, preferences = real_data
    source = json.loads((RUNTIME / 'days/2026-10-09/workspace.json').read_text())
    snapshot = json.loads((RUNTIME / 'days/2026-10-12/scan.json').read_text())
    inherited = inherit_workspace(source, snapshot['date'])
    rows = {r['symbol'].removesuffix('.US'): r for r in snapshot['rows']}
    negative = {t for t, s in inherited['statuses'].items() if s['status'] == 'focus' and any(
        tag_role(tag) in NEGATIVE_ROLES for tag in matched_tags(rows.get(t, {}), preferences['tags']))}
    assert negative and 'AXTI' in negative and 'AXTI' not in candidates(snapshot)
    result = apply_rules(inherited, snapshot, preferences)
    for ticker in negative:
        if ticker in candidates(snapshot):
            assert result['statuses'][ticker]['status'] == 'excluded'
        else:
            assert ticker not in result['statuses']
    for ticker, state in inherited['statuses'].items():
        if state['status'] == 'focus' and ticker not in negative:
            assert result['statuses'][ticker]['status'] == 'focus'


def test_real_hidden_expires_after_seven_calendar_days(real_data):
    _, _, preferences = real_data
    source = json.loads((RUNTIME / 'days/2026-10-08/workspace.json').read_text())
    assert source['statuses']['AVAH']['excluded_at'] == '2026-10-08'
    assert 'AVAH' in inherit_workspace(source, '2026-10-14')['statuses']
    assert 'AVAH' not in inherit_workspace(source, '2026-10-15')['statuses']
    snapshot = json.loads((RUNTIME / 'days/2026-10-15/scan.json').read_text())
    assert 'AVAH' not in candidates(snapshot)
    result = apply_rules(source, snapshot, preferences)
    assert 'AVAH' not in result['statuses']


def test_saved_rules_recompute_machine_sections_without_old_identity(real_data):
    data, snapshot, preferences = real_data
    preferences = deepcopy(preferences)
    preferences['tags'] = [t for t in preferences['tags'] if tag_role(t) not in NEGATIVE_ROLES]
    result = apply_rules(data, snapshot, preferences)
    assert not any(s['status'] == 'excluded' and s['section'] != 'hidden' for s in result['statuses'].values())


def test_real_machine_pin_hidden_release_and_focus_round_trip(saved_real_workspace, real_data):
    ws = saved_real_workspace
    _, snapshot, preferences = real_data
    ticker = next(t for t, s in ws.data['statuses'].items() if s['status'] == 'excluded' and s['section'] != 'hidden')
    original_rows = deepcopy(snapshot['rows'])
    ws.pin_ticker(ticker, True)
    saved = json.loads(ws.path.read_text())
    assert ticker not in saved['statuses'] and ticker in saved['pinned']
    tag = next(t['id'] for t in preferences['tags'] if tag_role(t) in ('setup', 'label'))
    ws.set_manual_tags(ticker, [tag])
    ws.reclassify(snapshot, preferences)
    annotation = json.loads(ws.path.read_text())['statuses'][ticker]
    assert annotation == {'manual_tags': [tag], 'manual_tags_date': ws.date}
    before = deepcopy(ws.data)
    ws.reload()
    assert ws.data == before  # Own file writes must not discard the in-memory projection.
    restored = Workspace(ws.path, root=ws.root)
    restored.reclassify(snapshot, preferences)
    assert ticker in restored.data['pinned']
    assert restored.section(ticker) == 'excluded'
    assert tag in restored.data['statuses'][ticker]['tags']
    restored.hide_ticker(ticker)
    restored.reclassify(snapshot, preferences)
    assert json.loads(ws.path.read_text())['statuses'][ticker]['section'] == 'hidden'
    restored.move_members([ticker], 'excluded', 'discover', candidates(snapshot))
    restored.reclassify(snapshot, preferences)
    assert restored.section(ticker) == 'excluded'
    row = next(r for r in snapshot['rows'] if r['symbol'] == ticker + '.US')
    restored.add_ticker(ticker, classification=focus_classification(row, preferences))
    restored.reclassify(snapshot, preferences)
    assert restored.section(ticker) == 'focus'  # Explicit same-day admission wins.
    assert json.loads(ws.path.read_text())['statuses'][ticker]['manual_focus_date'] == ws.date
    assert snapshot['rows'] == original_rows


def test_real_publication_and_feature_scope(saved_real_workspace, real_data):
    ws = saved_real_workspace
    _, snapshot, preferences = real_data
    expected = {t for t, s in ws.data['statuses'].items() if s['status'] == 'focus' or is_hidden(s, ws.date) or
                (s['status'] == 'discover' and s.get('manual_discover_date') == ws.date)}
    assert workspace_scope(ws.root, ws.date) == expected
    publish_day(ws.root, snapshot)
    saved = json.loads(ws.path.read_text())
    assert saved == persistent_workspace(ws.data)
    assert all(s['section'] == 'hidden' for s in saved['statuses'].values() if s.get('status') == 'excluded')
    loaded = Workspace(ws.path, root=ws.root)
    loaded.reclassify(snapshot, preferences)
    assert {t: (s['status'], s['section'], s['tags']) for t, s in loaded.data['statuses'].items()} == {
        t: (s['status'], s['section'], s['tags']) for t, s in ws.data['statuses'].items()}
    assert persistent_workspace(loaded.data) == saved


def test_real_search_discover_is_same_day_only(saved_real_workspace, real_data):
    ws = saved_real_workspace
    _, snapshot, preferences = real_data
    ticker = next(r['symbol'].removesuffix('.US') for r in snapshot['rows'] if not r['candidate'] and
                  r['symbol'].removesuffix('.US') not in ws.data['statuses'])
    ws.add_ticker(ticker, 'discover')
    ws.reclassify(snapshot, preferences)
    restored = Workspace(ws.path, root=ws.root)
    restored.reclassify(snapshot, preferences)
    assert restored.section(ticker) == 'discover' and ticker in restored.data['pinned']
    assert ticker in workspace_scope(ws.root, ws.date)
    tomorrow = (date.fromisoformat(ws.date) + timedelta(days=1)).isoformat()
    assert ticker not in inherit_workspace(restored.data, tomorrow)['statuses']

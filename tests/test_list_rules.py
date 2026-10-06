import copy
import json

import pytest

from data_service.config import workspace_tickers
from data_service.list_rules import apply_rules, matches_filters
from data_service.preferences import validate_preferences
from data_service.workspace import Workspace, derive_day_view, empty_workspace, inherit_workspace, migrate_workspace


def preferences():
    return {'activeList': 'discover', 'sort': 'default', 'activeTag': 'default', 'tags': [
        {'id': 'default', 'name': 'Default', 'filters': {}},
        {'id': 'ext', 'name': 'Extended', 'filters': {'extended_k': {'min': 1.5}}},
        {'id': 'broken-tag', 'name': 'Broken', 'filters': {'broken_k': {'min': 1}, 'below_days': {'min': 2}}},
        {'id': 'surf', 'name': 'Surf-10', 'filters': {'ema10_touch_days_5d': {'min': 3}}},
        {'id': 'body-label', 'name': 'Large body', 'role': 'label', 'filters': {'adr20': {'min': 5}}},
        {'id': 'empty', 'name': 'Empty', 'filters': {}},
    ]}


def snapshot(day='2026-10-01', **tickers):
    return {'date': day, 'rows': [{'symbol': ticker + '.US', 'candidate': True, **fields} for ticker, fields in tickers.items()]}


def excluded(ticker, section, at='2026-10-01'):
    data = empty_workspace()
    data['statuses'][ticker] = {'status': 'excluded', 'section': section, 'status_at': at, 'excluded_at': at, 'tags': []}
    data['orders']['excluded'] = [ticker]
    return data


def test_matching_finite_missing_and_inclusive_bounds():
    rule = {'x': {'min': 1, 'max': 2}, 'category': {'values': ['good', 'fine']}}
    assert matches_filters({'x': 1, 'category': 'fine'}, rule)
    assert matches_filters({'x': 2, 'category': 'good'}, rule)
    assert not matches_filters({'x': 2}, rule)
    for value in (None, True, float('nan'), float('inf')):
        assert not matches_filters({'x': value, 'category': 'good'}, rule)
    assert not matches_filters({'x': 2}, {'x': {'max': 2, 'maxExclusive': True}})


def test_discover_and_focus_negative_rules_broken_priority_and_tag_roles():
    data = empty_workspace()
    data['statuses']['FOCUS'] = {'status': 'focus', 'section': 'unclassified'}
    prefs = validate_preferences(preferences())
    prefs['tags'][1]['name'] = 'Stretched'  # Stable role survives a rename.
    result = apply_rules(data, snapshot(FOCUS={'extended_k': 2}, DISC={'extended_k': 2, 'broken_k': 2, 'below_days': 3},
                                        AUX={'adr20': 7}, POT={'ema10_touch_days_5d': 4, 'adr20': 7}), prefs)
    assert result['statuses']['FOCUS']['section'] == 'extended'
    assert result['statuses']['DISC']['section'] == 'broken'
    assert result['statuses']['POT']['tags'] == ['surf', 'body-label']
    assert result['statuses']['POT']['section'] == 'surf'
    assert result['statuses']['AUX']['section'] == 'unclassified'
    assert all('empty' not in state['tags'] for state in result['statuses'].values())
    assert workspace_tickers(result) == []
    assert data['statuses']['FOCUS']['status'] == 'focus'


def test_hidden_skips_all_matching_and_survives_candidate_gaps_until_day_seven():
    data = excluded('HID', 'hidden')
    inherited = inherit_workspace(data, {'HID'}, set(), '2026-10-05')
    result = apply_rules(inherited, snapshot('2026-10-05', HID={'candidate': False, 'ema10_touch_days_5d': 5, 'extended_k': 3}), preferences())
    assert result['statuses']['HID']['section'] == 'hidden'
    assert result['statuses']['HID']['tags'] == []
    result = apply_rules(result, snapshot('2026-10-08', HID={'ema10_touch_days_5d': 5}), preferences())
    assert result['statuses']['HID']['status'] == 'discover'
    assert result['statuses']['HID']['section'] == 'surf'
    assert result['statuses']['HID']['released_at'] == '2026-10-08'
    view = derive_day_view('2026-10-08', {'HID'}, set(), result)
    assert view.returned == {'HID'}


def test_negative_deadline_not_extended_by_daily_matching_but_resets_after_expiry():
    data = excluded('EXT', 'extended')
    result = apply_rules(data, snapshot('2026-10-07', EXT={'extended_k': 2}), preferences())
    assert result['statuses']['EXT']['excluded_at'] == '2026-10-01'
    result = apply_rules(result, snapshot('2026-10-08', EXT={'extended_k': 2}), preferences())
    assert result['statuses']['EXT']['section'] == 'extended'
    assert result['statuses']['EXT']['excluded_at'] == '2026-10-08'
    assert apply_rules(result, snapshot('2026-10-08', EXT={'extended_k': 2}), preferences()) == result


def test_review_persists_without_setup_or_ranking_then_negative_reassigns():
    result = apply_rules(excluded('POT', 'broken'), snapshot('2026-10-02', POT={'candidate': False, 'ema10_touch_days_5d': 4}), preferences())
    assert result['statuses']['POT']['section'] == 'review'
    assert 'excluded_at' not in result['statuses']['POT']
    result = apply_rules(result, snapshot('2026-10-20', POT={'candidate': False}), preferences())
    assert result['statuses']['POT']['section'] == 'review'
    assert result['statuses']['POT']['tags'] == []
    result = apply_rules(result, snapshot('2026-10-21', POT={'candidate': False, 'extended_k': 2}), preferences())
    assert result['statuses']['POT']['section'] == 'extended'
    assert result['statuses']['POT']['excluded_at'] == '2026-10-21'


def test_manual_focus_and_tags_only_current_day_and_new_section_members_lead(tmp_path):
    folder = tmp_path / '2026-10-01'
    folder.mkdir()
    path = folder / 'workspace.json'
    data = empty_workspace()
    data['statuses'] = {'OLD': {'status': 'focus', 'section': 'surf', 'tags': ['surf']},
                        'NEXT': {'status': 'focus', 'section': 'surf', 'tags': ['surf']}}
    data['orders']['focus'] = ['NEXT', 'OLD']
    path.write_text(json.dumps(data))
    ws = Workspace(path)
    ws.add_ticker('NEW')
    ws.set_manual_tags('NEW', ['surf'])
    ws.reclassify(snapshot(OLD={'ema10_touch_days_5d': 4}, NEXT={'ema10_touch_days_5d': 4}, NEW={'extended_k': 2}), preferences())
    assert ws.data['orders']['focus'] == ['NEW', 'NEXT', 'OLD']
    assert ws.data['statuses']['NEW']['section'] == 'surf'
    assert ws.data['statuses']['NEW']['tags'] == ['ext', 'surf']
    inherited = inherit_workspace(ws.data, {'OLD', 'NEW', 'NEXT'}, {'OLD', 'NEW', 'NEXT'}, '2026-10-02')
    result = apply_rules(inherited, snapshot('2026-10-02', OLD={'ema10_touch_days_5d': 4}, NEXT={'ema10_touch_days_5d': 4}, NEW={'extended_k': 2}), preferences())
    assert result['statuses']['NEW']['status'] == 'excluded'
    assert result['statuses']['NEW']['tags'] == ['ext']
    assert result['orders']['focus'] == ['NEXT', 'OLD']


def test_reclassification_save_failure_rolls_back_and_retry_is_not_noop(tmp_path, monkeypatch):
    path = tmp_path / 'workspace.json'
    path.write_text(json.dumps(empty_workspace()))
    ws = Workspace(path)
    original = copy.deepcopy(ws.data)
    current = snapshot(ws.date, AAA={'extended_k': 2})
    with monkeypatch.context() as patch:
        patch.setattr(type(path), 'write_text', lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError('read only')))
        with pytest.raises(PermissionError):
            ws.reclassify(current, preferences())
    assert ws.data == original
    assert ws.reclassify(current, preferences())
    assert not ws.reclassify(current, preferences())


@pytest.mark.parametrize('edit', ['delete', 'label'])
def test_deleted_or_repurposed_tag_clears_same_day_manual_section(edit):
    data = empty_workspace()
    data['statuses']['AAA'] = {'status': 'focus', 'section': 'surf', 'tags': ['surf'], 'manual_section_date': '2026-10-01'}
    prefs = preferences()
    if edit == 'delete':
        prefs['tags'] = [tag for tag in prefs['tags'] if tag['id'] != 'surf']
    else:
        next(tag for tag in prefs['tags'] if tag['id'] == 'surf')['role'] = 'label'
    result = apply_rules(data, snapshot(AAA={'ema10_touch_days_5d': 4}), prefs)
    state = result['statuses']['AAA']
    assert state['status'] == 'focus'
    assert state['section'] == 'unclassified'
    assert 'manual_section_date' not in state
    assert result['orders']['focus'] == ['AAA']


def test_migration_combines_focus_wait_and_preferences_without_candidate_carry():
    old = {'version': 2, 'statuses': {'A': {'status': 'focus'}, 'B': {'status': 'wait'}, 'H': {'status': 'hidden', 'status_at': '2026-10-01'}},
           'orders': {'focus': ['A'], 'wait': ['B'], 'hidden': ['H']}, 'carried': ['NOTCAND']}
    result = migrate_workspace(old, '2026-10-02')
    assert result['orders']['focus'] == ['A', 'B']
    assert result['orders']['excluded'] == ['H']
    assert all(ticker.status == 'focus' for ticker in workspace_tickers(old))
    view = derive_day_view('2026-10-02', {'C'}, set(), result)
    assert view.as_dict()['lists'] == {'discover': ['C'], 'focus': ['A', 'B'], 'excluded': ['H']}
    prefs = preferences()
    prefs['activeList'] = 'hidden'
    assert validate_preferences(prefs)['activeList'] == 'excluded'
    assert prefs['tags'][1]['role'] == 'extended'

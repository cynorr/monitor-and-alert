"""Pure daily Tag matching and three-list classification; no market-data requests."""
from copy import deepcopy
import math

from .preferences import tag_role
from .workspace import HIDDEN_DAYS, _status_age, is_hidden, migrate_workspace


def matches_filters(row, filters):
    """Same inclusive bounds / explicit exclusive maximum as UI filters.ts."""
    for key, rule in filters.items():
        if not any(bound in rule for bound in ('min', 'max', 'values')):
            continue
        value = row.get(key)
        if value is None:
            return False
        if 'values' in rule:
            if value not in rule['values']:
                return False
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return False
        if 'min' in rule and value < rule['min']:
            return False
        if 'max' in rule and (value >= rule['max'] if rule.get('maxExclusive') else value > rule['max']):
            return False
    return True


def active_tag(tag):
    return tag['id'] != 'default' and any(any(bound in rule for bound in ('min', 'max', 'values'))
                                        for rule in tag.get('filters', {}).values())


def matched_tags(row, definitions, manual=()):
    return [tag for tag in definitions if tag['id'] != 'default' and
            (tag['id'] in manual or (active_tag(tag) and matches_filters(row, tag['filters'])))]


def focus_classification(row, preferences):
    matched = matched_tags(row, preferences['tags'])
    return {'tags': [tag['id'] for tag in matched],
            'section': next((tag['id'] for tag in matched if tag_role(tag) == 'setup'), 'unclassified')}


def apply_rules(workspace, snapshot, preferences, selected_date=None):
    """Return a new workspace; only Focus is eligible for Longbridge membership."""
    selected_date = selected_date or snapshot['date']
    result = migrate_workspace(workspace, selected_date)
    states = result['statuses']
    previous_states = deepcopy(states)
    rows = {row['symbol'].removesuffix('.US'): row for row in snapshot['rows']}
    candidates = {ticker for ticker, row in rows.items() if row.get('candidate')}
    definitions = preferences['tags']
    tag_ids = {tag['id'] for tag in definitions if tag['id'] != 'default'}
    setup_sections = {'unclassified'} | {tag['id'] for tag in definitions if tag_role(tag) == 'setup'}
    scope = candidates | {ticker for ticker, state in states.items() if state.get('status') in ('focus', 'excluded')}

    for ticker in sorted(scope):
        state = states.setdefault(ticker, {'status': 'discover', 'section': 'unclassified', 'status_at': selected_date})
        if is_hidden(state, selected_date):
            state['tags'] = []
            state.pop('manual_tags', None)
            state.pop('manual_tags_date', None)
            continue

        expired = state.get('status') == 'excluded' and state.get('section') != 'review' and (
            _status_age(selected_date, state.get('excluded_at', state.get('status_at', selected_date))) >= HIDDEN_DAYS)
        hidden_expired = expired and state.get('section') == 'hidden'
        if hidden_expired:
            state.update(status='discover', section='unclassified', released_at=selected_date)
            state.pop('excluded_at', None)

        if state.get('manual_tags_date') != selected_date:
            state.pop('manual_tags', None)
            state.pop('manual_tags_date', None)
        manual = set(state.get('manual_tags', [])) & tag_ids
        matched = matched_tags(rows.get(ticker, {}), definitions, manual)
        state['tags'] = [tag['id'] for tag in matched]
        potential = [tag['id'] for tag in matched if tag_role(tag) == 'setup']
        negative = next((role for role in ('broken', 'extended') if any(tag_role(tag) == role for tag in matched)), None)
        manual_focus = state.get('status') == 'focus' and state.get('manual_focus_date') == selected_date

        if negative and not manual_focus:
            if state.get('status') != 'excluded' or state.get('section') == 'review' or expired:
                state['excluded_at'] = selected_date
            state.update(status='excluded', section=negative)
            state.pop('manual_section_date', None)
        elif state.get('status') == 'excluded':
            if potential:
                state.update(section='review')
                state.pop('excluded_at', None)
            elif state.get('section') != 'review' and expired:
                state.update(status='discover', section='unclassified', released_at=selected_date)
                state.pop('excluded_at', None)
        elif state.get('manual_section_date') != selected_date or state.get('section') not in setup_sections:
            state['section'] = potential[0] if potential else 'unclassified'
            state.pop('manual_section_date', None)

        # A release returns only actual candidates; Review and Focus may outlive rankings.
        if state.get('status') == 'discover' and ticker not in candidates:
            del states[ticker]
        else:
            if state.get('section') == 'review':
                state.pop('manual_section_date', None)
            state.setdefault('status_at', selected_date)

    for ticker, state in list(states.items()):
        if state.get('status') == 'discover' and ticker not in candidates:
            del states[ticker]

    # Moved/new members lead their section; unchanged members retain manual order.
    orders = {}
    for status in ('discover', 'focus', 'excluded'):
        members = {ticker for ticker, state in states.items() if state.get('status') == status}
        unchanged = [ticker for ticker in result['orders'].get(status, []) if ticker in members and
                     previous_states.get(ticker, {}).get('status') == status and
                     previous_states.get(ticker, {}).get('section') == states[ticker].get('section')]
        incoming = sorted(members - set(unchanged))
        orders[status] = incoming + unchanged
    result['orders'] = orders
    return result

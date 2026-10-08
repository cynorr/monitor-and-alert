"""Saved Tag definitions and the shared field contract for list classification."""
import json
import math
import re
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'ui/src/filter-catalog.json'
CATALOG = json.loads(CATALOG_PATH.read_text())
FIELDS = {field['key']: field for field in CATALOG}
INITIAL_PREFERENCES = {'activeList': 'discover', 'sort': 'default', 'activeTag': None, 'tags': []}
APPEARANCE_KEYS = {'icon', 'color', 'background', 'backgroundColor'}
TAG_ICONS = {'surf', 'bounce', 'prior-run', 'orderly-pullback', 'extended', 'broken', 'label'}


def validate_appearance(value):
    if not isinstance(value, dict) or set(value) != APPEARANCE_KEYS:
        raise ValueError('Tag appearance requires icon, color, background and backgroundColor')
    if not isinstance(value['icon'], str) or value['icon'] not in TAG_ICONS:
        raise ValueError('Invalid Tag appearance icon')
    if not isinstance(value['background'], str) or value['background'] not in ('transparent', 'frosted'):
        raise ValueError('Invalid Tag appearance background')
    for key in ('color', 'backgroundColor'):
        if not isinstance(value[key], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value[key]):
            raise ValueError('Tag appearance colors must use #RRGGBB')


def tag_role(tag):
    return tag.get('role') or {'extended': 'extended', 'broken': 'broken', 'under-50': 'under50'}.get(tag['name'].strip().casefold(), 'setup')


def validate_preferences(value):
    value['activeList'] = {'wait': 'focus', 'hidden': 'excluded'}.get(value['activeList'], value['activeList'])
    if value['activeList'] not in ('discover','focus','excluded') or value['sort'] not in ('default','rfl1m','rfl3m','rfl6m'):
        raise ValueError('Invalid list or sort')
    tags = value['tags']
    if len(tags) > 10:
        raise ValueError('Maximum 10 tags')
    names, ids = set(), set()
    for tag in tags:
        name = tag['name'].strip()
        if not name or len(name) > 24 or name.casefold() in names or not tag['id'] or tag['id'] in ids:
            raise ValueError('Use unique Tag IDs and names of 1–24 characters')
        tag['role'] = tag_role(tag)
        if tag['role'] not in ('setup', 'extended', 'broken', 'under50', 'label'):
            raise ValueError('Invalid Tag role')
        names.add(name.casefold())
        ids.add(tag['id'])
        tag['name'] = name
        if 'appearance' in tag:
            validate_appearance(tag['appearance'])
        for key, rule in tag['filters'].items():
            if key not in FIELDS:
                raise ValueError('Unknown filter field')
            if FIELDS[key]['type'] == 'number':
                if set(rule) - {'min','max','maxExclusive'}:
                    raise ValueError('Invalid numeric filter')
                for bound in ('min','max'):
                    if bound in rule and (isinstance(rule[bound], bool) or not isinstance(rule[bound], (int,float)) or not math.isfinite(rule[bound])):
                        raise ValueError('Filter bounds must be finite numbers')
                if 'min' in rule and 'max' in rule and rule['min'] > rule['max']:
                    raise ValueError('Filter minimum exceeds maximum')
            elif set(rule) != {'values'} or not isinstance(rule['values'], list) or not set(rule['values']) <= {item['value'] for item in FIELDS[key]['options']}:
                raise ValueError('Invalid classification filter')
    if value['activeTag'] is not None and value['activeTag'] not in ids:
        raise ValueError('Active Tag must exist')
    return value

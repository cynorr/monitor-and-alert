"""One saved Tag collection; filter matching belongs to the UI."""
import json
import math
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'ui/src/filter-catalog.json'
CATALOG = json.loads(CATALOG_PATH.read_text())
FIELDS = {field['key']: field for field in CATALOG}
DEFAULT = {'activeList': 'discover', 'sort': 'default', 'activeTag': 'default',
           'tags': [{'id': 'default', 'name': 'Default', 'filters': {}}]}


def validate_preferences(value):
    if value['activeList'] not in ('discover','focus','wait','hidden') or value['sort'] not in ('default','rfl1m','rfl3m','rfl6m'):
        raise ValueError('Invalid list or sort')
    tags = value['tags']
    if not 1 <= len(tags) <= 10:
        raise ValueError('Keep between 1 and 10 tags')
    names, ids = set(), set()
    for tag in tags:
        name = tag['name'].strip()
        if not name or len(name) > 24 or name.casefold() in names or not tag['id'] or tag['id'] in ids:
            raise ValueError('Use unique Tag IDs and names of 1–24 characters')
        if tag['id'] == 'default' and name != 'Default':
            raise ValueError('Default cannot be renamed')
        names.add(name.casefold())
        ids.add(tag['id'])
        tag['name'] = name
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
            elif set(rule) != {'values'} or not set(rule['values']) <= {item['value'] for item in FIELDS[key]['options']}:
                raise ValueError('Invalid classification filter')
    if 'default' not in ids or value['activeTag'] not in ids:
        raise ValueError('Default and active Tag must exist')
    return value

export function matchesFilters(row, filters) {
    return Object.entries(filters).every(([key, rule]) => {
        if (rule.min === undefined && rule.max === undefined && rule.values === undefined)
            return true;
        const value = row[key];
        if (value === null || value === undefined)
            return false;
        if (rule.values !== undefined)
            return rule.values.includes(value);
        if (typeof value !== 'number' || !Number.isFinite(value))
            return false;
        return (rule.min === undefined || value >= rule.min) &&
            (rule.max === undefined || (rule.maxExclusive ? value < rule.max : value <= rule.max));
    });
}
export function sliderValues(field, rows, rule) {
    const observed = rows.map(row => row[field.key]).filter((value) => typeof value === 'number' && Number.isFinite(value)).map(value => value / field.scale);
    const values = [...field.values, field.default];
    if (observed.length) {
        const low = Math.min(...observed), high = Math.max(...observed);
        if (low < values[0])
            values.push(Math.floor(low));
        if (high > field.values[field.values.length - 1])
            values.push(Math.ceil(high));
    }
    for (const bound of [rule.min, rule.max])
        if (bound !== undefined)
            values.push(bound / field.scale);
    return [...new Set(values)].sort((a, b) => a - b);
}
export class FilterPanel {
    catalog;
    change;
    fields = new Map();
    scales = new Map();
    remembered = new Map();
    filters = {};
    constructor(root, catalog, change) {
        this.catalog = catalog;
        this.change = change;
        const groups = new Map();
        for (const field of catalog) {
            let group = groups.get(field.group);
            if (!group) {
                group = document.createElement('section');
                group.className = 'filter-group';
                const heading = document.createElement('h3');
                heading.textContent = field.group;
                group.append(heading);
                root.append(group);
                groups.set(field.group, group);
            }
            const row = document.createElement('div');
            row.className = 'filter-rule';
            const label = document.createElement('span');
            label.textContent = field.label + (field.unit ? ' ' + field.unit : '');
            label.className = 'rule-label';
            const choices = document.createElement('div');
            choices.className = 'rule-choices';
            row.append(label, choices);
            if (field.type === 'choice') {
                for (const option of [{ label: 'Any', value: '' }, ...field.options]) {
                    const button = document.createElement('button');
                    button.textContent = option.label;
                    button.dataset.choice = option.value;
                    button.addEventListener('click', () => {
                        const filters = structuredClone(this.filters);
                        if (!option.value)
                            delete filters[field.key];
                        else {
                            const values = new Set(filters[field.key]?.values ?? []);
                            if (values.has(option.value))
                                values.delete(option.value);
                            else
                                values.add(option.value);
                            if (values.size)
                                filters[field.key] = { values: field.options.map(item => item.value).filter(value => values.has(value)) };
                            else
                                delete filters[field.key];
                        }
                        this.change(filters);
                    });
                    choices.append(button);
                }
            }
            else {
                for (const [mode, text] of [['any', 'Any'], ['min', '≥'], ['max', '≤'], ['range', '↔']]) {
                    const button = document.createElement('button');
                    button.textContent = text;
                    button.dataset.mode = mode;
                    button.addEventListener('click', () => this.setMode(field, mode));
                    choices.append(button);
                }
                const tracks = document.createElement('div');
                tracks.className = 'rule-tracks';
                for (let index = 0; index < 2; index++) {
                    const wrapper = document.createElement('label');
                    wrapper.className = 'slider-value';
                    const input = document.createElement('input');
                    input.type = 'range';
                    input.setAttribute('aria-label', field.group + ': ' + field.label + (index ? ' maximum' : ' threshold'));
                    const output = document.createElement('output');
                    input.addEventListener('input', () => {
                        const bound = input.dataset.bound, remembered = this.remembered.get(field.key);
                        remembered[bound] = this.scales.get(field.key)[Number(input.value)];
                        if (this.mode(this.filters[field.key]) === 'range') {
                            if (bound === 'min')
                                remembered.max = Math.max(remembered.min, remembered.max);
                            else
                                remembered.min = Math.min(remembered.min, remembered.max);
                        }
                        this.setMode(field, this.mode(this.filters[field.key]) === 'any' ? field.direction : this.mode(this.filters[field.key]));
                    });
                    wrapper.append(input, output);
                    tracks.append(wrapper);
                }
                row.append(tracks);
            }
            group.append(row);
            this.fields.set(field.key, row);
        }
    }
    mode(rule = {}) {
        return rule.min !== undefined && rule.max !== undefined ? 'range' : rule.min !== undefined ? 'min' : rule.max !== undefined ? 'max' : 'any';
    }
    setMode(field, mode) {
        const filters = structuredClone(this.filters), remembered = this.remembered.get(field.key);
        if (mode === 'any')
            delete filters[field.key];
        else if (mode === 'range')
            filters[field.key] = { min: remembered.min * field.scale, max: Math.max(remembered.min, remembered.max) * field.scale };
        else
            filters[field.key] = { [mode]: remembered[mode] * field.scale };
        this.change(filters);
    }
    render(filters, rows) {
        this.filters = filters;
        for (const field of this.catalog) {
            const row = this.fields.get(field.key), rule = filters[field.key] ?? {}, mode = this.mode(rule);
            if (field.type === 'choice') {
                row.querySelectorAll('button').forEach(button => {
                    const selected = button.dataset.choice ? rule.values?.includes(button.dataset.choice) ?? false : rule.values === undefined;
                    button.classList.toggle('active', selected);
                    button.setAttribute('aria-pressed', String(selected));
                });
                continue;
            }
            const remembered = this.remembered.get(field.key) ?? { min: field.default, max: field.default };
            if (rule.min !== undefined)
                remembered.min = rule.min / field.scale;
            if (rule.max !== undefined)
                remembered.max = rule.max / field.scale;
            this.remembered.set(field.key, remembered);
            const values = sliderValues(field, rows, { min: remembered.min * field.scale, max: remembered.max * field.scale, ...rule });
            this.scales.set(field.key, values);
            row.querySelectorAll('[data-mode]').forEach(button => {
                button.classList.toggle('active', button.dataset.mode === mode);
                button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
            });
            row.querySelectorAll('input').forEach((input, index) => {
                const bound = index ? 'max' : mode === 'max' ? 'max' : mode === 'any' ? field.direction : 'min';
                input.parentElement.hidden = index === 1 && mode !== 'range';
                input.dataset.bound = bound;
                input.min = '0';
                input.max = String(values.length - 1);
                input.step = '1';
                input.value = String(values.indexOf(remembered[bound]));
                input.parentElement.querySelector('output').textContent = `${bound === 'min' ? '≥' : rule.maxExclusive ? '<' : '≤'} ${remembered[bound]}`;
            });
            row.classList.toggle('rule-any', mode === 'any');
        }
    }
}

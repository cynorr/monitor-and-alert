import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { matchesFilters, sliderValues } from '../public/filters.js';
import { withSavedTag, tagChanged } from '../public/tags.js';
const catalog = JSON.parse(readFileSync(new URL('../src/filter-catalog.json', import.meta.url)));

test('all 38 conditions have unique fields and numeric slider stops', () => {
    assert.equal(catalog.length, 38);
    assert.equal(new Set(catalog.map(field => field.key)).size, 38);
    for (const field of catalog.filter(field => field.type === 'number')) {
        const values = sliderValues(field, [], {});
        assert.ok(values.length > 1 && values.includes(field.default));
        assert.deepEqual(values, [...values].sort((a, b) => a - b));
    }
});

test('signed numeric boundaries are inclusive, conjunctive and reject active missing/nonfinite values', () => {
    const filters = { extended_k: { min: -1, max: 0 }, below_days: { max: 3 } };
    assert.ok(matchesFilters({ extended_k: -1, below_days: 3 }, filters));
    assert.ok(matchesFilters({ extended_k: 0, below_days: 0 }, filters));
    assert.equal(matchesFilters({ extended_k: 0, below_days: 4 }, filters), false);
    assert.equal(matchesFilters({ extended_k: null, below_days: 0 }, filters), false);
    assert.ok(matchesFilters({}, { extended_k: {} }));
    assert.equal(matchesFilters({ extended_k: Infinity }, { extended_k: { min: 0 } }), false);
    assert.equal(matchesFilters({ close: 10 }, { close: { min: 5, max: 10, maxExclusive: true } }), false);
});

test('MA classification options are OR within a field and AND with numeric conditions', () => {
    const filters = { ma_arrangement: { values: ['ema10_lead', 'ema20_lead'] }, below_days: { max: 2 } };
    assert.ok(matchesFilters({ ma_arrangement: 'ema10_lead', below_days: 2 }, filters));
    assert.ok(matchesFilters({ ma_arrangement: 'ema20_lead', below_days: 1 }, filters));
    assert.equal(matchesFilters({ ma_arrangement: 'ema20_lead', below_days: 3 }, filters), false);
    assert.equal(matchesFilters({ ma_arrangement: 'under50', below_days: 0 }, filters), false);
    assert.ok(matchesFilters({ ma_arrangement: 'missing' }, { ma_arrangement: { values: ['missing'] } }));
});

test('sliders cover outliers and preserve saved fractional thresholds in display units', () => {
    const adv = catalog.find(field => field.key === 'adv20');
    const values = sliderValues(adv, [{ adv20: 70_000_100_000 }], { min: 12_345_678 });
    assert.ok(values.includes(12.345678) && values.at(-1) >= 70000.1);
    const distance = catalog.find(field => field.key === 'extended_k');
    assert.ok(sliderValues(distance, [{ extended_k: -21.5 }], {}).includes(-22));
});

test('draft edits leave saved filters intact until explicit save, and cancellation restores them', () => {
    const saved = { id: 'surf', name: 'Surf', filters: { below_days: { max: 2 } } };
    const draft = structuredClone(saved);
    draft.filters.below_days.max = 1;
    assert.ok(tagChanged(saved, draft));
    const result = withSavedTag([saved], draft);
    assert.equal(result[0].filters.below_days.max, 1);
    assert.equal(saved.filters.below_days.max, 2);
    assert.equal(tagChanged(saved, structuredClone(saved)), false);
});

test('new Tags have independent filters, unique names and a ten-Tag limit', () => {
    const tags = [{ id: 'default', name: 'Default', filters: { below_days: { min: 2 } } }];
    const result = withSavedTag(tags, { id: 'new', name: ' Bounce ', filters: tags[0].filters });
    assert.equal(result[1].name, 'Bounce');
    result[1].filters.below_days.min = 5;
    assert.equal(tags[0].filters.below_days.min, 2);
    assert.throws(() => withSavedTag(result, { id: 'other', name: 'bounce', filters: {} }));
    const ten = Array.from({ length: 10 }, (_, i) => ({ id: String(i), name: String(i), filters: {} }));
    assert.throws(() => withSavedTag(ten, { id: 'new', name: 'New', filters: {} }));
});

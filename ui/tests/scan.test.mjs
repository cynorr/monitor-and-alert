import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { matchesFilters, sliderValues } from '../public/filters.js';
import { withSavedTag, tagChanged, tagRole } from '../public/tags.js';
import { scanProgress, selectionRequest } from '../public/types.js';
import { collapseKey, growthValue, isReviewSelection, listSections, sectionKey } from '../public/board.js';
import { matchesTag } from '../public/scan.js';
const catalog = JSON.parse(readFileSync(new URL('../src/filter-catalog.json', import.meta.url)));

test('scan progress keeps last ready date and seconds visible during preparation or errors', () => {
    const stage = { status: 'ready', target: '2026-10-02', updated_at: null, error: null };
    const state = { target_date: '2026-10-02', running: false, ready: true,
        daily: { ...stage }, splits: { ...stage }, bars: { ...stage, input_revision: 'old' },
        features: { ...stage, date: '2026-10-01', input_revision: 'old', updated_at: '2026-10-01T23:01:02+00:00' } };
    assert.equal(scanProgress(state).text, 'Scan Ready 2026-10-01 · 19:01:02 ET');
    state.running = true;
    state.daily.status = 'running';
    assert.match(scanProgress(state).text, /Scan Ready 2026-10-01.*Downloading daily/);
    state.running = false;
    state.daily.status = 'error';
    state.daily.error = 'daily: Massive HTTP 503';
    assert.ok(scanProgress(state).error);
    assert.equal(scanProgress(state).title, state.daily.error);
    state.daily.error = null;
    state.error = 'Pipeline status could not be saved';
    assert.match(scanProgress(state).text, /Refresh failed/);
    assert.equal(scanProgress(state).title, state.error);
});

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


test('setup sections preserve Tag order; renamed negative and helper labels remain outside setup sections', () => {
    const tags = [
        { id: 'default', name: 'Default', filters: {} },
        { id: 'first', name: 'Surf-20', role: 'setup', filters: {} },
        { id: 'negative', name: 'Too far', role: 'extended', filters: {} },
        { id: 'helper', name: 'Higher lows', role: 'label', filters: {} },
        { id: 'second', name: 'Bounce-10', role: 'setup', filters: {} },
    ];
    assert.deepEqual(listSections(true, 'focus', tags).map(section => section.id), ['first','second','unclassified']);
    assert.deepEqual(listSections(true, 'excluded', tags).map(section => section.id), ['review','broken','extended','hidden']);
    assert.deepEqual(listSections(false, 'discover', tags).map(section => section.list), ['focus','focus','focus','excluded']);
    assert.equal(sectionKey({ status: 'focus', section: 'second', tags: ['first','second'] }), 'focus:second');
    assert.equal(tagRole(tags[2]), 'extended');
});

test('manual Tags match the saved Tag filter; unsaved rule preview still requires the draft conditions', () => {
    const tag = { id: 'surf', name: 'Surf', filters: { below_days: { max: 1 } } };
    const row = { tags: ['surf'], below_days: 3 };
    assert.ok(matchesTag(row, tag));
    assert.equal(matchesTag(row, tag, false), false);
    assert.ok(matchesTag({ below_days: 1 }, tag, false));
    assert.equal(matchesTag({ tags: ['other'], below_days: null }, tag), false);
    assert.ok(tagChanged(tag, { ...tag, role: 'label' }));
});


test('Scan and Monitor fold independently; the same symbol keeps Review preview separate from Holdings live selection', () => {
    const folded = new Set([collapseKey(false, 'excluded:review')]);
    assert.ok(folded.has(collapseKey(false, 'excluded:review')));
    assert.equal(folded.has(collapseKey(true, 'excluded:review')), false);
    folded.add(collapseKey(true, 'focus:surf'));
    assert.equal(folded.has(collapseKey(false, 'focus:surf')), false);
    const row = { symbol: 'XYZ.US', status: 'excluded', section: 'review' };
    assert.ok(isReviewSelection(row, 'watchlist'));
    assert.equal(isReviewSelection(row, 'holdings'), false);
    const preview = selectionRequest('XYZ.US', '5m', 1, 'monitor', 'watchlist');
    const live = selectionRequest('XYZ.US', '5m', 2, 'monitor', 'holdings');
    assert.equal(preview.symbol, live.symbol);
    assert.equal(preview.source, 'watchlist');
    assert.equal(live.source, 'holdings');
    assert.equal(live.request_id, 2);
});

test('Growth formats the raw return percentage without changing its meaning at the multiple threshold', () => {
    assert.equal(growthValue(0), '0%');
    assert.equal(growthValue(12), '12%');
    assert.equal(growthValue(12.34), '12.3%');
    assert.equal(growthValue(99.9), '99.9%');
    assert.equal(growthValue(100), '2.0x');
    assert.equal(growthValue(130), '2.3x');
    assert.equal(growthValue(234), '3.3x');
    for (const value of [null, undefined, NaN, Infinity, -Infinity, '130']) assert.equal(growthValue(value), '—');
});

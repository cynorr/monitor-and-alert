import test from 'node:test';
import assert from 'node:assert/strict';
import { Watchlist } from '../public/list.js';

const ticker = (name, status = 'discover', section = 'unclassified') =>
    ({ ticker: name, symbol: name + '.US', status, section });
function listFixture() {
    const list = Object.create(Watchlist.prototype);
    Object.assign(list, { editable: true, busy: false, keyboardEnabled: true, search: null,
        scan: { enabled: true, activeList: 'discover' }, tickers: [ticker('A')], selected: 'A.US', collapsed: new Set() });
    return list;
}
const key = (key, extra = {}) => ({ key, target: { closest: () => null }, preventDefault() {}, ...extra });

test('keyboard routes Scan removal, directional admission, swap and Command pin independently', () => {
    const list = listFixture(), calls = [];
    list.actOnTicker = (item, action) => calls.push(action);
    list.swapSelected = direction => calls.push(['swap', direction]);
    list.togglePin = (item, pinned) => calls.push(['pin', pinned]);
    list.handleKey(key('Backspace')); list.handleKey(key('Delete'));
    list.handleKey(key('ArrowRight', { shiftKey: true }));
    list.handleKey(key('ArrowLeft', { shiftKey: true }));
    list.handleKey(key('ArrowUp', { shiftKey: true }));
    list.handleKey(key('ArrowDown', { shiftKey: true, metaKey: true }));
    assert.deepEqual(calls, ['remove', 'remove', 'focus', ['swap', -1], ['pin', false]]);
    calls.length = 0; list.tickers[0].status = 'excluded';
    list.handleKey(key('ArrowLeft', { shiftKey: true }));
    list.handleKey(key('ArrowRight', { shiftKey: true }));
    assert.deepEqual(calls, ['focus']);
    calls.length = 0; list.scan.enabled = false;
    list.handleKey(key('Delete')); list.handleKey(key('Backspace'));
    list.handleKey(key('ArrowLeft', { shiftKey: true }));
    list.handleKey(key('ArrowUp', { shiftKey: true, metaKey: true }));
    assert.deepEqual(calls, [['pin', true]]);
    calls.length = 0; list.editable = false;
    list.handleKey(key('ArrowUp', { shiftKey: true, metaKey: true }));
    list.handleKey(key('ArrowDown', { shiftKey: true }));
    list.scan.enabled = true;
    list.handleKey(key('Backspace', { target: { closest: () => ({}) } }));
    assert.deepEqual(calls, []);
});

test('single-row actions only advance for the agreed whitelist; machine release and repeated pin do nothing', async () => {
    const list = listFixture(), calls = [];
    list.mutate = async (payload, advance) => { calls.push([payload, advance?.ticker]); };
    const a = list.tickers[0];
    await list.actOnTicker(a, 'remove');
    a.status = 'focus'; await list.actOnTicker(a, 'remove');
    a.status = 'excluded'; a.section = 'broken'; await list.actOnTicker(a, 'remove');
    await list.actOnTicker(a, 'focus');
    a.section = 'hidden'; await list.actOnTicker(a, 'remove');
    a.pinned = true; await list.togglePin(a, true); await list.togglePin(a, false);
    assert.deepEqual(calls.map(([p, a]) => [p.action, p.target ?? p.pinned, a]),
        [['hide', undefined, 'A'], ['move', 'discover', 'A'], ['move', 'focus', 'A'], ['move', 'discover', 'A'], ['pin', false, 'A']]);
    calls.length = 0; list.scan.enabled = false; a.status = 'focus'; a.section = 'unclassified';
    await list.actOnTicker(a, 'remove');
    assert.deepEqual(calls, [[{ action: 'hide', ticker: 'A' }, undefined]]);
});

test('next uses pre-action visible order, stays at the tail, clears empty and never overrides another selection', () => {
    const list = listFixture(), choices = [];
    list.selected = 'B.US';
    list.advancing = { symbol: 'B.US', list: 'discover', scan: true, order: ['A.US', 'B.US', 'C.US'] };
    list.onSelect = symbol => choices.push(symbol);
    const rows = names => new Map(names.map(n => [n + '.US', { scrollIntoView() {} }]));
    list.rows = rows(['B', 'A', 'C']); list.advanceSelection(); // Pin B before A.
    list.rows = rows(['A']); list.advanceSelection(); // Last survivor; no wrap to unrelated list.
    list.rows = rows([]); list.advanceSelection();
    assert.deepEqual(choices, ['C.US', 'A.US', '']);
    list.selected = 'A.US'; list.advanceSelection();
    assert.equal(choices.length, 3);
    list.selected = 'B.US'; list.scan.activeList = 'focus'; list.advanceSelection();
    assert.equal(choices.length, 3);
});

test('Page navigation unfolds the next section and does not wrap', () => {
    const list = listFixture(), choices = [];
    const groups = ['A', 'B'].map(name => ({ dataset: { firstSymbol: name + '.US' },
        querySelector: () => ({ dataset: { toggle: name } }) }));
    list.rows = new Map(groups.map((group, i) => [[...['A.US', 'B.US']][i], { closest: () => group, scrollIntoView() {} }]));
    list.collapsed.add('B'); list.render = () => {};
    list.onSelect = symbol => { list.selected = symbol; choices.push(symbol); };
    globalThis.document = { getElementById: () => ({ querySelectorAll: () => groups }) };
    try {
        list.jumpSection(-1); assert.deepEqual(choices, []);
        list.jumpSection(1); assert.equal(list.collapsed.has('B'), false);
        list.jumpSection(1); assert.deepEqual(choices, ['B.US']);
        list.jumpSection(-1); assert.deepEqual(choices, ['B.US', 'A.US']);
    } finally { delete globalThis.document; }
});

test('saving skips transient first-row fallback; failure and ordinary edits do not advance', async () => {
    const list = listFixture(), choices = [];
    const nodes = new Map();
    globalThis.document = { getElementById: id => { if (!nodes.has(id)) nodes.set(id, {}); return nodes.get(id); } };
    list.tickers.push(ticker('B')); list.visible = () => list.tickers;
    list.render = () => { list.rows = new Map(list.tickers.map(t => [t.symbol, { scrollIntoView() {} }])); };
    list.onSelect = symbol => { list.selected = symbol; choices.push(symbol); };
    list.onUpdate = data => list.update(data); list.render();
    const a = list.tickers[0];
    globalThis.fetch = async () => ({ ok: true, json: async () => ({ board: [ticker('B')], editable: true }) });
    try {
        await list.mutate({ action: 'hide', ticker: 'A' }, a);
        assert.deepEqual(choices, ['B.US']);
        choices.length = 0;
        await list.mutate({ action: 'tag', ticker: 'B', tags: [] });
        assert.deepEqual(choices, []);
        globalThis.fetch = async () => ({ ok: false, json: async () => ({ error: 'Could not save' }) });
        await list.mutate({ action: 'hide', ticker: 'B' }, list.tickers[0]);
        assert.deepEqual(choices, []); assert.equal(list.selected, 'B.US');
        assert.equal(list.advancing, undefined);
    } finally { delete globalThis.document; delete globalThis.fetch; }
});

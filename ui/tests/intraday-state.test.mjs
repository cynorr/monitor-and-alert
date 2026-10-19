import test from 'node:test';
import assert from 'node:assert/strict';
import { rankedRows, compareRank, adrText, adrTitle } from '../public/intraday-state.js';
import { sortedHoldingRows } from '../public/holdings.js';
import { listColumns } from '../public/board.js';
import { attentionAppearance, attentionState } from '../public/attention.js';

const row = (ticker, extra = {}) => ({ ticker, symbol: ticker + '.US', status: 'focus', ...extra });
const state = (rank, extra = {}) => ({ rank, state: 'up-notice', up_adr: .7, down_adr: .2, adr20: 5, ...extra });

test('pins keep owner order; price, cumulative and local discrete tiers precede stable original order', () => {
    const rows = [row('A'), row('PIN2', { pinned: true, pin_index: 1 }), row('B'), row('C'), row('PIN1', { pinned: true, pin_index: 0 }), row('D')];
    const states = { 'A.US': state([2, 2, 1]), 'B.US': state([3, 0, 0]), 'C.US': state([2, 2, 3]), 'D.US': state([2, 2, 1]) };
    const original = structuredClone(rows);
    assert.deepEqual(rankedRows(rows, states).map(r => r.ticker), ['PIN1', 'PIN2', 'B', 'C', 'A', 'D']);
    assert.deepEqual(rows, original);
    assert.equal(compareRank(state([2, 1, 1], { up_adr: .61 }), state([2, 1, 1], { up_adr: .99 })), 0);
});

test('holdings risk sorts ahead of potential, duplicates stay together and closed lots remain at tail', () => {
    const holding = (ticker, ids) => ({ ticker, sequences: ids.map(id => ({ buy_ids: [id], closed_today: id === 'closed' })) });
    const data = [holding('UP', ['up']), holding('RISK', ['one', 'closed', 'two']), holding('NOTICE', ['warning'])];
    const states = { 'UP.US': state([2, 3, 3]), 'RISK.US': state([4, 0, 0]), 'NOTICE.US': state([3, 0, 0]) };
    assert.deepEqual(sortedHoldingRows(data, null, states).map(r => r.sequence.buy_ids[0]), ['one', 'two', 'warning', 'up', 'closed']);
    assert.deepEqual(sortedHoldingRows(data, null).map(r => r.sequence.buy_ids[0]), ['up', 'one', 'two', 'warning', 'closed']);
});

test('ADR label describes the displayed direction while tooltip keeps both values and percentage units', () => {
    assert.equal(adrText(state([2, 0, 0])), '↑0.70×');
    assert.equal(adrText(state([4, 0, 0], { state: 'down-urgent', down_adr: 1.05 })), '↓1.05×');
    assert.match(adrTitle(state([2, 0, 0])), /ADR20 5.00%/);
    assert.equal(adrText(), '—');
});

test('state columns are confined to an enabled current Focus presentation', () => {
    assert.deepEqual(listColumns(false, true, true).filter(c => ['state-adr', 'cum-vol', 'local-vol'].includes(c.field)).map(c => c.label), ['ADR', 'CumVol', 'LocalVol']);
    assert.ok(!listColumns(true, true).some(c => c.field === 'state-adr'));
});

test('symbol unread and concurrent playback are independent from read and price state', () => {
    const classes = () => {
        const values = new Set();
        return { values, classList: { toggle: (key, on) => on ? values.add(key) : values.delete(key) } };
    };
    const a = classes(), b = classes();
    const playing = attentionState({ unread: ['A.US','B.US'], sound: { playing: ['A.US','B.US'] } });
    attentionAppearance(a, 'A.US', playing); attentionAppearance(b, 'B.US', playing);
    assert.ok(a.values.has('ringing') && b.values.has('ringing'));
    const read = attentionState({ unread: ['B.US'], sound: { playing: ['A.US','B.US'] } });
    attentionAppearance(a, 'A.US', read); attentionAppearance(b, 'B.US', read);
    assert.equal(a.values.size, 0); assert.ok(b.values.has('ringing'));
    attentionAppearance(b, 'B.US', attentionState({ unread: ['B.US'], sound: { playing: [] } }));
    assert.ok(b.values.has('attention') && !b.values.has('ringing'));
});

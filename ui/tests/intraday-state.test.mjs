import test from 'node:test';
import assert from 'node:assert/strict';
import { rankedRows, compareRank, adrText, adrTitle, volumeBadge } from '../public/intraday-state.js';
import { sortedHoldingRows } from '../public/holdings.js';
import { listColumns } from '../public/board.js';
import { attentionAppearance, attentionState } from '../public/attention.js';

const row = (ticker, extra = {}) => ({ ticker, symbol: ticker + '.US', status: 'focus', ...extra });
const state = (rank, extra = {}) => ({ rank, state: 'up-notice', up_adr: .7, down_adr: .2, adr20: 5, ...extra });

test('volume-only state leaves ADR empty until its own inputs arrive', () => {
    const partial = state([0, 2, 1], { state: null, up_adr: null, down_adr: null, adr20: null });
    assert.equal(adrText(partial), '—');
    assert.match(adrTitle(partial), /Waiting/);
    assert.ok(compareRank(partial, state([0, 0, 0])) < 0);
});

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

test('latest unread direction and grade replace the wave; old playback cannot revive it after read', () => {
    const pulses = [];
    const wave = { dataset: {}, animate: frames => { pulses.push(frames); return {}; } };
    const node = { dataset: {}, querySelector: () => wave };
    const now = Date.now() / 1000;
    const notice = { symbol:'A.US', direction:'down', level:2, fired_at:now };
    const state = attentionState({ unread:[notice], sound:{ playing:[{symbol:'A.US',fired_at:now-1,pulse_at:now}] } });
    attentionAppearance(node, 'A.US', state);
    assert.equal(node.dataset.alert, 'down-urgent'); assert.equal(pulses.length, 0);
    state.playing.set('A.US', {symbol:'A.US',fired_at:now,pulse_at:now});
    attentionAppearance(node, 'A.US', state); attentionAppearance(node, 'A.US', state);
    assert.equal(pulses.length, 1);
    state.unread.set('A.US', {...notice,direction:'up',level:1});
    attentionAppearance(node, 'A.US', state); assert.equal(node.dataset.alert, 'up-notice');
    state.unread.clear(); attentionAppearance(node, 'A.US', state);
    assert.equal(node.dataset.alert, undefined); assert.equal(pulses.length, 1);
});

test('Focus hides small raw multiples without treating them as missing or changing Holdings formatting', () => {
    const value = state([0,0,0], {state:'neutral',up_adr:.5});
    assert.equal(adrText(value, true), ''); assert.equal(adrText(value), '↑0.50×');
    assert.equal(adrText({...value,up_adr:.501}, true), '↑0.50×');
    assert.equal(adrText(undefined, true), '—');
    let cleared = false;
    volumeBadge({replaceChildren:()=>{cleared=true;}}, {ratio:.5}, true);
    assert.ok(cleared);
});

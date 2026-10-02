import test from 'node:test';
import assert from 'node:assert/strict';
import { sortedHoldingRows } from '../public/holdings.js';

const fields = ['market_value', 'holding_days', 'total_pnl_percent', 'total_pnl', 'sold_percent', 'day_pnl'];
function holding(ticker, value, id = ticker) {
    return { ticker, change_percent: value, extended_percent: value, sequences: [{
        buy_ids: [id], ...Object.fromEntries(fields.map(field => [field, value])), sells: [],
    }] };
}
const symbols = rows => rows.map(row => row.holding.ticker);

test('all eight numeric columns sort descending using numbers, including losses', () => {
    const data = [holding('SMALL', '2'), holding('NEG', '-10'), holding('BIG', '12')];
    for (const field of [...fields, 'change_percent', 'extended_percent']) {
        assert.deepEqual(symbols(sortedHoldingRows(data, field)), ['BIG', 'SMALL', 'NEG'], field);
    }
});

test('symbol sort is descending and removing sort restores the original account order', () => {
    const data = [holding('IOVA', '2'), holding('ABCL', '3'), holding('TXG', '1')];
    const original = structuredClone(data);
    assert.deepEqual(symbols(sortedHoldingRows(data, 'symbol')), ['TXG', 'IOVA', 'ABCL']);
    assert.deepEqual(symbols(sortedHoldingRows(data, 'market_value')), ['ABCL', 'IOVA', 'TXG']);
    assert.deepEqual(symbols(sortedHoldingRows(data, null)), ['IOVA', 'ABCL', 'TXG']);
    assert.deepEqual(data, original);
});

test('missing and nonfinite metrics follow valid negative values', () => {
    const data = [holding('MISSING', null), holding('LOSS', '-5'), holding('LESS_LOSS', '-2'), holding('BAD', 'NaN')];
    assert.deepEqual(symbols(sortedHoldingRows(data, 'extended_percent')), ['LESS_LOSS', 'LOSS', 'MISSING', 'BAD']);
});

test('duplicate ticker sequences sort independently, keep sales attached, and keep ties stable', () => {
    const first = holding('XYZ', '2', 'first'), second = holding('XYZ', '20', 'second');
    first.sequences.push(second.sequences[0]);
    second.sequences[0].sells.push({ id: 'sale', value: '99' });
    const rows = sortedHoldingRows([first, holding('OTHER', '20')], 'total_pnl');
    assert.deepEqual(rows.map(row => row.sequence.buy_ids[0]), ['second', 'OTHER', 'first']);
    assert.equal(rows[0].sequence.sells[0].id, 'sale');
});

test('net liquidation sorts by original precision rather than rounded display values', () => {
    const rows = sortedHoldingRows([holding('LOW', '991.1'), holding('HIGH', '991.4')], 'market_value');
    assert.deepEqual(symbols(rows), ['HIGH', 'LOW']);
});

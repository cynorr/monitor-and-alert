import test from 'node:test';
import assert from 'node:assert/strict';
import { holdingsColumns } from '../public/schwab-holdings.js';

test('Holdings keeps the detail and Total fields aligned when the session changes', () => {
    const accountFields = ['symbol', 'sold_percent', 'market_value', 'holding_days', 'percent',
        'open_profit_loss', 'change_percent'];
    const fields = (regular, intraday) => holdingsColumns(regular, intraday).map(column => column.field);
    assert.deepEqual(fields(false, true), [...accountFields, 'extended_percent', 'day_profit_loss', 'actions']);
    assert.deepEqual(fields(true, false), [...accountFields, 'day_profit_loss', 'actions']);
    assert.deepEqual(fields(true, true), [...accountFields, 'day_profit_loss', 'state-adr', 'cum-vol', 'local-vol', 'actions']);
});

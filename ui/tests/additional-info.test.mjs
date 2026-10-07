import test from 'node:test';
import assert from 'node:assert/strict';
import { AdditionalInfoDisplay, acceptsAdditional, categoryText, earningsText, marketCap } from '../public/additional-info.js';

const at = value => Date.parse(value) / 1000;
const event = date => ({ date, session: 'time-after-hours', fiscal_period: 'Aug/2026' });
const info = {
    symbol: 'XYZ.US', company_name: 'XYZ & Co. <name>', sector: 'Technology', industry: 'Semiconductors',
    market_cap: '1200000000', earnings: { last: event('2026-10-01'), next: event('2026-10-15') },
    companies_updated_at: '2026-10-07T12:00:00Z', earnings_updated_at: '2026-10-07T12:00:00Z',
    server_time: at('2026-10-07T12:00:00Z'),
};

test('recent actual report wins; next report returns after seven days; past dates are not upcoming', () => {
    assert.equal(earningsText(info).text, 'Last earnings report · 6 days ago');
    const result = earningsText(info, at('2026-10-09T12:00:00Z'));
    assert.equal(result.text, 'Next earnings report · In 6 days');
    assert.match(result.title, /Estimated.*2026-10-15.*After hours/);
    assert.equal(earningsText({ ...info, earnings: { last: null, next: null } }).text, '');
    assert.equal(earningsText({ ...info, earnings: { last: null, next: event('2026-10-06') } }).text, '');
    assert.equal(earningsText({ ...info, earnings: { last: event('2026-10-06'), next: null } }).text, 'Last earnings report · 1 day ago');
});

test('calendar days use New York rather than browser timezone, including the DST transition', () => {
    const value = { ...info, earnings: { last: null, next: event('2026-11-02') } };
    assert.equal(earningsText(value, at('2026-11-01T04:30:00Z')).text, 'Next earnings report · In 1 day');
    assert.equal(earningsText(value, at('2026-11-03T04:30:00Z')).text, 'Earnings today');
    assert.equal(earningsText({ ...value, earnings: { last: event('2026-11-02'), next: null } },
        at('2026-11-03T04:30:00Z')).text, 'Last earnings report · Today');
});

test('metadata requires matching selection identity independently of chart revisions', () => {
    const selected = { symbol: 'XYZ.US', request_id: 10, mode: 'monitor', source: 'holdings' };
    assert.ok(acceptsAdditional({ ...info, ...selected, type: 'additional_info' }, selected));
    for (const [key, value] of [['symbol', 'OTHER.US'], ['request_id', 9], ['mode', 'scan'], ['source', 'watchlist']])
        assert.equal(acceptsAdditional({ ...info, ...selected, [key]: value }, selected), false);
});

test('categories keep at most two distinct heads without parenthetical or colon detail', () => {
    assert.equal(categoryText('Health Care', 'Biotechnology: Biological Products (No Diagnostic Substances)'), 'Health Care · Biotechnology');
    assert.equal(categoryText('Finance', 'Finance: Consumer Services'), 'Finance');
    assert.equal(categoryText(' Finance ', 'finance: Consumer Services: Other'), 'Finance');
    assert.equal(categoryText('Technology', 'Computer Software: Prepackaged Software'), 'Technology · Computer Software');
    assert.equal(categoryText('Consumer Staples', 'Beverages (Production/Distribution)'), 'Consumer Staples · Beverages');
    assert.equal(categoryText(null, '  Major   Banks  '), 'Major Banks');
    assert.equal(categoryText('Technology', null), 'Technology');
    assert.equal(categoryText(null, null), '');
});

test('nullable fields hide safely and names render as text', () => {
    const nodes = new Map();
    globalThis.document = { getElementById(id) { if (!nodes.has(id)) nodes.set(id, {setAttribute(key,value) {this[key]=value;}}); return nodes.get(id); } };
    const display = new AdditionalInfoDisplay();
    display.update(info);
    assert.equal(nodes.get('daily-company-name').textContent, 'XYZ & Co. <name>');
    assert.equal(nodes.get('daily-classification').textContent, 'Technology · Semiconductors');
    assert.equal(nodes.get('intraday-market-cap').textContent, 'Market Cap 1.2B');
    assert.equal(nodes.get('daily-earnings-countdown').textContent, '· 6 days ago');
    display.update(null);
    assert.ok(['daily-company-name', 'daily-classification', 'intraday-market-cap', 'daily-earnings'].every(id => nodes.get(id).hidden));
    assert.equal(nodes.get('daily-earnings-label').textContent, '');
    assert.equal(nodes.get('daily-earnings-countdown').textContent, '');
    for (const cap of [null, '0', '-1', 'NaN', 'Infinity']) assert.equal(marketCap(cap), '');
});

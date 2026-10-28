import { attentionState, attentionAppearance } from './attention.js';
import { symbolRow } from './symbol-row.js';
import { HoldingsLayout } from './holdings-layout.js';
import { $ } from './types.js';
import { compareRank, stateAppearance, adrText, adrTitle, volumeBadge } from './intraday-state.js';
export function holdingsErrorAdvice(kind) {
    switch (kind) {
        case 'request': return { reason: 'Account request failed', action: 'Automatic retries continue. If this persists, check your network and SnapTrade connection, or share the details with Codex.' };
        case 'accounting': return { reason: 'Trade matching or position check failed', action: 'Check the trade associations and quantities, or share the details with Codex. A trade mismatch needs correction; restarting will not resolve it. Automatic retries continue.' };
        case 'storage': return { reason: 'Holdings cache could not be saved', action: 'Check available disk space and runtime folder permissions. Automatic retries continue.' };
        default: return { reason: 'Holdings refresh failed', action: 'Automatic retries continue. If this persists, share the details with Codex.' };
    }
}
const money = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const percentage = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const netLiq = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const quantity = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 });
const soldPercent = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const signed = (value, percent = false, extended = false) => `${Number(value) > 0 ? '+' : ''}${(percent ? extended ? money : percentage : netLiq).format(Number(value))}${percent ? '%' : ''}`;
const pnlClass = (value) => Number(value) > 0 ? 'positive' : Number(value) < 0 ? 'negative' : '';
const symbolFor = (ticker) => ticker.endsWith('.US') ? ticker : ticker + '.US';
export function sortedHoldingRows(holdings, sort, states = {}) {
    const all = holdings.flatMap(holding => holding.sequences.map(sequence => ({ holding, sequence })));
    const rows = all.filter(row => !row.sequence.closed_today), closed = all.filter(row => row.sequence.closed_today);
    const value = ({ holding, sequence }) => {
        if (!sort)
            return null;
        if (sort === 'symbol')
            return holding.ticker;
        return sort === 'change_percent' || sort === 'extended_percent' ? holding[sort] : sequence[sort];
    };
    rows.sort((a, b) => {
        const rank = compareRank(states[symbolFor(a.holding.ticker)], states[symbolFor(b.holding.ticker)]);
        if (rank || !sort)
            return rank;
        const left = value(a), right = value(b);
        if (sort === 'symbol')
            return String(right).localeCompare(String(left), 'en');
        const x = left == null ? null : Number(left), y = right == null ? null : Number(right);
        const missingX = x == null || !Number.isFinite(x), missingY = y == null || !Number.isFinite(y);
        return missingX ? (missingY ? 0 : 1) : missingY ? -1 : y - x;
    });
    return [...rows, ...closed];
}
export class HoldingsList {
    onSelect;
    isActive;
    onWidth;
    selected = '';
    data = null;
    expanded = new Set();
    structure = '';
    rows = new Map();
    groups = new Map();
    order = '';
    sort = null;
    layout;
    collapsed = false;
    regularSession = false;
    intraday = { enabled: false, symbols: {} };
    attention = attentionState();
    ordered() { return sortedHoldingRows(this.data?.data?.holdings ?? [], this.sort, this.intraday.enabled && this.regularSession ? this.intraday.symbols : {}); }
    constructor(onSelect, isActive, onWidth) {
        this.onSelect = onSelect;
        this.isActive = isActive;
        this.onWidth = onWidth;
        this.layout = new HoldingsLayout($('holdings-table'), () => this.intraday.enabled && this.regularSession ? 9 : 8, onWidth);
        try {
            this.collapsed = localStorage.getItem('holdings-collapsed') === 'true';
        }
        catch { /* Optional storage. */ }
        $('holdings-warning').addEventListener('click', () => {
            const details = $('holdings-error-details');
            details.hidden = !details.hidden;
            $('holdings-warning').setAttribute('aria-expanded', String(!details.hidden));
        });
        document.addEventListener('click', event => {
            if (!$('holdings-error').contains(event.target))
                this.closeError();
        });
        $('holdings-toggle').addEventListener('click', () => {
            this.collapsed = !this.collapsed;
            try {
                localStorage.setItem('holdings-collapsed', String(this.collapsed));
            }
            catch { /* Optional storage. */ }
            this.render();
        });
        $('holdings-rows').addEventListener('click', event => {
            const target = event.target;
            const toggle = target.closest('[data-trades]');
            if (toggle) {
                const key = toggle.dataset.trades;
                this.expanded.has(key) ? this.expanded.delete(key) : this.expanded.add(key);
                this.render();
                return;
            }
            const row = target.closest('[data-holding]');
            if (row)
                this.choose(row.dataset.holding);
        });
        $('holdings-table').querySelector('thead').addEventListener('click', event => {
            const button = event.target.closest('[data-holdings-sort]');
            if (!button)
                return;
            const next = button.dataset.holdingsSort;
            this.sort = this.sort === next ? null : next;
            this.render();
        });
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && !$('holdings-error-details').hidden) {
                this.closeError();
                $('holdings-warning').focus();
                return;
            }
            if (this.collapsed || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey ||
                event.target.closest('input,textarea,select,[contenteditable="true"],#holdings-error'))
                return;
            if (event.key === 'Enter' || event.key === ' ') {
                const row = event.target.closest('tr[data-holding]');
                if (row && !event.target.closest('button')) {
                    event.preventDefault();
                    this.choose(row.dataset.holding);
                }
            }
            else if (this.isActive() && ['ArrowUp', 'ArrowDown'].includes(event.key)) {
                const keys = [...this.rows.keys()];
                if (!keys.length)
                    return;
                event.preventDefault();
                const index = Math.max(0, Math.min(keys.length - 1, keys.indexOf(this.selected) + (event.key === 'ArrowDown' ? 1 : -1)));
                this.choose(keys[index]);
                this.rows.get(keys[index])?.focus();
                this.rows.get(keys[index])?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            }
        });
    }
    choose(key) {
        for (const holding of this.data?.data?.holdings ?? []) {
            if (holding.sequences.some(sequence => sequence.buy_ids.join(':') === key)) {
                this.onSelect(symbolFor(holding.ticker), key);
                return;
            }
        }
    }
    has(key) { return this.data?.data?.holdings.some(h => h.sequences.some(s => s.buy_ids.join(':') === key)) ?? false; }
    first() {
        const first = this.ordered()[0];
        return first ? { symbol: symbolFor(first.holding.ticker), key: first.sequence.buy_ids.join(':') } : null;
    }
    forSymbol(symbol) {
        const row = this.ordered().find(row => symbolFor(row.holding.ticker) === symbol);
        return row ? { symbol, key: row.sequence.buy_ids.join(':') } : null;
    }
    jumpUnread() {
        const next = this.ordered().find(row => this.attention.unread.has(symbolFor(row.holding.ticker)));
        if (!next)
            return;
        this.collapsed = false;
        try {
            localStorage.setItem('holdings-collapsed', 'false');
        }
        catch { /* Optional storage. */ }
        const key = next.sequence.buy_ids.join(':');
        this.choose(key);
        this.render();
        this.rows.get(key)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
    update(state, regularSession, intraday) {
        this.data = state;
        this.intraday = intraday ?? { enabled: false, symbols: {} };
        if (regularSession !== undefined)
            this.regularSession = regularSession;
        this.render();
    }
    tick(now = Date.now()) {
        const data = this.data?.data, updated = $('holdings-updated');
        updated.hidden = !!data && now - Date.parse(data.fetched_at) < 60_000;
        updated.textContent = data ? new Date(data.fetched_at).toLocaleTimeString('en-GB', { hour12: false }) :
            this.data?.error ? 'Refresh failed' : this.data?.loading ? 'Loading…' : '';
        updated.title = this.data?.error ?? (data ? `Last successful account refresh ${new Date(data.fetched_at).toLocaleString('en-GB')} · Positions as of ${data.positions_as_of}` : '');
        updated.classList.toggle('negative', !!this.data?.error);
        $('holdings-error').hidden = !this.data?.error || updated.hidden;
        if ($('holdings-error').hidden)
            this.closeError();
        const advice = holdingsErrorAdvice(this.data?.error_kind);
        for (const [id, text] of [['holdings-error-reason', advice.reason], ['holdings-error-action', advice.action],
            ['holdings-error-detail', this.data?.error ?? '']]) {
            if ($(id).textContent !== text)
                $(id).textContent = text;
        }
    }
    closeError() {
        $('holdings-error-details').hidden = true;
        $('holdings-warning').setAttribute('aria-expanded', 'false');
    }
    cell(row, text) {
        const cell = row.insertCell();
        cell.textContent = text;
        return cell;
    }
    value(cell, text) {
        cell.textContent = text;
    }
    render() {
        $('holdings').hidden = !this.data;
        $('holdings-content').hidden = this.collapsed;
        $('holdings').dataset.expanded = String(!this.collapsed);
        $('holdings-toggle').setAttribute('aria-expanded', String(!this.collapsed));
        $('holdings-arrow').textContent = this.collapsed ? '▸' : '▾';
        const data = this.data?.data;
        const table = $('holdings-table');
        const showState = this.intraday.enabled && this.regularSession;
        if (table.classList.contains('holdings-state') !== showState) {
            table.classList.toggle('holdings-state', showState);
            this.layout.reset();
        }
        if (table.classList.contains('holdings-regular') !== this.regularSession) {
            table.classList.toggle('holdings-regular', this.regularSession);
            this.layout.reset();
        }
        if (this.regularSession && this.sort === 'extended_percent')
            this.sort = null;
        for (const button of Array.from($('holdings-table').querySelectorAll('[data-holdings-sort]'))) {
            const active = button.dataset.holdingsSort === this.sort;
            button.closest('th').setAttribute('aria-sort', active ? 'descending' : 'none');
            button.title = active ? 'Restore default order' : 'Sort descending';
        }
        $('holdings-count').textContent = data ? String(data.holdings.reduce((n, h) => n + h.sequences.length, 0)) : '';
        this.tick();
        $('holdings-account').textContent = data ? netLiq.format(Number(data.funds.account_total)) : '—';
        $('holdings-account').title = data ? `Latest position value + SnapTrade cash ${money.format(Number(data.funds.cash))}` : '';
        $('holdings-empty').hidden = !!data?.holdings.length;
        $('holdings-empty').textContent = data ? 'No holdings' : this.data?.error ? 'Holdings unavailable' : 'Loading…';
        const structure = JSON.stringify([data?.holdings.map(h => [h.ticker, h.sequences.map(s => [s.buy_ids, s.opened_on, s.closed_today, s.is_new, s.sold_percent, s.buys, s.sells])]), [...this.expanded]]);
        if (structure !== this.structure) {
            this.structure = structure;
            this.rows.clear();
            this.groups.clear();
            this.order = '';
            this.layout.invalidate();
            const body = document.createDocumentFragment();
            for (const holding of data?.holdings ?? []) {
                for (const sequence of holding.sequences) {
                    const key = sequence.buy_ids.join(':'), row = document.createElement('tr');
                    row.dataset.holding = key;
                    row.tabIndex = 0;
                    row.classList.toggle('holding-closed', sequence.closed_today);
                    row.setAttribute('aria-label', `Select ${holding.ticker}, bought ${sequence.opened_on}`);
                    const label = this.cell(row, '');
                    const toggle = document.createElement('button');
                    toggle.className = 'holdings-trades';
                    toggle.textContent = this.expanded.has(key) ? '▾' : '▸';
                    toggle.dataset.trades = key;
                    toggle.hidden = Number(sequence.sold_percent) === 0;
                    toggle.setAttribute('aria-expanded', String(this.expanded.has(key)));
                    toggle.setAttribute('aria-label', `Toggle ${holding.ticker} trades`);
                    const name = document.createElement('span');
                    name.className = 'ticker';
                    name.textContent = holding.ticker;
                    label.append(toggle, name);
                    if (sequence.is_new) {
                        const flag = document.createElement('span');
                        flag.className = 'symbol-flag new';
                        flag.textContent = 'NEW';
                        label.append(flag);
                    }
                    for (let column = 1; column < 12; column++)
                        this.cell(row, '');
                    symbolRow(row, label);
                    body.append(row);
                    this.rows.set(key, row);
                    const group = [row];
                    this.groups.set(key, group);
                    if (this.expanded.has(key) && Number(sequence.sold_percent) > 0) {
                        for (const trade of [...sequence.buys, ...sequence.sells]) {
                            const sale = 'pnl' in trade ? trade : null;
                            const detail = document.createElement('tr');
                            detail.className = 'holding-trade';
                            detail.dataset.holding = key;
                            detail.classList.toggle('holding-closed', sequence.closed_today);
                            this.cell(detail, sale ? 'Sold' : 'Buy');
                            this.cell(detail, trade.date);
                            this.cell(detail, sale ? String(sale.holding_days) : '');
                            this.cell(detail, sale ? signed(sale.pnl_percent, true) : '').className = sale ? pnlClass(sale.pnl_percent) : '';
                            this.cell(detail, sale ? signed(sale.pnl) : '').className = sale ? pnlClass(sale.pnl) : '';
                            this.cell(detail, quantity.format(Number(trade.quantity)));
                            this.cell(detail, money.format(Number(trade.value) / Number(trade.quantity)));
                            this.cell(detail, '');
                            this.cell(detail, '');
                            for (let column = 0; column < 3; column++)
                                this.cell(detail, '');
                            body.append(detail);
                            group.push(detail);
                        }
                    }
                }
            }
            $('holdings-rows').replaceChildren(body);
        }
        for (const holding of data?.holdings ?? [])
            for (const sequence of holding.sequences) {
                const key = sequence.buy_ids.join(':'), row = this.rows.get(key);
                const state = showState && !sequence.closed_today ? this.intraday.symbols[symbolFor(holding.ticker)] : undefined;
                stateAppearance(row, state);
                attentionAppearance(row, sequence.closed_today ? '' : symbolFor(holding.ticker), this.attention);
                row.cells[9].textContent = adrText(state);
                row.cells[9].title = adrTitle(state);
                volumeBadge(row.cells[10], state?.cum_vol);
                volumeBadge(row.cells[11], state?.local_vol);
                row.classList.toggle('active', key === this.selected);
                row.setAttribute('aria-selected', String(key === this.selected));
                this.value(row.cells[1], netLiq.format(Number(sequence.market_value)));
                const priceTime = new Date(typeof holding.price_timestamp === 'number' ? holding.price_timestamp * 1000 : holding.price_timestamp).toLocaleString('en-GB');
                const session = holding.price_session === 'Intraday' ? 'Regular' : holding.price_session;
                row.cells[1].title = sequence.closed_today ? 'Closed today · no remaining position' :
                    `${holding.price_source === 'longbridge' ? 'Longbridge' : 'SnapTrade fallback'}${session ? ' · ' + session : ''} · ${priceTime}`;
                this.value(row.cells[2], String(sequence.holding_days));
                this.value(row.cells[3], signed(sequence.total_pnl_percent, true));
                row.cells[3].className = pnlClass(sequence.total_pnl_percent);
                this.value(row.cells[4], signed(sequence.total_pnl));
                row.cells[4].className = pnlClass(sequence.total_pnl);
                const sold = Number(sequence.sold_percent), soldText = soldPercent.format(sold);
                this.value(row.cells[5], sold === 0 ? '' : soldText === '0' ? '<1%' : `${soldText}%`);
                for (const [index, value, percent, empty] of [[6, holding.change_percent, true, '—'], [7, holding.extended_percent, true, ''], [8, sequence.day_pnl, false, '—']]) {
                    this.value(row.cells[index], value == null ? empty : signed(value, percent, index === 7));
                    row.cells[index].className = value == null ? '' : pnlClass(value);
                }
                row.cells[7].title = holding.extended_percent != null ? `${session}: change from regular close` : '';
                const basis = sequence.day_reference_source === 'entry' ? 'entry price' :
                    sequence.day_reference_source === 'mixed' ? 'weighted entry / previous regular close' : 'previous regular close';
                row.cells[8].title = sequence.day_reference_price != null ?
                    `${sequence.closed_today ? 'Realized today' : quantity.format(Number(sequence.held_quantity)) + ' remaining shares'} · ${basis} ${money.format(Number(sequence.day_reference_price))} · ${session ?? ''} · ${priceTime}` : 'Daily P/L unavailable: missing price or previous regular close';
            }
        $('holdings-total-value').textContent = data ? netLiq.format(Number(data.funds.stock_market_value)) : '—';
        $('holdings-total-pnl').textContent = data ? signed(data.summary.pnl) : '—';
        $('holdings-total-pnl').className = data ? pnlClass(data.summary.pnl) : '';
        $('holdings-total-percent').textContent = data?.summary.pnl_percent != null ? signed(data.summary.pnl_percent, true) : '—';
        $('holdings-total-percent').className = data?.summary.pnl_percent != null ? pnlClass(data.summary.pnl_percent) : '';
        $('holdings-total-day').textContent = data?.summary.day_pnl != null ? signed(data.summary.day_pnl) : '—';
        $('holdings-total-day').className = data?.summary.day_pnl != null ? pnlClass(data.summary.day_pnl) : '';
        const ordered = this.ordered();
        const order = JSON.stringify(ordered.map(({ sequence }) => sequence.buy_ids.join(':')));
        if (order !== this.order) {
            this.order = order;
            const focused = document.activeElement;
            const focusKey = focused?.closest('[data-holding]')?.dataset.holding;
            const tradesFocus = focused?.hasAttribute('data-trades');
            const body = document.createDocumentFragment(), rows = new Map();
            for (const { sequence } of ordered) {
                const key = sequence.buy_ids.join(':');
                for (const row of this.groups.get(key))
                    body.append(row);
                rows.set(key, this.rows.get(key));
            }
            $('holdings-rows').replaceChildren(body);
            this.rows = rows;
            const row = focusKey ? this.rows.get(focusKey) : null;
            if (row)
                (tradesFocus ? row.querySelector('[data-trades]') : row).focus({ preventScroll: true });
        }
        if (!this.data) {
            this.layout.reset();
            this.onWidth(260);
        }
        else if (data)
            this.layout.measure();
    }
}

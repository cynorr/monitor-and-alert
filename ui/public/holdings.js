import { $ } from './types.js';
const money = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const percentage = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const netLiq = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const quantity = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 });
const soldPercent = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const signed = (value, percent = false, extended = false) => `${Number(value) > 0 ? '+' : ''}${(percent ? extended ? money : percentage : netLiq).format(Number(value))}${percent ? '%' : ''}`;
const pnlClass = (value) => Number(value) > 0 ? 'positive' : Number(value) < 0 ? 'negative' : '';
const symbolFor = (ticker) => ticker.endsWith('.US') ? ticker : ticker + '.US';
export function sortedHoldingRows(holdings, sort) {
    const rows = holdings.flatMap(holding => holding.sequences.map(sequence => ({ holding, sequence })));
    if (!sort)
        return rows;
    const value = ({ holding, sequence }) => {
        if (sort === 'symbol')
            return holding.ticker;
        return sort === 'change_percent' || sort === 'extended_percent' ? holding[sort] : sequence[sort];
    };
    return rows.sort((a, b) => {
        const left = value(a), right = value(b);
        if (sort === 'symbol')
            return String(right).localeCompare(String(left), 'en');
        const x = left == null ? null : Number(left), y = right == null ? null : Number(right);
        const missingX = x == null || !Number.isFinite(x), missingY = y == null || !Number.isFinite(y);
        return missingX ? (missingY ? 0 : 1) : missingY ? -1 : y - x;
    });
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
    widthSignature = '';
    minimumWidth = 0;
    collapsed = false;
    regularSession = false;
    constructor(onSelect, isActive, onWidth) {
        this.onSelect = onSelect;
        this.isActive = isActive;
        this.onWidth = onWidth;
        try {
            this.collapsed = localStorage.getItem('holdings-collapsed') === 'true';
        }
        catch { /* Optional storage. */ }
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
            if (this.collapsed || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey ||
                event.target.closest('input,textarea,select,[contenteditable="true"]'))
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
        const first = sortedHoldingRows(this.data?.data?.holdings ?? [], this.sort)[0];
        return first ? { symbol: symbolFor(first.holding.ticker), key: first.sequence.buy_ids.join(':') } : null;
    }
    update(state, regularSession) {
        this.data = state;
        if (regularSession !== undefined)
            this.regularSession = regularSession;
        this.render();
    }
    setRegularSession(regularSession) {
        if (this.regularSession === regularSession)
            return;
        this.regularSession = regularSession;
        this.render();
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
        $('holdings-toggle').setAttribute('aria-expanded', String(!this.collapsed));
        $('holdings-arrow').textContent = this.collapsed ? '▸' : '▾';
        const data = this.data?.data;
        const table = $('holdings-table');
        if (table.classList.contains('holdings-regular') !== this.regularSession) {
            table.classList.toggle('holdings-regular', this.regularSession);
            this.minimumWidth = 0;
            this.widthSignature = '';
        }
        if (this.regularSession && this.sort === 'extended_percent')
            this.sort = null;
        for (const button of Array.from($('holdings-table').querySelectorAll('[data-holdings-sort]'))) {
            const active = button.dataset.holdingsSort === this.sort;
            button.closest('th').setAttribute('aria-sort', active ? 'descending' : 'none');
            button.title = active ? 'Restore default order' : 'Sort descending';
        }
        $('holdings-count').textContent = data ? String(data.holdings.reduce((n, h) => n + h.sequences.length, 0)) : '';
        $('holdings-updated').textContent = this.data?.error ? 'Refresh failed' : this.data?.loading ? 'Loading…' :
            data ? new Date(data.fetched_at).toLocaleTimeString('en-GB', { hour12: false }) : '';
        $('holdings-updated').title = this.data?.error ?? (data ? `Positions as of ${data.positions_as_of}` : '');
        $('holdings-updated').classList.toggle('negative', !!this.data?.error);
        $('holdings-account').textContent = data ? money.format(Number(data.funds.account_total)) : '—';
        $('holdings-account').title = data ? `Latest position value + SnapTrade cash ${money.format(Number(data.funds.cash))}` : '';
        $('holdings-empty').hidden = !!data?.holdings.length;
        $('holdings-empty').textContent = data ? 'No holdings' : this.data?.error ? 'Holdings unavailable' : 'Loading…';
        const structure = JSON.stringify([data?.holdings.map(h => [h.ticker, h.sequences.map(s => [s.buy_ids, s.opened_on, s.sold_percent, s.buys, s.sells])]), [...this.expanded]]);
        if (structure !== this.structure) {
            this.structure = structure;
            this.rows.clear();
            this.groups.clear();
            this.order = '';
            this.widthSignature = '';
            const body = document.createDocumentFragment();
            for (const holding of data?.holdings ?? []) {
                for (const sequence of holding.sequences) {
                    const key = sequence.buy_ids.join(':'), row = document.createElement('tr');
                    row.dataset.holding = key;
                    row.tabIndex = 0;
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
                    for (let column = 1; column < 9; column++)
                        this.cell(row, '');
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
                            this.cell(detail, sale ? 'Sold' : 'Buy');
                            this.cell(detail, trade.date);
                            this.cell(detail, sale ? String(sale.holding_days) : '');
                            this.cell(detail, sale ? signed(sale.pnl_percent, true) : '').className = sale ? pnlClass(sale.pnl_percent) : '';
                            this.cell(detail, sale ? signed(sale.pnl) : '').className = sale ? pnlClass(sale.pnl) : '';
                            this.cell(detail, quantity.format(Number(trade.quantity)));
                            this.cell(detail, money.format(Number(trade.value) / Number(trade.quantity)));
                            this.cell(detail, '');
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
                row.classList.toggle('active', key === this.selected);
                row.setAttribute('aria-selected', String(key === this.selected));
                this.value(row.cells[1], netLiq.format(Number(sequence.market_value)));
                const priceTime = new Date(typeof holding.price_timestamp === 'number' ? holding.price_timestamp * 1000 : holding.price_timestamp).toLocaleString('en-GB');
                const session = holding.price_session === 'Intraday' ? 'Regular' : holding.price_session;
                row.cells[1].title = `${holding.price_source === 'longbridge' ? 'Longbridge' : 'SnapTrade fallback'}${session ? ' · ' + session : ''} · ${priceTime}`;
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
                row.cells[8].title = holding.day_reference_price != null ?
                    `${quantity.format(Number(sequence.held_quantity))} shares × (latest price − ${money.format(Number(holding.day_reference_price))} previous regular close) · ${session} · ${priceTime}` : 'Daily P/L unavailable: missing Longbridge price or previous regular close';
            }
        $('holdings-total-value').textContent = data ? netLiq.format(Number(data.funds.stock_market_value)) : '—';
        $('holdings-total-pnl').textContent = data ? signed(data.summary.pnl) : '—';
        $('holdings-total-pnl').className = data ? pnlClass(data.summary.pnl) : '';
        $('holdings-total-percent').textContent = data?.summary.pnl_percent != null ? signed(data.summary.pnl_percent, true) : '—';
        $('holdings-total-percent').className = data?.summary.pnl_percent != null ? pnlClass(data.summary.pnl_percent) : '';
        $('holdings-total-day').textContent = data?.summary.day_pnl != null ? signed(data.summary.day_pnl) : '—';
        $('holdings-total-day').className = data?.summary.day_pnl != null ? pnlClass(data.summary.day_pnl) : '';
        const ordered = sortedHoldingRows(data?.holdings ?? [], this.sort);
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
            this.minimumWidth = 0;
            this.onWidth(260);
        }
        else if (data)
            this.measureWidth();
    }
    measureWidth() {
        const table = $('holdings-table');
        // Numeric fonts are tabular: measure again only when content gains digits
        // or the row structure changes, rather than cloning on each quote update.
        const lengths = Array.from({ length: table.tHead.rows[0].cells.length }, (_, index) => Math.max(0, ...Array.from(table.rows, row => {
            const cell = row.cells[index];
            return cell && getComputedStyle(cell).display !== 'none' ? Math.max(...Array.from(cell.childNodes, node => node.textContent?.length ?? 0)) : 0;
        })));
        const signature = JSON.stringify(lengths);
        if (signature !== this.widthSignature) {
            this.widthSignature = signature;
            const copy = table.cloneNode(true);
            copy.removeAttribute('id');
            copy.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
            copy.classList.add('holdings-measure');
            copy.setAttribute('aria-hidden', 'true');
            document.body.append(copy);
            const intrinsic = Math.ceil(copy.getBoundingClientRect().width);
            copy.remove();
            const scroll = table.closest('.holdings-scroll');
            this.minimumWidth = Math.max(this.minimumWidth, intrinsic + 18 + scroll.offsetWidth - scroll.clientWidth);
        }
        this.onWidth(this.minimumWidth);
    }
}

import { $, money } from './types.js';
import { adjacentSymbol, listCells, listHeader, listMinimumWidth, revealSymbolRow, setListColumns, symbolRow, updateSymbolRow, type ListColumn } from './symbol-row.js';
import { attentionState, autoAlertButton } from './attention.js';
import { compareRank, type IntradayState } from './intraday-state.js';
import { numeric, openPercent, entryAmount, holdingTag, holdingDetails, type SchwabState, type AccountRow, type Position, type HoldingDetail } from './schwab-data.js';

export function orderedAccountRows(rows: AccountRow[], sort: string, intraday: IntradayState) {
    const kind = { entry: 0, holding: 1, order: 2, sold: 3 };
    const value = (r: AccountRow) => sort === 'symbol' ? r.ticker : sort === 'percent' ? openPercent(r.position) : sort === 'holding_days' ? r.days_over_year ? Infinity : r.holding_days : numeric(sort in r ? r[sort as 'change_percent'] : r.position?.[sort as keyof Position]);
    return [...rows].sort((a, b) => {
        if (kind[a.kind] !== kind[b.kind]) return kind[a.kind] - kind[b.kind];
        if (a.kind === 'sold') return 0;
        const rank = a.kind === 'holding' ? compareRank(intraday.symbols[a.symbol], intraday.symbols[b.symbol]) : 0;
        if (rank || !sort) return rank;
        const x = value(a), y = value(b);
        return sort === 'symbol' ? String(y).localeCompare(String(x)) : x == null ? y == null ? 0 : 1 : y == null ? -1 : Number(y) - Number(x);
    });
}
const columns = [
    { field: 'symbol', label: 'Symbol', width: 'max-content' },
    { field: 'sold_percent', label: '', width: 'max-content' },
    { field: 'market_value', label: 'Net Liq', width: 'max-content' },
    { field: 'holding_days', label: 'Days', width: 'max-content' },
    { field: 'percent', label: 'P/L %', width: 'max-content' },
    { field: 'open_profit_loss', label: 'P/L', width: 'max-content' },
    { field: 'change_percent', label: 'Chg%', width: 'max-content' },
    { field: 'extended_percent', label: 'Ext', width: 'max-content' },
    { field: 'day_profit_loss', label: 'P/L Day', width: 'max-content' },
    { field: 'state-adr', label: 'ADR', width: 'max-content' },
    { field: 'cum-vol', label: 'CumVol', width: 'max-content' },
    { field: 'local-vol', label: 'LocalVol', width: 'max-content' },
    { field: 'actions', label: '', width: 'minmax(calc(var(--row-action-size) + var(--row-action-end-gap)), 1fr)' },
] as const satisfies readonly ListColumn[];
type HoldingField = typeof columns[number]['field'];
type HoldingCells = Record<HoldingField, HTMLElement>;
type HoldingRow = { row: HTMLElement; cells: HoldingCells };

export function holdingsColumns(regular: boolean, intraday: boolean) {
    return columns.filter(({ field }) =>
        field === 'extended_percent' ? !regular :
        ['state-adr', 'cum-vol', 'local-vol'].includes(field) ? regular && intraday : true);
}

const detailFields = {
    qty: 'sold_percent', amount: 'market_value', days: 'holding_days', pnlPercent: 'percent',
    pnl: 'open_profit_loss', price: 'change_percent',
} as const;
const integer = (value: number | null) => value?.toLocaleString('en-US', { maximumFractionDigits: 0 }) ?? '';
const formatted = (v: number | null, percent = false) => v == null ? '' : `${v > 0 ? '+' : ''}${v.toLocaleString('en-US', { maximumFractionDigits: percent ? 1 : 0, minimumFractionDigits: percent ? 1 : 0 })}${percent ? '%' : ''}`;
const monitorsIntraday = (row: AccountRow) => row.kind === 'holding' || row.kind === 'entry';

export class SchwabHoldings {
    selected = '';
    attention = attentionState();
    private data: SchwabState | null = null;
    private states: IntradayState = { enabled: false, symbols: {} };
    private regular = false;
    private expanded = new Set<string>();
    private collapsed = false;
    private sort = '';
    private nodes = new Map<string, HoldingRow>();
    private details = new Map<string, HoldingRow>();
    private order = '';
    private visibleFields = new Set<HoldingField>();
    private minimumWidth = 0;
    private widthSignature = '';
    private readonly grid = $('schwab-grid');
    private readonly body = $('schwab-rows');
    private readonly total = listCells($('schwab-total'), columns, true);
    private get stateVisible() { return this.regular && this.states.enabled; }
    private ordered() { return orderedAccountRows(this.data?.rows ?? [], this.sort, this.regular && this.states.enabled ? this.states : { enabled: false, symbols: {} }); }
    constructor(private select: (symbol: string, key: string) => void, private active: () => boolean,
                private cancel: (id: string) => void, private width: (value: number) => void,
                private toggleAutoPause: (symbol: string) => void) {
        try { this.collapsed = localStorage.getItem('schwab-holdings-collapsed') === 'true'; } catch { }
        $('schwab-toggle').onclick = () => { this.collapsed = !this.collapsed; try { localStorage.setItem('schwab-holdings-collapsed', String(this.collapsed)); } catch { } this.render(); };
        this.total.symbol.textContent = 'Total';
        this.total.day_profit_loss.title = 'Schwab current-position day P/L; excludes realized sales';
        document.addEventListener('keydown', event => {
            if (!this.active() || this.collapsed || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey ||
                event.isComposing || (event.target as HTMLElement).closest('input,textarea,select,button:not(.ticker),[contenteditable]')) return;
            if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
            const next = adjacentSymbol(this.ordered().map(row => row.symbol), this.selected, event.key === 'ArrowDown' ? 1 : -1);
            if (!next) return;
            event.preventDefault();
            this.selectRow(next, true);
        });
    }
    has(key: string) { return this.data?.rows.some(r => r.symbol === key) ?? false; }
    canPause(symbol: string) {
        return this.attention.eligible.has(symbol) && this.data?.rows.some(row => row.symbol === symbol && monitorsIntraday(row));
    }
    first() { const row = this.ordered()[0]; return row ? { symbol: row.symbol, key: row.symbol } : null; }
    jumpUnread() {
        const row = this.ordered().find(r => monitorsIntraday(r) && this.attention.unread.has(r.symbol));
        if (row) {
            this.collapsed = false;
            this.select(row.symbol, row.symbol);
            this.render();
            revealSymbolRow(this.nodes.get(row.symbol)?.row);
        }
    }
    update(data: SchwabState | null, regular: boolean, states?: IntradayState) {
        this.data = data; this.regular = regular; this.states = states ?? { enabled: false, symbols: {} }; this.render();
    }
    tick() {
        const time = this.data?.account_updated_at, node = $('schwab-updated');
        node.hidden = !!time && Date.now() - Date.parse(time) < 60_000;
        node.textContent = time ? new Date(time).toLocaleTimeString('en-GB', { hour12: false }) : 'Loading…';
        node.title = `Schwab account ${time ?? 'not initialized'} · orders ${this.data?.orders_updated_at ?? 'not initialized'}`;
    }
    private selectRow(symbol: string, scroll = false) {
        this.select(symbol, symbol);
        revealSymbolRow(this.nodes.get(symbol)?.row, scroll);
    }

    private showFields(cells: HoldingCells) {
        for (const { field } of columns) cells[field].hidden = !this.visibleFields.has(field);
    }

    private renderColumns() {
        const visible = holdingsColumns(this.regular, this.stateVisible);
        if (visible.length === this.visibleFields.size && visible.every(({ field }) => this.visibleFields.has(field))) return;
        this.visibleFields = new Set(visible.map(({ field }) => field));
        setListColumns(this.grid, visible, this.stateVisible ? 'cum-vol' : 'actions');
        listHeader($('schwab-head'), visible, (cell, { field, label }) => {
            cell.setAttribute('role', 'columnheader');
            if (['state-adr', 'cum-vol', 'local-vol', 'actions'].includes(field)) return;
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = label;
            button.setAttribute('aria-label', label || 'Sold percentage');
            button.onclick = () => { this.sort = this.sort === field ? '' : field; this.render(); };
            cell.replaceChildren(button);
        });
        this.showFields(this.total);
        for (const { cells } of this.nodes.values()) this.showFields(cells);
        for (const { cells } of this.details.values()) this.showFields(cells);
        this.minimumWidth = 0;
        this.widthSignature = '';
    }

    private measureWidth() {
        if (this.collapsed) return;
        const signature = Array.from(this.grid.querySelectorAll<HTMLElement>('[data-field]:not([hidden])'),
            cell => cell.textContent?.length ?? 0).join(',');
        if (signature === this.widthSignature) return;
        this.widthSignature = signature;
        this.minimumWidth = Math.max(this.minimumWidth, listMinimumWidth(this.grid));
        this.width(this.minimumWidth);
    }

    private mainRow(item: AccountRow) {
        const existing = this.nodes.get(item.symbol);
        if (existing) return existing;
        const { row, cells } = symbolRow(item.ticker, columns, 'cum-vol', true);
        row.dataset.holding = item.symbol;
        this.showFields(cells);
        const toggle = document.createElement('button'); toggle.className = 'holdings-trades';
        toggle.type = 'button';
        toggle.onclick = event => { event.stopPropagation(); this.expanded.has(item.symbol) ? this.expanded.delete(item.symbol) : this.expanded.add(item.symbol); this.render(); };
        const tag = document.createElement('small'); tag.className = 'symbol-flag holding-tag'; tag.hidden = true;
        cells.symbol.prepend(toggle); cells.symbol.append(tag);
        cells.actions.classList.add('row-actions');
        cells.actions.append(autoAlertButton(item.symbol, this.toggleAutoPause));
        row.onclick = () => this.selectRow(item.symbol);
        const entry = { row, cells };
        this.nodes.set(item.symbol, entry); return entry;
    }
    private detailRow(symbol: string, value: HoldingDetail, closed: boolean) {
        const key = symbol + '/' + value.key;
        let entry = this.details.get(key);
        if (!entry) {
            const row = document.createElement('div'); row.className = 'list-grid-row holding-trade'; row.dataset.detail = key;
            const cells = listCells(row, columns, true);
            this.showFields(cells);
            entry = { row, cells };
            this.details.set(key, entry);
            const label = cells.symbol; label.className = 'holding-detail-label';
            const stem = document.createElement('span'); stem.className = 'holding-detail-outgoing'; stem.setAttribute('aria-hidden', 'true');
            const node = document.createElement('span'); node.className = 'holding-detail-node'; node.setAttribute('aria-hidden', 'true');
            const kind = document.createElement('span'); kind.dataset.part = 'kind';
            label.append(stem, node, kind);
            for (const [part, field] of Object.entries(detailFields)) cells[field].dataset.part = part;
            const cancel = document.createElement('button'); cancel.className = 'icon-button holding-cancel'; cancel.type = 'button';
            cancel.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
            const date = document.createElement('time'); date.dataset.part = 'date';
            cells.day_profit_loss.append(cancel, date);
        }
        const { row, cells } = entry;
        row.classList.toggle('holding-closed', closed);
        const history = value.kind === 'Buy' || value.kind === 'Sold';
        row.classList.toggle('holding-history', history); row.dataset.detailKind = value.kind;
        const values = { kind: value.kind, date: value.date ?? '', days: value.days == null ? '' : String(value.days), qty: value.qty.toLocaleString('en-US', { maximumFractionDigits: 6 }), price: value.price == null ? '' : money(value.price), amount: integer(value.amount), pnlPercent: formatted(value.pnlPercent, true), pnl: formatted(value.pnl) };
        const estimate = value.kind === 'Stop' ? 'Estimated P/L at stop' : '';
        const titles = { kind: '', date: '', days: '', qty: 'Quantity', price: value.kind === 'Stop' ? 'Stop price' : 'Price', amount: value.kind === 'Buy' ? 'Cost' : 'Value', pnlPercent: estimate, pnl: estimate };
        row.querySelectorAll<HTMLElement>('[data-part]').forEach(span => {
            const part = span.dataset.part as keyof typeof values; span.textContent = values[part]; span.title = titles[part];
            if (part === 'pnl' || part === 'pnlPercent') { const pnl = value[part]; span.classList.toggle('positive', pnl != null && pnl > 0); span.classList.toggle('negative', pnl != null && pnl < 0); }
        });
        const date = row.querySelector<HTMLTimeElement>('[data-part="date"]')!;
        date.hidden = !value.date; date.dateTime = value.date ?? '';
        const cancel = row.querySelector<HTMLButtonElement>('button')!;
        const cancelCell = cells[this.regular ? 'day_profit_loss' : 'extended_percent'];
        if (cancel.parentElement !== cancelCell) cancelCell.prepend(cancel);
        cancel.hidden = !value.cancelId; cancel.setAttribute('aria-label', `Cancel ${value.kind.toLowerCase()} order for ${symbol.replace('.US', '')}`); cancel.title = 'Cancel order';
        cancel.onclick = event => { event.stopPropagation(); if (value.cancelId) this.cancel(value.cancelId); };
        return row;
    }
    render() {
        $('schwab-holdings').hidden = !this.data;
        if (!this.data) {
            this.minimumWidth = 0;
            this.widthSignature = '';
            this.width(0);
            return;
        }
        this.renderColumns();
        $('schwab-content').hidden = this.collapsed;
        $('schwab-toggle').setAttribute('aria-expanded', String(!this.collapsed)); $('schwab-arrow').textContent = this.collapsed ? '▸' : '▾';
        $('schwab-count').textContent = String(this.data.rows.length);
        const account = this.data.account, buyingPower = numeric(account?.stock_buying_power), funds = numeric(account?.available_funds);
        $('schwab-account').textContent = integer(numeric(account?.liquidation_value));
        $('schwab-account').title = ['Schwab liquidationValue', buyingPower != null && 'Stock BP ' + money(buyingPower),
            funds != null && 'Available ' + money(funds)].filter(Boolean).join(' · ');
        this.tick();
        if (this.regular && this.sort === 'extended_percent') this.sort = '';
        $('schwab-head').querySelectorAll<HTMLElement>('[data-field]').forEach(cell => {
            if (cell.dataset.field === this.sort) cell.setAttribute('aria-sort', 'descending');
            else cell.removeAttribute('aria-sort');
        });
        const desired: HTMLElement[] = [], keep = new Set<string>(), detailKeys = new Set<string>();
        for (const item of this.ordered()) {
            keep.add(item.symbol);
            const { row, cells } = this.mainRow(item), detail = holdingDetails(item);
            row.dataset.holdingKind = item.kind;
            row.classList.toggle('holding-closed', item.kind === 'sold');
            const toggle = cells.symbol.querySelector<HTMLButtonElement>('.holdings-trades')!;
            toggle.hidden = !detail.length; toggle.textContent = this.expanded.has(item.symbol) ? '▾' : '▸'; toggle.setAttribute('aria-label', `Toggle ${item.ticker} details`); toggle.setAttribute('aria-expanded', String(this.expanded.has(item.symbol)));
            const tag = row.querySelector<HTMLElement>('.holding-tag')!, nextTag = holdingTag(item);
            if (tag.textContent !== nextTag) tag.textContent = nextTag;
            tag.hidden = !nextTag;
            const p = item.position, value = p ? numeric(p.market_value) : item.kind === 'entry' ? entryAmount(item) : item.kind === 'sold' ? 0 : null;
            cells.market_value.textContent = integer(value);
            cells.market_value.title = item.kind === 'entry' ? 'Entry value' : 'Schwab account snapshot';
            const values = {
                percent: openPercent(p), open_profit_loss: numeric(p?.open_profit_loss), change_percent: numeric(item.change_percent),
                extended_percent: numeric(item.extended_percent), day_profit_loss: numeric(p?.day_profit_loss),
            };
            for (const field of Object.keys(values) as (keyof typeof values)[]) {
                const cell = cells[field], number = values[field];
                const fromQuote = field === 'change_percent' || field === 'extended_percent';
                cell.textContent = formatted(number, field === 'percent' || fromQuote);
                cell.classList.toggle('positive', number != null && number > 0);
                cell.classList.toggle('negative', number != null && number < 0);
                cell.title = fromQuote ? 'Longbridge quote' : 'Schwab account snapshot';
            }
            cells.holding_days.textContent = item.days_over_year ? '>1y' : item.holding_days == null ? '' : String(item.holding_days);
            const sold = numeric(item.sold_percent);
            cells.sold_percent.textContent = sold == null || sold === 0 ? '' : sold < .5 ? '<1%' : Math.round(sold) + '%';
            const monitored = monitorsIntraday(item);
            const state = this.regular && monitored ? this.states.symbols[item.symbol] : undefined;
            updateSymbolRow(row, monitored ? item.symbol : '', item.symbol === this.selected, state, this.attention);
            desired.push(row);
            if (this.expanded.has(item.symbol)) {
                for (const value of detail) {
                    const child = this.detailRow(item.symbol, value, item.kind === 'sold');
                    desired.push(child); detailKeys.add(child.dataset.detail!);
                }
            }
        }
        for (const key of this.nodes.keys()) if (!keep.has(key)) { this.nodes.delete(key); this.expanded.delete(key); }
        for (const key of this.details.keys()) if (!detailKeys.has(key)) this.details.delete(key);
        const order = desired.map(row => row.dataset.detail ?? row.dataset.holding).join('|');
        if (order !== this.order) { const focused = document.activeElement as HTMLElement | null; this.body.replaceChildren(...desired); this.order = order; if (focused && this.body.contains(focused)) focused.focus({ preventScroll: true }); }
        $('schwab-empty').hidden = this.data.rows.length > 0; $('schwab-empty').textContent = this.data.account ? 'No holdings or orders' : 'Waiting for Schwab account';
        const positions = this.data.rows.flatMap(row => row.position ? [row.position] : []);
        const sum = (field: keyof Position) => { if (!this.data?.account) return null; const values = positions.map(position => numeric(position[field])); return values.every(value => value != null) ? values.reduce<number>((sum, value) => sum + value!, 0) : null; };
        const costs = positions.map(position => numeric(position.quantity) != null && numeric(position.average_price) != null ? Number(position.quantity) * Number(position.average_price) : null);
        const cost = costs.every(value => value != null) ? costs.reduce<number>((sum, value) => sum + value!, 0) : null, pnl = sum('open_profit_loss');
        this.total.market_value.textContent = integer(sum('market_value')); this.total.open_profit_loss.textContent = formatted(pnl);
        this.total.percent.textContent = formatted(pnl != null && cost && cost > 0 ? pnl / cost * 100 : null, true);
        this.total.day_profit_loss.textContent = formatted(sum('day_profit_loss'));
        this.measureWidth();
    }
}

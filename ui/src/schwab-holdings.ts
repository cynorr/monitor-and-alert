import { $, money } from './types.js';
import { symbolRow } from './symbol-row.js';
import { attentionState, attentionAppearance } from './attention.js';
import { adrText, adrTitle, compareRank, stateAppearance, volumeBadge, type IntradayState } from './intraday-state.js';
import { HoldingsLayout } from './holdings-layout.js';
import { numeric, openPercent, entryAmount, holdingTags, holdingDetails, type TradeState, type TradeRow, type Position, type HoldingDetail } from './schwab-data.js';

export function orderedTradeRows(rows: TradeRow[], sort: string, intraday: IntradayState) {
    const kind = { entry: 0, holding: 1, order: 2, sold: 3 };
    const value = (r: TradeRow) => sort === 'symbol' ? r.ticker : sort === 'percent' ? openPercent(r.position) : numeric(sort in r ? r[sort as 'change_percent'] : r.position?.[sort as keyof Position]);
    return [...rows].sort((a, b) => {
        if (kind[a.kind] !== kind[b.kind]) return kind[a.kind] - kind[b.kind];
        if (a.kind === 'sold') return 0;
        const rank = compareRank(intraday.symbols[a.symbol], intraday.symbols[b.symbol]);
        if (rank || !sort) return rank;
        const x = value(a), y = value(b);
        return sort === 'symbol' ? String(y).localeCompare(String(x)) : x == null ? y == null ? 0 : 1 : y == null ? -1 : Number(y) - Number(x);
    });
}
const fields = ['symbol', 'market_value', 'percent', 'open_profit_loss', 'change_percent', 'extended_percent', 'day_profit_loss', 'adr', 'cum', 'local'];
const labels = ['Symbol', 'Net Liq', 'P/L %', 'P/L', 'Chg%', 'Ext', 'P/L Day', 'ADR', 'CumVol', 'LocalVol'];
const integer = (value: number | null) => value?.toLocaleString('en-US', { maximumFractionDigits: 0 }) ?? '';
const formatted = (v: number | null, percent = false) => v == null ? '—' : `${v > 0 ? '+' : ''}${v.toLocaleString('en-US', { maximumFractionDigits: percent ? 1 : 0, minimumFractionDigits: percent ? 1 : 0 })}${percent ? '%' : ''}`;

export class SchwabHoldings {
    selected = '';
    attention = attentionState();
    private data: TradeState | null = null;
    private states: IntradayState = { enabled: false, symbols: {} };
    private regular = false;
    private expanded = new Set<string>();
    private collapsed = false;
    private sort = '';
    private nodes = new Map<string, HTMLTableRowElement>();
    private details = new Map<string, HTMLTableRowElement>();
    private order = '';
    private layout: HoldingsLayout;
    private ordered() { return orderedTradeRows(this.data?.rows ?? [], this.sort, this.regular && this.states.enabled ? this.states : { enabled: false, symbols: {} }); }
    constructor(private select: (symbol: string, key: string) => void, private active: () => boolean,
                private cancel: (id: string) => void, width: (value: number) => void) {
        this.layout = new HoldingsLayout($('schwab-table') as HTMLTableElement, () => this.regular && this.states.enabled ? 7 : 6, width);
        try { this.collapsed = localStorage.getItem('schwab-holdings-collapsed') === 'true'; } catch { }
        $('schwab-toggle').onclick = () => { this.collapsed = !this.collapsed; try { localStorage.setItem('schwab-holdings-collapsed', String(this.collapsed)); } catch { } this.render(); };
        const header = $('schwab-head');
        labels.forEach((label, index) => { const th = document.createElement('th'), button = document.createElement('button'); th.dataset.field = fields[index]; button.textContent = label; button.onclick = () => { this.sort = this.sort === fields[index] ? '' : fields[index]; this.render(); }; if (index < 7) th.append(button); else th.textContent = label; header.append(th); });
        document.addEventListener('keydown', event => {
            if (!this.active() || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey || (event.target as HTMLElement).closest('input,textarea,select,button,[contenteditable]')) return;
            if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
            const rows = this.ordered(); if (!rows.length) return;
            const index = Math.max(0, Math.min(rows.length - 1, rows.findIndex(r => r.symbol === this.selected) + (event.key === 'ArrowDown' ? 1 : -1)));
            event.preventDefault(); this.select(rows[index].symbol, rows[index].symbol); this.nodes.get(rows[index].symbol)?.focus();
        });
    }
    has(key: string) { return this.data?.rows.some(r => r.symbol === key) ?? false; }
    first() { const row = this.ordered()[0]; return row ? { symbol: row.symbol, key: row.symbol } : null; }
    jumpUnread() { const row = this.ordered().find(r => r.kind === 'holding' && this.attention.unread.has(r.symbol)); if (row) { this.collapsed = false; this.select(row.symbol, row.symbol); this.render(); } }
    update(data: TradeState | null, regular: boolean, states?: IntradayState) {
        if (this.regular !== regular || this.states.enabled !== !!states?.enabled) this.layout.reset();
        this.data = data; this.regular = regular; this.states = states ?? { enabled: false, symbols: {} }; this.render();
    }
    tick() {
        const time = this.data?.account_updated_at, node = $('schwab-updated');
        node.hidden = !!time && Date.now() - Date.parse(time) < 60_000;
        node.textContent = time ? new Date(time).toLocaleTimeString('en-GB', { hour12: false }) : 'Loading…';
        node.title = `Schwab account ${time ?? 'not initialized'} · orders ${this.data?.orders_updated_at ?? 'not initialized'}`;
    }
    private mainRow(item: TradeRow) {
        let row = this.nodes.get(item.symbol);
        if (row) return row;
        row = document.createElement('tr'); row.tabIndex = 0; row.dataset.holding = item.symbol;
        fields.forEach(field => { const cell = row!.insertCell(); cell.dataset.field = field; }); symbolRow(row, row.cells[0]);
        const toggle = document.createElement('button'); toggle.className = 'holdings-trades';
        toggle.onclick = event => { event.stopPropagation(); this.expanded.has(item.symbol) ? this.expanded.delete(item.symbol) : this.expanded.add(item.symbol); this.render(); };
        const ticker = document.createElement('span'); ticker.className = 'ticker'; ticker.textContent = item.ticker;
        const tags = document.createElement('span'); tags.className = 'holding-tags'; row.cells[0].append(toggle, ticker, tags);
        row.onclick = () => this.select(item.symbol, item.symbol);
        this.nodes.set(item.symbol, row); return row;
    }
    private detailRow(symbol: string, value: HoldingDetail, closed: boolean, columns: number) {
        const key = symbol + '/' + value.key;
        let row = this.details.get(key);
        if (!row) {
            row = document.createElement('tr'); row.className = 'holding-trade'; row.dataset.detail = key;
            this.details.set(key, row);
        }
        if (row.dataset.columns !== String(columns)) {
            row.replaceChildren(); row.dataset.columns = String(columns);
            for (const part of ['kind', 'amount', 'pnlPercent', 'pnl', 'qty']) row.insertCell().dataset.part = part;
            const priceCell = row.insertCell(), price = document.createElement('span'); price.dataset.part = 'price'; priceCell.append(price);
            const cancel = document.createElement('button'); cancel.className = 'icon-button holding-cancel'; cancel.type = 'button';
            cancel.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
            const cancelCell = columns > 6 ? row.insertCell() : priceCell;
            if (cancelCell === priceCell) cancel.classList.add('inline-cancel');
            cancelCell.append(cancel);
            const cell = columns > 7 ? row.insertCell() : cancelCell;
            if (columns > 7) cell.colSpan = columns - 7;
            const line = document.createElement('div'); line.className = 'schwab-detail-values' + (columns <= 7 ? ' inline' : '');
            for (const part of ['stop', 'riskPercent', 'risk']) { const span = document.createElement('span'); span.dataset.part = part; line.append(span); }
            cell.append(line);
        }
        row.classList.toggle('holding-closed', closed);
        const values = { kind: value.kind, qty: value.qty.toLocaleString('en-US', { maximumFractionDigits: 6 }), price: value.price == null ? '' : money(value.price), stop: value.stop == null ? '' : money(value.stop), amount: integer(value.amount), pnlPercent: value.pnlPercent == null ? '' : formatted(value.pnlPercent, true), pnl: value.pnl == null ? '' : formatted(value.pnl), riskPercent: value.riskPercent == null ? '' : value.riskPercent.toFixed(2) + '%', risk: integer(value.risk) };
        const titles = { kind: '', qty: 'Quantity', price: value.kind === 'Buy' ? 'Average cost' : 'Price', stop: 'Stop price', amount: value.kind === 'Buy' ? 'Cost' : 'Value', pnlPercent: '', pnl: '', riskPercent: 'Risk percent', risk: 'Risk amount' };
        row.querySelectorAll<HTMLElement>('[data-part]').forEach(span => {
            const part = span.dataset.part as keyof typeof values; span.textContent = values[part]; span.title = titles[part];
            if (part === 'pnl' || part === 'pnlPercent') { const pnl = value[part]; span.classList.toggle('positive', pnl != null && pnl > 0); span.classList.toggle('negative', pnl != null && pnl < 0); }
        });
        const cancel = row.querySelector<HTMLButtonElement>('button')!;
        cancel.hidden = !value.cancelId; cancel.setAttribute('aria-label', `Cancel ${value.kind.toLowerCase()} order for ${symbol.replace('.US', '')}`); cancel.title = 'Cancel order';
        cancel.onclick = event => { event.stopPropagation(); if (value.cancelId) this.cancel(value.cancelId); };
        return row;
    }
    render() {
        $('schwab-holdings').hidden = !this.data;
        if (!this.data) { this.layout.reset(); return; }
        const table = $('schwab-table') as HTMLTableElement;
        table.dataset.regular = String(this.regular); table.classList.toggle('holdings-state', this.regular && this.states.enabled);
        const columns = Array.from(table.tHead!.rows[0].cells).filter(cell => getComputedStyle(cell).display !== 'none').length;
        $('schwab-content').hidden = this.collapsed;
        $('schwab-toggle').setAttribute('aria-expanded', String(!this.collapsed)); $('schwab-arrow').textContent = this.collapsed ? '▸' : '▾';
        $('schwab-count').textContent = String(this.data.rows.length);
        $('schwab-account').textContent = integer(numeric(this.data.account?.liquidation_value)) || '—';
        $('schwab-account').title = `Schwab liquidationValue · Stock BP ${money(numeric(this.data.account?.stock_buying_power))} · Available ${money(numeric(this.data.account?.available_funds))}`;
        this.tick();
        if (this.regular && this.sort === 'extended_percent') this.sort = '';
        table.querySelectorAll<HTMLElement>('th[data-field]').forEach(th => th.setAttribute('aria-sort', th.dataset.field === this.sort ? 'descending' : 'none'));
        const desired: HTMLTableRowElement[] = [], keep = new Set<string>(), detailKeys = new Set<string>();
        for (const item of this.ordered()) {
            keep.add(item.symbol);
            const row = this.mainRow(item), detail = holdingDetails(item);
            row.classList.toggle('active', item.symbol === this.selected); row.classList.toggle('holding-closed', item.kind === 'sold'); row.setAttribute('aria-selected', String(item.symbol === this.selected));
            const toggle = row.cells[0].querySelector('button')!;
            toggle.hidden = !detail.length; toggle.textContent = this.expanded.has(item.symbol) ? '▾' : '▸'; toggle.setAttribute('aria-label', `Toggle ${item.ticker} details`); toggle.setAttribute('aria-expanded', String(this.expanded.has(item.symbol)));
            const tags = row.querySelector<HTMLElement>('.holding-tags')!, nextTags = holdingTags(item);
            if (tags.textContent !== nextTags.join('')) { tags.replaceChildren(...nextTags.map(tag => { const span = document.createElement('small'); span.className = 'symbol-flag' + (tag === 'Entry' ? ' entry' : ''); span.textContent = tag; return span; })); }
            const p = item.position, value = p ? numeric(p.market_value) : item.kind === 'entry' ? entryAmount(item) : item.kind === 'sold' ? 0 : null;
            const values = [value, openPercent(p), numeric(p?.open_profit_loss), numeric(item.change_percent), numeric(item.extended_percent), numeric(p?.day_profit_loss)];
            values.forEach((value, i) => { const cell = row.cells[i + 1]; cell.textContent = i === 0 ? integer(value) || '—' : formatted(value, [1, 3, 4].includes(i)); cell.className = i > 0 && value != null ? value > 0 ? 'positive' : value < 0 ? 'negative' : '' : ''; cell.title = i === 0 && item.kind === 'entry' ? 'Entry value' : i === 3 || i === 4 ? 'Longbridge quote' : 'Schwab account snapshot'; });
            const state = this.regular && item.kind === 'holding' ? this.states.symbols[item.symbol] : undefined;
            stateAppearance(row, state); attentionAppearance(row, item.kind === 'holding' ? item.symbol : '', this.attention);
            row.cells[7].textContent = adrText(state); row.cells[7].title = adrTitle(state); volumeBadge(row.cells[8], state?.cum_vol); volumeBadge(row.cells[9], state?.local_vol);
            desired.push(row);
            if (this.expanded.has(item.symbol)) for (const value of detail) { const child = this.detailRow(item.symbol, value, item.kind === 'sold', columns); desired.push(child); detailKeys.add(child.dataset.detail!); }
        }
        for (const key of this.nodes.keys()) if (!keep.has(key)) { this.nodes.delete(key); this.expanded.delete(key); }
        for (const key of this.details.keys()) if (!detailKeys.has(key)) this.details.delete(key);
        const order = desired.map(row => row.dataset.detail ?? row.dataset.holding).join('|');
        if (order !== this.order) { const focused = document.activeElement as HTMLElement | null; $('schwab-rows').replaceChildren(...desired); this.order = order; if (focused && $('schwab-rows').contains(focused)) focused.focus({ preventScroll: true }); }
        $('schwab-empty').hidden = this.data.rows.length > 0; $('schwab-empty').textContent = this.data.account ? 'No holdings or orders' : 'Waiting for Schwab account';
        const positions = this.data.rows.flatMap(row => row.position ? [row.position] : []);
        const sum = (field: keyof Position) => { if (!this.data?.account) return null; const values = positions.map(position => numeric(position[field])); return values.every(value => value != null) ? values.reduce<number>((sum, value) => sum + value!, 0) : null; };
        const costs = positions.map(position => numeric(position.quantity) != null && numeric(position.average_price) != null ? Number(position.quantity) * Number(position.average_price) : null);
        const cost = costs.every(value => value != null) ? costs.reduce<number>((sum, value) => sum + value!, 0) : null, pnl = sum('open_profit_loss');
        $('schwab-total-value').textContent = integer(sum('market_value')) || '—'; $('schwab-total-pnl').textContent = formatted(pnl);
        $('schwab-total-percent').textContent = formatted(pnl != null && cost && cost > 0 ? pnl / cost * 100 : null, true); $('schwab-total-day').textContent = formatted(sum('day_profit_loss'));
        this.layout.measure();
    }
}

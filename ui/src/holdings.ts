import { $ } from './types.js';

type Sale = { id: string; date: string; quantity: string; value: string; holding_days: number; pnl: string; pnl_percent: string; sold_percent: string };
type Sequence = { buy_ids: string[]; opened_on: string; holding_days: number; held_quantity: string; buy_quantity: string; sold_quantity: string; buy_price: string; market_value: string; total_pnl: string; total_pnl_percent: string; day_pnl: string | null; sold_percent: string; sells: Sale[] };
type Holding = { ticker: string; price_source: string; price_session: string | null; price_timestamp: string | number; change_percent: string | null; extended_percent: string | null; day_reference_price: string | null; sequences: Sequence[] };
export type HoldingsState = { data: { fetched_at: string; positions_as_of: string; funds: { stock_market_value: string; account_total: string; cash: string }; summary: { pnl: string; pnl_percent: string | null; day_pnl: string | null }; holdings: Holding[] } | null; loading: boolean; error: string | null };
const money = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const quantity = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 });
const soldPercent = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });
const signed = (value: string, percent = false) => `${Number(value) > 0 ? '+' : ''}${money.format(Number(value))}${percent ? '%' : ''}`;
const pnlClass = (value: string) => Number(value) > 0 ? 'positive' : Number(value) < 0 ? 'negative' : '';
const symbolFor = (ticker: string) => ticker.endsWith('.US') ? ticker : ticker + '.US';

export class HoldingsList {
    selected = '';
    private data: HoldingsState | null = null;
    private expanded = new Set<string>();
    private structure = '';
    private rows = new Map<string, HTMLTableRowElement>();
    private collapsed = false;

    constructor(private onSelect: (symbol: string, key: string) => void, private isActive: () => boolean) {
        try { this.collapsed = localStorage.getItem('holdings-collapsed') === 'true'; } catch { /* Optional storage. */ }
        $('holdings-toggle').addEventListener('click', () => {
            this.collapsed = !this.collapsed;
            try { localStorage.setItem('holdings-collapsed', String(this.collapsed)); } catch { /* Optional storage. */ }
            this.render();
        });
        $('holdings-rows').addEventListener('click', event => {
            const target = event.target as HTMLElement;
            const toggle = target.closest<HTMLElement>('[data-sales]');
            if (toggle) {
                const key = toggle.dataset.sales!;
                this.expanded.has(key) ? this.expanded.delete(key) : this.expanded.add(key);
                this.render(); return;
            }
            const row = target.closest<HTMLElement>('[data-holding]');
            if (row) this.choose(row.dataset.holding!);
        });
        $('holdings-save').addEventListener('click', () => { void this.saveImage(); });
        document.addEventListener('keydown', event => {
            if (this.collapsed || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey ||
                (event.target as HTMLElement).closest('input,textarea,select,[contenteditable="true"]')) return;
            if (event.key === 'Enter' || event.key === ' ') {
                const row = (event.target as HTMLElement).closest<HTMLElement>('tr[data-holding]');
                if (row && !(event.target as HTMLElement).closest('button')) { event.preventDefault(); this.choose(row.dataset.holding!); }
            } else if (this.isActive() && ['ArrowUp','ArrowDown'].includes(event.key)) {
                const keys = [...this.rows.keys()];
                if (!keys.length) return;
                event.preventDefault();
                const index = Math.max(0, Math.min(keys.length - 1, keys.indexOf(this.selected) + (event.key === 'ArrowDown' ? 1 : -1)));
                this.choose(keys[index]); this.rows.get(keys[index])?.focus();
                this.rows.get(keys[index])?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
            }
        });
    }

    private choose(key: string) {
        for (const holding of this.data?.data?.holdings ?? []) {
            if (holding.sequences.some(sequence => sequence.buy_ids.join(':') === key)) {
                this.onSelect(symbolFor(holding.ticker), key); return;
            }
        }
    }

    has(key: string) { return this.data?.data?.holdings.some(h => h.sequences.some(s => s.buy_ids.join(':') === key)) ?? false; }
    first() {
        const holding = this.data?.data?.holdings[0], sequence = holding?.sequences[0];
        return holding && sequence ? { symbol: symbolFor(holding.ticker), key: sequence.buy_ids.join(':') } : null;
    }

    update(state: HoldingsState | null) { this.data = state; this.render(); }

    private cell(row: HTMLTableRowElement, text: string, subtitle?: string) {
        const cell = row.insertCell(); cell.append(document.createTextNode(text));
        if (subtitle !== undefined) { const small = document.createElement('small'); small.textContent = subtitle; cell.append(small); }
        return cell;
    }
    private value(cell: Element, text: string, subtitle?: string) {
        if (!cell.firstChild) cell.append(document.createTextNode(''));
        cell.firstChild!.textContent = text;
        if (subtitle !== undefined) cell.querySelector('small')!.textContent = subtitle;
    }

    render() {
        $('holdings').hidden = !this.data;
        $('holdings-content').hidden = this.collapsed;
        $('holdings-toggle').setAttribute('aria-expanded', String(!this.collapsed));
        $('holdings-arrow').textContent = this.collapsed ? '▸' : '▾';
        const data = this.data?.data;
        $('holdings-count').textContent = data ? String(data.holdings.reduce((n, h) => n + h.sequences.length, 0)) : '';
        $('holdings-updated').textContent = this.data?.error ? 'Refresh failed' : this.data?.loading ? 'Loading…' :
            data ? new Date(data.fetched_at).toLocaleTimeString('en-GB', { hour12: false }) : '';
        $('holdings-updated').title = this.data?.error ?? (data ? `Positions as of ${data.positions_as_of}` : '');
        $('holdings-updated').classList.toggle('negative', !!this.data?.error);
        $('holdings-account').textContent = data ? money.format(Number(data.funds.account_total)) : '—';
        $('holdings-account').title = data ? `Latest position value + SnapTrade cash ${money.format(Number(data.funds.cash))}` : '';
        $('holdings-empty').hidden = !!data?.holdings.length;
        $('holdings-empty').textContent = data ? 'No holdings' : this.data?.error ? 'Holdings unavailable' : 'Loading…';
        ($('holdings-save') as HTMLButtonElement).disabled = !data;
        const structure = JSON.stringify([data?.holdings.map(h => [h.ticker, h.sequences.map(s => [s.buy_ids, s.opened_on, s.sells])]), [...this.expanded]]);
        if (structure !== this.structure) {
            this.structure = structure; this.rows.clear();
            const body = document.createDocumentFragment();
            for (const holding of data?.holdings ?? []) {
                for (const sequence of holding.sequences) {
                    const key = sequence.buy_ids.join(':'), row = document.createElement('tr');
                    row.dataset.holding = key; row.tabIndex = 0;
                    row.setAttribute('aria-label', `Select ${holding.ticker}, bought ${sequence.opened_on}`);
                    const label = this.cell(row, '');
                    const toggle = document.createElement('button'); toggle.className = 'holdings-sales';
                    toggle.textContent = this.expanded.has(key) ? '▾' : '▸'; toggle.dataset.sales = key;
                    toggle.hidden = !sequence.sells.length; toggle.setAttribute('aria-expanded', String(this.expanded.has(key)));
                    toggle.setAttribute('aria-label', `Toggle ${holding.ticker} sales`);
                    const name = document.createElement('span'); name.className = 'ticker'; name.textContent = holding.ticker;
                    label.append(toggle, name);
                    this.cell(row, '', ''); this.cell(row, ''); this.cell(row, ''); this.cell(row, ''); this.cell(row, '', ''); this.cell(row, '', sequence.opened_on);
                    this.cell(row, ''); this.cell(row, ''); this.cell(row, '');
                    body.append(row); this.rows.set(key, row);
                    if (this.expanded.has(key)) for (const sale of sequence.sells) {
                        const detail = document.createElement('tr'); detail.className = 'holding-sale'; detail.dataset.holding = key;
                        this.cell(detail, 'Sold').title = sale.id;
                        this.cell(detail, '—'); this.cell(detail, String(sale.holding_days));
                        this.cell(detail, signed(sale.pnl_percent, true)).className = pnlClass(sale.pnl_percent);
                        this.cell(detail, signed(sale.pnl)).className = pnlClass(sale.pnl);
                        this.cell(detail, `${soldPercent.format(Number(sale.sold_percent))}%`, quantity.format(Number(sale.quantity)));
                        this.cell(detail, money.format(Number(sale.value) / Number(sale.quantity)), sale.date);
                        this.cell(detail, ''); this.cell(detail, ''); this.cell(detail, '');
                        body.append(detail);
                    }
                }
            }
            $('holdings-rows').replaceChildren(body);
        }
        for (const holding of data?.holdings ?? []) for (const sequence of holding.sequences) {
            const key = sequence.buy_ids.join(':'), row = this.rows.get(key)!;
            row.classList.toggle('active', key === this.selected);
            row.setAttribute('aria-selected', String(key === this.selected));
            this.value(row.cells[1], money.format(Number(sequence.market_value)), `${quantity.format(Number(sequence.held_quantity))} shares`);
            const priceTime = new Date(typeof holding.price_timestamp === 'number' ? holding.price_timestamp * 1000 : holding.price_timestamp).toLocaleString('en-GB');
            const session = holding.price_session === 'Intraday' ? 'Regular' : holding.price_session;
            row.cells[1].title = `${holding.price_source === 'longbridge' ? 'Longbridge' : 'SnapTrade fallback'}${session ? ' · ' + session : ''} · ${priceTime}`;
            this.value(row.cells[2], String(sequence.holding_days));
            this.value(row.cells[3], signed(sequence.total_pnl_percent, true)); row.cells[3].className = pnlClass(sequence.total_pnl_percent);
            this.value(row.cells[4], signed(sequence.total_pnl)); row.cells[4].className = pnlClass(sequence.total_pnl);
            this.value(row.cells[5], `${soldPercent.format(Number(sequence.sold_percent))}%`, `${quantity.format(Number(sequence.sold_quantity))} / ${quantity.format(Number(sequence.buy_quantity))}`);
            this.value(row.cells[6], money.format(Number(sequence.buy_price)));
            for (const [index, value, percent, empty] of [[7, holding.change_percent, true, '—'], [8, holding.extended_percent, true, ''], [9, sequence.day_pnl, false, '—']] as const) {
                this.value(row.cells[index], value == null ? empty : signed(value, percent));
                row.cells[index].className = value == null ? '' : pnlClass(value);
            }
            row.cells[8].title = holding.extended_percent != null ? `${session}: change from regular close` : '';
            row.cells[9].title = holding.day_reference_price != null ?
                `${quantity.format(Number(sequence.held_quantity))} shares × (latest price − ${money.format(Number(holding.day_reference_price))} previous regular close) · ${session} · ${priceTime}` : 'Daily P/L unavailable: missing Longbridge price or previous regular close';
        }
        $('holdings-total-value').textContent = data ? money.format(Number(data.funds.stock_market_value)) : '—';
        $('holdings-total-pnl').textContent = data ? signed(data.summary.pnl) : '—';
        $('holdings-total-pnl').className = data ? pnlClass(data.summary.pnl) : '';
        $('holdings-total-percent').textContent = data?.summary.pnl_percent != null ? signed(data.summary.pnl_percent, true) : '—';
        $('holdings-total-percent').className = data?.summary.pnl_percent != null ? pnlClass(data.summary.pnl_percent) : '';
        $('holdings-total-day').textContent = data?.summary.day_pnl != null ? signed(data.summary.day_pnl) : '—';
        $('holdings-total-day').className = data?.summary.day_pnl != null ? pnlClass(data.summary.day_pnl) : '';
    }

    private async saveImage() {
        const table = $('holdings-table');
        const width = table.offsetWidth + 40, height = table.offsetHeight + 40;
        const content = document.createElement('div'); content.setAttribute('xmlns', 'http://www.w3.org/1999/xhtml');
        const style = document.createElement('style');
        style.textContent = Array.from(document.styleSheets).flatMap(sheet => Array.from(sheet.cssRules).map(rule => rule.cssText)).join('\n');
        content.append(style, table.cloneNode(true)); content.style.cssText = `padding:20px;width:${width}px;background:white;font:13px sans-serif;`;
        const source = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><foreignObject width="100%" height="100%">${new XMLSerializer().serializeToString(content)}</foreignObject></svg>`;
        const image = new Image(); image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(source); await image.decode();
        const canvas = document.createElement('canvas'); canvas.width = width * 2; canvas.height = height * 2;
        canvas.getContext('2d')!.drawImage(image, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/png'));
        if (!blob) return;
        const link = document.createElement('a'); link.download = `holdings-${this.data!.data!.fetched_at.slice(0,10)}.png`;
        link.href = URL.createObjectURL(blob); document.body.append(link); link.click(); link.remove();
        window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    }
}

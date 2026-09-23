import { $, money, extendedQuote, type Ticker } from './types.js';

export type ListState = { type?: string; board: Ticker[]; editable: boolean; mode?: string; workspace_error?: string | null; notice?: string };

export class Watchlist {
    tickers: Ticker[] = [];
    selected = '';
    private editable = false;
    private collapsed = new Set<string>();
    private rows = new Map<string, HTMLElement>();
    private key = '';
    private dragged = '';
    private targetSection = 'focus';
    private busy = false;
    private dragStart: { ticker: string; x: number; y: number } | null = null;
    private suppressClick = false;

    constructor(private onSelect: (symbol: string) => void) {
        $('search').addEventListener('input', () => this.render());
        $('symbols').addEventListener('click', event => {
            if (this.suppressClick) return;
            const target = event.target as HTMLElement;
            const add = target.closest<HTMLElement>('[data-add]');
            if (add) {
                this.targetSection = add.dataset.add!;
                $('add-title').textContent = `Add to ${this.targetSection === 'focus' ? 'Focus' : 'Wait'}`;
                ($('add-ticker') as HTMLInputElement).value = '';
                $('add-error').textContent = '';
                ($('add-dialog') as HTMLDialogElement).showModal();
                ($('add-ticker') as HTMLInputElement).focus();
                return;
            }
            const toggle = target.closest<HTMLElement>('[data-toggle]');
            if (toggle) {
                const section = toggle.dataset.toggle!;
                if (this.collapsed.has(section)) this.collapsed.delete(section); else this.collapsed.add(section);
                this.render(); return;
            }
            const row = target.closest<HTMLElement>('[data-symbol]');
            if (!row) return;
            if (target.closest('.delete-ticker')) {
                void this.mutate({ action: 'delete', ticker: row.dataset.ticker });
            } else this.onSelect(row.dataset.symbol!);
        });
        $('symbols').addEventListener('pointerdown', event => {
            const target = event.target as HTMLElement;
            const row = target.closest<HTMLElement>('[data-symbol]');
            if (!row || target.closest('.delete-ticker') || !this.editable || this.busy || event.button !== 0) return;
            this.dragStart = { ticker: row.dataset.ticker!, x: event.clientX, y: event.clientY };
        });
        $('symbols').addEventListener('pointermove', event => {
            if (!this.dragStart) return;
            if (event.buttons !== 1) { this.endDrag(); return; }
            if (!this.dragged) {
                if (Math.hypot(event.clientX - this.dragStart.x, event.clientY - this.dragStart.y) < 5) return;
                this.dragged = this.dragStart.ticker;
                $('symbols').setPointerCapture(event.pointerId);
                const row = [...this.rows.values()].find(row => row.dataset.ticker === this.dragged);
                row?.classList.add('dragging');
            }
            event.preventDefault();
            const bounds = $('symbols').getBoundingClientRect();
            if (event.clientY < bounds.top + 24) $('symbols').scrollTop -= 18;
            if (event.clientY > bounds.bottom - 24) $('symbols').scrollTop += 18;
            const target = document.elementFromPoint(event.clientX, event.clientY) as HTMLElement | null;
            const section = target?.closest<HTMLElement>('[data-section]');
            this.clearDrop();
            if (!section) return;
            const row = target?.closest<HTMLElement>('[data-symbol]');
            if (row) row.classList.add(event.clientY < row.getBoundingClientRect().top + row.offsetHeight / 2 ? 'drop-before' : 'drop-after');
            else section.classList.add('drop-section');
        });
        $('symbols').addEventListener('pointerup', event => {
            const ticker = this.dragged;
            this.dragStart = null;
            if (!ticker) return;
            event.preventDefault();
            this.suppressClick = true;
            window.setTimeout(() => { this.suppressClick = false; }, 0);
            const target = document.elementFromPoint(event.clientX, event.clientY) as HTMLElement | null;
            const section = target?.closest<HTMLElement>('[data-section]')?.dataset.section;
            const row = target?.closest<HTMLElement>('[data-symbol]');
            this.endDrag();
            if (!section || row?.dataset.ticker === ticker) return;
            const items = this.tickers.filter(t => t.status === section && t.ticker !== ticker);
            let index = items.length;
            if (row) index = items.findIndex(t => t.symbol === row.dataset.symbol) + (event.clientY >= row.getBoundingClientRect().top + row.offsetHeight / 2 ? 1 : 0);
            else if (target?.closest('.group')) index = 0;
            void this.mutate({ action: 'move', ticker, section, index });
        });
        $('symbols').addEventListener('pointercancel', () => this.endDrag());
        $('add-cancel').addEventListener('click', () => ($('add-dialog') as HTMLDialogElement).close());
        $('add-form').addEventListener('submit', event => {
            event.preventDefault();
            void this.mutate({ action: 'add', ticker: ($('add-ticker') as HTMLInputElement).value, section: this.targetSection }, true);
        });
        document.addEventListener('keydown', event => {
            if (!['ArrowUp', 'ArrowDown'].includes(event.key) || event.metaKey || event.ctrlKey || event.altKey ||
                (event.target as HTMLElement).matches('input,textarea') || ($('add-dialog') as HTMLDialogElement).open) return;
            const rows = Array.from(this.rows.values());
            if (!rows.length) return;
            const index = rows.findIndex(row => row.dataset.symbol === this.selected);
            const next = Math.max(0, Math.min(rows.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)));
            event.preventDefault(); this.onSelect(rows[next].dataset.symbol!);
            rows[next].scrollIntoView({ block: 'nearest' });
        });
    }

    update(data: ListState) {
        this.tickers = data.board;
        this.editable = data.editable;
        $('symbol-count').textContent = String(this.tickers.length);
        $('simulation').hidden = data.mode !== 'simulation';
        $('workspace-error').textContent = data.workspace_error ?? '';
        if (!this.tickers.some(t => t.symbol === this.selected) && (this.selected || this.tickers.length))
            this.onSelect(this.tickers[0]?.symbol ?? '');
        this.render();
    }

    private clearDrop() {
        document.querySelectorAll('.drop-before,.drop-after,.drop-section').forEach(node => node.classList.remove('drop-before', 'drop-after', 'drop-section'));
    }

    private endDrag() {
        this.dragged = ''; this.dragStart = null; this.clearDrop();
        document.querySelector('.dragging')?.classList.remove('dragging');
    }

    private async mutate(payload: object, adding = false) {
        if (this.busy) return;
        this.busy = true;
        const submit = $('add-submit') as HTMLButtonElement;
        submit.disabled = true;
        submit.textContent = 'Validating…';
        const message = $(adding ? 'add-error' : 'list-notice');
        message.textContent = '';
        try {
            const response = await fetch('/v1/list', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error ?? 'Could not save list');
            this.update(data);
            $('list-notice').textContent = data.notice ?? '';
            if (adding) ($('add-dialog') as HTMLDialogElement).close();
        } catch (error) {
            message.textContent = error instanceof Error ? error.message : 'Could not save list';
        } finally {
            this.busy = false; submit.disabled = false; submit.textContent = 'Add';
        }
    }

    render() {
        const term = ($('search') as HTMLInputElement).value.trim().toUpperCase();
        const visible = this.tickers.filter(t => t.ticker.includes(term));
        const key = JSON.stringify([visible.map(t => [t.symbol, t.status]), [...this.collapsed], this.editable]);
        if (key !== this.key) {
            this.key = key; this.rows.clear();
            const fragment = document.createDocumentFragment();
            for (const group of ['focus', 'wait']) {
                const section = document.createElement('section'); section.dataset.section = group;
                const heading = document.createElement('div'); heading.className = 'group';
                const toggle = document.createElement('button'); toggle.dataset.toggle = group;
                toggle.textContent = `${this.collapsed.has(group) ? '▸' : '▾'} ${group === 'focus' ? 'Focus' : 'Wait'}`;
                toggle.setAttribute('aria-expanded', String(!this.collapsed.has(group)));
                const add = document.createElement('button'); add.dataset.add = group; add.textContent = '+';
                add.setAttribute('aria-label', `Add ticker to ${group === 'focus' ? 'Focus' : 'Wait'}`); add.disabled = !this.editable;
                heading.append(toggle, add); section.append(heading);
                const items = visible.filter(t => t.status === group);
                if (!this.collapsed.has(group)) {
                    for (const ticker of items) {
                        const row = document.createElement('div'); row.className = 'symbol-row';
                        row.dataset.symbol = ticker.symbol; row.dataset.ticker = ticker.ticker;
                        const name = document.createElement('button'); name.className = 'ticker'; name.textContent = ticker.ticker.replace(/\.US$/, '');
                        name.setAttribute('aria-label', `Select ${ticker.ticker}`);
                        const mark = document.createElement('span'); mark.className = 'warn'; mark.textContent = '!'; mark.hidden = true; name.append(mark);
                        const remove = document.createElement('button'); remove.className = 'delete-ticker'; remove.textContent = '×';
                        remove.setAttribute('aria-label', `Delete ${ticker.ticker}`); remove.title = `Delete ${ticker.ticker}`; remove.hidden = !this.editable;
                        row.append(name, document.createElement('span'), document.createElement('span'), document.createElement('span'), remove);
                        section.append(row); this.rows.set(ticker.symbol, row);
                    }
                    if (!items.length) {
                        const empty = document.createElement('div'); empty.className = 'empty-list'; empty.textContent = term ? 'No matches' : 'No symbols'; section.append(empty);
                    }
                }
                fragment.append(section);
            }
            $('symbols').replaceChildren(fragment);
        }
        for (const ticker of visible) {
            const row = this.rows.get(ticker.symbol);
            if (!row) continue;
            row.classList.toggle('active', ticker.symbol === this.selected);
            row.querySelector('button')!.setAttribute('aria-pressed', String(ticker.symbol === this.selected));
            const errors = [...(ticker.errors ?? []), ...(ticker.quote?.error ? ['Quote: ' + ticker.quote.error] : [])];
            const mark = row.querySelector<HTMLElement>('.warn')!; mark.hidden = !errors.length; mark.title = errors.join('\n');
            const regular = ticker.quote?.regular, extended = extendedQuote(ticker.quote);
            const change = regular?.prev_close ? (regular.last_price / regular.prev_close - 1) * 100 : null;
            const ext = extended && regular?.last_price ? (extended.last_price / regular.last_price - 1) * 100 : null;
            row.children[1].textContent = money(regular?.last_price);
            for (const [index, value] of [[2, change], [3, ext]] as const) {
                const cell = row.children[index];
                cell.textContent = value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
                cell.className = value == null ? '' : value >= 0 ? 'positive' : 'negative';
            }
            (row.children[3] as HTMLElement).title = extended ? `${extended.trade_session}: change from regular close` : '';
        }
    }
}

import { $, money, extendedQuote } from './types.js';
async function listRequest(payload, signal) {
    const response = await fetch('/v1/list', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal,
    });
    const data = await response.json();
    if (!response.ok)
        throw new Error(data.error ?? 'Request failed');
    return data;
}
export class Watchlist {
    onSelect;
    tickers = [];
    selected = '';
    editable = false;
    collapsed = new Set();
    rows = new Map();
    key = '';
    dragged = '';
    input = $('search');
    search = null;
    lookupTimer;
    lookupController;
    busy = false;
    dragStart = null;
    suppressClick = false;
    constructor(onSelect) {
        this.onSelect = onSelect;
        this.input.addEventListener('focus', () => { if (!this.search)
            this.beginSearch(); });
        this.input.addEventListener('input', () => this.changeSearch());
        $('symbols').addEventListener('click', event => {
            if (this.suppressClick)
                return;
            const target = event.target;
            const add = target.closest('[data-add]');
            if (add) {
                this.beginSearch(add.dataset.add);
                return;
            }
            if (target.closest('[data-candidate]')) {
                void this.commitSearch();
                return;
            }
            const toggle = target.closest('[data-toggle]');
            if (toggle) {
                const section = toggle.dataset.toggle;
                if (this.collapsed.has(section))
                    this.collapsed.delete(section);
                else
                    this.collapsed.add(section);
                this.render();
                return;
            }
            const row = target.closest('[data-symbol]');
            if (!row)
                return;
            if (target.closest('.delete-ticker')) {
                void this.mutate({ action: 'delete', ticker: row.dataset.ticker });
            }
            else if (this.search)
                this.endSearch(row.dataset.symbol);
            else
                this.onSelect(row.dataset.symbol);
        });
        $('symbols').addEventListener('pointerdown', event => {
            const target = event.target;
            const row = target.closest('[data-symbol]');
            if (!row || target.closest('.delete-ticker') || !this.editable || this.busy || event.button !== 0)
                return;
            this.dragStart = { ticker: row.dataset.ticker, x: event.clientX, y: event.clientY };
        });
        $('symbols').addEventListener('pointermove', event => {
            if (!this.dragStart)
                return;
            if (event.buttons !== 1) {
                this.endDrag();
                return;
            }
            if (!this.dragged) {
                if (Math.hypot(event.clientX - this.dragStart.x, event.clientY - this.dragStart.y) < 5)
                    return;
                this.dragged = this.dragStart.ticker;
                $('symbols').setPointerCapture(event.pointerId);
                const row = [...this.rows.values()].find(row => row.dataset.ticker === this.dragged);
                row?.classList.add('dragging');
            }
            event.preventDefault();
            const bounds = $('symbols').getBoundingClientRect();
            if (event.clientY < bounds.top + 24)
                $('symbols').scrollTop -= 18;
            if (event.clientY > bounds.bottom - 24)
                $('symbols').scrollTop += 18;
            const target = document.elementFromPoint(event.clientX, event.clientY);
            const section = target?.closest('[data-section]');
            this.clearDrop();
            if (!section)
                return;
            const row = target?.closest('[data-symbol]');
            if (row)
                row.classList.add(event.clientY < row.getBoundingClientRect().top + row.offsetHeight / 2 ? 'drop-before' : 'drop-after');
            else
                section.classList.add('drop-section');
        });
        $('symbols').addEventListener('pointerup', event => {
            const ticker = this.dragged;
            this.dragStart = null;
            if (!ticker)
                return;
            event.preventDefault();
            this.suppressClick = true;
            window.setTimeout(() => { this.suppressClick = false; }, 0);
            const target = document.elementFromPoint(event.clientX, event.clientY);
            const section = target?.closest('[data-section]')?.dataset.section;
            const row = target?.closest('[data-symbol]');
            this.endDrag();
            if (!section || row?.dataset.ticker === ticker)
                return;
            const items = this.tickers.filter(t => t.status === section && t.ticker !== ticker);
            let index = items.length;
            if (row)
                index = items.findIndex(t => t.symbol === row.dataset.symbol) + (event.clientY >= row.getBoundingClientRect().top + row.offsetHeight / 2 ? 1 : 0);
            else if (target?.closest('.group'))
                index = 0;
            void this.mutate({ action: 'move', ticker, section, index });
        });
        $('symbols').addEventListener('pointercancel', () => this.endDrag());
        document.addEventListener('keydown', event => {
            if (event.metaKey || event.ctrlKey || event.altKey || event.isComposing)
                return;
            if (event.key === '/') {
                event.preventDefault();
                this.beginSearch();
                return;
            }
            if (this.search && ['Escape', 'Enter'].includes(event.key)) {
                event.preventDefault();
                if (event.key === 'Escape')
                    this.endSearch();
                else
                    void this.commitSearch();
                return;
            }
            if (event.target.closest('input,textarea,select,[contenteditable="true"]') ||
                !['ArrowUp', 'ArrowDown'].includes(event.key))
                return;
            event.preventDefault();
            const direction = event.key === 'ArrowDown' ? 1 : -1;
            if (event.shiftKey) {
                void this.swapSelected(direction);
                return;
            }
            const rows = [...this.rows.values()];
            if (!rows.length)
                return;
            const index = rows.findIndex(row => row.dataset.symbol === this.selected);
            const next = Math.max(0, Math.min(rows.length - 1, index + direction));
            this.onSelect(rows[next].dataset.symbol);
            rows[next].scrollIntoView({ block: 'nearest' });
        });
    }
    query() { return this.input.value.trim().toUpperCase(); }
    matches() { return this.tickers.filter(t => t.ticker.includes(this.query())); }
    cancelLookup() {
        clearTimeout(this.lookupTimer);
        this.lookupController?.abort();
        this.lookupController = undefined;
    }
    beginSearch(section = 'focus') {
        this.endDrag();
        this.input.value = '';
        this.changeSearch(section);
        this.input.focus();
    }
    changeSearch(section = this.search?.section ?? 'focus') {
        this.cancelLookup();
        const search = { section, message: '' };
        this.search = search;
        this.render();
        const term = this.query();
        if (term && this.editable && !this.tickers.some(t => t.ticker === term))
            this.lookupTimer = window.setTimeout(() => { void this.lookup(search, term); }, 1000);
    }
    lookup(search, term) {
        clearTimeout(this.lookupTimer);
        if (search.lookup)
            return search.lookup;
        if (!this.editable)
            return Promise.resolve(null);
        search.message = 'Searching…';
        this.render();
        this.lookupController = new AbortController();
        search.lookup = listRequest({ action: 'lookup', ticker: term }, this.lookupController.signal)
            .then(candidate => {
            if (this.search !== search)
                return null;
            search.candidate = candidate;
            search.message = '';
            return candidate;
        })
            .catch(error => {
            if (this.search === search) {
                const message = error instanceof Error ? error.message : 'Search unavailable';
                search.message = message === 'US ticker not found' ? '' : message;
            }
            return null;
        })
            .finally(() => { if (this.search === search)
            this.render(); });
        return search.lookup;
    }
    endSearch(symbol) {
        this.endDrag();
        this.cancelLookup();
        this.search = null;
        this.input.value = '';
        this.input.blur();
        $('list-notice').textContent = '';
        const ticker = this.tickers.find(t => t.symbol === symbol);
        if (ticker)
            this.collapsed.delete(ticker.status);
        this.render();
        if (symbol)
            this.onSelect(symbol);
        this.rows.get(symbol ?? this.selected)?.scrollIntoView({ block: 'nearest' });
    }
    async commitSearch() {
        const search = this.search, term = this.query();
        if (!search || !term || this.busy)
            return;
        // Enter selects the exact local ticker, or the first currently displayed local match.
        const local = this.tickers.find(t => t.ticker === term) ?? (!search.candidate ? this.matches()[0] : undefined);
        if (local) {
            this.endSearch(local.symbol);
            return;
        }
        const candidate = search.candidate ?? await this.lookup(search, term);
        if (this.search !== search || !candidate)
            return;
        const result = await this.mutate({ action: 'add', ticker: candidate.ticker, section: search.section });
        if (result && this.search === search) {
            const added = result.board.find(t => t.ticker === candidate.ticker);
            if (added)
                this.endSearch(added.symbol);
        }
    }
    async swapSelected(direction) {
        if (!this.editable || this.busy || this.search)
            return;
        const ticker = this.tickers.find(t => t.symbol === this.selected);
        if (!ticker)
            return;
        const items = this.tickers.filter(t => t.status === ticker.status);
        const index = items.indexOf(ticker) + direction;
        if (index < 0 || index >= items.length)
            return;
        await this.mutate({ action: 'move', ticker: ticker.ticker, section: ticker.status, index });
        this.rows.get(this.selected)?.scrollIntoView({ block: 'nearest' });
    }
    update(data) {
        this.tickers = data.board;
        this.editable = data.editable;
        $('symbol-count').textContent = String(this.tickers.length);
        $('simulation').hidden = data.mode !== 'simulation';
        $('workspace-error').textContent = data.workspace_error ?? '';
        if (!this.tickers.some(t => t.symbol === this.selected) && (this.selected || this.tickers.length))
            this.onSelect(this.tickers[0]?.symbol ?? '');
        this.render();
    }
    clearDrop() {
        document.querySelectorAll('.drop-before,.drop-after,.drop-section').forEach(node => node.classList.remove('drop-before', 'drop-after', 'drop-section'));
    }
    endDrag() {
        this.dragged = '';
        this.dragStart = null;
        this.clearDrop();
        document.querySelector('.dragging')?.classList.remove('dragging');
    }
    async mutate(payload) {
        if (this.busy)
            return null;
        this.busy = true;
        const search = this.search;
        if (search)
            search.message = 'Saving…';
        $('list-notice').textContent = '';
        this.render();
        try {
            const data = await listRequest(payload);
            this.update(data);
            if (!this.search)
                $('list-notice').textContent = data.notice ?? '';
            return data;
        }
        catch (error) {
            const message = error instanceof Error ? error.message : 'Could not save list';
            if (search && this.search === search)
                search.message = message;
            else
                $('list-notice').textContent = message;
            return null;
        }
        finally {
            this.busy = false;
            this.render();
        }
    }
    render() {
        const visible = this.search ? this.matches() : this.tickers;
        const candidate = this.search?.candidate;
        const showCandidate = candidate && !this.tickers.some(t => t.ticker === candidate.ticker);
        $('list-columns').hidden = !!this.search && !visible.length;
        if (this.search)
            $('list-notice').textContent = this.search.message;
        const key = JSON.stringify([visible.map(t => [t.symbol, t.status]), [...this.collapsed], this.editable,
            this.search?.section, showCandidate ? candidate : null]);
        if (key !== this.key) {
            this.key = key;
            this.rows.clear();
            const fragment = document.createDocumentFragment();
            if (showCandidate) {
                const result = document.createElement('button');
                result.className = 'search-result';
                result.dataset.candidate = candidate.ticker;
                const name = document.createElement('strong');
                name.textContent = candidate.ticker;
                const action = document.createElement('span');
                action.textContent = 'Add';
                const company = document.createElement('span');
                company.className = 'security-name';
                company.textContent = candidate.name;
                result.append(name, action, company);
                fragment.append(result);
            }
            for (const group of ['focus', 'wait']) {
                const items = visible.filter(t => t.status === group);
                if (this.search && !items.length)
                    continue;
                const section = document.createElement('section');
                section.dataset.section = group;
                const heading = document.createElement('div');
                heading.className = 'group';
                const toggle = document.createElement('button');
                toggle.dataset.toggle = group;
                const arrow = document.createElement('span');
                arrow.className = 'section-arrow';
                const collapsed = !this.search && this.collapsed.has(group);
                arrow.textContent = collapsed ? '▸' : '▾';
                arrow.setAttribute('aria-hidden', 'true');
                toggle.append(arrow, group === 'focus' ? 'Focus' : 'Wait');
                toggle.setAttribute('aria-expanded', String(!collapsed));
                const add = document.createElement('button');
                add.dataset.add = group;
                add.textContent = '+';
                add.setAttribute('aria-label', `Add ticker to ${group === 'focus' ? 'Focus' : 'Wait'}`);
                add.disabled = !this.editable;
                heading.append(toggle, add);
                section.append(heading);
                if (!collapsed) {
                    for (const ticker of items) {
                        const row = document.createElement('div');
                        row.className = 'symbol-row';
                        row.dataset.symbol = ticker.symbol;
                        row.dataset.ticker = ticker.ticker;
                        const name = document.createElement('button');
                        name.className = 'ticker';
                        name.textContent = ticker.ticker.replace(/\.US$/, '');
                        name.setAttribute('aria-label', `Select ${ticker.ticker}`);
                        const mark = document.createElement('span');
                        mark.className = 'warn';
                        mark.textContent = '!';
                        mark.hidden = true;
                        name.append(mark);
                        const remove = document.createElement('button');
                        remove.className = 'delete-ticker icon-button';
                        remove.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg>';
                        remove.setAttribute('aria-label', `Delete ${ticker.ticker}`);
                        remove.title = `Delete ${ticker.ticker}`;
                        remove.hidden = !this.editable;
                        row.append(name, document.createElement('span'), document.createElement('span'), document.createElement('span'), remove);
                        section.append(row);
                        this.rows.set(ticker.symbol, row);
                    }
                    if (!items.length) {
                        const empty = document.createElement('div');
                        empty.className = 'empty-list';
                        empty.textContent = 'No symbols';
                        section.append(empty);
                    }
                }
                fragment.append(section);
            }
            $('symbols').replaceChildren(fragment);
        }
        const result = $('symbols').querySelector('[data-candidate]');
        if (result)
            result.disabled = this.busy;
        for (const ticker of visible) {
            const row = this.rows.get(ticker.symbol);
            if (!row)
                continue;
            row.classList.toggle('active', ticker.symbol === this.selected);
            row.querySelector('button').setAttribute('aria-pressed', String(ticker.symbol === this.selected));
            const errors = [...(ticker.errors ?? []), ...(ticker.quote?.error ? ['Quote: ' + ticker.quote.error] : [])];
            const mark = row.querySelector('.warn');
            mark.hidden = !errors.length;
            mark.title = errors.join('\n');
            const regular = ticker.quote?.regular, extended = extendedQuote(ticker.quote);
            const change = regular?.prev_close ? (regular.last_price / regular.prev_close - 1) * 100 : null;
            const ext = extended && regular?.last_price ? (extended.last_price / regular.last_price - 1) * 100 : null;
            row.children[1].textContent = money(regular?.last_price);
            for (const [index, value] of [[2, change], [3, ext]]) {
                const cell = row.children[index];
                cell.textContent = value == null ? (index === 3 ? '' : '—') : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
                cell.className = value == null ? '' : value >= 0 ? 'positive' : 'negative';
            }
            row.children[3].title = extended ? `${extended.trade_session}: change from regular close` : '';
        }
    }
}

import { $, money, compact, extendedQuote, type Ticker } from './types.js';
import type { ScanControls } from './scan.js';
import type { MassiveState } from './types.js';
import type { Preferences } from './tags.js';
import { tagLogo } from './tag-appearance.js';
import { post } from './api.js';
import type { HoldingsState } from './holdings.js';
import { collapseKey, countBadge, growthValue, listSections, rowTags, sectionKey } from './board.js';

export type ListState = { type?: string; board: Ticker[]; editable: boolean; mode?: string; app_mode?: 'scan' | 'monitor'; mock?: boolean; date?: string; dates?: string[]; preferences?: Preferences; workspace_error?: string | null; notice?: string; holdings?: HoldingsState | null; massive?: MassiveState | null; scan_running?: boolean };

type Candidate = { ticker: string; name: string };
type Search = { list: string; section: string; candidate?: Candidate; message: string; lookup?: Promise<Candidate | null> };

export class Watchlist {
    scan?: ScanControls;
    tickers: Ticker[] = [];
    selected = '';
    keyboardEnabled = true;
    private editable = false;
    private collapsed = new Set<string>(['monitor:excluded:review']);
    private manualEditor = '';
    private preferences?: Preferences;
    private rows = new Map<string, HTMLElement>();
    private key = '';
    private dragged = '';
    private input = $('search') as HTMLInputElement;
    private search: Search | null = null;
    private lookupTimer?: number;
    private lookupController?: AbortController;
    private busy = false;
    private dragStart: { ticker: string; x: number; y: number } | null = null;
    private suppressClick = false;

    constructor(private onSelect: (symbol: string) => void, private onUpdate: (data: ListState) => void) {
        this.input.addEventListener('focus', () => { if (!this.search) this.beginSearch(); });
        this.input.addEventListener('input', () => this.changeSearch());
        $('symbols').addEventListener('click', event => {
            if (this.suppressClick) return;
            const target = event.target as HTMLElement;
            const add = target.closest<HTMLElement>('[data-add]');
            if (add) { this.beginSearch(add.dataset.add!, add.dataset.list ?? 'focus'); return; }
            const edit = target.closest<HTMLElement>('[data-tag-edit]');
            if (edit) { this.manualEditor = this.manualEditor === edit.dataset.tagEdit ? '' : edit.dataset.tagEdit!; this.render(); return; }
            const tagToggle = target.closest<HTMLElement>('[data-manual-tag]');
            if (tagToggle) {
                const item = this.tickers.find(t => t.ticker === tagToggle.dataset.ticker)!;
                const tags = new Set(item.manual_tags ?? []);
                if (tags.has(tagToggle.dataset.manualTag!)) tags.delete(tagToggle.dataset.manualTag!); else tags.add(tagToggle.dataset.manualTag!);
                void this.mutate({ action: 'tag', ticker: item.ticker, tags: [...tags] }); return;
            }
            const focus = target.closest<HTMLElement>('[data-to-focus]');
            if (focus) { void this.mutate({ action: 'move', source: focus.dataset.source, target: 'focus', tickers: [focus.dataset.toFocus] }); return; }
            if (target.closest('[data-candidate]')) { void this.commitSearch(); return; }
            const toggle = target.closest<HTMLElement>('[data-toggle]');
            if (toggle) {
                const section = toggle.dataset.toggle!;
                if (this.collapsed.has(section)) this.collapsed.delete(section); else this.collapsed.add(section);
                this.render(); return;
            }
            const row = target.closest<HTMLElement>('[data-symbol]');
            if (!row) return;
            if (target.matches('[data-check]')) { this.scan?.toggle(row.dataset.symbol!); return; }
            if (target.closest('.delete-ticker')) {
                const item = this.tickers.find(t => t.symbol === row.dataset.symbol)!;
                if (item.status === 'excluded')
                    void this.mutate({ action: 'move', tickers: [item.ticker], source: 'excluded', target: 'discover' });
                else void this.mutate({ action: 'delete', ticker: item.ticker });
            } else if (this.search) this.endSearch(row.dataset.symbol!);
            else this.onSelect(row.dataset.symbol!);
        });
        $('symbols').addEventListener('pointerdown', event => {
            const target = event.target as HTMLElement;
            const row = target.closest<HTMLElement>('[data-symbol]');
            if (!row || target.closest('button:not(.ticker),input,.manual-tag-editor') || !this.editable || this.busy || event.button !== 0 ||
                !this.scan?.manualOrder || row.dataset.list === 'excluded') return;
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
            if (!section || section.dataset.list === 'excluded') return;
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
            const group = target?.closest<HTMLElement>('[data-section]');
            const section = group?.dataset.section, list = group?.dataset.list;
            const row = target?.closest<HTMLElement>('[data-symbol]');
            this.endDrag();
            if (!section || !list || list === 'excluded' || row?.dataset.ticker === ticker) return;
            const items = this.tickers.filter(t => t.status === list && (t.section ?? 'unclassified') === section && t.ticker !== ticker);
            let index = items.length;
            if (row) index = items.findIndex(t => t.symbol === row.dataset.symbol) + (event.clientY >= row.getBoundingClientRect().top + row.offsetHeight / 2 ? 1 : 0);
            else if (target?.closest('.group')) index = 0;
            void this.mutate({ action: 'move', ticker, list_name: list, section, index });
        });
        $('symbols').addEventListener('pointercancel', () => this.endDrag());
        document.addEventListener('keydown', event => {
            if (event.metaKey || event.ctrlKey || event.altKey || event.isComposing) return;
            if (event.key === '/') {
                event.preventDefault(); this.beginSearch(); return;
            }
            if (event.key === ' ' && this.scan?.enabled && this.selected && this.editable && !(event.target as HTMLElement).closest('input,textarea,select,button')) {
                event.preventDefault(); this.scan.toggle(this.selected); return;
            }
            if (this.search && ['Escape', 'Enter'].includes(event.key)) {
                event.preventDefault();
                if (event.key === 'Escape') this.endSearch(); else void this.commitSearch();
                return;
            }
            if ((event.target as HTMLElement).closest('input,textarea,select,[contenteditable="true"]') ||
                !this.keyboardEnabled || !['ArrowUp', 'ArrowDown'].includes(event.key)) return;
            event.preventDefault();
            const direction = event.key === 'ArrowDown' ? 1 : -1;
            if (event.shiftKey) { void this.swapSelected(direction); return; }
            const rows = [...this.rows.values()];
            if (!rows.length) return;
            const index = rows.findIndex(row => row.dataset.symbol === this.selected);
            const next = Math.max(0, Math.min(rows.length - 1, index + direction));
            this.onSelect(rows[next].dataset.symbol!);
            rows[next].scrollIntoView({ block: 'nearest' });
        });
    }

    private query() { return this.input.value.trim().toUpperCase(); }
    private visible() { return this.scan ? this.scan.visible(this.tickers) : this.tickers; }
    private matches() { return this.visible().filter(t => t.ticker.includes(this.query())); }

    private cancelLookup() {
        clearTimeout(this.lookupTimer);
        this.lookupController?.abort();
        this.lookupController = undefined;
    }

    private beginSearch(section = 'unclassified', list = 'focus') {
        this.endDrag();
        this.input.value = '';
        this.changeSearch(section, list);
        this.input.focus();
    }

    private changeSearch(section = this.search?.section ?? 'unclassified', list = this.search?.list ?? 'focus') {
        this.cancelLookup();
        const search: Search = { list, section, message: '' };
        this.search = search;
        this.render();
        const term = this.query();
        if (term && this.editable && !this.tickers.some(t => t.ticker === term))
            this.lookupTimer = window.setTimeout(() => { void this.lookup(search, term); }, 1000);
    }

    private lookup(search: Search, term: string): Promise<Candidate | null> {
        clearTimeout(this.lookupTimer);
        if (search.lookup) return search.lookup;
        if (!this.editable) return Promise.resolve(null);
        search.message = 'Searching…'; this.render();
        this.lookupController = new AbortController();
        search.lookup = post<Candidate>('list', { action: 'lookup', ticker: term }, this.lookupController.signal)
            .then(candidate => {
                if (this.search !== search) return null;
                search.candidate = candidate; search.message = '';
                return candidate;
            })
            .catch(error => {
                if (this.search === search) {
                    const message = error instanceof Error ? error.message : 'Search unavailable';
                    search.message = message === 'US ticker not found' ? '' : message;
                }
                return null;
            })
            .finally(() => { if (this.search === search) this.render(); });
        return search.lookup;
    }

    private endSearch(symbol?: string) {
        this.endDrag();
        this.cancelLookup(); this.search = null;
        this.input.value = ''; this.input.blur();
        $('list-notice').textContent = '';
        const ticker = this.tickers.find(t => t.symbol === symbol);
        if (ticker) this.collapsed.delete(collapseKey(this.scan?.enabled === true, sectionKey(ticker)));
        this.render();
        if (symbol) this.onSelect(symbol);
        this.rows.get(symbol ?? this.selected)?.scrollIntoView({ block: 'nearest' });
    }

    private async commitSearch() {
        const search = this.search, term = this.query();
        if (!search || !term || this.busy) return;
        // Enter selects the exact local ticker, or the first currently displayed local match.
        const local = this.tickers.find(t => t.ticker === term) ?? (!search.candidate ? this.matches()[0] : undefined);
        if (local) { this.endSearch(local.symbol); return; }
        const candidate = search.candidate ?? await this.lookup(search, term);
        if (this.search !== search || !candidate) return;
        const result = await this.mutate({ action: 'add', ticker: candidate.ticker, list_name: search.list, section: search.section });
        if (result && this.search === search) {
            const added = result.board.find(t => t.ticker === candidate.ticker);
            if (added) this.endSearch(added.symbol);
        }
    }

    private async swapSelected(direction: number) {
        if (!this.editable || this.busy || this.search || !this.scan?.manualOrder) return;
        const ticker = this.tickers.find(t => t.symbol === this.selected);
        if (!ticker || ticker.status === 'excluded') return;
        const items = this.tickers.filter(t => sectionKey(t) === sectionKey(ticker));
        const index = items.indexOf(ticker) + direction;
        if (index < 0 || index >= items.length) return;
        await this.mutate({ action: 'move', ticker: ticker.ticker, list_name: ticker.status, section: ticker.section ?? 'unclassified', index });
        this.rows.get(this.selected)?.scrollIntoView({ block: 'nearest' });
    }

    update(data: ListState, maintainSelection = true) {
        this.tickers = data.board; this.preferences = data.preferences ?? this.preferences;
        this.editable = data.editable;
        $('symbol-count').textContent = String(this.visible().length);
        $('simulation').hidden = data.mode !== 'simulation';
        $('workspace-error').textContent = data.workspace_error ?? '';
        const visible = this.visible();
        if (maintainSelection && !visible.some(t => t.symbol === this.selected) && (this.selected || visible.length))
            this.onSelect(visible[0]?.symbol ?? '');
        this.render();
    }

    private clearDrop() {
        document.querySelectorAll('.drop-before,.drop-after,.drop-section').forEach(node => node.classList.remove('drop-before', 'drop-after', 'drop-section'));
    }

    private endDrag() {
        this.dragged = ''; this.dragStart = null; this.clearDrop();
        document.querySelector('.dragging')?.classList.remove('dragging');
    }

    private async mutate(payload: object): Promise<ListState | null> {
        if (this.busy) return null;
        this.busy = true;
        const search = this.search;
        if (search) search.message = 'Saving…';
        $('list-notice').textContent = '';
        this.render();
        try {
            const data = await post<ListState>('list', payload);
            this.onUpdate(data);
            if (!this.search) $('list-notice').textContent = data.notice ?? '';
            return data;
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Could not save list';
            if (search && this.search === search) search.message = message;
            else $('list-notice').textContent = message;
            return null;
        } finally {
            this.busy = false; this.render();
        }
    }

    render() {
        const visible = this.search ? this.matches() : this.visible();
        const scan = this.scan?.enabled === true;
        const candidate = this.search?.candidate;
        const showCandidate = candidate && !this.tickers.some(t => t.ticker === candidate.ticker);
        const tags = this.preferences?.tags ?? [];
        const tagDefinitions = new Map(tags.map(tag => [tag.id, tag]));
        const sections = listSections(scan, this.scan?.activeList ?? 'focus', tags);
        $('list-columns').hidden = !!this.search && !visible.length;
        if (this.search) $('list-notice').textContent = this.search.message;
        const key = JSON.stringify([visible.map(t => [t.symbol, t.status, t.section, rowTags(t), t.manual_tags, t.is_new, t.is_returned]), scan, [...this.collapsed], this.editable,
            tags, this.manualEditor, this.search?.section, showCandidate ? candidate : null]);
        if (key !== this.key) {
            this.key = key; this.rows.clear();
            const fragment = document.createDocumentFragment();
            if (showCandidate) {
                const result = document.createElement('button'); result.className = 'search-result'; result.dataset.candidate = candidate.ticker;
                const name = document.createElement('strong'); name.textContent = candidate.ticker;
                const action = document.createElement('span'); action.textContent = 'Add';
                const company = document.createElement('span'); company.className = 'security-name'; company.textContent = candidate.name;
                result.append(name, action, company); fragment.append(result);
            }
            for (const group of sections) {
                const items = visible.filter(t => sectionKey(t) === group.key);
                if (this.search && !items.length) continue;
                const section = document.createElement('section'); section.dataset.section = group.id; section.dataset.list = group.list;
                section.className = group.id === 'review' ? 'review-section' : '';
                const heading = document.createElement('div'); heading.className = 'group';
                const foldKey = collapseKey(scan, group.key);
                const toggle = document.createElement('button'); toggle.dataset.toggle = foldKey;
                const arrow = document.createElement('span'); arrow.className = 'section-arrow';
                const collapsed = !this.search && this.collapsed.has(foldKey);
                arrow.textContent = collapsed ? '▸' : '▾'; arrow.setAttribute('aria-hidden', 'true');
                toggle.append(arrow, group.name, countBadge(items.length));
                toggle.setAttribute('aria-expanded', String(!collapsed));
                if (group.id === 'review') toggle.title = 'Local Daily preview; Add to Focus starts live monitoring';
                const add = document.createElement('button'); add.dataset.add = group.id; add.dataset.list = group.list; add.textContent = '+';
                add.setAttribute('aria-label', `Add ticker to ${group.name}`); add.disabled = !this.editable;
                add.hidden = group.list !== 'focus';
                heading.append(toggle, add); section.append(heading);
                if (!collapsed) {
                    for (const ticker of items) {
                        const row = document.createElement('div'); row.className = 'symbol-row';
                        row.dataset.symbol = ticker.symbol; row.dataset.ticker = ticker.ticker; row.dataset.list = ticker.status;
                        const name = document.createElement('button'); name.className = 'ticker'; name.textContent = ticker.ticker.replace(/\.US$/, '');
                        name.setAttribute('aria-label', `Select ${ticker.ticker}`);
                        const mark = document.createElement('span'); mark.className = 'warn'; mark.textContent = '!'; mark.hidden = true; name.append(mark);
                        const symbolCell = document.createElement('div'); symbolCell.className = 'scan-symbol';
                        if (scan) {
                            const check = document.createElement('input'); check.type = 'checkbox'; check.dataset.check = ticker.symbol;
                            check.setAttribute('aria-label', `Select ${ticker.ticker} for move`); symbolCell.append(check);
                        }
                        symbolCell.append(name);
                        const label = ticker.is_new ? 'NEW' : ticker.is_returned ? 'RETURNED' : '';
                        if (label) { const flag = document.createElement('span'); flag.className = 'symbol-flag'; flag.textContent = label; symbolCell.append(flag); }
                        const action = document.createElement('button'); action.className = 'delete-ticker icon-button'; action.hidden = !this.editable;
                        if (group.id === 'review') {
                            action.dataset.toFocus = ticker.ticker; action.dataset.source = 'excluded'; action.textContent = '+';
                            action.title = `Add ${ticker.ticker} to Focus`;
                        } else if (ticker.status === 'excluded') {
                            action.textContent = '↩'; action.title = `Release ${ticker.ticker} to Discover`;
                        } else {
                            action.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg>';
                            action.title = `Exclude ${ticker.ticker} for 7 days`;
                        }
                        action.setAttribute('aria-label', action.title);
                        const growth = document.createElement('span'); growth.className = 'growth-cell'; growth.title = '1M / 3M / 6M return from low';
                        for (const [index, field] of ['rfl1m','rfl3m','rfl6m'].entries()) {
                            if (index) { const divider = document.createElement('span'); divider.className = 'growth-divider'; divider.textContent = '|'; growth.append(divider); }
                            const value = document.createElement('span'); value.className = 'growth-value'; value.dataset.growth = field; growth.append(value);
                        }
                        const badges = document.createElement('div'); badges.className = 'row-tags';
                        const ids = rowTags(ticker);
                        for (const id of ids.slice(0, 3)) {
                            badges.append(tagLogo(tagDefinitions.get(id) ?? { name: id }, ticker.manual_tags?.includes(id)));
                        }
                        if (ids.length > 3) {
                            const more = document.createElement('span'); more.className = 'tag-overflow'; more.textContent = '+' + (ids.length - 3);
                            more.title = ids.slice(3).map(id => (tagDefinitions.get(id)?.name ?? id) +
                                (ticker.manual_tags?.includes(id) ? ' · Manual · today only' : '')).join('\n');
                            more.setAttribute('aria-label', more.title); badges.append(more);
                        }
                        const edit = document.createElement('button'); edit.dataset.tagEdit = ticker.ticker; edit.className = 'tag-edit'; edit.textContent = 'Tags';
                        edit.title = 'Add manual Tags for today'; edit.hidden = ticker.section === 'hidden'; edit.disabled = !this.editable || edit.hidden;
                        edit.setAttribute('aria-expanded', String(this.manualEditor === ticker.ticker)); badges.append(edit);
                        row.append(symbolCell, document.createElement('span'), document.createElement('span'), document.createElement('span'), growth, badges, action);
                        section.append(row); this.rows.set(ticker.symbol, row);
                        if (this.manualEditor === ticker.ticker && this.editable && ticker.section !== 'hidden') {
                            const editor = document.createElement('div'); editor.className = 'manual-tag-editor';
                            for (const tag of tags.filter(tag => tag.id !== 'default')) {
                                const button = document.createElement('button'); button.dataset.manualTag = tag.id; button.dataset.ticker = ticker.ticker;
                                button.textContent = tag.name; button.setAttribute('aria-pressed', String(ticker.manual_tags?.includes(tag.id) ?? false));
                                button.title = 'Manual · today only'; editor.append(button);
                            }
                            section.append(editor);
                        }
                    }
                    if (!items.length) {
                        const empty = document.createElement('div'); empty.className = 'empty-list'; empty.textContent = 'No symbols'; section.append(empty);
                    }
                }
                fragment.append(section);
            }
            $('symbols').replaceChildren(fragment);
        }
        const result = $('symbols').querySelector<HTMLButtonElement>('[data-candidate]');
        if (result) result.disabled = this.busy;
        $('symbols').querySelectorAll<HTMLButtonElement>('[data-manual-tag]').forEach(button => { button.disabled = this.busy; });
        for (const ticker of visible) {
            const row = this.rows.get(ticker.symbol);
            if (!row) continue;
            row.classList.toggle('active', ticker.symbol === this.selected);
            row.querySelector('.ticker')!.setAttribute('aria-pressed', String(ticker.symbol === this.selected));
            const errors = [...(ticker.errors ?? []), ...(ticker.quote?.error ? ['Quote: ' + ticker.quote.error] : [])];
            const mark = row.querySelector<HTMLElement>('.warn')!; mark.hidden = !errors.length; mark.title = errors.join('\n');
            (row.querySelector('.delete-ticker') as HTMLButtonElement).disabled = this.busy || this.scan?.busy === true;
            row.querySelectorAll<HTMLElement>('[data-growth]').forEach(cell => { cell.textContent = growthValue(ticker[cell.dataset.growth!]); });
            const regular = ticker.quote?.regular, extended = extendedQuote(ticker.quote);
            if (scan) {
                const check = row.querySelector('[data-check]') as HTMLInputElement;
                check.checked = this.scan!.selected.has(ticker.symbol); check.disabled = !this.editable || this.scan!.busy;
                row.children[1].textContent = money(ticker.close);
                row.children[2].textContent = ticker.adr20 == null ? '—' : ticker.adr20.toFixed(1) + '%';
                row.children[3].textContent = ticker.adv20 == null ? '—' : '$' + compact(ticker.adv20);
                continue;
            }
            const preview = ticker.status === 'excluded';
            const change = regular?.prev_close ? (regular.last_price / regular.prev_close - 1) * 100 : null;
            const ext = extended && regular?.last_price ? (extended.last_price / regular.last_price - 1) * 100 : null;
            row.children[1].textContent = money(preview ? ticker.close : regular?.last_price);
            for (const [index, value] of [[2, change], [3, ext]] as const) {
                const cell = row.children[index];
                cell.textContent = preview ? '' : value == null ? (index === 3 ? '' : '—') : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
                cell.className = value == null ? '' : value >= 0 ? 'positive' : 'negative';
            }
            (row.children[1] as HTMLElement).title = preview ? 'Latest completed Massive Daily close' : 'Regular last price';
            (row.children[3] as HTMLElement).title = extended ? `${extended.trade_session}: change from regular close` : '';
        }
    }
}

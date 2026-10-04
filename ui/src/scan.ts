import { $, type Ticker } from './types.js';
import { post } from './api.js';
import { FilterPanel, matchesFilters, type Field } from './filters.js';
import { tagChanged, tagRole, withSavedTag, type Preferences, type Tag, type TagRole } from './tags.js';
import type { ListState } from './list.js';
import { rowTags } from './board.js';

const rank = (row: Ticker, field: string) => typeof row[field] === 'number' ? row[field] as number : Infinity;

export const matchesTag = (row: Ticker, tag: Tag, useAssigned = true) =>
    (useAssigned && tag.id !== 'default' && rowTags(row).includes(tag.id)) || matchesFilters(row, tag.filters);

export class ScanControls {
    enabled = false;
    selected = new Set<string>();
    preferences?: Preferences;
    private draft?: Tag;
    private rows: Ticker[] = [];
    private savedKey = '';
    private date = '';
    private editable = false;
    private panel?: FilterPanel;
    private pending = false;
    private serverRunning = false;
    private discard?: () => void;
    private deleting = false;

    constructor(private updateList: (data: ListState) => void, private changed: () => void) {
        void fetch('/v1/filter-catalog').then(response => response.json()).then((catalog: Field[]) => {
            if (!Array.isArray(catalog)) return; // The standalone simulator has no Scan endpoints.
            this.panel = new FilterPanel($('filter-rules'), catalog, filters => {
                this.draft!.filters = filters; this.selected.clear(); this.render(); this.changed();
            });
            this.render();
        });
        $('scan-lists').addEventListener('click', event => {
            const group = (event.target as HTMLElement).closest<HTMLElement>('[data-list]')?.dataset.list;
            if (group && this.preferences) { this.preferences.activeList = group; this.selected.clear(); this.render(); this.changed(); void this.persist(this.preferences); }
        });
        $('scan-sort').addEventListener('change', event => {
            this.preferences!.sort = (event.target as HTMLSelectElement).value; this.changed(); void this.persist(this.preferences!);
        });
        $('scan-date').addEventListener('change', event => { void this.action('scan', { date: (event.target as HTMLSelectElement).value }); });
        $('scan-refresh').addEventListener('click', () => { void this.action('scan', { generate: true }); });
        $('scan-refresh').title = 'Generate and open the latest completed trading date';
        $('scan-tags').addEventListener('click', event => {
            const id = (event.target as HTMLElement).closest<HTMLElement>('[data-tag]')?.dataset.tag;
            if (id) this.protectDraft(() => {
                this.preferences!.activeTag = id; this.resetDraft(); this.selected.clear(); this.render(); this.changed(); void this.persist(this.preferences!);
            });
        });
        $('tag-add').addEventListener('click', () => this.protectDraft(() => {
            this.draft = { ...structuredClone(this.savedTag()), id: crypto.randomUUID(), name: '', role: 'setup' };
            ( $('filter-editor') as HTMLDetailsElement).open = true;
            this.render(); ($('tag-name') as HTMLInputElement).focus();
        }));
        $('tag-name').addEventListener('input', event => { this.draft!.name = (event.target as HTMLInputElement).value; this.render(); });
        $('tag-role').addEventListener('change', event => { this.draft!.role = (event.target as HTMLSelectElement).value as TagRole; this.render(); });
        $('tag-save').addEventListener('click', () => { void this.saveTag(); });
        $('tag-cancel').addEventListener('click', () => { this.resetDraft(); this.discard = undefined; this.deleting = false; this.render(); this.changed(); });
        $('tag-delete').addEventListener('click', () => {
            if (!this.deleting) { this.deleting = true; this.render(); return; }
            const preferences = structuredClone(this.preferences!);
            preferences.tags = preferences.tags.filter(tag => tag.id !== this.draft!.id); preferences.activeTag = 'default';
            void this.persist(preferences, true);
        });
        $('tag-discard').addEventListener('click', () => { const proceed = this.discard; this.discard = undefined; proceed?.(); });
        $('clear-filters').addEventListener('click', () => { this.draft!.filters = {}; this.selected.clear(); this.render(); this.changed(); });
        $('scan-select-all').addEventListener('change', event => {
            this.selected = new Set((event.target as HTMLInputElement).checked ? this.visible(this.rows).map(row => row.symbol) : []);
            this.render(); this.changed();
        });
        $('scan-move').addEventListener('click', event => {
            const target = (event.target as HTMLElement).closest<HTMLElement>('[data-target]')?.dataset.target;
            if (target) void this.move(target);
        });
        window.addEventListener('beforeunload', event => { if (this.dirty()) { event.preventDefault(); event.returnValue = ''; } });
    }

    private savedTag() { return this.preferences!.tags.find(tag => tag.id === this.preferences!.activeTag)!; }
    private resetDraft() { this.draft = { ...structuredClone(this.savedTag()), role: tagRole(this.savedTag()) }; }
    private dirty() { return !!this.draft && !!this.preferences && (this.draft.id !== this.savedTag().id || tagChanged(this.savedTag(), this.draft)); }
    private protectDraft(proceed: () => void) {
        if (this.dirty()) { this.discard = proceed; this.render(); }
        else proceed();
    }

    update(data: ListState) {
        this.enabled = data.app_mode === 'scan'; this.rows = data.board; this.editable = data.editable;
        this.serverRunning = data.scan_running === true;
        $('scan-controls').hidden = !data.preferences;
        for (const id of ['scan-date-row', 'scan-lists', 'scan-batch', 'scan-move']) $(id).hidden = !this.enabled;
        if (!data.preferences) return;
        const key = JSON.stringify(data.preferences);
        if (key !== this.savedKey) {
            const keepDraft = this.dirty() && this.preferences?.activeTag === data.preferences.activeTag &&
                JSON.stringify(this.preferences.tags) === JSON.stringify(data.preferences.tags);
            this.savedKey = key; this.preferences = structuredClone(data.preferences);
            if (!keepDraft) { this.resetDraft(); this.selected.clear(); }
        }
        if (this.date !== data.date) { this.date = data.date!; this.selected.clear(); }
        const select = $('scan-date') as HTMLSelectElement;
        if (JSON.stringify(Array.from(select.options).map(option => option.value)) !== JSON.stringify(data.dates))
            select.replaceChildren(...(data.dates ?? []).map(date => new Option(date, date)));
        select.value = this.date;
        this.selected = new Set([...this.selected].filter(symbol => data.board.some(row => row.symbol === symbol)));
        this.render();
    }

    visible(rows: Ticker[]) {
        if (!this.preferences || !this.draft) return this.enabled ? rows : rows.filter(row => row.status === 'focus' || (row.status === 'excluded' && row.section === 'review'));
        const sort = this.enabled ? this.preferences.sort : 'default';
        const useTags = !this.dirty() && this.draft.id !== 'default';
        return rows.filter(row => (this.enabled ? row.status === this.activeList : row.status === 'focus' || (row.status === 'excluded' && row.section === 'review')) &&
            matchesTag(row, this.draft!, useTags))
            .sort((a,b) => (sort === 'default' ? 0 : rank(a, sort + '_rank') - rank(b, sort + '_rank')) || rank(a,'order_index') - rank(b,'order_index'));
    }

    get activeList() { return this.enabled ? this.preferences?.activeList ?? 'discover' : 'focus'; }
    get busy() { return this.pending; }
    get manualOrder() { return !this.enabled || this.preferences?.sort === 'default'; }
    toggle(symbol: string) { if (this.selected.has(symbol)) this.selected.delete(symbol); else this.selected.add(symbol); this.render(); this.changed(); }

    private async persist(preferences: Preferences, fold = false) {
        this.pending = true; $('scan-error').textContent = ''; this.render();
        try {
            const data = await post<ListState>('preferences', structuredClone(preferences));
            this.savedKey = ''; this.updateList(data);
            if (fold) ($('filter-editor') as HTMLDetailsElement).open = false;
            this.deleting = false;
        } catch (error) {
            this.preferences = JSON.parse(this.savedKey);
            $('scan-error').textContent = (error as Error).message;
        }
        finally { this.pending = false; this.render(); }
    }

    private async saveTag() {
        try {
            const preferences = structuredClone(this.preferences!);
            preferences.tags = withSavedTag(preferences.tags, this.draft!); preferences.activeTag = this.draft!.id;
            await this.persist(preferences, true);
        } catch (error) { $('scan-error').textContent = (error as Error).message; }
    }

    private async action(resource: string, payload: object) {
        this.pending = true; this.render(); $('scan-error').textContent = '';
        try { this.updateList(await post<ListState>(resource, payload)); return true; }
        catch (error) { $('scan-error').textContent = (error as Error).message; return false; }
        finally { this.pending = false; this.render(); }
    }

    private async move(target: string) {
        const tickers = this.visible(this.rows).filter(row => this.selected.has(row.symbol)).map(row => row.ticker);
        if (await this.action('list', { action: 'move', source: this.activeList, target, tickers })) this.selected.clear();
        this.render(); this.changed();
    }

    private render() {
        if (!this.preferences || !this.draft) return;
        const filtered = this.visible(this.rows);
        $('scan-result-count').textContent = `${filtered.length} / ${this.rows.filter(row => row.status === this.activeList).length}`;
        $('scan-lists').querySelectorAll<HTMLButtonElement>('[data-list]').forEach(button => {
            const group = button.dataset.list!, count = this.rows.filter(row => row.status === group && matchesTag(row, this.draft!, !this.dirty())).length;
            button.textContent = group[0].toUpperCase() + group.slice(1) + ' ' + count;
            button.classList.toggle('active', group === this.activeList); button.disabled = this.pending;
        });
        $('scan-tags').replaceChildren(...this.preferences.tags.map(tag => {
            const button = document.createElement('button'); button.dataset.tag = tag.id; button.textContent = tag.name;
            button.classList.toggle('active', tag.id === this.preferences!.activeTag); button.disabled = this.pending; return button;
        }));
        ($('scan-sort') as HTMLSelectElement).value = this.preferences.sort;
        const name = $('tag-name') as HTMLInputElement;
        if (name.value !== this.draft.name) name.value = this.draft.name;
        name.readOnly = this.draft.id === 'default';
        const role = $('tag-role') as HTMLSelectElement; role.value = tagRole(this.draft); role.disabled = this.pending || this.draft.id === 'default';
        $('tag-unsaved').hidden = !this.dirty();
        ($('tag-save') as HTMLButtonElement).disabled = this.pending || !this.dirty();
        ($('tag-add') as HTMLButtonElement).disabled = this.pending || this.preferences.tags.length >= 10;
        $('tag-delete').hidden = this.draft.id === 'default' || !this.preferences.tags.some(tag => tag.id === this.draft!.id);
        $('tag-delete').textContent = this.deleting ? 'Confirm delete' : 'Delete Tag';
        $('tag-discard').hidden = !this.discard;
        $('filter-rules').querySelectorAll<HTMLInputElement | HTMLButtonElement>('input,button').forEach(node => { node.disabled = this.pending; });
        this.panel?.render(this.draft.filters, this.rows);
        $('filter-count').textContent = String(Object.keys(this.draft.filters).length) + ' active';
        const all = $('scan-select-all') as HTMLInputElement, count = filtered.filter(row => this.selected.has(row.symbol)).length;
        all.checked = !!filtered.length && count === filtered.length; all.indeterminate = count > 0 && count < filtered.length; all.disabled = !this.editable || this.pending || !filtered.length;
        $('scan-move').querySelectorAll<HTMLButtonElement>('[data-target]').forEach(button => { button.disabled = !this.editable || this.pending || !count || button.dataset.target === this.activeList; });
        ($('scan-refresh') as HTMLButtonElement).disabled = this.pending || this.serverRunning;
        for (const id of ['scan-date', 'scan-sort', 'tag-name', 'tag-cancel', 'tag-delete', 'clear-filters'])
            ($(id) as HTMLInputElement | HTMLButtonElement).disabled = this.pending;
    }
}

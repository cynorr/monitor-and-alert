import { $ } from './types.js';
import { post } from './api.js';
import { FilterPanel, matchesFilters } from './filters.js';
import { tagChanged, tagFiltersChanged, tagRole, withSavedTag } from './tags.js';
import { TAG_ICONS, tagAppearance, tagLogo } from './tag-appearance.js';
import { countBadge, rowTags } from './board.js';
const rank = (row, field) => typeof row[field] === 'number' ? row[field] : Infinity;
export const matchesTag = (row, tag, useAssigned = true) => (useAssigned && rowTags(row).includes(tag.id)) || matchesFilters(row, tag.filters);
export class ScanControls {
    updateList;
    changed;
    enabled = false;
    selected = new Set();
    preferences;
    draft;
    baseline;
    rows = [];
    savedKey = '';
    date = '';
    editable = false;
    panel;
    pending = false;
    serverRunning = false;
    discard;
    deleting = false;
    holdingSymbols = new Set();
    editorOpen = false;
    constructor(updateList, changed) {
        this.updateList = updateList;
        this.changed = changed;
        $('filter-toggle').addEventListener('click', () => { this.editorOpen = !this.editorOpen; this.render(); });
        $('tag-icon').replaceChildren(...TAG_ICONS.map(([id, name]) => new Option(name, id)));
        void fetch('/v1/filter-catalog').then(response => response.json()).then((catalog) => {
            if (!Array.isArray(catalog))
                return; // The standalone simulator has no Scan endpoints.
            this.panel = new FilterPanel($('filter-rules'), catalog, filters => {
                this.draft.filters = filters;
                this.selected.clear();
                this.render();
                this.changed();
            });
            this.render();
        });
        $('scan-lists').addEventListener('click', event => {
            const group = event.target.closest('[data-list]')?.dataset.list;
            if (group && this.preferences) {
                this.preferences.activeList = group;
                this.selected.clear();
                this.render();
                this.changed();
                void this.persist(this.preferences);
            }
        });
        $('scan-sort').addEventListener('change', event => {
            this.preferences.sort = event.target.value;
            this.changed();
            void this.persist(this.preferences);
        });
        $('scan-date').addEventListener('change', event => { void this.action('scan', { date: event.target.value }); });
        $('scan-refresh').addEventListener('click', () => { void this.action('scan', { generate: true }); });
        $('scan-refresh').title = 'Prepare and open the latest completed trading date; skip completed steps';
        $('scan-tags').addEventListener('click', event => {
            const id = event.target.closest('[data-tag]')?.dataset.tag;
            if (id)
                this.protectDraft(() => {
                    this.preferences.activeTag = this.preferences.activeTag === id ? null : id;
                    this.resetDraft();
                    this.selected.clear();
                    this.render();
                    this.changed();
                    void this.persist(this.preferences);
                });
        });
        $('tag-add').addEventListener('click', () => this.protectDraft(() => {
            this.draft = { ...structuredClone(this.draft), id: crypto.randomUUID(), name: '', role: 'setup' };
            this.editorOpen = true;
            this.render();
            $('tag-name').focus();
        }));
        $('tag-name').addEventListener('input', event => { this.draft.name = event.target.value; this.render(); });
        $('tag-role').addEventListener('change', event => { this.draft.role = event.target.value; this.render(); });
        for (const [id, key] of [['tag-icon', 'icon'], ['tag-color', 'color'], ['tag-background', 'background'], ['tag-background-color', 'backgroundColor']]) {
            $(id).addEventListener(id.includes('color') ? 'input' : 'change', event => {
                const appearance = this.draft.appearance;
                const value = event.target.value;
                if (key === 'icon')
                    appearance.icon = value;
                else if (key === 'background')
                    appearance.background = value;
                else
                    appearance[key] = value;
                this.render();
            });
        }
        $('tag-save').addEventListener('click', () => { void this.saveTag(); });
        $('tag-cancel').addEventListener('click', () => { this.resetDraft(); this.discard = undefined; this.deleting = false; this.render(); this.changed(); });
        $('tag-delete').addEventListener('click', () => {
            if (!this.deleting) {
                this.deleting = true;
                this.render();
                return;
            }
            const preferences = structuredClone(this.preferences);
            preferences.tags = preferences.tags.filter(tag => tag.id !== this.draft.id);
            preferences.activeTag = null;
            void this.persist(preferences, true);
        });
        $('tag-discard').addEventListener('click', () => { const proceed = this.discard; this.discard = undefined; proceed?.(); });
        $('clear-filters').addEventListener('click', () => { this.draft.filters = {}; this.selected.clear(); this.render(); this.changed(); });
        $('scan-select-all').addEventListener('change', event => {
            this.selected = new Set(event.target.checked ? this.visible(this.rows).map(row => row.symbol) : []);
            this.render();
            this.changed();
        });
        $('scan-move').addEventListener('click', event => {
            const target = event.target.closest('[data-target]')?.dataset.target;
            if (target)
                void this.move(target);
        });
        window.addEventListener('beforeunload', event => { if (this.dirty()) {
            event.preventDefault();
            event.returnValue = '';
        } });
    }
    savedTag() { return this.preferences.tags.find(tag => tag.id === this.preferences.activeTag); }
    resetDraft() {
        const tag = this.savedTag() ?? { id: crypto.randomUUID(), name: '', role: 'setup', filters: {} };
        this.baseline = { ...structuredClone(tag), role: tagRole(tag), appearance: tagAppearance(tag) };
        this.draft = structuredClone(this.baseline);
    }
    dirty() { return !!this.draft && !!this.baseline && tagChanged(this.baseline, this.draft); }
    useAssignedTags() {
        const saved = this.savedTag();
        return !!saved && !!this.draft && !tagFiltersChanged(saved, this.draft);
    }
    protectDraft(proceed) {
        if (this.dirty()) {
            this.discard = proceed;
            this.render();
        }
        else
            proceed();
    }
    update(data) {
        this.enabled = data.app_mode === 'scan';
        this.rows = data.board;
        this.editable = data.editable;
        this.holdingSymbols = new Set(data.holding_symbols ?? []);
        this.serverRunning = data.scan_running === true;
        $('scan-controls').hidden = !data.preferences;
        $('list-tools').hidden = !data.preferences;
        for (const id of ['scan-date-row', 'scan-lists', 'scan-batch', 'scan-move'])
            $(id).hidden = !this.enabled;
        if (!data.preferences)
            return;
        const preferences = { ...data.preferences, tags: data.preferences.tags.map(tag => ({ ...tag, appearance: tagAppearance(tag) })) };
        const key = JSON.stringify(preferences);
        if (key !== this.savedKey) {
            const keepDraft = this.dirty() && this.preferences?.activeTag === preferences.activeTag &&
                JSON.stringify(this.preferences.tags) === JSON.stringify(preferences.tags);
            this.savedKey = key;
            this.preferences = structuredClone(preferences);
            if (!keepDraft) {
                this.resetDraft();
                this.selected.clear();
            }
        }
        if (this.date !== data.date) {
            this.date = data.date;
            this.selected.clear();
        }
        const select = $('scan-date');
        if (JSON.stringify(Array.from(select.options).map(option => option.value)) !== JSON.stringify(data.dates))
            select.replaceChildren(...(data.dates ?? []).map(date => new Option(date, date)));
        select.value = this.date;
        this.selected = new Set([...this.selected].filter(symbol => this.available(data.board).some(row => row.symbol === symbol)));
        this.render();
    }
    visible(rows) {
        rows = this.available(rows);
        const sort = this.enabled ? this.preferences?.sort ?? 'default' : 'default';
        const inList = (row) => this.enabled ? row.status === this.activeList : row.status === 'focus' || (row.status === 'excluded' && row.section === 'review');
        const useTags = this.preferences ? this.useAssignedTags() : false;
        return rows.filter(row => inList(row) && (!this.draft || matchesTag(row, this.draft, useTags)))
            .sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned) ||
            (a.pinned && b.pinned ? rank(a, 'pin_index') - rank(b, 'pin_index') :
                (sort === 'default' ? 0 : rank(a, sort + '_rank') - rank(b, sort + '_rank')) || rank(a, 'order_index') - rank(b, 'order_index')));
    }
    isHolding(symbol) { return this.holdingSymbols.has(symbol); }
    available(rows) { return rows.filter(row => !this.isHolding(row.symbol)); }
    get activeList() { return this.enabled ? this.preferences?.activeList ?? 'discover' : 'focus'; }
    async showFocus() {
        if (!this.preferences)
            return;
        this.preferences.activeList = 'focus';
        this.preferences.activeTag = null;
        this.resetDraft();
        this.render();
        await this.persist(this.preferences);
    }
    get busy() { return this.pending; }
    get manualOrder() { return !this.enabled || this.preferences?.sort === 'default'; }
    toggle(symbol) { if (this.selected.has(symbol))
        this.selected.delete(symbol);
    else
        this.selected.add(symbol); this.render(); this.changed(); }
    async persist(preferences, fold = false) {
        this.pending = true;
        $('scan-error').textContent = '';
        this.render();
        try {
            const data = await post('preferences', structuredClone(preferences));
            this.savedKey = '';
            this.updateList(data);
            if (fold)
                this.editorOpen = false;
            this.deleting = false;
        }
        catch (error) {
            this.preferences = JSON.parse(this.savedKey);
            $('scan-error').textContent = error.message;
        }
        finally {
            this.pending = false;
            this.render();
        }
    }
    async saveTag() {
        try {
            const preferences = structuredClone(this.preferences);
            preferences.tags = withSavedTag(preferences.tags, this.draft);
            preferences.activeTag = this.draft.id;
            await this.persist(preferences, true);
        }
        catch (error) {
            $('scan-error').textContent = error.message;
        }
    }
    async action(resource, payload) {
        this.pending = true;
        this.render();
        $('scan-error').textContent = '';
        try {
            this.updateList(await post(resource, payload));
            return true;
        }
        catch (error) {
            $('scan-error').textContent = error.message;
            return false;
        }
        finally {
            this.pending = false;
            this.render();
        }
    }
    async move(target) {
        const tickers = this.visible(this.rows).filter(row => this.selected.has(row.symbol)).map(row => row.ticker);
        if (await this.action('list', { action: 'move', source: this.activeList, target, tickers }))
            this.selected.clear();
        this.render();
        this.changed();
    }
    render() {
        if (!this.preferences || !this.draft)
            return;
        $('filter-editor').hidden = !this.editorOpen;
        $('filter-toggle').setAttribute('aria-expanded', String(this.editorOpen));
        const available = this.available(this.rows);
        const filtered = this.visible(this.rows);
        $('scan-result-count').replaceChildren(countBadge(filtered.length), ' / ', countBadge(available.filter(row => row.status === this.activeList).length));
        $('scan-lists').querySelectorAll('[data-list]').forEach(button => {
            const group = button.dataset.list, count = available.filter(row => row.status === group && matchesTag(row, this.draft, this.useAssignedTags())).length;
            button.replaceChildren(group[0].toUpperCase() + group.slice(1), countBadge(count));
            button.classList.toggle('active', group === this.activeList);
            button.disabled = this.pending;
        });
        const displayPriority = (tag) => tagRole(tag) === 'setup' ? 0 : ['extended', 'broken', 'under50'].includes(tagRole(tag)) ? 2 : 1;
        $('scan-tags').replaceChildren(...[...this.preferences.tags].sort((a, b) => displayPriority(a) - displayPriority(b)).map(tag => {
            const button = document.createElement('button');
            button.dataset.tag = tag.id;
            button.textContent = tag.name;
            button.classList.toggle('active', tag.id === this.preferences.activeTag);
            button.disabled = this.pending;
            return button;
        }));
        $('scan-sort').value = this.preferences.sort;
        const name = $('tag-name');
        if (name.value !== this.draft.name)
            name.value = this.draft.name;
        const role = $('tag-role');
        role.value = tagRole(this.draft);
        role.disabled = this.pending;
        const appearance = this.draft.appearance;
        for (const [id, value] of [['tag-icon', appearance.icon], ['tag-color', appearance.color], ['tag-background', appearance.background], ['tag-background-color', appearance.backgroundColor]])
            $(id).value = value;
        $('tag-background-color').disabled = this.pending || appearance.background === 'transparent';
        $('tag-preview').replaceChildren(tagLogo(this.draft));
        $('tag-unsaved').hidden = !this.dirty();
        $('tag-save').disabled = this.pending || !this.dirty();
        $('tag-add').disabled = this.pending || this.preferences.tags.length >= 10;
        $('tag-delete').hidden = !this.preferences.tags.some(tag => tag.id === this.draft.id);
        $('tag-delete').textContent = this.deleting ? 'Confirm delete' : 'Delete Tag';
        $('tag-discard').hidden = !this.discard;
        $('filter-rules').querySelectorAll('input,button').forEach(node => { node.disabled = this.pending; });
        this.panel?.render(this.draft.filters, available);
        $('filter-count').replaceChildren(countBadge(Object.keys(this.draft.filters).length));
        const all = $('scan-select-all'), count = filtered.filter(row => this.selected.has(row.symbol)).length;
        all.checked = !!filtered.length && count === filtered.length;
        all.indeterminate = count > 0 && count < filtered.length;
        all.disabled = !this.editable || this.pending || !filtered.length;
        $('scan-move').querySelectorAll('[data-target]').forEach(button => { button.disabled = !this.editable || this.pending || !count || button.dataset.target === this.activeList; });
        $('scan-refresh').disabled = this.pending || this.serverRunning;
        for (const id of ['scan-date', 'scan-sort', 'tag-name', 'tag-cancel', 'tag-delete', 'clear-filters', 'tag-icon', 'tag-color', 'tag-background'])
            $(id).disabled = this.pending;
    }
}

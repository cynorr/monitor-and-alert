import type { Ticker } from './types.js';
import { tagRole, type Tag } from './tags.js';

export type ListSection = { list: string; id: string; name: string; key: string; pinned?: boolean };
export type ListColumn = { field: string; label: string; width: string };
export function listColumns(scan: boolean, regular: boolean): ListColumn[] {
    const symbol = { field: 'symbol', label: 'Symbol', width: `minmax(${scan ? 84 : 100}px,1.1fr)` };
    const price = { field: 'price', label: scan ? 'Price' : 'Last', width: 'minmax(62px,.7fr)' };
    const tags = { field: 'tags', label: 'Tags', width: 'minmax(110px,1.15fr)' };
    const actions = { field: 'actions', label: '', width: '60px' };
    if (scan) return [symbol, price, { field: 'adr', label: 'ADR20', width: 'minmax(64px,.7fr)' },
        { field: 'adv', label: 'ADV20', width: 'minmax(68px,.8fr)' },
        { field: 'growth', label: 'Growth', width: 'minmax(144px,1.5fr)' }, tags, actions];
    return [symbol, price, { field: 'change', label: 'Chg%', width: 'minmax(64px,.7fr)' },
        ...(!regular ? [{ field: 'ext', label: 'Ext', width: 'minmax(68px,.8fr)' }] : []), tags, actions];
}
export const rowTags = (row: Ticker) => row.tags ?? row.tag_ids ?? [];
export const potentialTags = (tags: Tag[]) => tags.filter(tag => tagRole(tag) === 'setup');
export const collapseKey = (scan: boolean, key: string) => `${scan ? 'scan' : 'monitor'}:${key}`;
export const sectionKey = (row: Ticker) => `${row.status}:${row.section ?? 'unclassified'}`;
export function listSections(scan: boolean, list: string, tags: Tag[]): ListSection[] {
    const sections = (name: string) => potentialTags(tags).map(tag => ({ list: name, id: tag.id, name: tag.name, key: `${name}:${tag.id}` }))
        .concat({ list: name, id: 'unclassified', name: 'Unclassified', key: `${name}:unclassified` });
    if (!scan) return sections('focus');
    if (list !== 'excluded') return sections(list);
    return ['broken', 'extended', 'under50', 'hidden'].map(id => ({ list, id, name: id === 'under50' ? 'Under-50' : id[0].toUpperCase() + id.slice(1), key: `${list}:${id}` }));
}

export function growthValue(value: unknown) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
    return value >= 100 ? (1 + value / 100).toFixed(1) + 'x' : value.toFixed(1).replace(/\.0$/, '') + '%';
}
export function countBadge(count: number) {
    const badge = document.createElement('span'); badge.className = 'count-badge'; badge.textContent = String(count);
    return badge;
}

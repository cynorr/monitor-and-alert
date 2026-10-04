import type { Ticker } from './types.js';
import { tagRole, type Tag } from './tags.js';

export type ListSection = { list: string; id: string; name: string; key: string };
export const rowTags = (row: Ticker) => row.tags ?? row.tag_ids ?? [];
export const potentialTags = (tags: Tag[]) => tags.filter(tag => tagRole(tag) === 'setup');
export const collapseKey = (scan: boolean, key: string) => `${scan ? 'scan' : 'monitor'}:${key}`;
export const isReviewSelection = (row: Ticker | undefined, source: 'watchlist' | 'holdings') =>
    source === 'watchlist' && row?.status === 'excluded' && row.section === 'review';
export const sectionKey = (row: Ticker) => `${row.status}:${row.section ?? 'unclassified'}`;
export function listSections(scan: boolean, list: string, tags: Tag[]): ListSection[] {
    const sections = (name: string) => potentialTags(tags).map(tag => ({ list: name, id: tag.id, name: tag.name, key: `${name}:${tag.id}` }))
        .concat({ list: name, id: 'unclassified', name: 'Unclassified', key: `${name}:unclassified` });
    if (!scan) return sections('focus').concat({ list: 'excluded', id: 'review', name: 'Review', key: 'excluded:review' });
    if (list !== 'excluded') return sections(list);
    return ['review', 'broken', 'extended', 'hidden'].map(id => ({ list, id, name: id[0].toUpperCase() + id.slice(1), key: `${list}:${id}` }));
}

export function growthValue(value: unknown) {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
    return value >= 100 ? (1 + value / 100).toFixed(1) + 'x' : value.toFixed(1).replace(/\.0$/, '') + '%';
}
export function countBadge(count: number) {
    const badge = document.createElement('span'); badge.className = 'count-badge'; badge.textContent = String(count);
    return badge;
}

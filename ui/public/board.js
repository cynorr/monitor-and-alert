import { tagRole } from './tags.js';
export const rowTags = (row) => row.tags ?? row.tag_ids ?? [];
export const potentialTags = (tags) => tags.filter(tag => tagRole(tag) === 'setup');
export const collapseKey = (scan, key) => `${scan ? 'scan' : 'monitor'}:${key}`;
export const isReviewSelection = (row, source) => source === 'watchlist' && row?.status === 'excluded' && row.section === 'review';
export const sectionKey = (row) => `${row.status}:${row.section ?? 'unclassified'}`;
export function listSections(scan, list, tags) {
    const sections = (name) => potentialTags(tags).map(tag => ({ list: name, id: tag.id, name: tag.name, key: `${name}:${tag.id}` }))
        .concat({ list: name, id: 'unclassified', name: 'Unclassified', key: `${name}:unclassified` });
    if (!scan)
        return sections('focus').concat({ list: 'excluded', id: 'review', name: 'Review', key: 'excluded:review' });
    if (list !== 'excluded')
        return sections(list);
    return ['review', 'broken', 'extended', 'under50', 'hidden'].map(id => ({ list, id, name: id === 'under50' ? 'Under-50' : id[0].toUpperCase() + id.slice(1), key: `${list}:${id}` }));
}
export function growthValue(value) {
    if (typeof value !== 'number' || !Number.isFinite(value))
        return '—';
    return value >= 100 ? (1 + value / 100).toFixed(1) + 'x' : value.toFixed(1).replace(/\.0$/, '') + '%';
}
export function countBadge(count) {
    const badge = document.createElement('span');
    badge.className = 'count-badge';
    badge.textContent = String(count);
    return badge;
}

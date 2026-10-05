import type { Filters } from './filters.js';
import { tagAppearance, type TagAppearance } from './tag-appearance.js';
export type TagRole = 'setup' | 'extended' | 'broken' | 'label';
export type Tag = { id: string; name: string; filters: Filters; role?: TagRole; appearance?: TagAppearance };
export const tagRole = (tag: Tag): TagRole => tag.role ?? (tag.id === 'default' ? 'label' : ['extended','broken'].includes(tag.name.toLowerCase()) ? tag.name.toLowerCase() as TagRole : 'setup');
export type Preferences = { activeList: string; sort: string; activeTag: string; tags: Tag[] };
export const tagFiltersChanged = (saved: Tag, draft: Tag) => saved.id !== draft.id || JSON.stringify(saved.filters) !== JSON.stringify(draft.filters);
export const tagChanged = (saved: Tag, draft: Tag) => saved.name !== draft.name || tagRole(saved) !== tagRole(draft) || tagFiltersChanged(saved, draft) ||
    JSON.stringify(tagAppearance(saved)) !== JSON.stringify(tagAppearance(draft));

export function withSavedTag(tags: Tag[], draft: Tag) {
    const name = draft.name.trim();
    if (!name || name.length > 24 || tags.some(tag => tag.id !== draft.id && tag.name.toLowerCase() === name.toLowerCase()))
        throw new Error('Use a unique name of 1–24 characters');
    if (tags.length >= 10 && !tags.some(tag => tag.id === draft.id)) throw new Error('Maximum 10 tags');
    const saved = { ...structuredClone(draft), name, appearance: tagAppearance(draft) };
    return tags.some(tag => tag.id === draft.id) ? tags.map(tag => tag.id === draft.id ? saved : tag) : [...tags, saved];
}

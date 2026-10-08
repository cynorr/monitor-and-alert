import { tagAppearance } from './tag-appearance.js';
export function tagRole(tag) {
    if (tag.role)
        return tag.role;
    if (tag.id === 'default')
        return 'label';
    const name = tag.name.trim().toLowerCase();
    return name === 'extended' || name === 'broken' ? name : name === 'under-50' ? 'under50' : 'setup';
}
export const tagFiltersChanged = (saved, draft) => saved.id !== draft.id || JSON.stringify(saved.filters) !== JSON.stringify(draft.filters);
export const tagChanged = (saved, draft) => saved.name !== draft.name || tagRole(saved) !== tagRole(draft) || tagFiltersChanged(saved, draft) ||
    JSON.stringify(tagAppearance(saved)) !== JSON.stringify(tagAppearance(draft));
export function withSavedTag(tags, draft) {
    const name = draft.name.trim();
    if (!name || name.length > 24 || tags.some(tag => tag.id !== draft.id && tag.name.toLowerCase() === name.toLowerCase()))
        throw new Error('Use a unique name of 1–24 characters');
    if (tags.length >= 10 && !tags.some(tag => tag.id === draft.id))
        throw new Error('Maximum 10 tags');
    const saved = { ...structuredClone(draft), name, appearance: tagAppearance(draft) };
    return tags.some(tag => tag.id === draft.id) ? tags.map(tag => tag.id === draft.id ? saved : tag) : [...tags, saved];
}

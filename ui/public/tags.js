export const tagChanged = (saved, draft) => saved.name !== draft.name || JSON.stringify(saved.filters) !== JSON.stringify(draft.filters);
export function withSavedTag(tags, draft) {
    const name = draft.name.trim();
    if (!name || name.length > 24 || tags.some(tag => tag.id !== draft.id && tag.name.toLowerCase() === name.toLowerCase()))
        throw new Error('Use a unique name of 1–24 characters');
    if (tags.length >= 10 && !tags.some(tag => tag.id === draft.id))
        throw new Error('Maximum 10 tags');
    const saved = { ...structuredClone(draft), name };
    return tags.some(tag => tag.id === draft.id) ? tags.map(tag => tag.id === draft.id ? saved : tag) : [...tags, saved];
}

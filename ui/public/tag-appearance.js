export const TAG_ICONS = [
    ['surf', 'Surf'], ['bounce', 'Bounce'], ['prior-run', 'Prior-run'],
    ['orderly-pullback', 'Orderly-pullback'], ['extended', 'Extended'], ['broken', 'Broken'], ['under50', 'Under-50'], ['label', 'Label'],
];
const paths = {
    surf: '<path d="M3 8L10 5L16 7L24 3L33 4"/><path class="tag-ma" d="M3 16C15 16 21 11 33 10"/>',
    bounce: '<path d="M3 2L15 16L31 2M24 2H31V9"/><path class="tag-ma" d="M3 16Q18 16 33 13"/>',
    'prior-run': '<path d="M3 16H11V12H19V7H27V2H33"/>',
    'orderly-pullback': '<path d="M3 3H11V7H19V11H27V15H33"/>',
    extended: '<path d="M3 18C25 18 32 18 33 2"/>',
    broken: '<path d="M3 2L12 3L20 13L32 17M27 17H32V12"/><path class="tag-ma" d="M3 7H33"/>',
    under50: '<path class="tag-ma" d="M2 4Q6 0 10 4T18 4T26 4T34 4"/><rect x="5" y="10" width="10" height="8" rx="3"/><rect x="21" y="10" width="10" height="8" rx="3"/><path d="M15 12Q18 9 21 12M2 12H5M31 12H34"/>',
    label: '<path d="M3 3H22L33 10L22 17H3Z"/><circle cx="24" cy="10" r="1.5"/>',
};
// Legacy names provide initial defaults only; saved appearance always wins.
export function tagAppearance(tag) {
    if (tag.appearance)
        return { ...tag.appearance };
    const name = tag.name.toLowerCase().replace(/[\s_-]/g, '');
    const icon = tag.role === 'under50' || name === 'under50' ? 'under50' : name.startsWith('surf') ? 'surf' : name.startsWith('bounce') ? 'bounce' :
        name === 'priorrun' ? 'prior-run' : name === 'orderlypullback' ? 'orderly-pullback' :
            name === 'extended' ? 'extended' : name === 'broken' ? 'broken' : 'label';
    const ma = /(?:surf|bounce)(10|20|50)$/.exec(name)?.[1];
    return { icon, color: ma === '10' ? '#2962ff' : ma === '20' ? '#e4b400' : ma === '50' || icon === 'under50' ? '#e53935' : '#64748b',
        background: 'frosted', backgroundColor: '#e5e7eb' };
}
export function tagLogo(tag, manual = false) {
    const appearance = tagAppearance(tag);
    const logo = document.createElement('span');
    logo.className = 'tag-logo';
    logo.dataset.icon = appearance.icon;
    logo.dataset.background = appearance.background;
    logo.style.color = appearance.color;
    // The user chooses a hue; opacity stays subtle so tags remain secondary.
    logo.style.backgroundColor = appearance.background === 'transparent' ? 'transparent' : appearance.backgroundColor + '33';
    const label = tag.name + (manual ? ' · Manual · today only' : '');
    logo.title = label;
    logo.setAttribute('role', 'img');
    logo.setAttribute('aria-label', label);
    logo.innerHTML = '<svg viewBox="0 0 36 20" fill="none" stroke="currentColor" aria-hidden="true">' + paths[appearance.icon] + '</svg>';
    return logo;
}

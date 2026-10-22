export const compareRank = (a, b) => {
    for (let i = 0; i < 3; i++) {
        const difference = (b?.rank[i] ?? 0) - (a?.rank[i] ?? 0);
        if (difference)
            return difference;
    }
    return 0;
};
export function rankedRows(rows, states) {
    return [...rows].sort((a, b) => a.pinned || b.pinned ?
        a.pinned && b.pinned ? (a.pin_index ?? 0) - (b.pin_index ?? 0) : a.pinned ? -1 : 1 :
        compareRank(states[a.symbol], states[b.symbol]));
}
export function stateAppearance(row, value) {
    row.dataset.intraday = value?.state ?? 'neutral';
}
export function adrText(value) {
    if (!value?.state || value.up_adr == null || value.down_adr == null)
        return '—';
    const down = value.state.startsWith('down') ||
        (value.state === 'neutral' && value.role === 'holding' && value.down_adr > value.up_adr);
    return `${down ? '↓' : '↑'}${(down ? value.down_adr : value.up_adr).toFixed(2)}×`;
}
export function adrTitle(value) {
    return value?.up_adr != null && value.down_adr != null && value.adr20 != null ? `Up ${value.up_adr.toFixed(2)}× · Down ${value.down_adr.toFixed(2)}× · Previous-day ADR20 ${value.adr20.toFixed(2)}%` : 'Waiting for current Regular quote and historical ADR20';
}
export function volumeBadge(cell, value) {
    let badge = cell.querySelector('.volume-badge');
    if (!badge) {
        badge = document.createElement('span');
        badge.className = 'volume-badge';
        cell.replaceChildren(badge);
    }
    badge.textContent = value?.ratio == null ? '—' : value.ratio.toFixed(1) + '×';
    badge.dataset.level = String(value?.level ?? 0);
    badge.title = value ? `${value.window ? value.window + ' · ' : ''}Volume ${value.actual?.toLocaleString('en-US') ?? '—'} · Historical mean ${value.average?.toLocaleString('en-US', { maximumFractionDigits: 0 }) ?? '—'} · ${value.samples}/5 sessions · Historical partial 5m is interpolated` : 'Waiting for matching intraday volume';
}

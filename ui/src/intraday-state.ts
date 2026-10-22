import type { Ticker } from './types.js';

export type VolumeState = { ratio: number | null; actual: number | null; average: number | null; samples: number; level: number; window?: string };
export type SymbolState = {
    role: 'candidate' | 'holding'; state: 'neutral' | 'up-notice' | 'up-urgent' | 'down-notice' | 'down-urgent' | null;
    above_open: boolean | null; adr20: number | null; up_adr: number | null; down_adr: number | null;
    up_level: number | null; down_level: number | null; rank: number[]; timestamp: number | null;
    cum_vol: VolumeState | null; local_vol: VolumeState | null;
};
export type IntradayState = { enabled: boolean; symbols: Record<string, SymbolState> };
export const compareRank = (a?: SymbolState, b?: SymbolState) => {
    for (let i = 0; i < 3; i++) {
        const difference = (b?.rank[i] ?? 0) - (a?.rank[i] ?? 0);
        if (difference) return difference;
    }
    return 0;
};
export function rankedRows(rows: Ticker[], states: Record<string, SymbolState>) {
    return [...rows].sort((a, b) => a.pinned || b.pinned ?
        a.pinned && b.pinned ? (a.pin_index ?? 0) - (b.pin_index ?? 0) : a.pinned ? -1 : 1 :
        compareRank(states[a.symbol], states[b.symbol]));
}
export function stateAppearance(row: HTMLElement, value?: SymbolState) {
    row.dataset.intraday = value?.state ?? 'neutral';
}
export function adrText(value?: SymbolState) {
    if (!value?.state || value.up_adr == null || value.down_adr == null) return '—';
    const down = value.state.startsWith('down') ||
        (value.state === 'neutral' && value.role === 'holding' && value.down_adr > value.up_adr);
    return `${down ? '↓' : '↑'}${(down ? value.down_adr : value.up_adr).toFixed(2)}×`;
}
export function adrTitle(value?: SymbolState) {
    return value?.up_adr != null && value.down_adr != null && value.adr20 != null ? `Up ${value.up_adr.toFixed(2)}× · Down ${value.down_adr.toFixed(2)}× · Previous-day ADR20 ${value.adr20.toFixed(2)}%` : 'Waiting for current Regular quote and historical ADR20';
}
export function volumeBadge(cell: HTMLElement, value?: VolumeState | null) {
    let badge = cell.querySelector<HTMLElement>('.volume-badge');
    if (!badge) { badge = document.createElement('span'); badge.className = 'volume-badge'; cell.replaceChildren(badge); }
    badge.textContent = value?.ratio == null ? '—' : value.ratio.toFixed(1) + '×';
    badge.dataset.level = String(value?.level ?? 0);
    badge.title = value ? `${value.window ? value.window + ' · ' : ''}Volume ${value.actual?.toLocaleString('en-US') ?? '—'} · Historical mean ${value.average?.toLocaleString('en-US', { maximumFractionDigits: 0 }) ?? '—'} · ${value.samples}/5 sessions · Historical partial 5m is interpolated` : 'Waiting for matching intraday volume';
}

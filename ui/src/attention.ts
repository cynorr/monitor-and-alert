import type { AlertState, AlertNotice, AlertPlayback } from './alerts.js';

export type Attention = { unread: Map<string, AlertNotice>; playing: Map<string, AlertPlayback> };
export const attentionState = (state?: AlertState): Attention => ({
    unread: new Map(state?.unread.map(notice => [notice.symbol, notice]) ?? []),
    playing: new Map(state?.sound.playing.map(beat => [beat.symbol, beat]) ?? []),
});
export function attentionAppearance(row: HTMLElement, symbol: string, state: Attention) {
    const notice = state.unread.get(symbol), beat = state.playing.get(symbol);
    if (notice) row.dataset.alert = `${notice.direction}-${notice.level === 2 ? 'urgent' : 'notice'}`;
    else delete row.dataset.alert;
    row.title = notice ? `Unread ${notice.direction === 'up' ? 'upward' : 'downward'} alert · ${notice.level === 2 ? 'Urgent' : 'Notice'}` : '';
    const wave = row.querySelector<HTMLElement>('.price-wave');
    if (!wave || !notice || !beat || beat.fired_at !== notice.fired_at || wave.dataset.pulse === String(beat.pulse_at)) return;
    wave.dataset.pulse = String(beat.pulse_at);
    const elapsed = (Date.now() / 1000 - beat.pulse_at) * 1000;
    if (elapsed >= 190) return;
    const pulse = wave.animate([{ opacity: .35 }, { opacity: 1, offset: .25 }, { opacity: .85 }], { duration: 190 });
    pulse.currentTime = Math.max(0, elapsed);
}

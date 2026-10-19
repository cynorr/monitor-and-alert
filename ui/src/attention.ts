import type { AlertState } from './alerts.js';

export type Attention = { unread: Set<string>; playing: Set<string> };
export const attentionState = (state?: AlertState): Attention => ({
    unread: new Set(state?.unread ?? []), playing: new Set(state?.sound.playing ?? []),
});
export function attentionAppearance(node: HTMLElement, symbol: string, state: Attention) {
    node.classList.toggle('attention', state.unread.has(symbol));
    node.classList.toggle('ringing', state.unread.has(symbol) && state.playing.has(symbol));
}

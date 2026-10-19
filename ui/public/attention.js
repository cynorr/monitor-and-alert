export const attentionState = (state) => ({
    unread: new Set(state?.unread ?? []), playing: new Set(state?.sound.playing ?? []),
});
export function attentionAppearance(node, symbol, state) {
    node.classList.toggle('attention', state.unread.has(symbol));
    node.classList.toggle('ringing', state.unread.has(symbol) && state.playing.has(symbol));
}

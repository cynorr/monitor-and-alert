export const attentionState = (state) => ({
    unread: new Map(state?.unread.map(notice => [notice.symbol, notice]) ?? []),
    playing: new Map(state?.sound.playing.map(beat => [beat.symbol, beat]) ?? []),
    eligible: new Set(state?.eligible_symbols),
    paused: new Set(state?.paused_auto_symbols),
});
let autoAlertIconId = 0;
export function autoAlertButton(symbol, toggle) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'icon-button auto-alert';
    button.hidden = true;
    button.setAttribute('aria-keyshortcuts', 'M');
    const mask = `auto-alert-cut-${++autoAlertIconId}`;
    const slash = 'M4 4l16 16';
    button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">
        <mask id="${mask}" maskUnits="userSpaceOnUse" x="0" y="0" width="24" height="24">
            <rect width="24" height="24" fill="white" stroke="none"/>
            <path d="${slash}" stroke="black" stroke-width="4.4"/>
        </mask>
        <path class="auto-alert-bell" mask="url(#${mask})" d="M18 9a6 6 0 0 0-12 0v4l-2 3h16l-2-3V9M10 20h4"/>
        <path class="auto-alert-slash" d="${slash}"/>
    </svg>`;
    button.onclick = event => { event.stopPropagation(); toggle(symbol); };
    return button;
}
export function attentionAppearance(row, symbol, state) {
    const button = row.querySelector('.auto-alert');
    if (button) {
        const paused = state.paused.has(symbol);
        button.hidden = !state.eligible.has(symbol);
        button.setAttribute('aria-pressed', String(paused));
        button.title = paused ? 'Resume Auto Alerts (M)' : 'Pause Auto Alerts Today (M)';
        button.setAttribute('aria-label', button.title);
    }
    const notice = state.unread.get(symbol), beat = state.playing.get(symbol);
    if (notice)
        row.dataset.alert = `${notice.direction}-${notice.level === 2 ? 'urgent' : 'notice'}`;
    else
        delete row.dataset.alert;
    row.title = notice ? `Unread ${notice.direction === 'up' ? 'upward' : 'downward'} alert · ${notice.level === 2 ? 'Urgent' : 'Notice'}` : '';
    const wave = row.querySelector('.price-wave');
    if (!wave || !notice || !beat || beat.fired_at !== notice.fired_at || wave.dataset.pulse === String(beat.pulse_at))
        return;
    wave.dataset.pulse = String(beat.pulse_at);
    const elapsed = (Date.now() / 1000 - beat.pulse_at) * 1000;
    if (elapsed >= 190)
        return;
    const pulse = wave.animate([{ opacity: .35 }, { opacity: 1, offset: .25 }, { opacity: .85 }], { duration: 190 });
    pulse.currentTime = Math.max(0, elapsed);
}

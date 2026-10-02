import { $ } from './types.js';
export function initLayout() {
    const root = $('workspace'), minimum = [320, 320, 600];
    let ratios = null, holdingsWidth = 600;
    function widths() {
        const available = root.clientWidth - 44;
        if (!ratios) {
            const chart = Math.max(minimum[0], (available - minimum[2]) / 2);
            return [chart, chart, minimum[2]];
        }
        const extra = Math.max(0, available - minimum.reduce((a, b) => a + b, 0));
        const wanted = ratios.map((r, i) => Math.max(0, r * available - minimum[i]));
        const total = wanted.reduce((a, b) => a + b, 0) || 1;
        return minimum.map((m, i) => m + extra * wanted[i] / total);
    }
    function paint(values = widths()) {
        root.style.minWidth = `${minimum.reduce((a, b) => a + b, 0) + 44}px`;
        root.style.gridTemplateColumns = root.dataset.mode === 'scan'
            ? `${values[0] + values[1] + 12}px 12px ${values[2]}px`
            : `${values[0]}px 12px ${values[1]}px 12px ${values[2]}px`;
    }
    function remember(values) { const total = values.reduce((a, b) => a + b, 0); ratios = values.map(v => v / total); }
    for (let index = 0; index < 2; index++) {
        const handle = $('divider-' + index);
        handle.addEventListener('pointerdown', event => {
            const start = event.clientX, initial = widths();
            handle.setPointerCapture(event.pointerId);
            document.body.classList.add('resizing');
            const move = (e) => { const delta = Math.max(minimum[index] - initial[index], Math.min(initial[index + 1] - minimum[index + 1], e.clientX - start)); const next = initial.slice(); next[index] += delta; next[index + 1] -= delta; remember(next); paint(next); };
            const end = () => { handle.removeEventListener('pointermove', move); document.body.classList.remove('resizing'); };
            handle.addEventListener('pointermove', move);
            handle.addEventListener('lostpointercapture', end, { once: true });
        });
        handle.addEventListener('dblclick', () => { ratios = null; paint(); });
        handle.addEventListener('keydown', event => {
            if (!['ArrowLeft', 'ArrowRight'].includes(event.key))
                return;
            event.preventDefault();
            const values = widths();
            const delta = Math.max(minimum[index] - values[index], Math.min(values[index + 1] - minimum[index + 1], event.key === 'ArrowRight' ? 12 : -12));
            values[index] += delta;
            values[index + 1] -= delta;
            remember(values);
            paint(values);
        });
    }
    new ResizeObserver(() => paint()).observe(root);
    paint();
    return { setMode(mode) {
            if (root.dataset.mode === mode)
                return;
            root.dataset.mode = mode;
            minimum[2] = mode === 'scan' ? 400 : holdingsWidth;
            $('divider-1').setAttribute('aria-label', mode === 'scan' ? 'Resize Daily and watchlist' : 'Resize Intraday and watchlist');
            paint();
        }, setHoldingsWidth(width) {
            if (holdingsWidth === width)
                return;
            holdingsWidth = width;
            if (root.dataset.mode !== 'scan') {
                minimum[2] = width;
                paint();
            }
        } };
}

import { $ } from './types.js';
// Share the default list proportion across Scan and Monitor.
const LIST_WIDTH_RATIO = 0.32;
const LIST_MIN_WIDTH = 680;
const CHART_MIN_WIDTH = 320;
const DIVIDER_WIDTH = 12;
const WORKSPACE_PADDING = 20;
export function initLayout() {
    const root = $('workspace');
    let ratios = null, holdingsWidth = LIST_MIN_WIDTH;
    const isScan = () => root.dataset.mode === 'scan';
    function minimum() {
        return isScan()
            ? [CHART_MIN_WIDTH, LIST_MIN_WIDTH]
            : [CHART_MIN_WIDTH, CHART_MIN_WIDTH, Math.max(LIST_MIN_WIDTH, holdingsWidth)];
    }
    function widths() {
        const minima = minimum();
        const available = Math.max(minima.reduce((a, b) => a + b, 0), root.clientWidth - WORKSPACE_PADDING - DIVIDER_WIDTH * (minima.length - 1));
        if (!ratios) {
            const list = Math.max(minima[minima.length - 1], Math.min(available * LIST_WIDTH_RATIO, available - CHART_MIN_WIDTH * (minima.length - 1)));
            const chart = (available - list) / (minima.length - 1);
            return isScan() ? [chart, list] : [chart, chart, list];
        }
        const extra = Math.max(0, available - minima.reduce((a, b) => a + b, 0));
        const wanted = ratios.map((r, i) => Math.max(0, r * available - minima[i]));
        const total = wanted.reduce((a, b) => a + b, 0) || 1;
        return minima.map((m, i) => m + extra * wanted[i] / total);
    }
    function paint(values = widths()) {
        const minima = minimum();
        root.style.minWidth = `${minima.reduce((a, b) => a + b, 0) + WORKSPACE_PADDING + DIVIDER_WIDTH * (minima.length - 1)}px`;
        root.style.gridTemplateColumns = values.map(value => `${value}px`).join(` ${DIVIDER_WIDTH}px `);
    }
    function remember(values) { const total = values.reduce((a, b) => a + b, 0); ratios = values.map(v => v / total); }
    function resized(values, index, delta) {
        const minima = minimum();
        const movement = Math.max(minima[index] - values[index], Math.min(values[index + 1] - minima[index + 1], delta));
        const next = values.slice();
        next[index] += movement;
        next[index + 1] -= movement;
        remember(next);
        paint(next);
    }
    for (let index = 0; index < 2; index++) {
        const handle = $('divider-' + index);
        handle.addEventListener('pointerdown', event => {
            if (isScan() && index === 0)
                return;
            const adjacent = isScan() ? 0 : index;
            const start = event.clientX, initial = widths();
            handle.setPointerCapture(event.pointerId);
            document.body.classList.add('resizing');
            const move = (e) => resized(initial, adjacent, e.clientX - start);
            const end = () => { handle.removeEventListener('pointermove', move); document.body.classList.remove('resizing'); };
            handle.addEventListener('pointermove', move);
            handle.addEventListener('lostpointercapture', end, { once: true });
        });
        handle.addEventListener('dblclick', () => { ratios = null; paint(); });
        handle.addEventListener('keydown', event => {
            if (!['ArrowLeft', 'ArrowRight'].includes(event.key))
                return;
            if (isScan() && index === 0)
                return;
            event.preventDefault();
            resized(widths(), isScan() ? 0 : index, event.key === 'ArrowRight' ? 12 : -12);
        });
    }
    new ResizeObserver(() => paint()).observe(root);
    paint();
    return { setMode(mode) {
            if (root.dataset.mode === mode)
                return;
            root.dataset.mode = mode;
            ratios = null;
            $('divider-1').setAttribute('aria-label', mode === 'scan' ? 'Resize Daily and watchlist' : 'Resize Intraday and watchlist');
            paint();
        }, setHoldingsWidth(width) {
            if (holdingsWidth === width)
                return;
            holdingsWidth = width;
            if (!isScan())
                paint();
        } };
}

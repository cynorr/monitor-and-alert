import { $ } from './types.js';
// One chart group and one list; every visible chart has the same width.
const LIST_WIDTH_RATIO = 0.32;
const LIST_MIN_WIDTH = 680;
const CHART_MIN_WIDTH = 320;
const DIVIDER_WIDTH = 12;
const WORKSPACE_PADDING = 20;
export function initLayout() {
    const root = $('workspace');
    let listRatio = null, holdingsWidth = LIST_MIN_WIDTH;
    function widths() {
        const charts = Array.from(root.querySelectorAll('.chart-panel')).filter(panel => !panel.hidden);
        const count = charts.length;
        const chartMin = Math.max(CHART_MIN_WIDTH, ...charts.map(panel => Number(panel.dataset.minWidth ?? CHART_MIN_WIDTH)));
        const listMin = Math.max(LIST_MIN_WIDTH, count > 1 ? holdingsWidth : 0);
        const minimum = chartMin * count + listMin;
        const available = Math.max(minimum, root.clientWidth - WORKSPACE_PADDING - DIVIDER_WIDTH * count);
        const list = Math.max(listMin, Math.min(available * (listRatio ?? LIST_WIDTH_RATIO), available - chartMin * count));
        return { count, chartMin, listMin, minimum, available, list };
    }
    function paint() {
        const { count, minimum, available, list } = widths();
        root.style.minWidth = `${minimum + WORKSPACE_PADDING + DIVIDER_WIDTH * count}px`;
        root.style.gridTemplateColumns = [...Array(count).fill((available - list) / count), list].map(value => `${value}px`).join(` ${DIVIDER_WIDTH}px `);
    }
    function resized(initial, delta) {
        listRatio = Math.max(initial.listMin, Math.min(initial.list - delta, initial.available - initial.chartMin * initial.count)) / initial.available;
        paint();
    }
    const handle = $('divider-1');
    handle.addEventListener('pointerdown', event => {
        const start = event.clientX, initial = widths();
        handle.setPointerCapture(event.pointerId);
        document.body.classList.add('resizing');
        const move = (e) => resized(initial, e.clientX - start);
        const end = () => { handle.removeEventListener('pointermove', move); document.body.classList.remove('resizing'); };
        handle.addEventListener('pointermove', move);
        handle.addEventListener('lostpointercapture', end, { once: true });
    });
    handle.addEventListener('dblclick', () => { listRatio = null; paint(); });
    handle.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight'].includes(event.key))
            return;
        event.preventDefault();
        event.stopPropagation();
        resized(widths(), event.key === 'ArrowRight' ? 12 : -12);
    });
    new ResizeObserver(() => paint()).observe(root);
    paint();
    return { setMode(mode) {
            if (root.dataset.mode === mode)
                return;
            root.dataset.mode = mode;
            listRatio = null;
            $('intraday-panel').dataset.minWidth = String(mode === 'trade' ? 540 : CHART_MIN_WIDTH);
            handle.setAttribute('aria-label', 'Resize charts and watchlist');
            paint();
        }, setHoldingsWidth(width) {
            if (holdingsWidth === width)
                return;
            holdingsWidth = width;
            if (widths().count > 1)
                paint();
        } };
}

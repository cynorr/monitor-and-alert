import { $ } from './types.js';
export function initLayout() {
    const root = $('workspace'), defaults = [0.38, 0.38, 0.24], minimum = [320, 320, 260];
    let ratios = defaults.slice();
    try {
        const saved = JSON.parse(localStorage.getItem('chart-columns') ?? 'null');
        if (Array.isArray(saved) && saved.length === 3 && saved.every(n => Number.isFinite(n) && n > 0))
            ratios = saved;
    }
    catch { /* Storage is optional. */ }
    function widths() {
        const available = root.clientWidth - 44;
        const extra = Math.max(0, available - minimum.reduce((a, b) => a + b, 0));
        const wanted = ratios.map((r, i) => Math.max(0, r * available - minimum[i]));
        const total = wanted.reduce((a, b) => a + b, 0) || 1;
        return minimum.map((m, i) => m + extra * wanted[i] / total);
    }
    function paint(values = widths()) { root.style.gridTemplateColumns = `${values[0]}px 12px ${values[1]}px 12px ${values[2]}px`; }
    function remember(values: number[]) { const total = values.reduce((a, b) => a + b, 0); ratios = values.map(v => v / total); try {
        localStorage.setItem('chart-columns', JSON.stringify(ratios));
    }
    catch { /* Storage is optional. */ } }
    for (let index = 0; index < 2; index++) {
        const handle = $('divider-' + index);
        handle.addEventListener('pointerdown', event => {
            const start = event.clientX, initial = widths();
            handle.setPointerCapture(event.pointerId);
            document.body.classList.add('resizing');
            const move = (e: PointerEvent) => { const delta = Math.max(minimum[index] - initial[index], Math.min(initial[index + 1] - minimum[index + 1], e.clientX - start)); const next = initial.slice(); next[index] += delta; next[index + 1] -= delta; remember(next); paint(next); };
            const end = () => { handle.removeEventListener('pointermove', move); document.body.classList.remove('resizing'); };
            handle.addEventListener('pointermove', move);
            handle.addEventListener('lostpointercapture', end, { once: true });
        });
        handle.addEventListener('dblclick', () => { ratios = defaults.slice(); remember(widths()); paint(); });
        handle.addEventListener('keydown', event => { if (!['ArrowLeft', 'ArrowRight'].includes(event.key))
            return; event.preventDefault(); const values = widths(); const delta = Math.max(minimum[index] - values[index], Math.min(values[index + 1] - minimum[index + 1], event.key === 'ArrowRight' ? 12 : -12)); values[index] += delta; values[index + 1] -= delta; remember(values); paint(values); });
    }
    new ResizeObserver(() => paint()).observe(root);
    paint();
}

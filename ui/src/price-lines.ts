import type { IPrimitivePaneRenderer } from 'lightweight-charts';
import type { Panel } from './chart.js';

// Alert and Trade share chart geometry; each keeps its own editing/submission rules.
export function panePoint(panel: Panel, event: Pick<PointerEvent, 'clientX' | 'clientY'>) {
    const pane = panel.chart.panes()[0].getHTMLElement();
    if (!pane) return null;
    const bounds = pane.getBoundingClientRect(), size = panel.chart.paneSize(0);
    const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
    return x >= 0 && x < size.width && y >= 0 && y < size.height ? { x, y } : null;
}
export function priceAtPointer(panel: Panel, event: Pick<PointerEvent, 'clientY'>) {
    const pane = panel.chart.panes()[0].getHTMLElement();
    return pane ? panel.candles.coordinateToPrice(event.clientY - pane.getBoundingClientRect().top) : null;
}
export function nearPriceLine(coordinate: number | null, y: number) { return coordinate != null && Math.abs(coordinate - y) <= 6; }
export function horizontalLines(rows: () => { y: number | null; color: string }[], dashed = false): IPrimitivePaneRenderer {
    return { draw: target => target.useBitmapCoordinateSpace(({ context: ctx, bitmapSize, horizontalPixelRatio, verticalPixelRatio }) => {
        // Solid Trade lines occupy one physical pixel, including on Retina screens.
        const width = dashed ? Math.max(1, Math.round(verticalPixelRatio)) : 1;
        ctx.lineWidth = width;
        ctx.setLineDash(dashed ? [6 * horizontalPixelRatio, 6 * horizontalPixelRatio] : []);
        for (const row of rows()) {
            if (row.y == null) continue;
            const y = Math.round(row.y * verticalPixelRatio) + (width % 2 ? .5 : 0);
            if (y < 0 || y > bitmapSize.height) continue;
            ctx.strokeStyle = row.color;
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(bitmapSize.width, y); ctx.stroke();
        }
        ctx.setLineDash([]);
    }) };
}

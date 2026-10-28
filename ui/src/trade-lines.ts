import type { IPriceLine, ISeriesPrimitive, PrimitiveHoveredItem, SeriesAttachedParameter } from 'lightweight-charts';
import type { Panel } from './chart.js';
import type { Order } from './schwab-data.js';
import { $ } from './types.js';
import { horizontalLines, nearPriceLine, panePoint, priceAtPointer } from './price-lines.js';

export type TradeLine = { key: string; price: number; color: string; editable: boolean; order?: Order };
export class TradeLines implements ISeriesPrimitive {
    private lines = new Map<string, { axis: IPriceLine; value: TradeLine }>();
    private drag: { key: string; pointer: number; original: number; start: number; moved: boolean } | null = null;
    private suppressed = false;
    private selected = '';
    private requestUpdate = () => {};
    private renderer = horizontalLines(() => [...this.lines.values()].map(({ value }) => ({ y: this.coordinate(value), color: value.color })));
    private view = { zOrder: () => 'bottom' as const, renderer: () => this.renderer };
    constructor(private panel: Panel, private change: (line: TradeLine, price: string) => void) {
        panel.candles.attachPrimitive(this);
        const host = $(panel.id + '-chart');
        host.addEventListener('pointerdown', event => {
            if (event.button !== 0 || (event.metaKey && event.altKey) || (event.target as HTMLElement).closest('.alert-line-controls')) return;
            const point = panePoint(panel, event), hits = point ? this.hits(point.y) : [];
            if (!hits.length) { this.suppressed = false; return; }
            const index = hits.findIndex(line => line.key === this.selected), line = hits[(index + 1) % hits.length];
            this.selected = line.key;
            this.stop(event);
            this.drag = { key: line.key, pointer: event.pointerId, original: line.price, start: event.clientY, moved: false };
            host.setPointerCapture(event.pointerId);
        }, true);
        host.addEventListener('pointermove', event => {
            if (!this.drag || this.drag.pointer !== event.pointerId) return;
            this.stop(event);
            const price = priceAtPointer(panel, event), item = this.lines.get(this.drag.key);
            this.drag.moved ||= Math.abs(event.clientY - this.drag.start) >= 3;
            if (this.drag.moved && price != null && Number.isFinite(price) && price > 0 && item) this.change(item.value, price.toFixed(2));
        }, true);
        host.addEventListener('pointerup', event => {
            if (this.drag?.pointer !== event.pointerId) return;
            this.stop(event); this.drag = null; host.releasePointerCapture(event.pointerId);
        }, true);
        host.addEventListener('pointercancel', () => this.cancelDrag(), true);
        host.addEventListener('lostpointercapture', () => { if (this.drag) this.cancelDrag(); }, true);
        for (const name of ['mousedown', 'mouseup', 'click', 'touchstart']) host.addEventListener(name, event => {
            if (this.suppressed) { event.preventDefault(); event.stopImmediatePropagation(); if (name === 'click') this.suppressed = false; }
        }, true);
    }
    attached(parameter: SeriesAttachedParameter) { this.requestUpdate = parameter.requestUpdate; }
    detached() { this.requestUpdate = () => {}; }
    paneViews() { return [this.view]; }
    private coordinate(line: TradeLine) { return this.panel.candles.priceToCoordinate(line.price); }
    private hits(y: number) { return [...this.lines.values()].map(item => item.value).reverse().filter(line => line.editable && nearPriceLine(this.coordinate(line), y)); }
    hitTest(_x: number, y: number): PrimitiveHoveredItem | null {
        const line = this.hits(y)[0];
        return line ? { externalId: 'trade-' + line.key, zOrder: 'bottom', cursorStyle: 'ns-resize', distance: Math.abs(y - this.coordinate(line)!) } : null;
    }
    private stop(event: PointerEvent) { event.preventDefault(); event.stopImmediatePropagation(); this.suppressed = true; }
    update(values: TradeLine[]) {
        const keys = new Set(values.map(v => v.key));
        for (const [key, item] of this.lines) if (!keys.has(key)) { this.panel.candles.removePriceLine(item.axis); this.lines.delete(key); }
        for (const value of values) {
            let item = this.lines.get(value.key);
            if (!item) {
                const axis = this.panel.candles.createPriceLine({ price: value.price, color: value.color, lineVisible: false, axisLabelVisible: true, title: '' });
                item = { axis, value }; this.lines.set(value.key, item);
            }
            item.value = value; item.axis.applyOptions({ price: value.price, color: value.color });
        }
        this.panel.tradePrices = values.map(v => v.price);
        this.requestUpdate();
    }
    cancelDrag() { const drag = this.drag; this.drag = null; if (drag) { const item = this.lines.get(drag.key); if (item) this.change(item.value, drag.original.toFixed(2)); } }
}

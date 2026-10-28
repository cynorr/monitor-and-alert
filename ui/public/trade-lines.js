import { $ } from './types.js';
import { horizontalLines, nearPriceLine, panePoint, priceAtPointer } from './price-lines.js';
export class TradeLines {
    panel;
    change;
    lines = new Map();
    drag = null;
    suppressed = false;
    selected = '';
    requestUpdate = () => { };
    renderer = horizontalLines(() => [...this.lines.values()].map(({ value }) => ({ y: this.coordinate(value), color: value.color })));
    view = { zOrder: () => 'bottom', renderer: () => this.renderer };
    constructor(panel, change) {
        this.panel = panel;
        this.change = change;
        panel.candles.attachPrimitive(this);
        const host = $(panel.id + '-chart');
        host.addEventListener('pointerdown', event => {
            if (event.button !== 0 || (event.metaKey && event.altKey) || event.target.closest('.alert-line-controls'))
                return;
            const point = panePoint(panel, event), hits = point ? this.hits(point.y) : [];
            if (!hits.length) {
                this.suppressed = false;
                return;
            }
            const index = hits.findIndex(line => line.key === this.selected), line = hits[(index + 1) % hits.length];
            this.selected = line.key;
            this.stop(event);
            this.drag = { key: line.key, pointer: event.pointerId, original: line.price, start: event.clientY, moved: false };
            host.setPointerCapture(event.pointerId);
        }, true);
        host.addEventListener('pointermove', event => {
            if (!this.drag || this.drag.pointer !== event.pointerId)
                return;
            this.stop(event);
            const price = priceAtPointer(panel, event), item = this.lines.get(this.drag.key);
            this.drag.moved ||= Math.abs(event.clientY - this.drag.start) >= 3;
            if (this.drag.moved && price != null && Number.isFinite(price) && price > 0 && item)
                this.change(item.value, price.toFixed(2));
        }, true);
        host.addEventListener('pointerup', event => {
            if (this.drag?.pointer !== event.pointerId)
                return;
            this.stop(event);
            this.drag = null;
            host.releasePointerCapture(event.pointerId);
        }, true);
        host.addEventListener('pointercancel', () => this.cancelDrag(), true);
        host.addEventListener('lostpointercapture', () => { if (this.drag)
            this.cancelDrag(); }, true);
        for (const name of ['mousedown', 'mouseup', 'click', 'touchstart'])
            host.addEventListener(name, event => {
                if (this.suppressed) {
                    event.preventDefault();
                    event.stopImmediatePropagation();
                    if (name === 'click')
                        this.suppressed = false;
                }
            }, true);
    }
    attached(parameter) { this.requestUpdate = parameter.requestUpdate; }
    detached() { this.requestUpdate = () => { }; }
    paneViews() { return [this.view]; }
    coordinate(line) { return this.panel.candles.priceToCoordinate(line.price); }
    hits(y) { return [...this.lines.values()].map(item => item.value).reverse().filter(line => line.editable && nearPriceLine(this.coordinate(line), y)); }
    hitTest(_x, y) {
        const line = this.hits(y)[0];
        return line ? { externalId: 'trade-' + line.key, zOrder: 'bottom', cursorStyle: 'ns-resize', distance: Math.abs(y - this.coordinate(line)) } : null;
    }
    stop(event) { event.preventDefault(); event.stopImmediatePropagation(); this.suppressed = true; }
    update(values) {
        const keys = new Set(values.map(v => v.key));
        for (const [key, item] of this.lines)
            if (!keys.has(key)) {
                this.panel.candles.removePriceLine(item.axis);
                this.lines.delete(key);
            }
        for (const value of values) {
            let item = this.lines.get(value.key);
            if (!item) {
                const axis = this.panel.candles.createPriceLine({ price: value.price, color: value.color, lineVisible: false, axisLabelVisible: true, title: '' });
                item = { axis, value };
                this.lines.set(value.key, item);
            }
            item.value = value;
            item.axis.applyOptions({ price: value.price, color: value.color });
        }
        this.panel.tradePrices = values.map(v => v.price);
        this.requestUpdate();
    }
    cancelDrag() { const drag = this.drag; this.drag = null; if (drag) {
        const item = this.lines.get(drag.key);
        if (item)
            this.change(item.value, drag.original.toFixed(2));
    } }
}

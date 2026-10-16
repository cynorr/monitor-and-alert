import { $, dayKey, nyTime } from './types.js';
import { post } from './api.js';
export const alertPrice = (cents) => (cents / 100).toFixed(2);
const previewCents = (price) => {
    const [digits, exponent = '0'] = price.toString().split('e');
    return Math.round(Number(`${digits}e${Number(exponent) + 2}`));
};
export const eventTime = (event) => `${dayKey(event.quote_time)} ${nyTime.format(new Date(event.quote_time * 1000))} ET`;
export const crossingIcon = (direction) => `<svg viewBox="0 0 24 24" aria-hidden="true" data-icon="alert-cross-${direction}" class="crossing-icon ${direction}"><path d="M3 12h18M12 ${direction === 'up' ? '21V3m-5 5 5-5 5 5' : '3v18m-5-5 5 5 5-5'}"/></svg>`;
class AlertPrimitive {
    layer;
    requestUpdate = () => { };
    constructor(layer) {
        this.layer = layer;
    }
    attached(parameter) { this.requestUpdate = parameter.requestUpdate; }
    detached() { this.requestUpdate = () => { }; }
    updateAllViews() { this.layer.updateControls(); }
    renderer = { draw: target => target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
            for (const alert of this.layer.rows()) {
                const y = this.layer.coordinate(alert);
                if (y == null || y < 0 || y > mediaSize.height)
                    continue;
                const color = alert.state === 'active' ? '#000000' : '#9ca3af';
                ctx.strokeStyle = ctx.fillStyle = color;
                ctx.lineWidth = 1;
                // Match Lightweight Charts' 1px LargeDashed crosshair: 6px on / 6px off.
                ctx.setLineDash([6, 6]);
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(mediaSize.width, y);
                ctx.stroke();
                ctx.setLineDash([]);
            }
        }) };
    arrowRenderer = { draw: target => target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
            for (const alert of this.layer.rows()) {
                const y = this.layer.coordinate(alert);
                if (y == null || y < 0 || y > mediaSize.height)
                    continue;
                ctx.fillStyle = alert.state === 'active' ? '#000000' : '#9ca3af';
                // x=0 is the price-axis canvas edge and the native price-label edge.
                ctx.beginPath();
                ctx.moveTo(0, y - 3);
                ctx.lineTo(6, y);
                ctx.lineTo(0, y + 3);
                ctx.closePath();
                ctx.fill();
            }
        }) };
    view = { zOrder: () => 'top', renderer: () => this.renderer };
    arrowView = { zOrder: () => 'top', renderer: () => this.arrowRenderer };
    paneViews() { return [this.view]; }
    priceAxisPaneViews() { return [this.arrowView]; }
    hitTest(x, y) {
        const alert = this.layer.hits(y)[0];
        return alert ? { externalId: alert.id, zOrder: 'top', cursorStyle: 'ns-resize', distance: Math.abs(y - this.layer.coordinate(alert)) } : null;
    }
}
export class AlertChart {
    panel;
    controller;
    primitive = new AlertPrimitive(this);
    drag;
    suppressed = false;
    hovered = '';
    controls = document.createElement('div');
    priceLabel = document.createElement('span');
    remove = document.createElement('button');
    constructor(panel, controller) {
        this.panel = panel;
        this.controller = controller;
        const host = $(panel.id + '-chart');
        this.controls.className = 'alert-line-controls';
        this.controls.hidden = true;
        const capsule = document.createElement('div');
        capsule.className = 'alert-price-capsule';
        this.remove.type = 'button';
        this.remove.className = 'alert-line-delete';
        this.remove.setAttribute('aria-label', 'Delete alert');
        this.remove.title = 'Delete alert';
        this.remove.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg>';
        this.remove.addEventListener('click', () => { if (this.hovered)
            void this.controller.mutate({ action: 'delete', id: this.hovered }); });
        capsule.append(this.priceLabel, this.remove);
        this.controls.append(capsule);
        host.append(this.controls);
        panel.candles.attachPrimitive(this.primitive);
        host.addEventListener('pointerdown', event => this.down(event), true);
        host.addEventListener('pointermove', event => this.move(event), true);
        host.addEventListener('pointerup', event => this.up(event), true);
        host.addEventListener('pointercancel', () => this.cancel(), true);
        host.addEventListener('lostpointercapture', () => { if (this.drag)
            this.cancel(); }, true);
        host.addEventListener('pointerleave', () => { if (!this.drag)
            this.hover(''); });
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
    rows() { return this.controller.value?.alerts.filter(alert => alert.symbol === this.controller.symbol()) ?? []; }
    cents(alert) { return this.controller.preview?.id === alert.id ? this.controller.preview.cents : alert.price_cents; }
    coordinate(alert) { return this.panel.candles.priceToCoordinate(this.cents(alert) / 100); }
    hits(y) { return this.rows().filter(alert => { const point = this.coordinate(alert); return point != null && Math.abs(point - y) <= 6; }); }
    updateControls() {
        const alert = this.rows().find(alert => alert.id === (this.drag?.alert.id ?? this.hovered));
        const pane = this.panel.chart.panes()[0].getHTMLElement();
        const y = alert ? this.coordinate(alert) : null, size = this.panel.chart.paneSize(0);
        if (!pane || !alert || y == null || y < 0 || y > size.height) {
            this.controls.hidden = true;
            return;
        }
        this.controls.hidden = false;
        const bounds = pane.getBoundingClientRect(), host = $(this.panel.id + '-chart').getBoundingClientRect();
        this.controls.style.left = `${bounds.left - host.left + size.width * 2 / 3}px`;
        this.controls.style.top = `${bounds.top - host.top + y}px`;
        this.controls.classList.toggle('triggered', alert.state === 'triggered');
        this.priceLabel.textContent = alertPrice(this.cents(alert));
        this.remove.setAttribute('aria-label', `Delete alert ${this.priceLabel.textContent}`);
    }
    hover(id) {
        if (this.hovered === id)
            return;
        this.hovered = id;
        this.primitive.requestUpdate();
    }
    point(event) {
        const pane = this.panel.chart.panes()[0].getHTMLElement();
        if (!pane)
            return null;
        const bounds = pane.getBoundingClientRect(), size = this.panel.chart.paneSize(0);
        const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
        return x >= 0 && x < size.width && y >= 0 && y < size.height ? { x, y } : null;
    }
    stop(event) { event.preventDefault(); event.stopImmediatePropagation(); this.suppressed = true; }
    down(event) {
        if (event.button !== 0 || !this.controller.symbol())
            return;
        const point = this.point(event);
        if (!point)
            return;
        // Pointerdown precedes the chart's mouse listeners, so alert gestures own this press.
        if (event.metaKey && event.altKey) {
            const price = this.panel.candles.coordinateToPrice(point.y);
            if (price != null) {
                this.stop(event);
                void this.controller.create(price);
            }
            return;
        }
        if (this.remove.contains(event.target)) {
            this.stop(event);
            void this.controller.mutate({ action: 'delete', id: this.hovered });
            return;
        }
        const hits = this.hits(point.y);
        const capsule = this.controls.contains(event.target);
        if (!hits.length && !capsule) {
            this.controller.choose('');
            this.suppressed = false;
            return;
        }
        const previous = hits.findIndex(alert => alert.id === this.controller.selected);
        const alert = capsule ? this.rows().find(alert => alert.id === this.hovered) : hits[(previous + 1) % hits.length];
        this.controller.choose(alert.id);
        this.hover(alert.id);
        this.stop(event);
        this.drag = { alert, pointer: event.pointerId, startY: event.clientY, price: alert.price_cents / 100, moved: false };
        this.controller.preview = { id: alert.id, cents: alert.price_cents };
        event.currentTarget.setPointerCapture(event.pointerId);
    }
    move(event) {
        if (!this.drag) {
            if (this.controls.contains(event.target))
                return;
            const point = this.point(event), hits = point ? this.hits(point.y) : [];
            const alert = hits.find(alert => alert.id === this.controller.selected) ?? hits.find(alert => alert.id === this.hovered) ?? hits[0];
            this.hover(alert?.id ?? '');
            return;
        }
        if (event.pointerId !== this.drag.pointer)
            return;
        this.stop(event);
        const pane = this.panel.chart.panes()[0].getHTMLElement();
        const price = this.panel.candles.coordinateToPrice(event.clientY - pane.getBoundingClientRect().top);
        if (price != null && Number.isFinite(price) && price > 0)
            this.drag.price = price;
        this.controller.preview = { id: this.drag.alert.id, cents: previewCents(this.drag.price) };
        this.drag.moved ||= Math.abs(event.clientY - this.drag.startY) >= 3;
        this.controller.redraw();
    }
    up(event) {
        if (!this.drag || event.pointerId !== this.drag.pointer)
            return;
        this.stop(event);
        const drag = this.drag;
        this.drag = undefined;
        this.controller.preview = undefined;
        event.currentTarget.releasePointerCapture(event.pointerId);
        if (drag.moved)
            void this.controller.mutate({ action: 'rearm', id: drag.alert.id, generation: drag.alert.generation, price: drag.price });
        this.controller.redraw();
    }
    cancel() { if (this.drag)
        this.controller.preview = undefined; this.drag = undefined; this.hovered = ''; this.controller.redraw(); }
}
export class AlertController {
    symbol;
    mode;
    created;
    jump;
    value;
    selected = '';
    preview;
    layers;
    error = '';
    pending = new Set();
    constructor(panels, symbol, mode, created, jump) {
        this.symbol = symbol;
        this.mode = mode;
        this.created = created;
        this.jump = jump;
        this.layers = panels.map(panel => new AlertChart(panel, this));
        document.addEventListener('keydown', event => {
            if (event.target.closest('input,textarea,select,[contenteditable="true"]'))
                return;
            if (event.key === 'Escape') {
                this.layers.forEach(layer => layer.cancel());
                this.choose('');
            }
            if (event.key === 'Backspace' && this.selected) {
                event.preventDefault();
                event.stopImmediatePropagation();
                void this.mutate({ action: 'delete', id: this.selected });
            }
        }, true);
        $('alert-error-close').addEventListener('click', () => { this.error = ''; this.render(); });
    }
    update(value) {
        this.value = value;
        if (!value.alerts.some(alert => alert.id === this.selected))
            this.selected = '';
        this.redraw();
        this.render();
    }
    choose(id) { this.selected = id; this.redraw(); }
    changeSymbol() { this.layers.forEach(layer => layer.cancel()); this.choose(''); }
    redraw() { this.layers.forEach(layer => layer.primitive.requestUpdate()); }
    async mutate(payload) {
        try {
            const value = await post('alerts', payload);
            this.update(value);
            if (value.error)
                throw new Error(value.error);
            this.error = '';
            this.render();
            return true;
        }
        catch (error) {
            this.error = error.message;
            this.render();
            return false;
        }
    }
    async create(price) {
        const target = this.symbol();
        if (await this.mutate({ action: 'create', symbol: target, price, mode: this.mode() })) {
            try {
                await this.created(target);
            }
            catch (error) {
                this.error = error.message;
                this.render();
            }
        }
    }
    async open(event) {
        if (this.pending.has(event.id))
            return;
        this.pending.add(event.id);
        this.render();
        try {
            await this.jump(event);
            await this.mutate({ action: 'acknowledge', event_id: event.id });
        }
        catch (error) {
            this.error = error.message;
        }
        finally {
            this.pending.delete(event.id);
            this.render();
        }
    }
    render() {
        const value = this.value;
        const error = $('alert-error');
        const message = this.error || value?.error || value?.sound.error || '';
        error.hidden = !message;
        $('alert-error-message').textContent = message;
        const stack = $('alert-cards');
        const focused = document.activeElement?.dataset.alertAction;
        const focusEvent = document.activeElement?.dataset.event;
        stack.replaceChildren(...(value?.events ?? []).map(event => {
            const card = document.createElement('article');
            card.className = 'alert-card';
            card.setAttribute('aria-label', `${event.symbol.replace('.US', '')} ${event.direction === 'up' ? 'crossed up' : 'crossed down'} ${alertPrice(event.price_cents)}`);
            const open = document.createElement('button');
            open.className = 'alert-open';
            open.dataset.alertAction = 'open';
            open.dataset.event = event.id;
            open.innerHTML = crossingIcon(event.direction);
            const info = document.createElement('span'), title = document.createElement('strong'), stamp = document.createElement('time');
            title.textContent = `${event.symbol.replace('.US', '')}  ${alertPrice(event.price_cents)}`;
            stamp.textContent = eventTime(event);
            info.append(title, stamp);
            open.append(info);
            const jump = document.createElement('span');
            jump.textContent = '↗';
            jump.setAttribute('aria-hidden', 'true');
            open.append(jump);
            open.title = `Open chart · Last ${event.actual_price}`;
            open.disabled = this.pending.has(event.id) || !value?.eligible_symbols.includes(event.symbol);
            open.addEventListener('click', () => { void this.open(event); });
            const close = document.createElement('button');
            close.className = 'alert-close';
            close.textContent = '×';
            close.setAttribute('aria-label', 'Close alert');
            close.dataset.alertAction = 'close';
            close.dataset.event = event.id;
            close.disabled = this.pending.has(event.id);
            close.addEventListener('click', async () => { this.pending.add(event.id); this.render(); await this.mutate({ action: 'acknowledge', event_id: event.id }); this.pending.delete(event.id); this.render(); });
            card.append(open, close);
            return card;
        }));
        if (focused && focusEvent)
            stack.querySelector(`[data-alert-action="${focused}"][data-event="${focusEvent}"]`)?.focus();
    }
}

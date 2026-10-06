import type { ISeriesPrimitive, IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitiveAxisView, SeriesAttachedParameter, PrimitiveHoveredItem } from 'lightweight-charts';
import type { Panel } from './chart.js';
import { $, dayKey, nyTime } from './types.js';
import { post } from './api.js';

export type PriceAlert = { id: string; symbol: string; price_cents: number; generation: number; state: 'active' | 'triggered'; expires_at: number };
export type AlertEvent = { id: string; alert_id: string; generation: number; symbol: string; direction: 'up' | 'down'; price_cents: number; actual_price: number; quote_time: number; fired_at: number };
export type AlertState = { revision: number; alerts: PriceAlert[]; events: AlertEvent[]; eligible_symbols: string[]; scope_known: boolean; error: string | null; notification: { available: boolean; authorization: string; sound: boolean; alerts?: boolean; error: string | null } };
export const alertPrice = (cents: number) => (cents / 100).toFixed(2);
const previewCents = (price: number) => {
    const [digits, exponent = '0'] = price.toString().split('e');
    return Math.round(Number(`${digits}e${Number(exponent) + 2}`));
};
export const eventTime = (event: AlertEvent) => `${dayKey(event.quote_time)} ${nyTime.format(new Date(event.quote_time * 1000))} ET`;
export const crossingIcon = (direction: 'up' | 'down') => `<svg viewBox="0 0 24 24" aria-hidden="true" data-icon="alert-cross-${direction}" class="crossing-icon ${direction}"><path d="M3 12h18M12 ${direction === 'up' ? '21V3m-5 5 5-5 5 5' : '3v18m-5-5 5 5 5-5'}"/></svg>`;

class AlertPrimitive implements ISeriesPrimitive {
    requestUpdate = () => {};
    constructor(private layer: AlertChart) {}
    attached(parameter: SeriesAttachedParameter) { this.requestUpdate = parameter.requestUpdate; }
    detached() { this.requestUpdate = () => {}; }
    private renderer: IPrimitivePaneRenderer = { draw: target => target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
        for (const alert of this.layer.rows()) {
            const y = this.layer.coordinate(alert);
            if (y == null || y < 0 || y > mediaSize.height) continue;
            const color = alert.state === 'active' ? '#000000' : '#9ca3af';
            const selected = alert.id === this.layer.controller.selected;
            ctx.strokeStyle = ctx.fillStyle = color;
            ctx.lineWidth = selected ? 2 : 1;
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(mediaSize.width - 12, y); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(mediaSize.width - 6, y); ctx.lineTo(mediaSize.width - 14, y - 4); ctx.lineTo(mediaSize.width - 14, y + 4); ctx.closePath(); ctx.fill();
            if (selected) { ctx.fillStyle = '#ffffff'; ctx.fillRect(mediaSize.width / 2 - 3, y - 3, 6, 6); ctx.strokeRect(mediaSize.width / 2 - 3, y - 3, 6, 6); }
        }
    }) };
    private view: IPrimitivePaneView = { zOrder: () => 'top', renderer: () => this.renderer };
    paneViews() { return [this.view]; }
    priceAxisViews(): ISeriesPrimitiveAxisView[] {
        return this.layer.rows().map(alert => ({
            coordinate: () => this.layer.coordinate(alert) ?? -10000,
            text: () => alertPrice(this.layer.cents(alert)), textColor: () => '#ffffff',
            backColor: () => alert.state === 'active' ? '#000000' : '#9ca3af',
            visible: () => this.layer.coordinate(alert) !== null, tickVisible: () => true,
        }));
    }
    hitTest(x: number, y: number): PrimitiveHoveredItem | null {
        const alert = this.layer.hits(y)[0];
        return alert ? { externalId: alert.id, zOrder: 'top', cursorStyle: 'ns-resize', distance: Math.abs(y - this.layer.coordinate(alert)!) } : null;
    }
}

export class AlertChart {
    primitive = new AlertPrimitive(this);
    private drag?: { alert: PriceAlert; pointer: number; startY: number; price: number; moved: boolean };
    private suppressed = false;
    constructor(private panel: Panel, public controller: AlertController) {
        panel.candles.attachPrimitive(this.primitive);
        const host = $(panel.id + '-chart');
        host.addEventListener('pointerdown', event => this.down(event), true);
        host.addEventListener('pointermove', event => this.move(event), true);
        host.addEventListener('pointerup', event => this.up(event), true);
        host.addEventListener('pointercancel', () => this.cancel(), true);
        host.addEventListener('lostpointercapture', () => this.cancel(), true);
        for (const name of ['mousedown', 'mouseup', 'click', 'touchstart']) host.addEventListener(name, event => {
            if (this.suppressed) { event.preventDefault(); event.stopImmediatePropagation(); if (name === 'click') this.suppressed = false; }
        }, true);
    }
    rows() { return this.controller.value?.alerts.filter(alert => alert.symbol === this.controller.symbol()) ?? []; }
    cents(alert: PriceAlert) { return this.drag?.alert.id === alert.id ? previewCents(this.drag.price) : alert.price_cents; }
    coordinate(alert: PriceAlert) { return this.panel.candles.priceToCoordinate(this.cents(alert) / 100); }
    hits(y: number) { return this.rows().filter(alert => { const point = this.coordinate(alert); return point != null && Math.abs(point - y) <= 6; }); }
    private point(event: PointerEvent) {
        const pane = this.panel.chart.panes()[0].getHTMLElement();
        if (!pane) return null;
        const bounds = pane.getBoundingClientRect(), size = this.panel.chart.paneSize(0);
        const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
        return x >= 0 && x < size.width && y >= 0 && y < size.height ? { x, y } : null;
    }
    private stop(event: PointerEvent) { event.preventDefault(); event.stopImmediatePropagation(); this.suppressed = true; }
    private down(event: PointerEvent) {
        if (event.button !== 0 || !this.controller.symbol()) return;
        const point = this.point(event);
        if (!point) return;
        // Pointerdown precedes the chart's mouse listeners, so alert gestures own this press.
        if (event.metaKey && event.altKey) {
            const price = this.panel.candles.coordinateToPrice(point.y);
            if (price != null) { this.stop(event); void this.controller.create(price); }
            return;
        }
        const hits = this.hits(point.y);
        if (!hits.length) { this.controller.choose(''); this.suppressed = false; return; }
        const previous = hits.findIndex(alert => alert.id === this.controller.selected);
        const alert = hits[(previous + 1) % hits.length];
        this.controller.choose(alert.id);
        this.stop(event);
        this.drag = { alert, pointer: event.pointerId, startY: event.clientY, price: alert.price_cents / 100, moved: false };
        (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    }
    private move(event: PointerEvent) {
        if (!this.drag || event.pointerId !== this.drag.pointer) return;
        this.stop(event);
        const pane = this.panel.chart.panes()[0].getHTMLElement()!;
        const price = this.panel.candles.coordinateToPrice(event.clientY - pane.getBoundingClientRect().top);
        if (price != null && Number.isFinite(price) && price > 0) this.drag.price = price;
        this.drag.moved ||= Math.abs(event.clientY - this.drag.startY) >= 3;
        this.controller.redraw();
    }
    private up(event: PointerEvent) {
        if (!this.drag || event.pointerId !== this.drag.pointer) return;
        this.stop(event);
        const drag = this.drag; this.drag = undefined;
        (event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
        if (drag.moved) void this.controller.mutate({ action: 'rearm', id: drag.alert.id, generation: drag.alert.generation, price: drag.price });
        this.controller.redraw();
    }
    cancel() { this.drag = undefined; this.controller.redraw(); }
}

export class AlertController {
    value?: AlertState;
    selected = '';
    private layers: AlertChart[];
    private error = '';
    private pending = new Set<string>();
    constructor(panels: Panel[], public symbol: () => string, private mode: () => 'scan' | 'monitor',
                private created: (symbol: string) => Promise<void>, private jump: (event: AlertEvent) => Promise<void>) {
        this.layers = panels.map(panel => new AlertChart(panel, this));
        document.addEventListener('keydown', event => {
            if ((event.target as HTMLElement).closest('input,textarea,select,[contenteditable="true"]')) return;
            if (event.key === 'Escape') { this.layers.forEach(layer => layer.cancel()); this.choose(''); }
            if (event.key === 'Backspace' && this.selected) { event.preventDefault(); event.stopImmediatePropagation(); void this.mutate({ action: 'delete', id: this.selected }); }
        }, true);
        $('alert-notifications').addEventListener('click', () => { void this.mutate({ action: 'notifications' }); });
        $('alert-error-close').addEventListener('click', () => { this.error = ''; this.render(); });
    }
    update(value: AlertState) {
        this.value = value;
        if (!value.alerts.some(alert => alert.id === this.selected)) this.selected = '';
        this.redraw(); this.render();
    }
    choose(id: string) { this.selected = id; this.redraw(); }
    changeSymbol() { this.layers.forEach(layer => layer.cancel()); this.choose(''); }
    redraw() { this.layers.forEach(layer => layer.primitive.requestUpdate()); }
    async mutate(payload: object): Promise<boolean> {
        try {
            const value = await post<AlertState>('alerts', payload);
            this.update(value);
            if (value.error) throw new Error(value.error);
            this.error = ''; this.render(); return true;
        } catch (error) { this.error = (error as Error).message; this.render(); return false; }
    }
    async create(price: number) {
        const target = this.symbol();
        if (await this.mutate({ action: 'create', symbol: target, price, mode: this.mode() })) {
            try { await this.created(target); } catch (error) { this.error = (error as Error).message; this.render(); }
        }
    }
    async open(event: AlertEvent) {
        if (this.pending.has(event.id)) return;
        this.pending.add(event.id); this.render();
        try {
            await this.jump(event);
            await this.mutate({ action: 'acknowledge', event_id: event.id });
            if (location.hash === '#alert=' + event.id) history.replaceState(null, '', location.pathname);
        } catch (error) { this.error = (error as Error).message; }
        finally { this.pending.delete(event.id); this.render(); }
    }
    private render() {
        const value = this.value;
        const notification = value?.notification;
        const note = $('alert-notifications') as HTMLButtonElement;
        note.hidden = !notification || (notification.authorization === 'authorized' && notification.sound && notification.alerts === true && !notification.error);
        note.disabled = !notification?.available;
        note.textContent = notification?.error ?? (notification?.authorization === 'not_determined' ? 'Enable notifications' : notification?.authorization === 'authorized' ? 'Notification sound/display is off' : notification?.available ? 'Notification settings' : 'Open Market Monitor.app for notifications');
        const error = $('alert-error');
        error.hidden = !this.error && !value?.error;
        $('alert-error-message').textContent = this.error || value?.error || '';
        const stack = $('alert-cards');
        const focused = (document.activeElement as HTMLElement)?.dataset.alertAction;
        const focusEvent = (document.activeElement as HTMLElement)?.dataset.event;
        stack.replaceChildren(...(value?.events ?? []).map(event => {
            const card = document.createElement('article'); card.className = 'alert-card';
            card.setAttribute('aria-label', `${event.symbol.replace('.US', '')} ${event.direction === 'up' ? 'crossed up' : 'crossed down'} ${alertPrice(event.price_cents)}`);
            const open = document.createElement('button'); open.className = 'alert-open'; open.dataset.alertAction = 'open'; open.dataset.event = event.id;
            open.innerHTML = crossingIcon(event.direction);
            const info = document.createElement('span'), title = document.createElement('strong'), stamp = document.createElement('time');
            title.textContent = `${event.symbol.replace('.US', '')}  ${alertPrice(event.price_cents)}`;
            stamp.textContent = eventTime(event); info.append(title, stamp); open.append(info);
            const jump = document.createElement('span'); jump.textContent = '↗'; jump.setAttribute('aria-hidden', 'true'); open.append(jump);
            open.title = `Open chart · Last ${event.actual_price}`;
            open.disabled = this.pending.has(event.id) || !value?.eligible_symbols.includes(event.symbol);
            open.addEventListener('click', () => { void this.open(event); });
            const close = document.createElement('button'); close.className = 'alert-close'; close.textContent = '×'; close.setAttribute('aria-label', 'Close alert'); close.dataset.alertAction = 'close'; close.dataset.event = event.id;
            close.disabled = this.pending.has(event.id);
            close.addEventListener('click', async () => { this.pending.add(event.id); this.render(); await this.mutate({ action: 'acknowledge', event_id: event.id }); this.pending.delete(event.id); this.render(); });
            card.append(open, close); return card;
        }));
        if (focused && focusEvent) stack.querySelector<HTMLButtonElement>(`[data-alert-action="${focused}"][data-event="${focusEvent}"]`)?.focus();
    }
}

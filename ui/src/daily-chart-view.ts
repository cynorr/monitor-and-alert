import type { AutoscaleInfo, ISeriesPrimitive, IPrimitivePaneRenderer, IPrimitivePaneView, LogicalRange, SeriesAttachedParameter, UTCTimestamp } from 'lightweight-charts';
import type { Panel } from './chart.js';
import { $, type Row, dayKey } from './types.js';
import { palette } from './palette.js';
import { BAR_SPACING, DAILY_ANCHOR_BARS, DAILY_ANCHOR_POSITION, DAILY_PERCENT_BAR_SPACING } from './chart-settings.js';

// Daily's coordinate policy and clipping marks use public chart APIs only.
export class DailyChartView implements ISeriesPrimitive {
    private anchor?: number;
    private rows: Row[] = [];
    private saved?: { range: LogicalRange; spacing: number };
    private pointerHeld = false;
    private requestUpdate = () => {};
    get previewing() { return this.saved !== undefined; }

    constructor(private panel: Panel) {
        panel.chart.applyOptions({
            rightPriceScale: { autoScale: true, mode: 0, scaleMargins: { top: 0, bottom: 0 } },
            handleScale: { axisPressedMouseMove: { price: false, time: true }, axisDoubleClickReset: { price: false, time: false } },
        });
        const autoscale = panel.candles.options().autoscaleInfoProvider;
        panel.candles.applyOptions({ autoscaleInfoProvider: (original: () => AutoscaleInfo | null) => {
            const range = this.fixedRange();
            if (this.previewing || !range) return autoscale ? autoscale(original) : original();
            return { priceRange: range };
        } });
        for (const line of Object.values(panel.lines))
            line.applyOptions({ autoscaleInfoProvider: (original: () => AutoscaleInfo | null) => this.previewing ? original() : null });
        panel.candles.attachPrimitive(this);
        panel.chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.sync());
        const host = $(panel.id + '-chart');
        host.addEventListener('pointerdown', () => { if (!this.previewing) this.pointerHeld = true; }, true);
        window.addEventListener('pointerup', () => { this.pointerHeld = false; }, true);
        window.addEventListener('pointercancel', () => { this.pointerHeld = false; }, true);
        for (const type of ['pointerdown', 'mousedown', 'touchstart', 'touchmove', 'wheel', 'click', 'dblclick']) {
            host.addEventListener(type, event => {
                if (this.previewing) { event.preventDefault(); event.stopImmediatePropagation(); }
            }, { capture: true, passive: false });
        }
        document.addEventListener('keydown', event => {
            if (event.isComposing || (event.target as HTMLElement).closest('input,textarea,select,[contenteditable]')) return;
            if (this.previewing && ['Backspace', 'Delete'].includes(event.key)) {
                event.preventDefault(); event.stopImmediatePropagation(); return;
            }
            if (event.code !== 'KeyF' || event.repeat || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey || this.pointerHeld) return;
            event.preventDefault();
            this.preview();
        }, true);
        document.addEventListener('keyup', event => { if (event.code === 'KeyF') this.restore(); });
        window.addEventListener('blur', () => { this.pointerHeld = false; this.restore(); });
        document.addEventListener('visibilitychange', () => { if (document.hidden) this.restore(); });
    }
    attached(parameter: SeriesAttachedParameter) { this.requestUpdate = parameter.requestUpdate; }
    detached() { this.requestUpdate = () => {}; }
    update(closed: Row[], active: Row | null) {
        const closes = closed.slice(-DAILY_ANCHOR_BARS).map(row => row.close).sort((a, b) => a - b);
        const middle = Math.floor(closes.length / 2);
        this.anchor = closes.length ? (closes[middle] + closes[Math.floor((closes.length - 1) / 2)]) / 2 : undefined;
        this.rows = [...closed, ...(active ? [active] : [])];
        this.sync();
    }
    private fixedRange() {
        if (this.anchor === undefined) return null;
        const height = this.panel.chart.panes()[0].getHeight() - 1;
        if (height <= 0) return null;
        const spacing = this.panel.chart.timeScale().options().barSpacing;
        const span = this.anchor * .01 * height / (spacing * DAILY_PERCENT_BAR_SPACING);
        const from = this.anchor - span * DAILY_ANCHOR_POSITION, to = from + span;
        return { minValue: from, maxValue: to };
    }
    sync() {
        // Keep native autoScale on to disable vertical panning, but supply only our fixed range.
        if (!this.previewing && this.anchor !== undefined) this.panel.candles.applyOptions({});
    }
    reset() {
        this.restore();
        this.anchor = undefined;
        this.rows = [];
        this.requestUpdate();
    }
    resetLatest() {
        this.restore();
        const scale = this.panel.chart.timeScale();
        scale.applyOptions({ barSpacing: BAR_SPACING });
        scale.scrollToPosition(1, false);
        this.sync();
    }
    private preview() {
        const scale = this.panel.chart.timeScale(), range = scale.getVisibleLogicalRange();
        const latest = this.rows.at(-1);
        if (!range || !latest || this.previewing) return;
        this.saved = { range, spacing: scale.options().barSpacing };
        const cutoff = new Date(dayKey(latest.time) + 'T12:00:00Z');
        cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 1);
        const first = this.rows.find(row => dayKey(row.time) >= cutoff.toISOString().slice(0, 10))!;
        this.panel.chart.applyOptions({ handleScale: false, handleScroll: false });
        this.panel.chart.priceScale('right').applyOptions({ autoScale: true, scaleMargins: { top: .07, bottom: .05 } });
        scale.setVisibleRange({ from: first.time as UTCTimestamp, to: latest.time as UTCTimestamp });
        this.requestUpdate();
    }
    restore() {
        const saved = this.saved;
        if (!saved) return;
        this.saved = undefined;
        this.panel.chart.applyOptions({
            handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: { price: false, time: true }, axisDoubleClickReset: { price: false, time: false } },
            handleScroll: true,
            rightPriceScale: { autoScale: true, scaleMargins: { top: 0, bottom: 0 } },
        });
        const scale = this.panel.chart.timeScale();
        scale.setVisibleLogicalRange(saved.range);
        scale.applyOptions({ barSpacing: saved.spacing });
        this.sync();
        this.requestUpdate();
    }
    private renderer: IPrimitivePaneRenderer = { draw: target => target.useMediaCoordinateSpace(({ context, mediaSize }) => {
        if (this.previewing) return;
        const scale = this.panel.chart.timeScale(), width = scale.options().barSpacing;
        context.fillStyle = palette.tagNeutral;
        for (const row of this.rows) {
            const x = scale.timeToCoordinate(row.time as UTCTimestamp);
            if (x == null || x + width / 2 < 0 || x - width / 2 > mediaSize.width) continue;
            const high = this.panel.candles.priceToCoordinate(Math.max(row.high, row.open, row.close));
            const low = this.panel.candles.priceToCoordinate(Math.min(row.low, row.open, row.close));
            const left = Math.max(0, x - width / 2), right = Math.min(mediaSize.width, x + width / 2);
            if (high != null && high < 0) context.fillRect(left, 0, right - left, 2);
            if (low != null && low > mediaSize.height - 1) context.fillRect(left, mediaSize.height - 2, right - left, 2);
        }
    }) };
    private view: IPrimitivePaneView = { zOrder: () => 'top', renderer: () => this.renderer };
    paneViews() { return [this.view]; }
}

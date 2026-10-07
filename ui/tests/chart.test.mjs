import test from 'node:test';
import assert from 'node:assert/strict';

// Exercise Panel's event handling; rendering and gesture layout are checked in the real browser.
const nodes = new Map();
function node(id) {
    if (!nodes.has(id)) nodes.set(id, {
        textContent: '', style: {}, dataset: {}, listeners: {}, hidden: false,
        addEventListener(type, handler) { this.listeners[type] = handler; },
        querySelector(selector) { return node(id + selector); },
    });
    return nodes.get(id);
}
globalThis.document = { getElementById: node };
globalThis.ResizeObserver = class { observe() {} };

function chart() {
    const series = [], panes = [0, 1].map(() => ({
        setStretchFactor() {}, getHeight: () => 240, getHTMLElement: () => null,
    }));
    const scale = {
        getVisibleRange: () => null, scrollPosition: () => 0, scrollToPosition() {},
        scrollToRealTime() {}, getVisibleLogicalRange: () => null,
    };
    return {
        addSeries(kind) {
            const item = { kind, rows: [], priceLines: [], applyOptions() {}, coordinateToPrice: y => y / 10,
                createPriceLine(options) {
                    const line = { options: { ...options }, applyOptions(next) { Object.assign(this.options, next); } };
                    this.priceLines.push(line); return line;
                },
                removePriceLine(line) { this.priceLines.splice(this.priceLines.indexOf(line), 1); },
                data() {
                    // Match the public library's field order and omission of whitespace.
                    return this.rows.filter(row => this.kind === 'candle' || row.value !== undefined).map(row =>
                        this.kind === 'candle' ? { open: row.open, high: row.high, low: row.low, close: row.close, time: row.time }
                            : { value: row.value, time: row.time, ...(row.color ? { color: row.color } : {}) });
                },
                setData(data) { this.rows = data; },
                update(row, historicalUpdate = false) {
                    const index = this.rows.findIndex(item => item.time === row.time);
                    if (index < 0) this.rows.push(row); else this.rows[index] = row;
                },
            };
            series.push(item);
            return item;
        },
        panes: () => panes, priceScale: () => ({ width: () => 55 }), timeScale: () => scale,
        subscribeCrosshairMove(handler) { this.crosshair = handler; }, subscribeClick() {},
        move(time, mouse = false, y = 88, paneIndex = 0) {
            const seriesData = new Map();
            for (const item of series) {
                const row = item.rows.find(row => row.time === time);
                if (row) seriesData.set(item, row);
            }
            this.crosshair({ time, seriesData, point: { x: 100, y }, paneIndex, sourceEvent: mouse ? {} : undefined });
        },
        // The real programmatic API updates the crosshair without emitting a move event.
        setCrosshairPosition(price, time, series) { this.crosshairTime = time; this.crosshairPrice = price; this.crosshairSeries = series; },
        clearCrosshairPosition() { this.crosshairTime = undefined; this.crosshairPrice = undefined; },
    };
}
globalThis.window = { LightweightCharts: {
    createChart: chart, ColorType: { Solid: 0 }, CrosshairMode: { Normal: 0 }, LineStyle: { LargeDashed: 3 },
    CandlestickSeries: 'candle', LineSeries: 'line', HistogramSeries: 'volume',
} };
const { Panel, linkTradingDay } = await import('../public/chart.js');

const at = value => Date.parse(value) / 1000;
const first = at('2026-10-01T13:30:00Z'), latest = at('2026-10-02T13:30:00Z');
const row = (time, volume) => ({ time, open: 10, high: 12, low: 9, close: 11, volume });
const snapshot = (bars, active = null) => ({ revision: 1, bars, active, indicators: {}, indicator_preview: {} });
const label = panel => node(panel.id + '-volume').textContent;

test('hovered closed volume survives quote updates and refreshes from the same candle', () => {
    const panel = new Panel('hover', true);
    panel.render(snapshot([row(first, 100), row(latest, 200)], row(latest + 300, 300)));
    panel.chart.move(first, true);
    assert.equal(label(panel), 'Vol 100');
    panel.render({ revision: 1, active: row(latest + 300, 400), indicator_preview: {} });
    assert.equal(label(panel), 'Vol 100');
    panel.render(snapshot([row(first, 150), row(latest, 200)], row(latest + 300, 400)));
    assert.equal(label(panel), 'Vol 150');
    node(panel.id + '-chart').listeners.mouseleave();
    assert.equal(label(panel), 'Vol 400');
});

test('price remains linked without a matching date; time and price clear independently', () => {
    const daily = new Panel('independent-daily', true), intraday = new Panel('independent-intraday', false);
    daily.render(snapshot([row(first, 1000), row(latest, 2000)]));
    intraday.render(snapshot([row(latest, 30)]));
    const link = linkTradingDay(daily, intraday);
    daily.chart.move(first, true);
    assert.equal(intraday.chart.crosshairTime, undefined);
    assert.equal(intraday.candles.priceLines.length, 1);
    const priceLine = intraday.candles.priceLines[0];
    assert.equal(priceLine.options.price, 8.8);
    assert.equal(label(intraday), 'Vol 30');
    daily.chart.move(first, true, 93);
    assert.equal(intraday.candles.priceLines[0], priceLine);
    assert.equal(priceLine.options.price, 9.3);
    // Matching time still reaches the chart even when the price is outside its scale.
    daily.chart.move(latest, true, 400);
    assert.equal(intraday.candles.priceLines.length, 0);
    assert.equal(intraday.chart.crosshairTime, latest);
    assert.equal(intraday.chart.crosshairPrice, 40);
    daily.chart.move(first, true, 75, 1);
    assert.equal(intraday.chart.crosshairTime, undefined);
    assert.equal(intraday.volume.priceLines[0].options.price, 7.5);
    node(daily.id + '-chart').listeners.mouseleave();
    assert.equal(intraday.volume.priceLines.length, 0);
    daily.chart.move(undefined, true, 91);
    assert.equal(intraday.candles.priceLines[0].options.price, 9.1);
    link.clear();
    assert.equal(intraday.candles.priceLines.length, 0);
    assert.equal(intraday.chart.crosshairTime, undefined);
});

test('hovered active volume updates and an unknown volume stays absent', () => {
    const panel = new Panel('active', false);
    panel.render(snapshot([row(first, 100)], row(latest, 200)));
    panel.chart.move(latest, true);
    panel.render({ revision: 1, active: row(latest, 250), indicator_preview: {} });
    assert.equal(label(panel), 'Vol 250');
    panel.render({ revision: 1, active: row(latest, null), indicator_preview: {} });
    assert.equal(label(panel), 'Vol —');
});

test('linked crosshair volume follows the peer candle and clears to each latest candle', () => {
    const daily = new Panel('linked-daily', true), intraday = new Panel('linked-intraday', false);
    daily.render(snapshot([row(first, 1000), row(latest, 2000)]));
    intraday.render(snapshot([row(first, 10), row(first + 300, 20), row(latest, 30)]));
    linkTradingDay(daily, intraday);
    daily.chart.move(first, true);
    assert.equal(label(daily), 'Vol 1K');
    assert.equal(label(intraday), 'Vol 10');
    assert.equal(intraday.chart.crosshairPrice, 8.8);
    assert.equal(intraday.chart.crosshairTime, first);
    assert.equal(intraday.chart.crosshairSeries, intraday.candles);
    intraday.render({ revision: 1, active: row(latest + 300, 40), indicator_preview: {} });
    assert.equal(label(intraday), 'Vol 10');
    assert.equal(intraday.chart.crosshairPrice, 8.8);
    node(daily.id + '-chart').listeners.mouseleave();
    assert.equal(label(daily), 'Vol 2K');
    assert.equal(label(intraday), 'Vol 40');
    assert.equal(intraday.chart.crosshairPrice, undefined);
    intraday.chart.move(first + 300, true, 103);
    assert.equal(label(daily), 'Vol 1K');
    assert.equal(label(intraday), 'Vol 20');
    assert.equal(daily.chart.crosshairPrice, 10.3);
    assert.equal(daily.chart.crosshairTime, first);
    intraday.chart.move(first + 300, false, 110);
    assert.equal(daily.chart.crosshairPrice, 10.3);
    intraday.chart.move(first + 300, true, 75, 1);
    assert.equal(daily.chart.crosshairPrice, 7.5);
    assert.equal(daily.chart.crosshairSeries, daily.volume);
});

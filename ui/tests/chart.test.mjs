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
            const item = { kind, data: [], applyOptions() {},
                setData(data) { this.data = data; },
                update(row) {
                    const index = this.data.findIndex(item => item.time === row.time);
                    if (index < 0) this.data.push(row); else this.data[index] = row;
                },
            };
            series.push(item);
            return item;
        },
        panes: () => panes, priceScale: () => ({ width: () => 55 }), timeScale: () => scale,
        subscribeCrosshairMove(handler) { this.crosshair = handler; }, subscribeClick() {},
        move(time, mouse = false) {
            const seriesData = new Map();
            for (const item of series) {
                const row = item.data.find(row => row.time === time);
                if (row) seriesData.set(item, row);
            }
            this.crosshair({ seriesData, sourceEvent: mouse ? {} : undefined });
        },
        // The real programmatic API updates the crosshair without emitting a move event.
        setCrosshairPosition(_price, time) { this.crosshairTime = time; },
        clearCrosshairPosition() { this.crosshairTime = undefined; },
    };
}
globalThis.window = { LightweightCharts: {
    createChart: chart, ColorType: { Solid: 0 }, CrosshairMode: { Normal: 0 }, LineStyle: { Dashed: 0 },
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
    assert.equal(label(panel), 'V 100');
    panel.render({ revision: 1, active: row(latest + 300, 400), indicator_preview: {} });
    assert.equal(label(panel), 'V 100');
    panel.render(snapshot([row(first, 150), row(latest, 200)], row(latest + 300, 400)));
    assert.equal(label(panel), 'V 150');
    node(panel.id + '-chart').listeners.mouseleave();
    assert.equal(label(panel), 'V 400');
});

test('hovered active volume updates and an unknown volume stays absent', () => {
    const panel = new Panel('active', false);
    panel.render(snapshot([row(first, 100)], row(latest, 200)));
    panel.chart.move(latest, true);
    panel.render({ revision: 1, active: row(latest, 250), indicator_preview: {} });
    assert.equal(label(panel), 'V 250');
    panel.render({ revision: 1, active: row(latest, null), indicator_preview: {} });
    assert.equal(label(panel), 'V —');
});

test('linked crosshair volume follows the peer candle and clears to each latest candle', () => {
    const daily = new Panel('linked-daily', true), intraday = new Panel('linked-intraday', false);
    daily.render(snapshot([row(first, 1000), row(latest, 2000)]));
    intraday.render(snapshot([row(first, 10), row(first + 300, 20), row(latest, 30)]));
    linkTradingDay(daily, intraday);
    daily.chart.move(first, true);
    assert.equal(label(daily), 'V 1K');
    assert.equal(label(intraday), 'V 10');
    intraday.render({ revision: 1, active: row(latest + 300, 40), indicator_preview: {} });
    assert.equal(label(intraday), 'V 10');
    node(daily.id + '-chart').listeners.mouseleave();
    assert.equal(label(daily), 'V 2K');
    assert.equal(label(intraday), 'V 40');
    intraday.chart.move(first + 300, true);
    assert.equal(label(daily), 'V 1K');
    assert.equal(label(intraday), 'V 20');
});

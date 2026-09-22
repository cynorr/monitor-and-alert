import { $, money, compact, dayKey } from './types.js';
const L = window.LightweightCharts;
const dateFormat = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric' });
const timeFormat = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
function dateOf(t) { return typeof t === 'number' ? new Date(t * 1000) : typeof t === 'string' ? new Date(t) : new Date(Date.UTC(t.year, t.month - 1, t.day, 12)); }
export class Panel {
    id;
    daily;
    chart;
    candles;
    volume;
    lines = {};
    rows = [];
    indicators = {};
    days = new Map();
    active = null;
    key = '';
    fitted = false;
    initialSpacing = false;
    hovering = false;
    precision = 2;
    onHover = () => { };
    onSelect = () => { };
    constructor(id, daily) {
        this.id = id;
        this.daily = daily;
        this.chart = L.createChart($(id + '-chart'), {
            autoSize: true,
            layout: { background: { type: L.ColorType.Solid, color: '#ffffff' }, textColor: '#727b88', fontSize: 10, attributionLogo: false, panes: { separatorColor: '#c6cbd1', separatorHoverColor: '#a8afb8' } },
            grid: { vertLines: { visible: false }, horzLines: { visible: false } },
            rightPriceScale: { borderVisible: false, minimumWidth: 55, scaleMargins: { top: 0.07, bottom: 0.05 } },
            timeScale: { borderColor: '#171b20', timeVisible: !daily, secondsVisible: false, rightOffset: 1, rightBarStaysOnScroll: true, barSpacing: 6, fixLeftEdge: false, lockVisibleTimeRangeOnResize: false, tickMarkFormatter: (t, type) => (daily || type < 3 ? dateFormat : timeFormat).format(dateOf(t)) },
            localization: { locale: 'en-US', timeFormatter: (t) => daily ? dayKey(Number(t)) : `${dayKey(Number(t))} ${timeFormat.format(dateOf(t))}` },
            crosshair: { mode: L.CrosshairMode.Normal, vertLine: { style: L.LineStyle.Dashed, color: '#737d8c', labelBackgroundColor: '#4c5667' }, horzLine: { style: L.LineStyle.Dashed, color: '#737d8c', labelBackgroundColor: '#4c5667' } },
        });
        this.candles = this.chart.addSeries(L.CandlestickSeries, { upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350', priceLineVisible: false });
        const colors = { ema10: '#2962ff', ema20: '#e4b400', [daily ? 'sma50' : 'sma65']: '#e53935' };
        for (const [name, color] of Object.entries(colors))
            this.lines[name] = this.chart.addSeries(L.LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
        this.volume = this.chart.addSeries(L.HistogramSeries, { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false }, 1);
        this.chart.panes()[0].setStretchFactor(1);
        this.chart.panes()[1].setStretchFactor(0.22);
        const volumePosition = () => {
            const label = $(id + '-volume');
            label.style.top = `${this.chart.panes()[0].getHeight() + 5}px`;
            label.style.right = `${this.chart.priceScale('right').width() + 8}px`;
        };
        const observer = new ResizeObserver(volumePosition);
        observer.observe($(id + '-chart'));
        const mainPane = this.chart.panes()[0].getHTMLElement();
        if (mainPane)
            observer.observe(mainPane);
        this.chart.subscribeCrosshairMove(param => {
            const candle = param.seriesData.get(this.candles);
            const volume = param.seriesData.get(this.volume);
            const row = candle ? { ...candle, time: Number(candle.time), volume: volume?.value ?? null } : undefined;
            this.hovering = !!row;
            this.showOHLC(row ?? this.active ?? this.rows.at(-1));
            // Programmatic/refresh events must not bounce the peer's candle price
            // back onto the mouse-driven crosshair.
            if (param.sourceEvent)
                this.onHover(row);
        });
        this.chart.subscribeClick(param => {
            const row = param.seriesData.get(this.candles);
            if (row)
                this.onSelect({ ...row, time: Number(row.time), volume: null });
        });
        $(id + '-chart').addEventListener('mouseleave', () => this.onHover());
        $(id + '-latest').addEventListener('click', () => {
            this.chart.timeScale().scrollToRealTime();
            const latest = this.active ?? this.rows.at(-1);
            if (latest)
                this.onSelect(latest);
        });
    }
    reset(key) {
        if (this.key === key)
            return;
        this.key = key;
        this.rows = [];
        this.days.clear();
        this.indicators = {};
        this.active = null;
        this.fitted = false;
        this.hovering = false;
        this.chart.clearCrosshairPosition();
        this.candles.setData([]);
        this.volume.setData([]);
        Object.values(this.lines).forEach(line => line.setData([]));
        $(this.id + '-empty').hidden = false;
        this.showOHLC();
        $(this.id + '-volume').textContent = 'V —';
        for (const name of Object.keys(this.lines)) {
            const node = $(this.id + '-legend').querySelector('.' + name);
            node.hidden = true;
        }
    }
    candle(row) { return { time: row.time, open: row.open, high: row.high, low: row.low, close: row.close }; }
    histogram(row) { return row.volume == null ? { time: row.time } : { time: row.time, value: row.volume, color: row.close >= row.open ? '#26a69a99' : '#ef535099' }; }
    render(data) {
        const next = data.active;
        const rebuild = data.bars !== undefined || this.active?.time !== next?.time || (!!this.active && this.active.volume !== null && next?.volume === null);
        if (data.bars !== undefined) {
            this.rows = data.bars;
            this.indicators = data.indicators ?? {};
        }
        this.active = next;
        const latest = next ?? this.rows.at(-1);
        if (latest) {
            const precision = latest.close < 1 ? 4 : 2;
            if (precision !== this.precision) {
                this.candles.applyOptions({ priceFormat: { type: 'price', precision, minMove: 10 ** -precision } });
                this.precision = precision;
            }
        }
        if (rebuild) {
            const scale = this.chart.timeScale(), timeRange = scale.getVisibleRange(), browsing = scale.scrollPosition() < 0;
            const rows = [...this.rows, ...(next ? [next] : [])];
            this.days.clear();
            for (const row of rows) {
                const day = dayKey(row.time);
                const items = this.days.get(day) ?? [];
                items.push(row);
                this.days.set(day, items);
            }
            this.candles.setData(rows.map(row => this.candle(row)));
            this.volume.setData(rows.map(row => this.histogram(row)));
            for (const [name, line] of Object.entries(this.lines))
                line.setData([...(this.indicators[name] ?? []), ...(data.indicator_preview[name] ? [data.indicator_preview[name]] : [])]);
            if (this.fitted && browsing && timeRange)
                scale.setVisibleRange(timeRange);
            else if (this.fitted)
                scale.scrollToPosition(1, false);
        }
        else if (next) {
            this.candles.update(this.candle(next));
            this.volume.update(this.histogram(next));
            const items = this.days.get(dayKey(next.time));
            if (items)
                items[items.length - 1] = next;
            for (const [name, line] of Object.entries(this.lines)) {
                const value = data.indicator_preview[name];
                if (value)
                    line.update(value);
            }
        }
        if (this.daily && !this.initialSpacing && this.rows.length && latest) {
            const scale = this.chart.timeScale();
            const cutoff = new Date(latest.time * 1000);
            cutoff.setUTCMonth(cutoff.getUTCMonth() - 9);
            const samples = this.rows[0].time * 1000 <= cutoff.getTime() ? this.rows.filter(r => r.time * 1000 >= cutoff.getTime()).length : 189;
            scale.applyOptions({ barSpacing: Math.max(0.5, scale.width() / (samples + 2)) });
            this.initialSpacing = true;
        }
        if (!this.fitted && latest) {
            const scale = this.chart.timeScale();
            scale.scrollToPosition(1, false);
            this.fitted = true;
        }
        $(this.id + '-empty').hidden = !!latest;
        $(this.id + '-volume').textContent = `V ${compact(latest?.volume)}`;
        if (!this.hovering)
            this.showOHLC(latest);
        for (const name of Object.keys(this.lines)) {
            const point = data.indicator_preview[name] ?? this.indicators[name]?.at(-1);
            const node = $(this.id + '-legend').querySelector('.' + name);
            node.hidden = !point;
        }
    }
    showOHLC(row) {
        const node = $(this.id + '-ohlc');
        if (!row) {
            node.textContent = '—';
            return;
        }
        const range = row.low > 0 ? ((row.high - row.low) / row.low * 100).toFixed(2) + '%' : '—';
        node.innerHTML = `O ${money(row.open)}  H <b>${money(row.high)}</b>  L <b>${money(row.low)}</b>  C ${money(row.close)}  <span title="(H − L) / L">Range <b>${range}</b></span>`;
    }
    reveal(row) {
        const index = this.rows.findIndex(r => r.time === row.time);
        const logical = index >= 0 ? index : this.rows.length;
        const scale = this.chart.timeScale(), range = scale.getVisibleLogicalRange();
        if (!range || (logical >= range.from && logical <= range.to))
            return;
        const half = (range.to - range.from) / 2;
        scale.setVisibleLogicalRange({ from: logical - half, to: logical + half });
    }
}
export function linkTradingDay(daily, intraday) {
    let linking = false, selectedTime;
    const restored = new Map();
    function target(peer, row) {
        const items = peer.days.get(dayKey(row.time));
        return items?.find(item => item.time === selectedTime) ?? items?.[0];
    }
    for (const [source, peer] of [[daily, intraday], [intraday, daily]]) {
        source.onHover = row => {
            if (linking)
                return;
            linking = true;
            try {
                const match = row ? target(peer, row) : undefined;
                if (match)
                    peer.chart.setCrosshairPosition(match.close, match.time, peer.candles);
                else
                    peer.chart.clearCrosshairPosition();
            }
            finally {
                linking = false;
            }
        };
        source.onSelect = row => {
            selectedTime = row.time;
            const day = dayKey(row.time);
            for (const panel of [daily, intraday]) {
                $(panel.id + '-panel').dataset.selectedDay = day;
                restored.set(panel, panel.key);
            }
            const match = target(peer, row);
            if (match)
                peer.reveal(match);
            source.onHover(row);
        };
    }
    return {
        clear() {
            selectedTime = undefined;
            restored.clear();
            for (const panel of [daily, intraday])
                delete $(panel.id + '-panel').dataset.selectedDay;
        },
        restore() {
            if (selectedTime === undefined)
                return;
            for (const panel of [daily, intraday]) {
                if (restored.get(panel) === panel.key)
                    continue;
                const items = panel.days.get(dayKey(selectedTime));
                const match = items?.find(row => row.time === selectedTime) ?? items?.[0];
                if (match) {
                    panel.reveal(match);
                    restored.set(panel, panel.key);
                }
            }
        },
    };
}

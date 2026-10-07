import type { IChartApi, ISeriesApi, IPriceLine, UTCTimestamp, Time, CandlestickData, LineData } from 'lightweight-charts';
import type * as ChartLibrary from 'lightweight-charts';
import { $, money, compact, dayKey, type Row, type Point, type ChartData } from './types.js';
import { BAR_SPACING, VOLUME_PANE_RATIO } from './chart-settings.js';
declare global {
    interface Window {
        LightweightCharts: typeof ChartLibrary;
    }
}
const L = window.LightweightCharts;
const dateFormat = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric' });
const timeFormat = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
function dateOf(t: Time) { return typeof t === 'number' ? new Date(t * 1000) : typeof t === 'string' ? new Date(t) : new Date(Date.UTC(t.year, t.month - 1, t.day, 12)); }
function syncSeries<T extends 'Candlestick' | 'Histogram' | 'Line'>(series: ISeriesApi<T>, rows: ReturnType<ISeriesApi<T>['data']>) {
    const previous = series.data();
    if (!previous.length && !rows.length) return false;
    // A new window needs setData; replacing a provisional tail uses update.
    if (!previous.length || rows.length < previous.length || previous.some((row, i) => row.time !== rows[i].time)) {
        series.setData([...rows]);
        return true;
    }
    for (let i = 0; i < rows.length; i++) {
        const old = previous[i] as unknown as Record<string, unknown> | undefined;
        const row = rows[i] as unknown as Record<string, unknown>;
        if (!old || Object.keys({ ...old, ...row }).some(key => old[key] !== row[key]))
            series.update(rows[i], i < previous.length - 1);
    }
    return false;
}
export class Panel {
    chart: IChartApi;
    candles: ISeriesApi<'Candlestick'>;
    volume: ISeriesApi<'Histogram'>;
    lines: Record<string, ISeriesApi<'Line'>> = {};
    rows: Row[] = [];
    indicators: Record<string, Point[]> = {};
    days = new Map<string, Row[]>();
    active: Row | null = null;
    key = '';
    fitted = false;
    hoveredTime?: number;
    precision = 2;
    private linkedPrice?: { series: ISeriesApi<'Candlestick'> | ISeriesApi<'Histogram'>; line: IPriceLine };
    onHover: (row?: Row, price?: number, paneIndex?: number, time?: number) => void = () => { };
    onSelect: (row: Row) => void = () => { };
    constructor(public id: string, public daily: boolean) {
        this.chart = L.createChart($(id + '-chart'), {
            autoSize: true,
            layout: { background: { type: L.ColorType.Solid, color: '#ffffff' }, textColor: '#727b88', fontSize: 12, attributionLogo: false, panes: { separatorColor: '#c6cbd1', separatorHoverColor: '#a8afb8' } },
            grid: { vertLines: { visible: false }, horzLines: { visible: false } },
            rightPriceScale: { borderVisible: false, minimumWidth: 55, scaleMargins: { top: 0.07, bottom: 0.05 } },
            timeScale: { borderColor: '#171b20', timeVisible: !daily, secondsVisible: false, rightOffset: 1, rightBarStaysOnScroll: true, barSpacing: BAR_SPACING, fixLeftEdge: false, lockVisibleTimeRangeOnResize: false, tickMarkFormatter: (t: Time, type: number) => (daily || type < 3 ? dateFormat : timeFormat).format(dateOf(t)) },
            localization: { locale: 'en-US', timeFormatter: (t: Time) => daily ? dayKey(Number(t)) : `${dayKey(Number(t))} ${timeFormat.format(dateOf(t))}` },
            crosshair: { mode: L.CrosshairMode.Normal, vertLine: { width: 1, style: L.LineStyle.LargeDashed, color: '#737d8c', labelBackgroundColor: '#4c5667' }, horzLine: { width: 1, style: L.LineStyle.LargeDashed, color: '#737d8c', labelBackgroundColor: '#4c5667' } },
        });
        this.candles = this.chart.addSeries(L.CandlestickSeries, { upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350', priceLineVisible: false });
        const colors = { ema10: '#2962ff', ema20: '#e4b400', [daily ? 'sma50' : 'sma65']: '#e53935' };
        for (const [name, color] of Object.entries(colors))
            this.lines[name] = this.chart.addSeries(L.LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
        this.volume = this.chart.addSeries(L.HistogramSeries, { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false }, 1);
        this.chart.panes()[0].setStretchFactor(1 - VOLUME_PANE_RATIO);
        this.chart.panes()[1].setStretchFactor(VOLUME_PANE_RATIO);
        const volumePosition = () => {
            const label = $(id + '-volume');
            label.style.top = `${this.chart.panes()[0].getHeight() + 5}px`;
            label.style.right = `${this.chart.priceScale('right').width() + 8}px`;
        };
        const observer = new ResizeObserver(volumePosition);
        observer.observe($(id + '-chart'));
        const mainPane = this.chart.panes()[0].getHTMLElement();
        if (mainPane) observer.observe(mainPane);
        this.chart.subscribeCrosshairMove(param => {
            const candle = param.seriesData.get(this.candles) as CandlestickData | undefined;
            // The library supplies the time; the original row owns Vol and its comparison.
            const time = candle ? Number(candle.time) : undefined;
            const row = time === this.active?.time ? this.active ?? undefined : this.rows.find(row => row.time === time);
            this.showHover(row);
            // Link the pointer's value, never the candle close or histogram value.
            if (param.sourceEvent) {
                const paneIndex = param.paneIndex ?? 0;
                const series = paneIndex === 1 ? this.volume : this.candles;
                const price = param.point ? series.coordinateToPrice(param.point.y) : null;
                this.onHover(row, price ?? undefined, paneIndex, typeof param.time === 'number' ? param.time : undefined);
            }
        });
        this.chart.subscribeClick(param => { const row = param.seriesData.get(this.candles) as CandlestickData | undefined; if (row)
            this.onSelect({ ...row, time: Number(row.time), volume: null }); });
        $(id + '-chart').addEventListener('mouseleave', () => {
            this.showHover();
            this.onHover();
        });
        $(id + '-latest').addEventListener('click', () => {
            this.chart.timeScale().scrollToRealTime();
            const latest = this.active ?? this.rows.at(-1);
            if (latest) this.onSelect(latest);
        });
    }
    reset(key: string) {
        if (this.key === key)
            return;
        this.key = key;
        this.rows = [];
        this.days.clear();
        this.indicators = {};
        this.active = null;
        this.fitted = false;
        this.hoveredTime = undefined;
        this.clearLinkedPrice();
        this.chart.clearCrosshairPosition();
        this.candles.setData([]);
        this.volume.setData([]);
        Object.values(this.lines).forEach(line => line.setData([]));
        $(this.id + '-empty').hidden = false;
        this.showCandleInfo();
        for (const name of Object.keys(this.lines)) {
            const node = $(this.id + '-legend').querySelector<HTMLElement>('.' + name)!;
            node.hidden = true;
        }
    }
    candle(row: Row): CandlestickData { return { time: row.time as UTCTimestamp, open: row.open, high: row.high, low: row.low, close: row.close }; }
    histogram(row: Row) { return row.volume == null ? { time: row.time as UTCTimestamp } : { time: row.time as UTCTimestamp, value: row.volume, color: row.close >= row.open ? '#26a69a99' : '#ef535099' }; }
    render(data: ChartData) {
        const next = data.active;
        const rebuild = data.bars !== undefined || this.active?.time !== next?.time;
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
            const replaced = syncSeries(this.candles, rows.map(row => this.candle(row)));
            syncSeries(this.volume, rows.map(row => this.histogram(row)));
            for (const [name, line] of Object.entries(this.lines))
                syncSeries(line, [...(this.indicators[name] ?? []), ...(data.indicator_preview[name] ? [data.indicator_preview[name]] : [])] as LineData[]);
            if (replaced && this.fitted && browsing && timeRange)
                scale.setVisibleRange(timeRange);
            else if (replaced && this.fitted)
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
                if (value) line.update(value as LineData);
            }
        }
        if (!this.fitted && latest) {
            const scale = this.chart.timeScale();
            scale.scrollToPosition(1, false);
            this.fitted = true;
        }
        $(this.id + '-empty').hidden = !!latest;
        const hovered = this.hoveredTime === next?.time ? next : this.rows.find(row => row.time === this.hoveredTime);
        this.showCandleInfo(hovered ?? latest);
        for (const name of Object.keys(this.lines)) {
            const point = data.indicator_preview[name] ?? this.indicators[name]?.at(-1);
            const node = $(this.id + '-legend').querySelector<HTMLElement>('.' + name)!;
            node.hidden = !point;
        }
    }
    showCandleInfo(row?: Row) {
        const volume = $(this.id + '-volume');
        const comparison = row?.volume_comparison;
        const percent = comparison?.percent;
        volume.textContent = `Vol ${compact(row?.volume)} · 5D Avg ${percent == null ? '—' : Math.trunc(percent) + '%'}`;
        volume.title = row?.time === this.active?.time && row ? (row.volume == null ? 'Current candle volume unavailable'
            : this.daily ? 'Current daily cumulative volume' : 'Volume for the current intraday candle') : 'Volume for this candle';
        volume.title += comparison ? `\nPrevious 5 trading days${this.daily ? '' : ', same regular-session time slot'}: average ${compact(comparison.average)}, ${comparison.samples} available sample${comparison.samples === 1 ? '' : 's'}. 100% = average.`
            : '\nPrevious 5 trading days: comparison unavailable.';
        const node = $(this.id + '-ohlc');
        if (!row) { node.textContent = '—'; return; }
        const range = row.low > 0 ? ((row.high - row.low) / row.low * 100).toFixed(2) + '%' : '—';
        node.innerHTML = `<span>O ${money(row.open)}</span><span>H <b>${money(row.high)}</b></span><span>L <b>${money(row.low)}</b></span><span>C ${money(row.close)}</span><span title="(H − L) / L">Range <b>${range}</b></span>`;
    }
    showHover(row?: Row) {
        this.hoveredTime = row?.time;
        this.showCandleInfo(row ?? this.active ?? this.rows.at(-1));
    }
    private clearLinkedPrice() {
        if (this.linkedPrice) this.linkedPrice.series.removePriceLine(this.linkedPrice.line);
        this.linkedPrice = undefined;
    }
    showLinkedHover(row?: Row, price?: number, paneIndex = 0) {
        const series = paneIndex === 1 ? this.volume : this.candles;
        if (row && price !== undefined) {
            this.clearLinkedPrice();
            this.chart.setCrosshairPosition(price, row.time as UTCTimestamp, series);
        } else {
            this.chart.clearCrosshairPosition();
            if (price === undefined) this.clearLinkedPrice();
            else {
                if (this.linkedPrice?.series !== series) {
                    this.clearLinkedPrice();
                    this.linkedPrice = { series, line: series.createPriceLine({ price, color: '#737d8c', lineWidth: 1,
                        lineStyle: L.LineStyle.LargeDashed, axisLabelColor: '#4c5667', axisLabelTextColor: '#ffffff', axisLabelVisible: true }) };
                } else this.linkedPrice.line.applyOptions({ price });
            }
        }
        // No matching date still allows a price line; OHLC/Vol stay at latest.
        this.showHover(row);
    }
    reveal(row: Row) {
        const index = this.rows.findIndex(r => r.time === row.time);
        const logical = index >= 0 ? index : this.rows.length;
        const scale = this.chart.timeScale(), range = scale.getVisibleLogicalRange();
        if (!range || (logical >= range.from && logical <= range.to))
            return;
        const half = (range.to - range.from) / 2;
        scale.setVisibleLogicalRange({ from: logical - half, to: logical + half });
    }
}
export function linkTradingDay(daily: Panel, intraday: Panel) {
    let linking = false, selectedTime: number | undefined;
    const restored = new Map<Panel, string>();
    function target(peer: Panel, time: number) {
        const items = peer.days.get(dayKey(time));
        return items?.find(item => item.time === selectedTime) ?? items?.[0];
    }
    for (const [source, peer] of [[daily, intraday], [intraday, daily]]) {
        source.onHover = (row, price, paneIndex = 0, time = row?.time) => {
            if (linking)
                return;
            linking = true;
            try {
                const match = time === undefined ? undefined : target(peer, time);
                peer.showLinkedHover(match, price, paneIndex);
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
            const match = target(peer, row.time);
            if (match)
                peer.reveal(match);
        };
    }
    return {
        clear() { selectedTime = undefined; restored.clear(); for (const panel of [daily, intraday]) {
            panel.showLinkedHover(); delete $(panel.id + '-panel').dataset.selectedDay;
        } },
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

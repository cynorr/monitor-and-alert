/* Android's one local chart. Only chart drawing crosses the native/WebView boundary. */
(() => {
    const L = LightweightCharts, host = document.getElementById('chart');
    let palette, chart, candles, amount, lines, rows = [], byTime = new Map(), anchor, context, priceLine, latestQuote;
    let viewport = { width: innerWidth, height: innerHeight };
    window.resizeDaily = (width, height) => {
        viewport = { width, height };
        for (const element of [document.documentElement, document.body, host]) {
            element.style.width = width + 'px'; element.style.height = height + 'px';
        }
        if (chart) { chart.resize(Math.floor(width), Math.floor(height)); candles.applyOptions({}); }
    };
    const formatter = value => {
        for (const [size, unit] of [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']])
            if (Math.abs(value) >= size) return '$' + (value / size).toFixed(2) + unit;
        return '$' + value.toFixed(0);
    };
    function readout(row) {
        document.getElementById('amount').textContent = row ?
            'Dollar Vol ' + (row.turnover == null ? '—' : formatter(row.turnover)) + ' · 5D Avg ' +
            (row.comparison == null ? '—' : Math.trunc(row.comparison) + '%') : '';
    }
    function notify(row) {
        NativeChart.hover(row ? JSON.stringify({ ...row, symbol: context.symbol, date: context.date }) : 'null');
    }
    function initialize() {
        if (chart) return;
        chart = L.createChart(host, {
            autoSize: false, width: Math.floor(viewport.width), height: Math.floor(viewport.height),
            localization: { locale: 'en-US' },
            layout: { background: { color: palette.white }, textColor: palette.ink, fontFamily: 'sans-serif', fontSize: 11,
                attributionLogo: false, panes: { separatorColor: palette.volumeLow, separatorHoverColor: palette.volumeLow, enableResize: true } },
            grid: { vertLines: { visible: false }, horzLines: { visible: false } },
            crosshair: { mode: L.CrosshairMode.Normal, vertLine: { style: L.LineStyle.Dashed }, horzLine: { style: L.LineStyle.Dashed } },
            rightPriceScale: { borderVisible: false, minimumWidth: 62, autoScale: true, mode: 0, scaleMargins: { top: 0, bottom: 0 } },
            timeScale: { borderVisible: false, barSpacing: 5, rightOffset: 1, minBarSpacing: 1 },
            handleScroll: { horzTouchDrag: true, vertTouchDrag: false, mouseWheel: true, pressedMouseMove: true },
            handleScale: { pinch: true, mouseWheel: true, axisPressedMouseMove: { price: false, time: true }, axisDoubleClickReset: { price: false, time: false } },
        });
        candles = chart.addSeries(L.CandlestickSeries, {
            upColor: palette.candleUp, downColor: palette.candleDown, borderVisible: false,
            wickUpColor: palette.candleUp, wickDownColor: palette.candleDown,
            lastValueVisible: false, priceLineVisible: false,
            autoscaleInfoProvider: original => {
                if (anchor == null) return original();
                const height = chart.panes()[0].getHeight() - 1;
                const span = anchor * .01 * height / chart.timeScale().options().barSpacing;
                const low = anchor - span * 2 / 3;
                return { priceRange: { minValue: low, maxValue: low + span } };
            },
        });
        lines = Object.fromEntries([['ema10', palette.blue], ['ema20', palette.yellow], ['sma50', palette.red]].map(([key, color]) => [key,
            chart.addSeries(L.LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, autoscaleInfoProvider: () => null })]));
        amount = chart.addSeries(L.HistogramSeries, { priceFormat: { type: 'custom', formatter }, priceLineVisible: false, lastValueVisible: false }, 1);
        chart.panes()[0].setStretchFactor(72); chart.panes()[1].setStretchFactor(28);
        candles.attachPrimitive({
            paneViews: () => [{ zOrder: () => 'top', renderer: () => ({ draw: target => target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
                ctx.fillStyle = palette.tagNeutral;
                const width = chart.timeScale().options().barSpacing;
                for (const row of rows) {
                    const x = chart.timeScale().timeToCoordinate(row.time);
                    if (x == null || x + width / 2 < 0 || x - width / 2 > mediaSize.width) continue;
                    const high = candles.priceToCoordinate(Math.max(row.high, row.open, row.close));
                    const low = candles.priceToCoordinate(Math.min(row.low, row.open, row.close));
                    if (high != null && high < 0) ctx.fillRect(Math.max(0, x - width / 2), 0, width, 2);
                    if (low != null && low > mediaSize.height - 1) ctx.fillRect(Math.max(0, x - width / 2), mediaSize.height - 2, width, 2);
                }
            }) }) }],
        });
        chart.timeScale().subscribeVisibleLogicalRangeChange(() => candles.applyOptions({}));
        chart.subscribeCrosshairMove(event => {
            const row = event.time == null ? null : byTime.get(event.time);
            readout(row || rows.at(-1)); notify(row);
        });
    }
    let pending;
    window.loadDaily = data => {
        if (!palette) { pending = data; return; }
        window.resizeDaily(viewport.width, viewport.height);
        initialize(); context = data;
        rows = data?.rows || []; byTime = new Map(rows.map(row => [row.time, row]));
        const closes = rows.slice(-5).map(row => row.close).sort((a, b) => a - b);
        anchor = closes.length ? (closes[Math.floor(closes.length / 2)] + closes[Math.floor((closes.length - 1) / 2)]) / 2 : null;
        candles.setData(rows);
        amount.setData(rows.map(row => row.turnover == null ? { time: row.time } : { time: row.time, value: row.turnover, color: row.close >= row.open ? palette.candleUp : palette.candleDown }));
        for (const [key, series] of Object.entries(lines)) series.setData(rows.filter(row => row[key] != null).map(row => ({ time: row.time, value: row[key] })));
        document.getElementById('empty').textContent = rows.length ? '' : data ? 'No local Daily history' : 'Select a symbol';
        readout(rows.at(-1)); window.resetDaily(); notify(null);
        window.updateQuote(latestQuote);
    };
    window.updateQuote = quote => {
        latestQuote = quote;
        if (!chart) return;
        if (!quote || !rows.length) { if (priceLine) candles.removePriceLine(priceLine); priceLine = null; return; }
        const color = quote.session === 'pre' ? palette.yellow : quote.session === 'post' ? palette.blue :
            quote.session === 'overnight' ? palette.ink : quote.previousClose == null || quote.price >= quote.previousClose ? palette.candleUp : palette.candleDown;
        const options = { price: quote.price, color, lineVisible: false, axisLabelVisible: true,
            axisLabelColor: color, axisLabelTextColor: quote.session === 'pre' ? palette.ink : palette.white };
        if (priceLine) priceLine.applyOptions(options); else priceLine = candles.createPriceLine(options);
    };
    window.resetDaily = () => { if (!chart) return; chart.timeScale().applyOptions({ barSpacing: 5 }); chart.timeScale().scrollToPosition(1, false); candles.applyOptions({}); };
    fetch('palette.json').then(result => result.json()).then(value => { palette = value; window.loadDaily(pending || null); });
})();

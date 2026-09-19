const L = window.LightweightCharts;
const $ = (id) => document.getElementById(id);
const money = (n) => n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: n < 1 ? 4 : 2 });
const compact = (n) => n == null ? '—' : Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(n);
const nyDate = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric' });
const nyTime = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const nyFull = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
function dateOf(t) { return typeof t === 'number' ? new Date(t * 1000) : typeof t === 'string' ? new Date(t) : new Date(Date.UTC(t.year, t.month - 1, t.day, 12)); }
const colors = { ema10: '#bd984e', ema20: '#5f8db4', sma50: '#a183b1' };
class Panel {
    id;
    daily;
    chart;
    candles;
    volume;
    lines = {};
    rows = [];
    indicators = {};
    active = null;
    key = '';
    fitted = false;
    hovering = false;
    precision = 2;
    constructor(id, daily) {
        this.id = id;
        this.daily = daily;
        this.chart = L.createChart($(id + '-chart'), {
            autoSize: true,
            layout: { background: { type: L.ColorType.Solid, color: '#ffffff' }, textColor: '#86968d', fontSize: 10, panes: { separatorColor: '#e9eeea', separatorHoverColor: '#d0ded5' } },
            grid: { vertLines: { color: '#f6f8f6' }, horzLines: { color: '#f0f4f1' } },
            rightPriceScale: { borderColor: '#eef2ee', minimumWidth: 60, scaleMargins: { top: 0.13, bottom: 0.08 } },
            timeScale: { borderColor: '#e9eeea', timeVisible: !daily, secondsVisible: false, rightOffset: 5, barSpacing: daily ? 6 : 7, tickMarkFormatter: (time, type) => (daily || type < 3 ? nyDate : nyTime).format(dateOf(time)) },
            localization: { locale: 'en-US', timeFormatter: (time) => (daily ? nyDate : nyFull).format(dateOf(time)) },
            crosshair: { mode: L.CrosshairMode.Normal, vertLine: { color: '#b6c7bc', labelBackgroundColor: '#4c6e5e' }, horzLine: { color: '#b6c7bc', labelBackgroundColor: '#4c6e5e' } },
        });
        this.candles = this.chart.addSeries(L.CandlestickSeries, { upColor: '#268a70', downColor: '#d37b6b', borderVisible: false, wickUpColor: '#268a70', wickDownColor: '#d37b6b', priceLineColor: '#879d90', priceLineStyle: L.LineStyle.Dashed });
        for (const [name, color] of Object.entries(colors))
            this.lines[name] = this.chart.addSeries(L.LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
        this.volume = this.chart.addSeries(L.HistogramSeries, { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false }, 1);
        this.chart.panes()[0].setStretchFactor(1);
        this.chart.panes()[1].setStretchFactor(0.22);
        this.chart.subscribeCrosshairMove(param => {
            const row = param.seriesData.get(this.candles);
            this.hovering = !!row;
            if (row) {
                const vol = param.seriesData.get(this.volume);
                this.showOHLC({ ...row, time: Number(row.time), volume: vol?.value ?? null });
            }
            else
                this.showOHLC(this.active ?? this.rows.at(-1));
        });
        $(id + '-latest').addEventListener('click', () => this.chart.timeScale().scrollToRealTime());
    }
    reset(key) {
        if (this.key === key)
            return;
        this.key = key;
        this.rows = [];
        this.indicators = {};
        this.active = null;
        this.fitted = false;
        this.candles.setData([]);
        this.volume.setData([]);
        Object.values(this.lines).forEach(line => line.setData([]));
        $(this.id + '-empty').hidden = false;
        $(this.id + '-empty').textContent = '正在加载…';
        $(this.id + '-state').textContent = '加载';
        this.showOHLC(undefined);
        $(this.id + '-count').textContent = '—';
        for (const [name, label] of Object.entries({ ema10: 'EMA 10', ema20: 'EMA 20', sma50: 'SMA 50' }))
            $(this.id + '-legend').querySelector('.' + name).textContent = label;
    }
    candle(row) { return { time: row.time, open: row.open, high: row.high, low: row.low, close: row.close }; }
    histogram(row) { return row.volume == null ? { time: row.time } : { time: row.time, value: row.volume, color: row.close >= row.open ? '#268a704d' : '#d37b6b4d' }; }
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
            const range = this.chart.timeScale().getVisibleLogicalRange();
            const timeRange = this.chart.timeScale().getVisibleRange();
            const browsingHistory = this.chart.timeScale().scrollPosition() < 0;
            const rows = [...this.rows, ...(next ? [next] : [])];
            this.candles.setData(rows.map(row => this.candle(row)));
            this.volume.setData(rows.map(row => this.histogram(row)));
            for (const [name, line] of Object.entries(this.lines))
                line.setData([...(this.indicators[name] ?? []), ...(data.indicator_preview[name] ? [data.indicator_preview[name]] : [])]);
            if (this.fitted && browsingHistory && timeRange)
                this.chart.timeScale().setVisibleRange(timeRange);
            else if (this.fitted && range)
                this.chart.timeScale().setVisibleLogicalRange(range);
        }
        else if (next) {
            this.candles.update(this.candle(next));
            this.volume.update(this.histogram(next));
            for (const [name, value] of Object.entries(data.indicator_preview))
                this.lines[name].update(value);
        }
        if (!this.fitted && this.rows.length) {
            const count = this.rows.length + (next ? 1 : 0);
            this.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, count - (this.daily ? 110 : 85)), to: count + 5 });
            this.fitted = true;
        }
        $(this.id + '-empty').hidden = !!latest;
        $(this.id + '-count').textContent = `${this.rows.length.toLocaleString()} BARS${next ? ' · LIVE' : ''}`;
        if (!this.hovering)
            this.showOHLC(latest);
        for (const [name, label] of Object.entries({ ema10: 'EMA 10', ema20: 'EMA 20', sma50: 'SMA 50' })) {
            const p = data.indicator_preview[name] ?? this.indicators[name]?.at(-1);
            $(this.id + '-legend').querySelector('.' + name).textContent = `${label}${p ? '  ' + money(p.value) : ''}`;
        }
    }
    showOHLC(row) { $(this.id + '-ohlc').textContent = row ? `O ${money(row.open)}   H ${money(row.high)}   L ${money(row.low)}   C ${money(row.close)}   V ${compact(row.volume)}` : '等待历史数据'; }
}
const daily = new Panel('daily', true), intraday = new Panel('intraday', false);
let tickers = [], symbol = '', timeframe = '5m', epoch = 0, streamEpoch = -1;
let socket = null, request = null;
let reconnectTimer, healthyKey = '', healthyAt = 0, lastMessage = 0, reconnectDelay = 1000;
let currentView = null;
function latestQuote(quote) { return quote ? [quote.regular, ...Object.values(quote.extended)].filter((q) => q !== null).sort((a, b) => b.timestamp - a.timestamp)[0] : undefined; }
function renderList() {
    const term = $('search').value.trim().toUpperCase(), fragment = document.createDocumentFragment();
    const focusedSymbol = document.activeElement?.dataset?.symbol;
    for (const group of ['focus', 'wait']) {
        const items = tickers.filter(t => t.status === group && t.ticker.includes(term));
        if (!items.length)
            continue;
        const label = document.createElement('div');
        label.className = 'group';
        label.textContent = `${group.toUpperCase()}  /  ${items.length.toString().padStart(2, '0')}`;
        fragment.append(label);
        for (const ticker of items) {
            const button = document.createElement('button');
            button.className = 'symbol-row' + (ticker.symbol === symbol ? ' active' : '');
            button.setAttribute('aria-pressed', String(ticker.symbol === symbol));
            button.dataset.symbol = ticker.symbol;
            button.setAttribute('aria-label', `选择 ${ticker.ticker}`);
            const name = document.createElement('span');
            name.className = 'ticker';
            name.textContent = ticker.ticker.replace('.US', '');
            if (ticker.warnings?.length) {
                const mark = document.createElement('span');
                mark.className = 'warn';
                mark.textContent = '△';
                mark.title = ticker.warnings.join('\n');
                name.append(mark);
            }
            const price = document.createElement('span');
            price.className = 'quote';
            price.textContent = money(latestQuote(ticker.quote)?.last_price);
            button.append(name, price);
            button.addEventListener('click', () => void select(ticker.symbol, timeframe));
            fragment.append(button);
        }
    }
    if (!fragment.childNodes.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-list';
        empty.textContent = '没有匹配的股票';
        fragment.append(empty);
    }
    const scroll = $('symbols').scrollTop;
    $('symbols').replaceChildren(fragment);
    $('symbols').scrollTop = scroll;
    if (focusedSymbol)
        Array.from(document.querySelectorAll('.symbol-row')).find(b => b.dataset.symbol === focusedSymbol)?.focus({ preventScroll: true });
}
function connection(text, kind = '') { const node = $('connection'); node.textContent = text; node.className = 'connection ' + kind; }
function showState(view) {
    const q = view.quote, checks = view.status.timeframes;
    const disconnected = ['STALE', 'STOPPED', 'OFFLINE'].includes(q.connection_health) || socket?.readyState !== WebSocket.OPEN;
    const loading = !checks['1d']?.loaded || !checks[timeframe]?.loaded || q.connection_health === 'CONNECTING';
    const key = `${symbol}/${timeframe}/${view.status.full_ready ? 'full' : view.status.ready ? 'ready' : 'loaded'}`;
    if (disconnected) {
        connection('连接中断', 'error');
        healthyKey = '';
    }
    else if (loading) {
        connection('加载');
        healthyKey = '';
    }
    else {
        if (healthyKey !== key) {
            healthyKey = key;
            healthyAt = Date.now();
        }
        connection(view.status.full_ready ? 'FULL READY' : view.status.ready ? 'READY' : '已加载', Date.now() - healthyAt < 5000 ? 'ok' : 'quiet');
    }
    $('daily-state').textContent = checks['1d']?.loaded ? '' : '加载';
    $('intraday-state').textContent = checks[timeframe]?.loaded ? '' : '加载';
    const warnings = [...new Set([...view.status.warnings, ...(q.error ? [q.error] : [])])];
    $('warning').hidden = !warnings.length;
    $('warning').textContent = warnings.length ? '△  ' + warnings.join(' · ') : '';
}
function apply(view) {
    if (view.symbol !== symbol || view.timeframe !== timeframe)
        return;
    currentView = view;
    daily.render(view.charts['1d']);
    intraday.render(view.charts[timeframe]);
    const q = latestQuote(view.quote);
    $('last-price').textContent = money(q?.last_price);
    const labels = { Intraday: 'REGULAR', Pre: 'PRE', Post: 'POST', Overnight: 'OVERNIGHT' };
    $('price-session').textContent = q ? labels[q.trade_session] ?? q.trade_session : '等待行情';
    $('price-time').textContent = q ? nyFull.format(new Date(q.timestamp * 1000)) + ' ET' : '';
    $('day-volume').textContent = compact(view.quote.regular?.cumulative_volume);
    $('adr').textContent = view.summary.adr20 == null ? '—' : view.summary.adr20.toFixed(2) + '%';
    $('adv').textContent = view.summary.adv20 == null ? '—' : (view.summary.estimated ? '≈ ' : '') + '$' + compact(view.summary.adv20);
    $('update-note').textContent = `美东时间 · ${view.charts[timeframe].active ? '最新 candle 实时更新' : '官方已收盘 K 线'} · ${nyTime.format(new Date(view.server_time * 1000))}`;
    if (view.board) {
        tickers = view.board;
        renderList();
    }
    showState(view);
}
async function select(next, tf) {
    symbol = next;
    timeframe = tf;
    const id = ++epoch;
    streamEpoch = -1;
    healthyKey = '';
    currentView = null;
    daily.reset(symbol + '/1d');
    intraday.reset(symbol + '/' + tf);
    $('selected-symbol').textContent = symbol.replace('.US', '');
    $('group-label').textContent = tickers.find(t => t.symbol === symbol)?.status.toUpperCase() ?? '';
    for (const key of ['last-price', 'adr', 'adv', 'day-volume'])
        $(key).textContent = '—';
    $('price-time').textContent = '';
    $('price-session').textContent = '等待行情';
    $('warning').hidden = true;
    document.querySelectorAll('[data-tf]').forEach(b => { b.classList.toggle('active', b.dataset.tf === tf); b.setAttribute('aria-pressed', String(b.dataset.tf === tf)); });
    renderList();
    connection('加载');
    request?.abort();
    request = new AbortController();
    if (socket?.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify({ type: 'select', symbol, timeframe, request_id: id }));
    try {
        const response = await fetch(`/v1/chart?symbol=${encodeURIComponent(symbol)}&timeframe=${tf}`, { signal: request.signal });
        if (!response.ok)
            throw new Error('Data unavailable');
        const view = await response.json();
        if (id === epoch && streamEpoch !== id)
            apply(view);
    }
    catch (error) {
        if (id === epoch && error.name !== 'AbortError')
            connection('连接中断', 'error');
    }
}
function connect() {
    clearTimeout(reconnectTimer);
    const current = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/v1/stream`);
    socket = current;
    current.onopen = () => { lastMessage = Date.now(); reconnectDelay = 1000; if (symbol)
        void select(symbol, timeframe); };
    current.onmessage = event => { if (socket !== current)
        return; lastMessage = Date.now(); const view = JSON.parse(event.data); if (view.type === 'view' && view.request_id === epoch) {
        streamEpoch = epoch;
        apply(view);
    } };
    current.onclose = () => { if (socket !== current)
        return; connection('连接中断', 'error'); healthyKey = ''; reconnectTimer = window.setTimeout(connect, reconnectDelay); reconnectDelay = Math.min(reconnectDelay * 2, 10000); };
    current.onerror = () => current.close();
}
$('search').addEventListener('input', renderList);
document.addEventListener('keydown', event => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key) || event.metaKey || event.ctrlKey || event.altKey)
        return;
    const items = Array.from(document.querySelectorAll('.symbol-row'));
    if (!items.length)
        return;
    const index = items.findIndex(b => b.dataset.symbol === symbol), next = Math.max(0, Math.min(items.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)));
    event.preventDefault();
    void select(items[next].dataset.symbol, timeframe);
    document.querySelector('.symbol-row.active')?.scrollIntoView({ block: 'nearest' });
});
document.querySelectorAll('[data-tf]').forEach(b => b.addEventListener('click', () => { if (symbol)
    void select(symbol, b.dataset.tf); }));
setInterval(() => { $('clock').textContent = nyFull.format(new Date()) + ' ET'; if (socket?.readyState === WebSocket.OPEN && Date.now() - lastMessage > 15000)
    socket.close(); if (currentView && socket?.readyState === WebSocket.OPEN)
    showState(currentView); }, 1000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && symbol && socket?.readyState === WebSocket.OPEN)
    void select(symbol, timeframe); });
async function start() {
    try {
        const response = await fetch('/v1/universe');
        if (!response.ok)
            throw new Error('Cannot load universe');
        tickers = await response.json();
        $('symbol-count').textContent = String(tickers.length);
        renderList();
        if (tickers.length)
            await select(tickers[0].symbol, timeframe);
        connect();
    }
    catch {
        connection('连接中断', 'error');
        window.setTimeout(start, 2000);
    }
}
void start();
export {};

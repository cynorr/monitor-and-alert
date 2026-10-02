import { $, money, compact, nyTime, extendedQuote, defaultTimeframe } from './types.js';
import { Panel, linkTradingDay } from './chart.js';
import { Watchlist } from './list.js';
import { initLayout } from './layout.js';
import { ScanControls } from './scan.js';
import { post } from './api.js';
import { HoldingsList } from './holdings.js';
const layout = initLayout();
const daily = new Panel('daily', true), intraday = new Panel('intraday', false);
const dayLink = linkTradingDay(daily, intraday);
let symbol = '', timeframe = defaultTimeframe(), epoch = 0;
let socket = null;
let reconnectTimer, lastMessage = 0, reconnectDelay = 1000, currentView = null;
let readyKey = '', readySince = 0, lastStage = '';
let selectionSource = 'watchlist', holdingKey = '';
const watchlist = new Watchlist(next => select(next, timeframe, 'watchlist'), applyList);
const holdings = new HoldingsList((next, key) => select(next, timeframe, 'holdings', key), () => selectionSource === 'holdings', width => layout.setHoldingsWidth(width));
let appMode = 'monitor', scanDate = '', modePending = false;
const scan = new ScanControls(applyList, () => { watchlist.render(); const rows = scan.visible(watchlist.tickers); if (!rows.some(row => row.symbol === symbol))
    select(rows[0]?.symbol ?? '', timeframe); });
watchlist.scan = scan;
function applyList(data) {
    const nextMode = data.app_mode ?? 'monitor';
    const changed = nextMode !== appMode || (nextMode === 'scan' && data.date !== scanDate);
    appMode = nextMode;
    scanDate = data.date ?? '';
    layout.setMode(appMode);
    $('intraday-panel').hidden = $('divider-0').hidden = appMode === 'scan';
    document.querySelectorAll('[data-app-mode]').forEach(button => {
        button.classList.toggle('active', button.dataset.appMode === appMode);
        button.disabled = modePending || (data.mode === 'simulation' && !data.app_mode);
    });
    $('mock-data').hidden = !data.mock;
    scan.update(data);
    if (changed) {
        symbol = '';
        watchlist.selected = '';
        selectionSource = 'watchlist';
        holdingKey = '';
        holdings.selected = '';
        ++epoch;
    }
    holdings.update(data.holdings ?? null);
    watchlist.update(data, selectionSource === 'watchlist');
    if (selectionSource === 'holdings' && !holdings.has(holdingKey)) {
        const first = holdings.first();
        if (first)
            select(first.symbol, timeframe, 'holdings', first.key);
        else
            select(data.board[0]?.symbol ?? '', timeframe, 'watchlist');
    }
    else if (!symbol && holdings.first()) {
        const first = holdings.first();
        select(first.symbol, timeframe, 'holdings', first.key);
    }
    const labels = appMode === 'scan' ? ['Symbol', 'Price', 'ADR20', 'ADV20', ''] : ['Symbol', 'Last', 'Chg%', 'Ext', ''];
    Array.from($('list-columns').children).forEach((node, index) => { node.textContent = labels[index]; });
    if (changed && !symbol)
        select('', timeframe);
}
function state(text, kind = '') {
    for (const id of ['daily', 'intraday']) {
        const node = $(id + '-state');
        node.textContent = text;
        node.className = 'state ' + kind;
    }
}
function showState(view) {
    if (appMode === 'scan') {
        state(view.date ?? '');
        return;
    }
    const errors = [...view.status.errors, ...(view.quote.error ? ['Quote: ' + view.quote.error] : [])];
    if (view.quote.connection_health === 'DISCONNECTED' || socket?.readyState !== WebSocket.OPEN)
        errors.push('Connection lost');
    const key = view.run_id + '/' + symbol;
    if (key !== readyKey || lastStage !== view.status.stage) {
        readyKey = key;
        lastStage = view.status.stage;
        readySince = Date.now();
    }
    if (errors.length)
        state('');
    else if (view.quote.connection_health === 'CONNECTING' || view.status.stage === 'loading')
        state('Loading');
    else if (view.status.stage === 'basic')
        state('Ready', 'basic');
    else
        state(Date.now() - readySince < 3000 ? 'Ready' : '', 'full');
    document.querySelectorAll('.quality').forEach(node => { node.hidden = !errors.length; node.title = errors.join('\n'); });
}
function apply(view) {
    if (view.symbol !== symbol || view.timeframe !== timeframe || (view.app_mode && view.app_mode !== appMode))
        return;
    currentView = view;
    daily.render(view.charts['1d']);
    if (appMode === 'monitor') {
        intraday.render(view.charts[timeframe]);
        dayLink.restore();
    }
    const extended = extendedQuote(view.quote), quote = extended ?? view.quote.regular;
    document.querySelectorAll('.last-price').forEach(node => node.textContent = money(quote?.last_price));
    document.querySelectorAll('.session').forEach(node => { node.hidden = !extended; node.textContent = extended?.trade_session.toUpperCase() ?? ''; });
    document.querySelectorAll('.clock').forEach(node => node.textContent = nyTime.format(new Date(view.server_time * 1000)) + ' ET');
    const bid = quote?.bid_price, ask = quote?.ask_price;
    document.querySelectorAll('.spread').forEach(node => { node.hidden = !bid && !ask; const sell = node.querySelector('.bid'), buy = node.querySelector('.ask'); sell.hidden = !bid; buy.hidden = !ask; sell.textContent = `Sell ${money(bid)}`; buy.textContent = `Buy ${money(ask)}`; });
    document.querySelectorAll('.adr').forEach(node => node.textContent = view.summary.adr20 == null ? '—' : view.summary.adr20.toFixed(2) + '%');
    document.querySelectorAll('.adv').forEach(node => node.textContent = view.summary.adv20 == null ? '—' : '$' + compact(view.summary.adv20));
    $('simulation').hidden = view.mode !== 'simulation';
    showState(view);
}
function select(next, tf, source = selectionSource, key = holdingKey) {
    if (next !== symbol)
        dayLink.clear();
    symbol = next;
    selectionSource = source;
    holdingKey = source === 'holdings' ? key : '';
    timeframe = tf;
    ++epoch;
    currentView = null;
    daily.reset(appMode + '/' + scanDate + '/' + symbol + '/1d');
    intraday.reset(symbol + '/' + tf);
    document.querySelectorAll('.symbol').forEach(node => node.textContent = symbol.replace('.US', '') || '—');
    document.querySelectorAll('.last-price,.adr,.adv').forEach(node => node.textContent = '—');
    document.querySelectorAll('.session,.spread,.quality').forEach(node => node.hidden = true);
    document.querySelectorAll('[data-tf]').forEach(button => { button.classList.toggle('active', button.dataset.tf === tf); button.setAttribute('aria-pressed', String(button.dataset.tf === tf)); });
    watchlist.selected = source === 'watchlist' ? symbol : '';
    watchlist.keyboardEnabled = source === 'watchlist';
    holdings.selected = source === 'holdings' ? holdingKey : '';
    holdings.render();
    watchlist.render();
    for (const id of ['daily', 'intraday'])
        $(id + '-empty').textContent = symbol ? 'Loading' : 'No symbol selected';
    state(symbol ? 'Loading' : '');
    sendSelection();
}
function sendSelection() {
    if (symbol && socket?.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify({ type: 'select', symbol, timeframe, request_id: epoch, mode: appMode }));
}
function connect() {
    clearTimeout(reconnectTimer);
    const current = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/v1/stream`);
    socket = current;
    current.onopen = () => { if (socket !== current)
        return; lastMessage = Date.now(); reconnectDelay = 1000; sendSelection(); };
    current.onmessage = event => {
        if (socket !== current)
            return;
        lastMessage = Date.now();
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'list') {
                applyList(data);
                return;
            }
            const view = data;
            if (view.type === 'view' && view.request_id === epoch)
                apply(view);
        }
        catch {
            current.close();
        }
    };
    current.onclose = () => {
        if (socket !== current)
            return;
        if (currentView)
            showState(currentView);
        else
            state('Loading');
        reconnectTimer = window.setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 10000);
    };
    current.onerror = () => current.close();
}
document.querySelectorAll('[data-tf]').forEach(button => button.addEventListener('click', () => {
    if (symbol)
        void select(symbol, button.dataset.tf);
}));
document.querySelectorAll('[data-app-mode]').forEach(button => button.addEventListener('click', async () => {
    if (button.dataset.appMode === appMode || modePending)
        return;
    modePending = true;
    document.querySelectorAll('[data-app-mode]').forEach(node => { node.disabled = true; });
    try {
        applyList(await post('mode', { mode: button.dataset.appMode }));
    }
    catch (error) {
        $('list-notice').textContent = error.message;
    }
    finally {
        modePending = false;
        document.querySelectorAll('[data-app-mode]').forEach(node => { node.disabled = false; });
    }
}));
setInterval(() => {
    if (socket?.readyState === WebSocket.OPEN && Date.now() - lastMessage > 15000)
        socket.close();
    if (currentView && socket?.readyState === WebSocket.OPEN)
        showState(currentView);
}, 1000);
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && symbol && socket?.readyState === WebSocket.OPEN)
        sendSelection();
});
select('', timeframe);
connect();

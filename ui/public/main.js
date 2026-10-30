import { attentionState } from './attention.js';
import { installPalette } from './palette.js';
import { $, money, compact, nyTime, defaultTimeframe, scanProgress, selectionRequest } from './types.js';
import { Panel, linkTradingDay } from './chart.js';
import { Watchlist } from './list.js';
import { initLayout } from './layout.js';
import { ScanControls } from './scan.js';
import { post } from './api.js';
import { TradeController } from './trade.js';
import { SchwabHoldings } from './schwab-holdings.js';
import { loadTradeConfig } from './trade-config.js';
import { HoldingsList } from './holdings.js';
import { AlertController } from './alerts.js';
import { AdditionalInfoDisplay, acceptsAdditional } from './additional-info.js';
installPalette();
const tradeConfig = await loadTradeConfig().catch(error => {
    $('intraday-state').textContent = error.message;
    $('intraday-state').className = 'state error';
    throw error;
});
const layout = initLayout();
const daily = new Panel('daily', true), intraday = new Panel('intraday', false);
const dayLink = linkTradingDay(daily, intraday);
const additional = new AdditionalInfoDisplay();
let symbol = '', timeframe = defaultTimeframe(), epoch = 0;
let socket = null;
let reconnectTimer, lastMessage = 0, reconnectDelay = 1000, currentView = null;
let readyKey = '', readySince = 0, lastStage = '';
let selectionSource = 'watchlist', holdingKey = '';
const watchlist = new Watchlist(next => select(next, timeframe, 'watchlist', ''), applyList);
const holdings = new HoldingsList((next, key) => select(next, timeframe, 'holdings', key), () => selectionSource === 'holdings', width => { if (appMode !== 'trade')
    layout.setHoldingsWidth(width); });
let appMode = 'monitor', scanDate = '', modePending = false;
const trade = new TradeController([daily, intraday], () => appMode, tradeConfig);
const schwab = new SchwabHoldings((next, key) => select(next, timeframe, 'holdings', key), () => appMode === 'trade' && selectionSource === 'holdings', id => void trade.cancel(id), width => { if (appMode === 'trade')
    layout.setHoldingsWidth(width); });
const activeHoldings = () => appMode === 'trade' ? schwab : holdings;
const scan = new ScanControls(applyList, () => { watchlist.render(); const rows = scan.visible(watchlist.tickers); if (selectionSource === 'watchlist' && !rows.some(row => row.symbol === symbol))
    select(rows[0]?.symbol ?? '', timeframe); });
watchlist.scan = scan;
const alerts = new AlertController([daily, intraday], () => symbol, () => appMode, async (selected) => {
    const tf = timeframe;
    if (appMode === 'scan' && scan.activeList !== 'focus')
        await scan.showList();
    applyList(await (await fetch('/v1/scan')).json());
    if (selected)
        select(selected, tf, selectionSource, holdingKey);
}, value => {
    watchlist.attention = holdings.attention = schwab.attention = attentionState(value);
    watchlist.render();
    activeHoldings().render();
});
function applyList(data) {
    const nextMode = data.app_mode ?? 'monitor';
    const changed = nextMode !== appMode || (nextMode === 'scan' && data.date !== scanDate);
    appMode = nextMode;
    scanDate = data.date ?? '';
    $('intraday-panel').hidden = $('chart-gap').hidden = appMode === 'scan';
    layout.setMode(appMode);
    document.querySelectorAll('[data-app-mode]').forEach(button => {
        button.classList.toggle('active', button.dataset.appMode === appMode);
        button.hidden = button.dataset.appMode === 'trade' && !data.trade_enabled;
        button.disabled = modePending || (button.dataset.appMode === 'trade' && !data.trade_enabled) || (data.mode === 'simulation' && !data.app_mode);
    });
    $('mock-data').hidden = !data.mock;
    const progress = $('scan-progress');
    progress.hidden = !data.massive;
    if (data.massive) {
        const status = scanProgress(data.massive);
        progress.hidden = !status.text;
        progress.textContent = status.text;
        progress.title = status.title;
        progress.classList.toggle('error', status.error);
    }
    scan.update(data);
    if (changed) {
        symbol = '';
        watchlist.selected = '';
        selectionSource = 'watchlist';
        holdingKey = '';
        holdings.selected = schwab.selected = '';
        ++epoch;
    }
    trade.update(data.trade ?? null);
    schwab.update(data.trade ?? null, data.current_regular_session === true, data.intraday);
    holdings.update(data.holdings ?? null, data.current_regular_session === true, data.intraday);
    watchlist.update(data, selectionSource === 'watchlist');
    if (selectionSource === 'holdings' && !activeHoldings().has(holdingKey)) {
        const first = activeHoldings().first();
        if (first)
            select(first.symbol, timeframe, 'holdings', first.key);
        else
            select(scan.visible(data.board)[0]?.symbol ?? '', timeframe, 'watchlist');
    }
    else if (!symbol && activeHoldings().first()) {
        const first = activeHoldings().first();
        select(first.symbol, timeframe, 'holdings', first.key);
    }
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
    const errors = [...view.status.errors, ...(view.quote.error ? ['Quote: ' + view.quote.error] : [])];
    if (view.quote.connection_health === 'DISCONNECTED' || socket?.readyState !== WebSocket.OPEN)
        errors.push('Connection lost');
    if (appMode === 'scan') {
        $('daily-state').textContent = view.date ?? '';
        $('intraday-state').textContent = '';
        document.querySelectorAll('.quality').forEach(node => { node.hidden = !errors.length; node.title = errors.join('\n'); });
        return;
    }
    const key = view.run_id + '/' + symbol;
    if (key !== readyKey || lastStage !== view.status.stage) {
        readyKey = key;
        lastStage = view.status.stage;
        readySince = Date.now();
    }
    if (errors.length)
        state('');
    else if (view.quote.connection_health === 'CONNECTING')
        state('Loading');
    else if (view.status.refreshing)
        state('Refreshing');
    else if (view.status.stage === 'loading')
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
    daily.setQuotePrice(view.quote, appMode !== 'scan');
    if (appMode !== 'scan') {
        intraday.render(view.charts[timeframe]);
        intraday.setQuotePrice(view.quote, true);
        dayLink.restore();
    }
    const quote = appMode === 'scan' ? null : view.quote.latest;
    document.querySelectorAll('.last-price').forEach(node => node.textContent = money(quote?.last_price));
    document.querySelectorAll('.clock').forEach(node => node.textContent = nyTime.format(new Date(view.server_time * 1000)) + ' ET');
    const bid = quote?.bid_price, ask = quote?.ask_price;
    document.querySelectorAll('.spread').forEach(node => { node.hidden = !bid && !ask; const sell = node.querySelector('.bid'), buy = node.querySelector('.ask'); sell.hidden = !bid; buy.hidden = !ask; sell.textContent = `Sell ${money(bid)}`; buy.textContent = `Buy ${money(ask)}`; });
    document.querySelectorAll('.adr').forEach(node => node.textContent = view.summary.adr20 == null ? '—' : view.summary.adr20.toFixed(2) + '%');
    document.querySelectorAll('.adv').forEach(node => node.textContent = view.summary.adv20 == null ? '—' : '$' + compact(view.summary.adv20));
    $('simulation').hidden = view.mode !== 'simulation';
    showState(view);
    trade.view(view);
    alerts.redraw();
    void alerts.read(view.symbol);
}
function select(next, tf, source = selectionSource, key = holdingKey) {
    void alerts.read(next);
    if (next !== symbol)
        dayLink.clear();
    symbol = next;
    trade.setSymbol(next);
    alerts.changeSymbol();
    selectionSource = source;
    holdingKey = source === 'holdings' ? key : '';
    timeframe = tf;
    ++epoch;
    currentView = null;
    daily.reset(appMode + '/' + scanDate + '/' + symbol + '/1d');
    intraday.reset(symbol + '/' + tf);
    document.querySelectorAll('.symbol').forEach(node => node.textContent = symbol.replace('.US', '') || '—');
    additional.update(null);
    document.querySelectorAll('.last-price,.adr,.adv').forEach(node => node.textContent = '—');
    document.querySelectorAll('.spread,.quality').forEach(node => node.hidden = true);
    document.querySelectorAll('[data-tf]').forEach(button => { button.classList.toggle('active', button.dataset.tf === tf); button.setAttribute('aria-pressed', String(button.dataset.tf === tf)); });
    watchlist.selected = source === 'watchlist' ? symbol : '';
    watchlist.keyboardEnabled = source === 'watchlist';
    activeHoldings().selected = source === 'holdings' ? holdingKey : '';
    activeHoldings().render();
    watchlist.render();
    for (const id of ['daily', 'intraday'])
        $(id + '-empty').textContent = symbol ? 'Loading' : 'No symbol selected';
    state(symbol ? 'Loading' : '');
    sendSelection();
}
function sendSelection() {
    if (symbol && socket?.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify(selectionRequest(symbol, timeframe, epoch, appMode, selectionSource)));
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
            if (data.type === 'trade_quote') {
                if (appMode === 'trade' && data.mode === appMode && data.symbol === symbol && data.request_id === epoch && data.source === selectionSource)
                    trade.updateQuote(data.quote);
                return;
            }
            if (data.type === 'additional_info') {
                const info = data;
                if (acceptsAdditional(info, { symbol, request_id: epoch, mode: appMode, source: selectionSource }))
                    additional.update(info);
                return;
            }
            if (data.type === 'alerts') {
                alerts.update(data);
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
document.addEventListener('keydown', event => {
    if (event.ctrlKey || event.altKey || event.shiftKey || event.isComposing ||
        event.target.closest('input,textarea,select,[contenteditable="true"]'))
        return;
    if (!event.metaKey && event.code === 'KeyR') {
        event.preventDefault();
        if (!event.repeat) {
            daily.resetLatest();
            if (appMode !== 'scan')
                intraday.resetLatest();
        }
        return;
    }
    const key = event.metaKey ? event.key.toLowerCase()
        : event.key === 'Home' ? 'u' : event.key === 'End' ? 'g' : '';
    if (!event.metaKey && key)
        event.preventDefault();
    if (key === 'g') {
        event.preventDefault();
        void watchlist.jumpUnread();
    }
    if (key === 'u' && appMode !== 'scan') {
        event.preventDefault();
        activeHoldings().jumpUnread();
    }
});
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
    additional.tick();
    holdings.tick();
    schwab.tick();
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

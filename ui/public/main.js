import { $, money, compact, nyTime, extendedQuote, defaultTimeframe, scanProgress, selectionRequest } from './types.js';
import { Panel, linkTradingDay } from './chart.js';
import { Watchlist } from './list.js';
import { initLayout } from './layout.js';
import { ScanControls } from './scan.js';
import { isReviewSelection } from './board.js';
import { post } from './api.js';
import { HoldingsList } from './holdings.js';
import { AlertController } from './alerts.js';
import { AdditionalInfoDisplay, acceptsAdditional } from './additional-info.js';
const layout = initLayout();
const daily = new Panel('daily', true), intraday = new Panel('intraday', false);
const dayLink = linkTradingDay(daily, intraday);
const additional = new AdditionalInfoDisplay();
let symbol = '', timeframe = defaultTimeframe(), epoch = 0;
let socket = null;
let reconnectTimer, lastMessage = 0, reconnectDelay = 1000, currentView = null;
let readyKey = '', readySince = 0, lastStage = '';
let selectionSource = 'watchlist', holdingKey = '';
const watchlist = new Watchlist(next => select(next, timeframe, 'watchlist'), applyList);
const holdings = new HoldingsList((next, key) => select(next, timeframe, 'holdings', key), () => selectionSource === 'holdings', width => layout.setHoldingsWidth(width));
let appMode = 'monitor', scanDate = '', modePending = false;
const scan = new ScanControls(applyList, () => { watchlist.render(); const rows = scan.visible(watchlist.tickers); if (selectionSource === 'watchlist' && !rows.some(row => row.symbol === symbol))
    select(rows[0]?.symbol ?? '', timeframe); });
watchlist.scan = scan;
let waitingJump = null;
const alerts = new AlertController([daily, intraday], () => symbol, () => appMode, async (selected) => {
    const tf = timeframe;
    if (appMode === 'scan' && scan.activeList !== 'focus')
        await scan.showFocus();
    applyList(await (await fetch('/v1/scan')).json());
    if (selected)
        select(selected, tf, selectionSource, holdingKey);
}, jumpToAlert);
async function jumpToAlert(event) {
    if (!alerts.value?.eligible_symbols.includes(event.symbol))
        throw new Error('Symbol is no longer in Focus or Holdings');
    applyList(await post('mode', { mode: 'monitor' }));
    await scan.showFocus();
    if (socket?.readyState !== WebSocket.OPEN)
        throw new Error('Chart connection unavailable');
    const holding = holdings.forSymbol(event.symbol);
    if (!watchlist.tickers.some(row => row.symbol === event.symbol && row.status === 'focus') && !holding)
        throw new Error('Symbol is no longer available');
    if (!holding)
        watchlist.showSymbol(event.symbol);
    select(event.symbol, timeframe, holding ? 'holdings' : 'watchlist', holding?.key ?? '');
    await new Promise((resolve, reject) => {
        const timeout = window.setTimeout(() => { waitingJump = null; reject(new Error('Could not open chart')); }, 8000);
        waitingJump = { symbol: event.symbol, resolve: () => { clearTimeout(timeout); waitingJump = null; resolve(); } };
    });
}
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
        holdings.selected = '';
        ++epoch;
    }
    holdings.update(data.holdings ?? null, data.current_regular_session === true);
    watchlist.update(data, selectionSource === 'watchlist');
    if (selectionSource === 'holdings' && !holdings.has(holdingKey)) {
        const first = holdings.first();
        if (first)
            select(first.symbol, timeframe, 'holdings', first.key);
        else
            select(scan.visible(data.board)[0]?.symbol ?? '', timeframe, 'watchlist');
    }
    else if (!symbol && holdings.first()) {
        const first = holdings.first();
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
    if (appMode === 'scan' || view.read_only_daily) {
        $('daily-state').textContent = (view.read_only_daily ? 'Daily preview · ' : '') + (view.date ?? '');
        $('intraday-state').textContent = '';
        document.querySelectorAll('.quality').forEach(node => { node.hidden = !view.status.errors.length; node.title = view.status.errors.join('\n'); });
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
    document.querySelectorAll('[data-tf]').forEach(button => { button.disabled = view.read_only_daily === true; });
    daily.render(view.charts['1d']);
    if (appMode === 'monitor' && !view.read_only_daily) {
        intraday.render(view.charts[timeframe]);
        dayLink.restore();
    }
    else if (view.read_only_daily) {
        intraday.reset('review/' + symbol);
        $('intraday-empty').textContent = 'Add to Focus for live data';
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
    alerts.redraw();
    if (waitingJump?.symbol === view.symbol && view.charts['1d'] && daily.rows.length)
        waitingJump.resolve();
}
function select(next, tf, source = selectionSource, key = holdingKey) {
    if (next !== symbol)
        dayLink.clear();
    symbol = next;
    alerts.changeSymbol();
    selectionSource = source;
    holdingKey = source === 'holdings' ? key : '';
    timeframe = tf;
    ++epoch;
    currentView = null;
    const preview = appMode === 'monitor' && isReviewSelection(watchlist.tickers.find(row => row.symbol === next), source);
    document.querySelectorAll('[data-tf]').forEach(button => { button.disabled = preview; });
    daily.reset(appMode + '/' + scanDate + '/' + symbol + '/1d');
    intraday.reset(symbol + '/' + tf);
    document.querySelectorAll('.symbol').forEach(node => node.textContent = symbol.replace('.US', '') || '—');
    additional.update(null);
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

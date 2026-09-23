import { $, money, compact, nyTime, extendedQuote } from './types.js';
import { Panel, linkTradingDay } from './chart.js';
import { initLayout } from './layout.js';
initLayout();
const daily = new Panel('daily', true), intraday = new Panel('intraday', false);
const dayLink = linkTradingDay(daily, intraday);
let tickers = [], symbol = '', timeframe = '5m', epoch = 0;
let socket = null;
let reconnectTimer, lastMessage = 0, reconnectDelay = 1000, currentView = null;
let listKey = '', readyKey = '', readySince = 0, lastStage = '';
const listRows = new Map();
function renderList() {
    const term = $('search').value.trim().toUpperCase();
    const visible = tickers.filter(t => t.ticker.includes(term));
    const key = visible.map(t => t.symbol + '/' + t.status).join(',');
    if (key !== listKey || !$('symbols').childNodes.length) {
        listKey = key;
        listRows.clear();
        const fragment = document.createDocumentFragment();
        for (const group of ['focus', 'wait']) {
            const items = visible.filter(t => t.status === group);
            if (!items.length)
                continue;
            const label = document.createElement('div');
            label.className = 'group';
            label.textContent = group === 'focus' ? 'Focus' : 'Wait';
            fragment.append(label);
            for (const ticker of items) {
                const button = document.createElement('button');
                button.dataset.symbol = ticker.symbol;
                button.setAttribute('aria-label', `Select ${ticker.ticker}`);
                const name = document.createElement('span');
                name.className = 'ticker';
                name.textContent = ticker.ticker.replace('.US', '');
                const mark = document.createElement('span');
                mark.className = 'warn';
                mark.textContent = '!';
                mark.hidden = true;
                name.append(mark);
                button.append(name, document.createElement('span'), document.createElement('span'), document.createElement('span'));
                fragment.append(button);
                listRows.set(ticker.symbol, button);
            }
        }
        if (!visible.length) {
            const empty = document.createElement('div');
            empty.className = 'empty-list';
            empty.textContent = 'No symbols';
            fragment.append(empty);
        }
        $('symbols').replaceChildren(fragment);
    }
    for (const ticker of visible) {
        const row = listRows.get(ticker.symbol);
        row.className = 'symbol-row' + (ticker.symbol === symbol ? ' active' : '');
        row.setAttribute('aria-pressed', String(ticker.symbol === symbol));
        const mark = row.querySelector('.warn');
        const errors = [...(ticker.errors ?? []), ...(ticker.quote?.error ? ['Quote: ' + ticker.quote.error] : [])];
        mark.hidden = !errors.length;
        mark.title = errors.join('\n');
        const regular = ticker.quote?.regular, extended = extendedQuote(ticker.quote);
        const change = regular?.prev_close ? (regular.last_price / regular.prev_close - 1) * 100 : null;
        const extChange = extended && regular?.last_price ? (extended.last_price / regular.last_price - 1) * 100 : null;
        row.children[1].textContent = money(regular?.last_price);
        for (const [index, value] of [[2, change], [3, extChange]]) {
            const cell = row.children[index];
            cell.textContent = value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
            cell.className = value == null ? '' : value >= 0 ? 'positive' : 'negative';
        }
        row.children[3].title = extended ? `${extended.trade_session}: change from regular close` : '';
    }
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
    if (view.symbol !== symbol || view.timeframe !== timeframe)
        return;
    currentView = view;
    daily.render(view.charts['1d']);
    intraday.render(view.charts[timeframe]);
    dayLink.restore();
    const extended = extendedQuote(view.quote), quote = extended ?? view.quote.regular;
    document.querySelectorAll('.last-price').forEach(node => node.textContent = money(quote?.last_price));
    document.querySelectorAll('.session').forEach(node => { node.hidden = !extended; node.textContent = extended?.trade_session.toUpperCase() ?? ''; });
    document.querySelectorAll('.clock').forEach(node => node.textContent = nyTime.format(new Date(view.server_time * 1000)) + ' ET');
    const bid = quote?.bid_price, ask = quote?.ask_price;
    document.querySelectorAll('.spread').forEach(node => { node.hidden = !bid && !ask; const sell = node.querySelector('.bid'), buy = node.querySelector('.ask'); sell.hidden = !bid; buy.hidden = !ask; sell.textContent = `Sell ${money(bid)}`; buy.textContent = `Buy ${money(ask)}`; });
    document.querySelectorAll('.adr').forEach(node => node.textContent = view.summary.adr20 == null ? '—' : view.summary.adr20.toFixed(2) + '%');
    document.querySelectorAll('.adv').forEach(node => node.textContent = view.summary.adv20 == null ? '—' : (view.summary.estimated ? '≈ ' : '') + '$' + compact(view.summary.adv20));
    $('simulation').hidden = view.mode !== 'simulation';
    if (view.board) {
        tickers = view.board;
        renderList();
    }
    showState(view);
}
function select(next, tf) {
    if (next !== symbol)
        dayLink.clear();
    symbol = next;
    timeframe = tf;
    ++epoch;
    currentView = null;
    daily.reset(symbol + '/1d');
    intraday.reset(symbol + '/' + tf);
    document.querySelectorAll('.symbol').forEach(node => node.textContent = symbol.replace('.US', ''));
    document.querySelectorAll('.last-price,.adr,.adv').forEach(node => node.textContent = '—');
    document.querySelectorAll('.session,.spread,.quality').forEach(node => node.hidden = true);
    document.querySelectorAll('[data-tf]').forEach(button => { button.classList.toggle('active', button.dataset.tf === tf); button.setAttribute('aria-pressed', String(button.dataset.tf === tf)); });
    renderList();
    state('Loading');
    sendSelection();
}
function sendSelection() {
    if (symbol && socket?.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify({ type: 'select', symbol, timeframe, request_id: epoch }));
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
            const view = JSON.parse(event.data);
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
$('symbols').addEventListener('click', event => {
    const row = event.target.closest('[data-symbol]');
    if (row?.dataset.symbol)
        select(row.dataset.symbol, timeframe);
});
$('search').addEventListener('input', renderList);
document.addEventListener('keydown', event => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key) || event.metaKey || event.ctrlKey || event.altKey)
        return;
    const items = Array.from(document.querySelectorAll('.symbol-row'));
    if (!items.length)
        return;
    const index = items.findIndex(button => button.dataset.symbol === symbol), next = Math.max(0, Math.min(items.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)));
    event.preventDefault();
    void select(items[next].dataset.symbol, timeframe);
    document.querySelector('.symbol-row.active')?.scrollIntoView({ block: 'nearest' });
});
document.querySelectorAll('[data-tf]').forEach(button => button.addEventListener('click', () => {
    if (symbol)
        void select(symbol, button.dataset.tf);
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
async function start() {
    try {
        const response = await fetch('/v1/universe');
        if (!response.ok)
            throw new Error('Universe unavailable');
        tickers = await response.json();
        $('symbol-count').textContent = String(tickers.length);
        renderList();
        if (tickers.length)
            select(tickers[0].symbol, timeframe);
        connect();
    }
    catch {
        state('Loading');
        window.setTimeout(start, 2000);
    }
}
void start();

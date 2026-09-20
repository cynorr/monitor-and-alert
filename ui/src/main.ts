import { $, money, compact, nyTime, extendedQuote, type Ticker, type View } from './types.js';
import { Panel, linkTradingDay } from './chart.js';
import { initLayout } from './layout.js';
initLayout();
const daily = new Panel('daily', true), intraday = new Panel('intraday', false);
const dayLink = linkTradingDay(daily, intraday);
let tickers: Ticker[] = [], symbol = '', timeframe = '5m', epoch = 0, streamEpoch = -1;
let socket: WebSocket | null = null, request: AbortController | null = null;
let reconnectTimer: number | undefined, lastMessage = 0, reconnectDelay = 1000, currentView: View | null = null;
function renderList() {
    const term = ($('search') as HTMLInputElement).value.trim().toUpperCase(), fragment = document.createDocumentFragment();
    const focusedSymbol = (document.activeElement as HTMLElement)?.dataset?.symbol;
    for (const group of ['focus', 'wait']) {
        const items = tickers.filter(t => t.status === group && t.ticker.includes(term));
        if (!items.length)
            continue;
        const label = document.createElement('div');
        label.className = 'group';
        label.textContent = group === 'focus' ? 'Focus' : 'Wait';
        fragment.append(label);
        for (const ticker of items) {
            const button = document.createElement('button');
            button.className = 'symbol-row' + (ticker.symbol === symbol ? ' active' : '');
            button.setAttribute('aria-pressed', String(ticker.symbol === symbol));
            button.dataset.symbol = ticker.symbol;
            button.setAttribute('aria-label', `Select ${ticker.ticker}`);
            const name = document.createElement('span');
            name.className = 'ticker';
            name.textContent = ticker.ticker.replace('.US', '');
            if (ticker.warnings?.length) {
                const mark = document.createElement('span');
                mark.className = 'warn';
                mark.textContent = '!';
                mark.title = [...new Set(ticker.warnings)].join('\n');
                name.append(mark);
            }
            const regular = ticker.quote?.regular, change = regular?.prev_close ? (regular.last_price / regular.prev_close - 1) * 100 : null;
            const last = document.createElement('span');
            last.textContent = money(regular?.last_price);
            const chg = document.createElement('span');
            chg.textContent = change == null ? '—' : `${change > 0 ? '+' : ''}${change.toFixed(2)}%`;
            chg.className = change == null ? '' : change >= 0 ? 'positive' : 'negative';
            const ext = document.createElement('span');
            const extended = extendedQuote(ticker.quote);
            ext.textContent = money(extended?.last_price);
            ext.title = extended?.trade_session ?? '';
            button.append(name, last, chg, ext);
            button.addEventListener('click', () => void select(ticker.symbol, timeframe));
            fragment.append(button);
        }
    }
    if (!fragment.childNodes.length) {
        const empty = document.createElement('div');
        empty.className = 'empty-list';
        empty.textContent = 'No symbols';
        fragment.append(empty);
    }
    const scroll = $('symbols').scrollTop;
    $('symbols').replaceChildren(fragment);
    $('symbols').scrollTop = scroll;
    if (focusedSymbol)
        Array.from(document.querySelectorAll<HTMLButtonElement>('.symbol-row')).find(b => b.dataset.symbol === focusedSymbol)?.focus({ preventScroll: true });
}
function state(text: string, error = false) { for (const id of ['daily', 'intraday']) {
    const node = $(id + '-state');
    node.textContent = text;
    node.className = 'state' + (error ? ' error' : '');
} }
function showState(view: View) {
    const disconnected = ['STALE', 'STOPPED', 'OFFLINE'].includes(view.quote.connection_health) || socket?.readyState !== WebSocket.OPEN;
    if (disconnected)
        state('Disconnected', true);
    else
        for (const [id, tf] of [['daily', '1d'], ['intraday', timeframe]]) {
            $(id + '-state').textContent = !view.status.timeframes[tf]?.loaded || view.quote.connection_health === 'CONNECTING' ? 'Loading' : '';
            $(id + '-state').className = 'state';
        }
    const warnings = [...new Set([...view.status.warnings, ...(view.quote.error ? ['Quote unavailable'] : [])])];
    document.querySelectorAll<HTMLElement>('.quality').forEach(node => { node.hidden = !warnings.length; node.title = warnings.join('\n'); });
}
function apply(view: View) {
    if (view.symbol !== symbol || view.timeframe !== timeframe)
        return;
    currentView = view;
    daily.render(view.charts['1d']);
    intraday.render(view.charts[timeframe]);
    dayLink.restore();
    const extended = extendedQuote(view.quote), quote = extended ?? view.quote.regular;
    document.querySelectorAll<HTMLElement>('.last-price').forEach(node => node.textContent = money(quote?.last_price));
    document.querySelectorAll<HTMLElement>('.session').forEach(node => { node.hidden = !extended; node.textContent = extended?.trade_session.toUpperCase() ?? ''; });
    document.querySelectorAll<HTMLElement>('.clock').forEach(node => node.textContent = nyTime.format(new Date(view.server_time * 1000)) + ' ET');
    const bid = quote?.bid_price, ask = quote?.ask_price;
    document.querySelectorAll<HTMLElement>('.spread').forEach(node => { node.hidden = !bid && !ask; const sell = node.querySelector<HTMLElement>('.bid')!, buy = node.querySelector<HTMLElement>('.ask')!; sell.hidden = !bid; buy.hidden = !ask; sell.textContent = `Sell ${money(bid)}`; buy.textContent = `Buy ${money(ask)}`; });
    document.querySelectorAll<HTMLElement>('.adr').forEach(node => node.textContent = view.summary.adr20 == null ? '—' : view.summary.adr20.toFixed(2) + '%');
    document.querySelectorAll<HTMLElement>('.adv').forEach(node => node.textContent = view.summary.adv20 == null ? '—' : (view.summary.estimated ? '≈ ' : '') + '$' + compact(view.summary.adv20));
    $('simulation').hidden = view.mode !== 'simulation';
    if (view.board) {
        tickers = view.board;
        renderList();
    }
    showState(view);
}
async function select(next: string, tf: string) {
    if (next !== symbol)
        dayLink.clear();
    symbol = next;
    timeframe = tf;
    const id = ++epoch;
    streamEpoch = -1;
    currentView = null;
    daily.reset(symbol + '/1d');
    intraday.reset(symbol + '/' + tf);
    document.querySelectorAll<HTMLElement>('.symbol').forEach(node => node.textContent = symbol.replace('.US', ''));
    document.querySelectorAll<HTMLElement>('.last-price,.adr,.adv').forEach(node => node.textContent = '—');
    document.querySelectorAll<HTMLElement>('.session,.spread,.quality').forEach(node => node.hidden = true);
    document.querySelectorAll<HTMLButtonElement>('[data-tf]').forEach(button => { button.classList.toggle('active', button.dataset.tf === tf); button.setAttribute('aria-pressed', String(button.dataset.tf === tf)); });
    renderList();
    state('Loading');
    request?.abort();
    request = new AbortController();
    if (socket?.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify({ type: 'select', symbol, timeframe, request_id: id }));
    try {
        const response = await fetch(`/v1/chart?symbol=${encodeURIComponent(symbol)}&timeframe=${tf}`, { signal: request.signal });
        if (!response.ok)
            throw new Error('Data unavailable');
        const view = await response.json() as View;
        if (id === epoch && streamEpoch !== id)
            apply(view);
    }
    catch (error) {
        if (id === epoch && (error as Error).name !== 'AbortError')
            state('Disconnected', true);
    }
}
function connect() {
    clearTimeout(reconnectTimer);
    const current = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/v1/stream`);
    socket = current;
    current.onopen = () => { lastMessage = Date.now(); reconnectDelay = 1000; if (symbol)
        void select(symbol, timeframe); };
    current.onmessage = event => { if (socket !== current)
        return; lastMessage = Date.now(); const view = JSON.parse(event.data) as View; if (view.type === 'view' && view.request_id === epoch) {
        streamEpoch = epoch;
        apply(view);
    } };
    current.onclose = () => { if (socket !== current)
        return; state('Disconnected', true); reconnectTimer = window.setTimeout(connect, reconnectDelay); reconnectDelay = Math.min(reconnectDelay * 2, 10000); };
    current.onerror = () => current.close();
}
$('search').addEventListener('input', renderList);
document.addEventListener('keydown', event => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key) || event.metaKey || event.ctrlKey || event.altKey)
        return;
    const items = Array.from(document.querySelectorAll<HTMLButtonElement>('.symbol-row'));
    if (!items.length)
        return;
    const index = items.findIndex(button => button.dataset.symbol === symbol), next = Math.max(0, Math.min(items.length - 1, index + (event.key === 'ArrowDown' ? 1 : -1)));
    event.preventDefault();
    void select(items[next].dataset.symbol!, timeframe);
    document.querySelector<HTMLButtonElement>('.symbol-row.active')?.scrollIntoView({ block: 'nearest' });
});
document.querySelectorAll<HTMLButtonElement>('[data-tf]').forEach(button => button.addEventListener('click', () => { if (symbol)
    void select(symbol, button.dataset.tf!); }));
setInterval(() => { if (socket?.readyState === WebSocket.OPEN && Date.now() - lastMessage > 15000)
    socket.close(); if (currentView && socket?.readyState === WebSocket.OPEN)
    showState(currentView); }, 1000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && symbol && socket?.readyState === WebSocket.OPEN)
    void select(symbol, timeframe); });
async function start() { try {
    const response = await fetch('/v1/universe');
    if (!response.ok)
        throw new Error('Universe unavailable');
    tickers = await response.json();
    $('symbol-count').textContent = String(tickers.length);
    renderList();
    if (tickers.length)
        await select(tickers[0].symbol, timeframe);
    connect();
}
catch {
    state('Disconnected', true);
    window.setTimeout(start, 2000);
} }
void start();

import { $, money, compact, nyTime, extendedQuote, type View } from './types.js';
import { Panel, linkTradingDay } from './chart.js';
import { Watchlist, type ListState } from './list.js';
import { initLayout } from './layout.js';
initLayout();
const daily = new Panel('daily', true), intraday = new Panel('intraday', false);
const dayLink = linkTradingDay(daily, intraday);
let symbol = '', timeframe = '5m', epoch = 0;
let socket: WebSocket | null = null;
let reconnectTimer: number | undefined, lastMessage = 0, reconnectDelay = 1000, currentView: View | null = null;
let readyKey = '', readySince = 0, lastStage = '';
const watchlist = new Watchlist(next => select(next, timeframe));
function state(text: string, kind = '') {
    for (const id of ['daily', 'intraday']) {
        const node = $(id + '-state'); node.textContent = text; node.className = 'state ' + kind;
    }
}
function showState(view: View) {
    const errors = [...view.status.errors, ...(view.quote.error ? ['Quote: ' + view.quote.error] : [])];
    if (view.quote.connection_health === 'DISCONNECTED' || socket?.readyState !== WebSocket.OPEN)
        errors.push('Connection lost');
    const key = view.run_id + '/' + symbol;
    if (key !== readyKey || lastStage !== view.status.stage) {
        readyKey = key; lastStage = view.status.stage; readySince = Date.now();
    }
    if (errors.length) state('');
    else if (view.quote.connection_health === 'CONNECTING' || view.status.stage === 'loading') state('Loading');
    else if (view.status.stage === 'basic') state('Ready', 'basic');
    else state(Date.now() - readySince < 3000 ? 'Ready' : '', 'full');
    document.querySelectorAll<HTMLElement>('.quality').forEach(node => { node.hidden = !errors.length; node.title = errors.join('\n'); });
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
    showState(view);
}
function select(next: string, tf: string) {
    if (next !== symbol)
        dayLink.clear();
    symbol = next;
    timeframe = tf;
    ++epoch;
    currentView = null;
    daily.reset(symbol + '/1d');
    intraday.reset(symbol + '/' + tf);
    document.querySelectorAll<HTMLElement>('.symbol').forEach(node => node.textContent = symbol.replace('.US', '') || '—');
    document.querySelectorAll<HTMLElement>('.last-price,.adr,.adv').forEach(node => node.textContent = '—');
    document.querySelectorAll<HTMLElement>('.session,.spread,.quality').forEach(node => node.hidden = true);
    document.querySelectorAll<HTMLButtonElement>('[data-tf]').forEach(button => { button.classList.toggle('active', button.dataset.tf === tf); button.setAttribute('aria-pressed', String(button.dataset.tf === tf)); });
    watchlist.selected = symbol;
    watchlist.render();
    for (const id of ['daily', 'intraday']) $(id + '-empty').textContent = symbol ? 'Loading' : 'No symbol selected';
    state(symbol ? 'Loading' : '');
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
    current.onopen = () => { if (socket !== current) return; lastMessage = Date.now(); reconnectDelay = 1000; sendSelection(); };
    current.onmessage = event => {
        if (socket !== current) return;
        lastMessage = Date.now();
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'list') { watchlist.update(data as ListState); return; }
            const view = data as View;
            if (view.type === 'view' && view.request_id === epoch) apply(view);
        } catch { current.close(); }
    };
    current.onclose = () => {
        if (socket !== current) return;
        if (currentView) showState(currentView); else state('Loading');
        reconnectTimer = window.setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 10000);
    };
    current.onerror = () => current.close();
}
document.querySelectorAll<HTMLButtonElement>('[data-tf]').forEach(button => button.addEventListener('click', () => { if (symbol)
    void select(symbol, button.dataset.tf!); }));
setInterval(() => { if (socket?.readyState === WebSocket.OPEN && Date.now() - lastMessage > 15000)
    socket.close(); if (currentView && socket?.readyState === WebSocket.OPEN)
    showState(currentView); }, 1000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && symbol && socket?.readyState === WebSocket.OPEN)
    sendSelection(); });
select('', timeframe);
connect();

import type { Panel } from './chart.js';
import { $, dayKey, type View } from './types.js';
import { numeric, editableStop, activeOrders, flattenOrders, type TradeState, type Order } from './schwab-data.js';
import { palette } from './palette.js';
import { TradeLines, type TradeLine } from './trade-lines.js';

const SPREAD_WARNING_PERCENT = 0.5;

export function quantityStep(price: number) {
    const target = Math.max(1, 500 / price), magnitude = 10 ** Math.floor(Math.log10(target));
    return Math.max(1, [1, 2, 5, 10].map(n => n * magnitude).reduce((a, b) => Math.abs(a - target) < Math.abs(b - target) ? a : b));
}
export function suggestedBuy(high: number | null, ask: number | null) {
    return high != null && ask != null ? Math.max(high, Math.round((ask + .01) * 100) / 100).toFixed(2) : '';
}
export function quantityTicks(maximum: number, step: number, width: number) {
    const count = Math.ceil(maximum / step);
    if (!count) return [{ quantity: 0, position: 0, label: true }];
    const spacing = Math.max(28, String(maximum).length * 5 + 8), slots = Math.max(1, Math.floor(width / spacing));
    const target = count / slots, magnitude = 10 ** Math.floor(Math.log10(target));
    const stride = Math.max(1, [1, 2, 5, 10].find(n => n * magnitude >= target)! * magnitude);
    return Array.from({ length: count + 1 }, (_, index) => ({ quantity: Math.min(maximum, index * step), position: index / count * 100,
        label: index === 0 || index === count || (index % stride === 0 && (count - index) / count * width >= spacing) }));
}
export class TradeError extends Error {
    constructor(message: string, public unknown = false) { super(message); }
}
export async function tradeRequest<T>(path: string, method = 'GET', payload?: object): Promise<T> {
    const writing = method !== 'GET', controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 35_000);
    try {
        if (writing && window.navigator.onLine === false) throw new TradeError('Not sent · offline');
        const response = await fetch('/v1/trade/' + path, { method, signal: controller.signal,
            ...(payload ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) } : {}) });
        const body = await response.json().catch(() => null);
        if (!response.ok) {
            const code = body?.error?.code;
            const labels: Record<string, string> = { AUTH_REQUIRED: 'Schwab authorization required', SCHWAB_UNAVAILABLE: 'Schwab unavailable', ORDER_CONFLICT: 'Order conflict; check the current order', RISK_LIMIT_EXCEEDED: 'Order exceeds a risk or price boundary', VALIDATION_FAILED: 'Invalid order parameters', ORDER_RESULT_UNKNOWN: 'Order result unknown. Check Schwab before submitting again', SCHWAB_REJECTED: 'Schwab rejected the request' };
            const detail = body?.error?.details?.broker_error;
            const message = detail ? JSON.stringify(detail) : body?.error?.message;
            const detailText = message && !/[\u3400-\u9fff]/.test(message) ? ' · ' + message : '';
            throw new TradeError(`${labels[code] ?? 'Request failed'}${detailText}`, body?.result === 'unknown' || code === 'ORDER_RESULT_UNKNOWN' || (writing && !code && response.status >= 500));
        }
        if (!body || (writing && body.result !== 'accepted')) throw new TradeError(writing ? 'Order response unknown. Check Schwab' : 'Invalid account response', writing);
        return body;
    } catch (error) {
        if (error instanceof TradeError) throw error;
        throw new TradeError(writing ? ((error as Error).name === 'AbortError' ? 'Request timed out · result unknown' : 'Connection lost · result unknown') : 'Cannot read Schwab quote', writing);
    } finally { window.clearTimeout(timeout); }
}

export type OrderMode = 'breakout-buy' | 'market-buy' | 'market-sell';
export function orderFieldsComplete(mode: OrderMode | null, qty: string, buy: string, stop: string) {
    if (!mode || !Number.isSafeInteger(Number(qty)) || Number(qty) <= 0) return false;
    return mode !== 'breakout-buy' || [buy, stop].every(value => Number.isFinite(Number(value)) && Number(value) > 0);
}

export class TradeController {
    private state: TradeState | null = null;
    private enabled = false;
    private symbol = '';
    private quote: { bid: string | null; ask: string | null; updated_at?: string | null } = { bid: null, ask: null };
    private high: number | null = null; private low: number | null = null;
    private quantityInitialized = false;
    private auto = true; private buy = ''; private stop = ''; private qty = '';
    private busy = false; private unknown = false; private message = ''; private sequence = 0;
    private acceptedTimer: number | undefined;
    private previews = new Map<string, string>();
    private replacements = new Map<string, string>();
    private mode: OrderMode | null = null;
    private lines: TradeLines[];
    private rulerStep = 1; private rulerMaximum = 1;
    private tickSignature = '';
    constructor(panels: Panel[], private appMode: () => string) {
        this.lines = panels.map(panel => new TradeLines(panel, (line, price) => {
            if (this.busy) return;
            if (line.order) { this.mode = null; this.previews.clear(); if (Number(price) !== Number(line.order.stop_price)) this.previews.set(line.order.order_id!, price); }
            else { this.auto = false; if (line.key === 'buy') this.buy = price; else this.stop = price; }
            this.render();
        }));
        const ruler = $('trade-ruler') as HTMLInputElement;
        new ResizeObserver(() => this.renderTicks()).observe(ruler);
        ruler.oninput = () => {
            this.quantityInitialized = true;
            this.qty = String(Math.min(this.rulerMaximum, Number(ruler.value) * this.rulerStep));
            this.render();
        };
        $('trade-auto').onclick = () => { this.auto = true; this.follow(); this.render(); };
        document.querySelectorAll<HTMLButtonElement>('[data-trade-mode]').forEach(button => {
            button.onclick = () => {
                const mode = button.dataset.tradeMode as OrderMode;
                this.mode = this.mode === mode ? null : mode;
                this.auto = true; this.buy = this.stop = this.qty = ''; this.quantityInitialized = false; this.previews.clear();
                this.follow(); this.render();
            };
        });
        $('trade-submit').onclick = () => void this.submit();
        $('trade-checked').onclick = () => { this.unknown = false; this.message = ''; this.render(); };
        $('trade-refresh').onclick = () => { void tradeRequest('orders').catch(error => { if (!this.unknown) this.message = (error as Error).message; this.render(); }); };
        document.addEventListener('keydown', event => { if (event.key === 'Escape') { this.lines.forEach(layer => layer.cancelDrag()); this.previews.clear(); this.render(); } });
    }
    private row() { return this.state?.rows.find(r => r.symbol === this.symbol); }
    setSymbol(symbol: string) {
        const enabled = this.appMode() === 'trade';
        if (symbol === this.symbol && enabled === this.enabled) return;
        this.enabled = enabled;
        ++this.sequence; this.symbol = symbol; this.quote = { bid: null, ask: null }; this.high = this.low = null;
        this.mode = null; this.quantityInitialized = false; this.auto = true; this.buy = this.stop = this.qty = ''; this.previews.clear(); this.render();
        if (!symbol || this.appMode() !== 'trade') return;
        const request = this.sequence;
        void tradeRequest<{ bid: string | null; ask: string | null; updated_at: string }>('quote?symbol=' + encodeURIComponent(symbol)).then(quote => {
            if (request !== this.sequence) return;
            this.updateQuote(quote);
        }).catch(error => { if (request === this.sequence && !this.unknown) { this.message = (error as Error).message; this.render(); } });
    }
    update(state: TradeState | null) {
        this.state = state;
        if (state) {
            const orders = flattenOrders(state.orders);
            for (const [old, next] of this.replacements) {
                const replacement = orders.find(order => order.order_id === next);
                if (!replacement || ['PENDING_REPLACE', 'PENDING_ACKNOWLEDGEMENT'].includes(replacement.status ?? '')) continue;
                this.previews.delete(old); this.replacements.delete(old);
                if (replacement.status === 'REJECTED' && !this.unknown) this.message = 'Replacement rejected by Schwab · check current orders';
            }
        }
        this.follow(); this.render();
    }
    updateQuote(quote: { bid: string | null; ask: string | null; updated_at?: string | null }) {
        if (quote.updated_at && (!this.quote.updated_at || Date.parse(quote.updated_at) >= Date.parse(this.quote.updated_at))) this.quote = quote;
        this.follow(); this.render();
    }
    view(view: View) {
        if (view.symbol !== this.symbol || this.appMode() !== 'trade') return;
        const regular = view.quote.regular;
        const today = regular && dayKey(regular.timestamp) === dayKey(view.server_time);
        this.high = today ? numeric(regular.high) : null; this.low = today ? numeric(regular.low) : null;
        this.follow(); this.render();
    }
    private follow() {
        if (this.busy || !this.mode) return;
        if (this.auto) { this.buy = suggestedBuy(this.high, numeric(this.quote.ask)); this.stop = this.low?.toFixed(2) ?? ''; }
        const reference = this.mode === 'breakout-buy' ? numeric(this.buy) : numeric(this.quote.ask);
        if (!this.quantityInitialized) {
            if (this.mode === 'market-sell') { this.quantityInitialized = true; this.qty = String(Math.floor(Number(this.row()?.position?.quantity ?? 0))); }
            else if (reference && reference > 0) { this.quantityInitialized = true; this.qty = String(Math.max(1, Math.floor(20_000 / reference))); }
        }
    }
    private async write(path: string, method: string, payload?: object) {
        if (this.busy || this.appMode() !== 'trade') return null;
        window.clearTimeout(this.acceptedTimer);
        this.busy = true; if (!this.unknown) this.message = ''; this.render();
        try {
            const result = await tradeRequest<{ new_order_id?: string }>(path, method, payload);
            if (!this.unknown) {
                this.message = 'Accepted';
                this.acceptedTimer = window.setTimeout(() => {
                    if (this.message === 'Accepted') { this.message = ''; this.render(); }
                }, 2000);
            }
            return result;
        } catch (error) {
            if (!this.unknown) { this.message = (error as Error).message; this.unknown = error instanceof TradeError && error.unknown; }
            return null;
        } finally { this.busy = false; this.render(); }
    }
    private pendingStop() { return this.row()?.orders.find(order => this.previews.has(order.order_id!)); }
    private async submit() {
        const stop = this.pendingStop();
        if (stop) { if (this.ready()) await this.applyStop(stop); return; }
        if (!orderFieldsComplete(this.mode, this.qty, this.buy, this.stop) || !this.ready()) return;
        const selection = this.sequence;
        const payload = { symbol: this.symbol.replace(/\.US$/, ''), qty: Number(this.qty), ...(this.mode === 'breakout-buy' ? { buy_stop: this.buy, sell_stop: this.stop } : {}) };
        const result = await this.write('orders/' + this.mode, 'POST', payload);
        if (result && selection === this.sequence) { this.mode = null; this.qty = ''; this.render(); }
    }
    async cancel(id: string) { await this.write('orders/' + encodeURIComponent(id), 'DELETE'); }
    private async applyStop(order: Order) {
        const price = this.previews.get(order.order_id!); if (!price || !editableStop(order) || this.replacements.has(order.order_id!)) return;
        const result = await this.write('orders/' + encodeURIComponent(order.order_id!) + '/stop', 'PUT', { new_stop: price });
        if (result?.new_order_id) this.replacements.set(order.order_id!, result.new_order_id);
        this.render();
    }
    private ready() { return !!this.state && this.state.health.auth_status === 'valid' && this.state.health.schwab_rest === 'connected' && !this.busy; }
    private renderTicks() {
        const ticks = quantityTicks(this.rulerMaximum, this.rulerStep, $('trade-ruler').clientWidth);
        const signature = JSON.stringify(ticks);
        if (signature === this.tickSignature) return;
        this.tickSignature = signature;
        const labeled = ticks.filter(tick => tick.label);
        $('trade-ruler-ticks').replaceChildren(...labeled.map((tick, index) => {
            const span = document.createElement('span'); span.className = 'trade-tick' + (index === 0 ? ' first' : index === labeled.length - 1 ? ' last' : '');
            span.style.left = tick.position + '%'; span.textContent = String(tick.quantity); return span;
        }));
    }
    render() {
        const visible = this.appMode() === 'trade'; $('trade-ticket').hidden = !visible;
        if (!visible) { this.lines.forEach(layer => layer.update([])); return; }
        const active = this.mode != null, breakout = this.mode === 'breakout-buy', pending = this.pendingStop();
        for (const id of ['trade-size', 'trade-preview']) { $(id).classList.toggle('trade-inactive', !active); $(id).setAttribute('aria-hidden', String(!active)); }
        $('trade-ticket').dataset.editing = pending ? 'stop' : this.mode ?? 'browse';
        $('trade-qty').textContent = active ? this.qty : '';
        document.querySelectorAll<HTMLButtonElement>('[data-trade-mode]').forEach(button => {
            const selected = button.dataset.tradeMode === this.mode;
            button.classList.toggle('active', selected); button.setAttribute('aria-pressed', String(selected));
            button.disabled = this.busy || !this.symbol;
        });
        ($('trade-auto') as HTMLButtonElement).disabled = this.busy || !active || this.auto;
        const reference = breakout ? numeric(this.buy) : numeric(this.mode === 'market-sell' ? this.quote.bid : this.quote.ask), qty = numeric(this.qty);
        const ruler = $('trade-ruler') as HTMLInputElement;
        if (!ruler.matches(':active')) {
            this.rulerStep = quantityStep(reference && reference > 0 ? reference : 100);
            this.rulerMaximum = this.mode === 'market-sell' ? Math.floor(Number(this.row()?.position?.quantity ?? 0)) : Math.floor(Number(this.state?.limits.buy_amount ?? 45000) / (reference || 100));
            ruler.step = '1'; ruler.max = String(Math.max(1, Math.ceil(this.rulerMaximum / this.rulerStep)));
        }
        ruler.value = String(Math.ceil(Number(this.qty) / this.rulerStep)); ruler.disabled = this.busy || !active || !this.symbol;
        this.renderTicks();
        ruler.setAttribute('aria-valuetext', `${this.qty || '0'} shares`);
        const ask = numeric(this.quote.ask), bid = numeric(this.quote.bid), spread = ask != null && bid != null ? ask - bid : null;
        $('trade-ask').textContent = ask?.toFixed(2) ?? '—'; $('trade-bid').textContent = bid?.toFixed(2) ?? '—';
        const spreadPercent = spread != null && bid && bid > 0 ? spread / bid * 100 : null;
        $('trade-spread-percent').textContent = spreadPercent != null ? spreadPercent.toFixed(2) + '%' : '';
        $('trade-spread-value').textContent = spread?.toFixed(2) ?? '';
        $('trade-spread-percent').classList.toggle('spread-wide', spreadPercent != null && spreadPercent > SPREAD_WARNING_PERCENT);
        const distance = breakout && reference != null && reference > 0 && numeric(this.stop) != null ? reference - Number(this.stop) : null;
        $('trade-estimate').textContent = active && reference != null && qty != null ? Math.round(reference * qty).toLocaleString('en-US') : '';
        $('trade-risk').textContent = active && distance != null && qty != null ? `Risk ${(distance / reference! * 100).toFixed(2)}% ｜ ${Math.round(distance * qty).toLocaleString('en-US')}` : '';
        const status = !this.state ? 'Loading Schwab' : this.state.health.auth_status === 'auth_required' ? 'Schwab authorization required' : this.state.health.schwab_rest !== 'connected' ? 'Schwab unavailable · last snapshot retained' : '';
        $('trade-message').textContent = this.message || status;
        $('trade-feedback').hidden = !this.message && !status && !pending;
        if (pending && !this.message && !status) $('trade-message').textContent = `Stop change · ${pending.quantity} shares`;
        $('trade-message').classList.toggle('unknown', this.unknown); $('trade-checked').hidden = !this.unknown;
        $('trade-message').classList.toggle('accepted', this.message === 'Accepted');
        $('trade-refresh').hidden = !this.unknown;
        const submit = $('trade-submit') as HTMLButtonElement;
        submit.setAttribute('aria-busy', String(this.busy));
        submit.disabled = !this.ready() || !this.symbol || (pending ? !editableStop(pending) || this.replacements.has(pending.order_id!) : !orderFieldsComplete(this.mode, this.qty, this.buy, this.stop));
        submit.setAttribute('aria-label', pending ? 'Send stop change' : 'Send order');
        const values: TradeLine[] = [];
        for (const order of this.row() ? activeOrders(this.row()!) : []) if (order.stop_price && numeric(order.stop_price)! > 0) {
            const key = order.order_id ?? `${order.parent_order_id}-awaiting`;
            values.push({ key, price: Number(this.previews.get(key) ?? order.stop_price), color: order.instruction === 'BUY' ? palette.blue : palette.red,
                editable: editableStop(order) && !this.busy && !this.replacements.has(key), order });
        }
        if (active) {
            if (numeric(this.buy)! > 0) values.push({ key: 'buy', price: Number(this.buy), color: palette.blue, editable: !this.busy });
            if (numeric(this.stop)! > 0) values.push({ key: 'stop', price: Number(this.stop), color: palette.red, editable: !this.busy });
        }
        this.lines.forEach(layer => layer.update(values));
    }
}

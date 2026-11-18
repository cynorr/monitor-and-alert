import type { Panel } from './chart.js';
import { $, dayKey, type View } from './types.js';
import { numeric, editableStop, activeOrders, flattenOrders, type SchwabState, type Order } from './schwab-data.js';
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

export type OrderMode = 'breakout-buy' | 'market-buy' | 'market-sell' | 'atr-stop' | 'ema-stop';
export function orderFieldsComplete(mode: OrderMode | null, qty: string, buy: string, stop: string) {
    if (!mode || !Number.isSafeInteger(Number(qty)) || Number(qty) <= 0) return false;
    const price = (value: string) => Number.isFinite(Number(value)) && Number(value) > 0;
    return mode === 'breakout-buy' ? price(buy) && price(stop) : ['atr-stop', 'ema-stop'].includes(mode) ? price(stop) : true;
}

export class TradeController {
    private state: SchwabState | null = null;
    private enabled = false;
    private symbol = '';
    private quote: { bid: string | null; ask: string | null; updated_at?: string | null } = { bid: null, ask: null };
    private high: number | null = null; private low: number | null = null;
    private reference: View['trade_reference'];
    private ema: 10 | 20 = 10;
    private emaInitialized = false;
    private selectedStop: string | null = null;
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
            if (line.order) { this.selectStop(line.order); if (Number(price) !== Number(line.order.stop_price)) this.previews.set(line.order.order_id!, price); else this.previews.delete(line.order.order_id!); }
            else { this.auto = false; if (line.key === 'buy') this.buy = price; else this.stop = price; }
            this.render();
        }, line => { if (line.order && !this.busy) { this.selectStop(line.order); this.render(); } }));
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
                this.selectedStop = null;
                if (mode === 'ema-stop') this.emaInitialized = false;
                this.auto = true; this.buy = this.stop = this.qty = ''; this.quantityInitialized = false; this.previews.clear();
                this.follow(); this.render();
            };
        });
        document.querySelectorAll<HTMLButtonElement>('[data-sell-percent]').forEach(button => {
            button.onclick = () => { this.qty = String(Math.floor(this.held() * Number(button.dataset.sellPercent) / 100)); this.render(); };
        });
        document.querySelectorAll<HTMLButtonElement>('[data-ema-period]').forEach(button => {
            button.onclick = () => { this.ema = Number(button.dataset.emaPeriod) as 10 | 20; this.emaInitialized = true; this.auto = true; this.follow(); this.render(); };
        });
        $('trade-submit').onclick = () => void this.submit();
        $('trade-checked').onclick = () => { this.unknown = false; this.message = ''; this.render(); };
        $('trade-refresh').onclick = () => { void tradeRequest('orders').catch(error => { if (!this.unknown) this.message = (error as Error).message; this.render(); }); };
        document.addEventListener('keydown', event => { if (event.key === 'Escape') { this.lines.forEach(layer => layer.cancelDrag()); this.previews.clear(); this.selectedStop = null; this.render(); } });
    }
    private row() { return this.state?.rows.find(r => r.symbol === this.symbol); }
    private held() { return Math.floor(Number(this.row()?.position?.quantity ?? 0)); }
    private selectStop(order: Order) {
        if (this.selectedStop === order.order_id) return;
        this.mode = null; this.selectedStop = order.order_id; this.previews.clear();
        this.qty = order.quantity ?? ''; this.quantityInitialized = true;
    }
    setSymbol(symbol: string) {
        const enabled = this.appMode() === 'monitor' && this.state !== null;
        if (symbol === this.symbol && enabled === this.enabled) return;
        this.enabled = enabled;
        ++this.sequence; this.symbol = symbol; this.quote = { bid: null, ask: null }; this.high = this.low = null;
        this.mode = null; this.selectedStop = null; this.reference = undefined; this.quantityInitialized = false; this.auto = true; this.buy = this.stop = this.qty = ''; this.previews.clear(); this.render();
        if (!symbol || !enabled) return;
        const request = this.sequence;
        void tradeRequest<{ bid: string | null; ask: string | null; updated_at: string }>('quote?symbol=' + encodeURIComponent(symbol)).then(quote => {
            if (request !== this.sequence) return;
            this.updateQuote(quote);
        }).catch(error => { if (request === this.sequence && !this.unknown) { this.message = (error as Error).message; this.render(); } });
    }
    update(state: SchwabState | null) {
        this.state = state;
        if (state) {
            const orders = flattenOrders(state.orders);
            for (const [old, next] of this.replacements) {
                const replacement = orders.find(order => order.order_id === next);
                if (!replacement || ['PENDING_REPLACE', 'PENDING_ACKNOWLEDGEMENT'].includes(replacement.status ?? '')) continue;
                this.previews.delete(old); this.replacements.delete(old);
                if (this.selectedStop === old) this.selectedStop = null;
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
        if (view.symbol !== this.symbol || this.appMode() !== 'monitor') return;
        const regular = view.quote.regular;
        const today = regular && dayKey(regular.timestamp) === dayKey(view.server_time);
        this.high = today ? numeric(regular.high) : null; this.low = today ? numeric(regular.low) : null;
        this.reference = view.trade_reference;
        this.follow(); this.render();
    }
    private follow() {
        if (this.busy || !this.mode) return;
        if (this.mode === 'ema-stop' && !this.emaInitialized && (this.reference?.ema10 != null || this.reference?.ema20 != null)) {
            this.ema = (this.reference.ema20 ?? -Infinity) > (this.reference.ema10 ?? -Infinity) ? 20 : 10;
            this.emaInitialized = true;
        }
        if (this.auto) {
            this.buy = suggestedBuy(this.high, numeric(this.quote.ask));
            const atr = this.reference?.atr20;
            const price = this.mode === 'atr-stop' ? this.high != null && atr != null ? this.high - 1.1 * atr : null :
                this.mode === 'ema-stop' ? this.reference?.[this.ema === 10 ? 'ema10' : 'ema20'] : this.low;
            this.stop = price?.toFixed(2) ?? '';
        }
        if (this.mode === 'atr-stop' || this.mode === 'ema-stop') { this.qty = String(this.held()); this.quantityInitialized = true; }
        const reference = this.mode === 'breakout-buy' ? numeric(this.buy) : numeric(this.quote.ask);
        if (!this.quantityInitialized) {
            if (this.mode === 'market-sell') { this.quantityInitialized = true; this.qty = String(Math.floor(this.held() * .3)); }
            else if (reference && reference > 0) { this.quantityInitialized = true; this.qty = String(Math.max(1, Math.floor(20_000 / reference))); }
        }
    }
    private async write(path: string, method: string, payload?: object) {
        if (this.busy || this.appMode() !== 'monitor') return null;
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
    private pendingStop() { return this.row()?.orders.find(order => order.order_id === this.selectedStop); }
    private stopChanged(order: Order) { return this.previews.has(order.order_id!) || Number(this.qty) !== Number(order.quantity); }
    private stopValid(price: string) { const bid = numeric(this.quote.bid), value = numeric(price); return value != null && value > 0 && bid != null && value < bid; }
    private fieldsValid() {
        if (!orderFieldsComplete(this.mode, this.qty, this.buy, this.stop)) return false;
        if (this.mode === 'atr-stop' || this.mode === 'ema-stop') {
            if (!this.stopValid(this.stop)) return false;
            if (this.mode === 'ema-stop' && (!this.reference?.session_close || this.reference.server_time >= this.reference.session_close)) return false;
        }
        return true;
    }
    private async submit() {
        const stop = this.pendingStop();
        if (stop) { if (this.ready()) await this.applyStop(stop); return; }
        if (!this.fieldsValid() || !this.ready()) return;
        const selection = this.sequence;
        const positionStop = this.mode === 'atr-stop' || this.mode === 'ema-stop';
        const payload = { symbol: this.symbol.replace(/\.US$/, ''), ...(positionStop ? {
            ...(this.mode === 'ema-stop' ? { ema: this.ema } : {}), ...(!this.auto ? { price: this.stop } : {})
        } : { qty: Number(this.qty), ...(this.mode === 'breakout-buy' ? { buy_stop: this.buy, sell_stop: this.stop } : {}) }) };
        const result = await this.write('orders/' + this.mode, 'POST', payload);
        if (result && selection === this.sequence) { this.mode = null; this.qty = ''; this.render(); }
    }
    async cancel(id: string) { await this.write('orders/' + encodeURIComponent(id), 'DELETE'); }
    private async applyStop(order: Order) {
        const price = this.previews.get(order.order_id!) ?? order.stop_price ?? '';
        if (!this.stopChanged(order) || !this.stopValid(price) || !editableStop(order) || this.replacements.has(order.order_id!) || !Number.isSafeInteger(Number(this.qty)) || Number(this.qty) <= 0) return;
        const result = await this.write('orders/' + encodeURIComponent(order.order_id!) + '/stop', 'PUT', { new_stop: price, qty: Number(this.qty) });
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
        const visible = this.appMode() === 'monitor' && this.state !== null; $('trade-ticket').hidden = !visible;
        if (!visible) { this.lines.forEach(layer => layer.update([])); return; }
        const pending = this.pendingStop(), active = this.mode != null || !!pending, breakout = this.mode === 'breakout-buy';
        const positionStop = this.mode === 'atr-stop' || this.mode === 'ema-stop';
        for (const id of ['trade-size', 'trade-preview']) { $(id).classList.toggle('trade-inactive', !active); $(id).setAttribute('aria-hidden', String(!active)); }
        $('trade-ticket').dataset.editing = pending ? 'stop' : this.mode ?? 'browse';
        $('trade-qty').textContent = active ? this.qty : '';
        $('trade-percent').textContent = active && (pending || this.mode === 'market-sell' || positionStop) && this.held() ? `${(Number(this.qty) / this.held() * 100).toFixed(1).replace(/\.0$/, '')}%` : '';
        $('trade-sell-presets').hidden = this.mode !== 'market-sell';
        $('trade-ema-periods').hidden = this.mode !== 'ema-stop';
        document.querySelectorAll<HTMLButtonElement>('[data-sell-percent]').forEach(button => { button.disabled = this.busy; });
        document.querySelectorAll<HTMLButtonElement>('[data-ema-period]').forEach(button => {
            button.classList.toggle('active', Number(button.dataset.emaPeriod) === this.ema);
            button.setAttribute('aria-pressed', String(Number(button.dataset.emaPeriod) === this.ema)); button.disabled = this.busy;
        });
        document.querySelectorAll<HTMLButtonElement>('[data-trade-mode]').forEach(button => {
            const selected = button.dataset.tradeMode === this.mode;
            button.classList.toggle('active', selected); button.setAttribute('aria-pressed', String(selected));
            button.disabled = this.busy || !this.symbol || (['market-sell', 'atr-stop', 'ema-stop'].includes(button.dataset.tradeMode!) && this.held() <= 0);
        });
        ($('trade-auto') as HTMLButtonElement).disabled = this.busy || !this.mode || this.auto;
        const selling = pending || this.mode === 'market-sell' || positionStop;
        const reference = pending ? numeric(this.previews.get(pending.order_id!) ?? pending.stop_price) : breakout ? numeric(this.buy) : numeric(selling ? this.quote.bid : this.quote.ask), qty = numeric(this.qty);
        const ruler = $('trade-ruler') as HTMLInputElement;
        if (!ruler.matches(':active')) {
            this.rulerStep = selling ? 1 : quantityStep(reference && reference > 0 ? reference : 100);
            this.rulerMaximum = selling ? this.held() : Math.floor(Number(this.state?.limits.buy_amount ?? 45000) / (reference || 100));
            ruler.step = '1'; ruler.max = String(Math.max(1, Math.ceil(this.rulerMaximum / this.rulerStep)));
        }
        ruler.value = String(Math.ceil(Number(this.qty) / this.rulerStep)); ruler.disabled = this.busy || !active || !this.symbol || positionStop;
        this.renderTicks();
        ruler.setAttribute('aria-valuetext', `${this.qty || '0'} shares`);
        const ask = numeric(this.quote.ask), bid = numeric(this.quote.bid), spread = ask != null && bid != null ? ask - bid : null;
        $('trade-ask').textContent = ask?.toFixed(2) ?? '—'; $('trade-bid').textContent = bid?.toFixed(2) ?? '—';
        const spreadPercent = spread != null && bid && bid > 0 ? spread / bid * 100 : null;
        $('trade-spread-percent').textContent = spreadPercent != null ? spreadPercent.toFixed(2) + '%' : '';
        $('trade-spread-value').textContent = spread?.toFixed(2) ?? '';
        $('trade-spread-percent').classList.toggle('spread-wide', spreadPercent != null && spreadPercent > SPREAD_WARNING_PERCENT);
        const distance = (breakout || positionStop) && reference != null && reference > 0 && numeric(this.stop) != null ? reference - Number(this.stop) : null;
        $('trade-estimate').textContent = active && reference != null && qty != null ? Math.round(reference * qty).toLocaleString('en-US') : '';
        $('trade-risk').textContent = active && distance != null && qty != null ? `Risk ${(distance / reference! * 100).toFixed(2)}% ｜ ${Math.round(distance * qty).toLocaleString('en-US')}` : '';
        const invalidStop = positionStop && !this.stopValid(this.stop) || pending && !this.stopValid(this.previews.get(pending.order_id!) ?? pending.stop_price ?? '');
        const status = !this.state ? 'Loading Schwab' : this.state.health.auth_status === 'auth_required' ? 'Schwab authorization required' : this.state.health.schwab_rest !== 'connected' ? 'Schwab unavailable · last snapshot retained' : invalidStop ? 'Stop must be positive and below Bid' : this.mode === 'ema-stop' && !this.fieldsValid() ? 'Today’s EMA order unavailable' : '';
        $('trade-message').textContent = this.message || status;
        $('trade-feedback').hidden = !this.message && !status && !pending;
        $('trade-message').classList.toggle('unknown', this.unknown); $('trade-checked').hidden = !this.unknown;
        $('trade-message').classList.toggle('accepted', this.message === 'Accepted');
        $('trade-refresh').hidden = !this.unknown;
        const submit = $('trade-submit') as HTMLButtonElement;
        submit.setAttribute('aria-busy', String(this.busy));
        submit.disabled = !this.ready() || !this.symbol || (pending ? !editableStop(pending) || this.replacements.has(pending.order_id!) || !this.stopChanged(pending) || !this.stopValid(this.previews.get(pending.order_id!) ?? pending.stop_price ?? '') || !Number.isSafeInteger(Number(this.qty)) || Number(this.qty) <= 0 : !this.fieldsValid());
        submit.setAttribute('aria-label', pending ? 'Send stop change' : 'Send order');
        const values: TradeLine[] = [];
        for (const order of this.row() ? activeOrders(this.row()!) : []) if (order.stop_price && numeric(order.stop_price)! > 0) {
            const key = order.order_id ?? `${order.parent_order_id}-awaiting`;
            values.push({ key, price: Number(this.previews.get(key) ?? order.stop_price), color: order.instruction === 'BUY' ? palette.blue : palette.red,
                editable: editableStop(order) && !this.busy && !this.replacements.has(key), order });
        }
        if (this.mode) {
            if (!positionStop && numeric(this.buy)! > 0) values.push({ key: 'buy', price: Number(this.buy), color: palette.blue, editable: !this.busy });
            if (numeric(this.stop)! > 0) values.push({ key: 'stop', price: Number(this.stop), color: palette.red, editable: !this.busy });
        }
        this.lines.forEach(layer => layer.update(values));
    }
}

// Native Schwab response fields and read-only calculations. No SnapTrade accounting.
export type Execution = { activity_id: string; leg_id: string; quantity: string; price: string; time: string };
export type Order = {
    order_id: string | null; parent_order_id: string | null; symbol: string | null; asset_type: string | null;
    instruction: string | null; order_type: string | null; strategy_type: string | null; status: string | null;
    quantity: string | null; filled_quantity: string | null; stop_price: string | null;
    duration: string | null; session: string | null; entered_at: string | null;
    editable: boolean | null; cancelable: boolean | null; executions: Execution[]; child_orders: Order[];
};
export type Position = { symbol: string; asset_type: string; quantity: string; average_price: string | null; market_value: string | null; open_profit_loss: string | null; day_profit_loss: string | null; day_profit_loss_percent: string | null };
export type SoldToday = { quantity: string; amount: string; average_price: string; executions: (Execution & { order_id: string })[] };
export type TradeRow = { symbol: string; ticker: string; kind: 'entry' | 'holding' | 'sold' | 'order'; position: Position | null; orders: Order[]; sold_today: SoldToday | null; change_percent: string | null; extended_percent: string | null };
type AccountField = 'liquidation_value' | 'long_market_value' | 'cash_balance' | 'available_funds' | 'buying_power' | 'intraday_buying_power' | 'day_trading_buying_power' | 'margin_balance' | 'maintenance_requirement' | 'stock_buying_power';
export type TradeState = {
    rows: TradeRow[]; orders: Order[]; account: (Record<AccountField, string | null> & { updated_at: string }) | null;
    account_updated_at: string | null; orders_updated_at: string | null;
    health: { service: string; auth_status: string; schwab_rest: string; schwab_stream: string; account_initialized: boolean; orders_initialized: boolean; last_account_update: string | null; last_orders_update: string | null };
    limits: { buy_amount: string; loss: string; stop_ratio: string };
};
export const numeric = (value: string | number | null | undefined) => value == null || value === '' || !Number.isFinite(Number(value)) ? null : Number(value);
export function openPercent(position: Position | null) {
    const pnl = numeric(position?.open_profit_loss), qty = numeric(position?.quantity), price = numeric(position?.average_price);
    return pnl != null && qty != null && price != null && qty * price > 0 ? pnl / (qty * price) * 100 : null;
}
export function flattenOrders(orders: Order[]) {
    const found = new Map<string | Order, Order>();
    const visit = (items: Order[]) => { for (const item of items) { const key = item.order_id ?? item; if (!found.has(key)) found.set(key, item); visit(item.child_orders); } };
    visit(orders); return [...found.values()];
}
const active = new Set(['WORKING', 'AWAITING_STOP_CONDITION', 'AWAITING_PARENT_ORDER', 'PENDING_ACTIVATION', 'QUEUED', 'PENDING_REPLACE', 'PENDING_CANCEL', 'PARTIALLY_FILLED', 'ACCEPTED', 'PENDING_ACKNOWLEDGEMENT']);
export const activeOrders = (row: TradeRow) => flattenOrders(row.orders).filter(order => order.status != null && active.has(order.status) && order.symbol === row.ticker);
export const entryOrders = (row: TradeRow) => activeOrders(row).filter(order => order.instruction === 'BUY');
export function editableStop(order: Order) {
    return !!order.order_id && (order.editable === true || order.status === 'PENDING_ACTIVATION') && order.instruction === 'SELL' && order.order_type === 'STOP' && order.strategy_type === 'SINGLE' && !order.child_orders.length && ['WORKING', 'AWAITING_STOP_CONDITION', 'QUEUED', 'ACCEPTED', 'PENDING_ACTIVATION'].includes(order.status ?? '');
}
export function entryPreview(order: Order) {
    const qty = numeric(order.quantity), price = numeric(order.stop_price);
    const stop = numeric(flattenOrders(order.child_orders).find(child => child.instruction === 'SELL' && child.order_type === 'STOP')?.stop_price);
    const amount = qty != null && price != null ? qty * price : null;
    const distance = price != null && stop != null ? price - stop : null;
    return { qty, price, stop, amount, riskPercent: distance != null && price && price > 0 ? distance / price * 100 : null, risk: distance != null && qty != null ? distance * qty : null };
}
export function entryAmount(row: TradeRow) {
    const values = entryOrders(row).map(order => entryPreview(order).amount);
    return values.length && values.every(value => value != null) ? values.reduce<number>((sum, value) => sum + value!, 0) : null;
}
export function holdingTags(row: TradeRow) {
    return [...(entryOrders(row).length ? ['Entry'] : []), ...(row.position && numeric(row.position.quantity)! > 0 && numeric(row.sold_today?.quantity)! > 0 ? ['Trim'] : [])];
}
export type HoldingDetail = { key: string; kind: 'Buy' | 'Sold' | 'Stop' | 'Entry'; qty: number; price: number | null; stop: number | null; amount: number | null; pnlPercent: number | null; pnl: number | null; riskPercent: number | null; risk: number | null; cancelId: string | null };
export function holdingDetails(row: TradeRow): HoldingDetail[] {
    const result: HoldingDetail[] = [], position = row.position, average = numeric(position?.average_price);
    const add = (key: string, kind: HoldingDetail['kind'], qty: number, price: number | null, order?: Order) => {
        const difference = kind !== 'Buy' && average != null && average > 0 && price != null ? price - average : null;
        const pnl = difference != null ? qty * difference : null;
        const pnlPercent = difference != null ? difference / average! * 100 : null;
        result.push({ key, kind, qty, price, stop: null, amount: price != null ? qty * price : null, pnlPercent, pnl, riskPercent: null, risk: null, cancelId: order?.cancelable && order.order_id ? order.order_id : null });
    };
    if (position && numeric(position.quantity)! > 0 && numeric(position.average_price) != null) add('buy', 'Buy', Number(position.quantity), Number(position.average_price));
    // Sold Today retains the backend's FILLED scope, grouped by real broker order.
    const sales = new Map<string, { qty: number; amount: number }>();
    for (const fill of row.sold_today?.executions ?? []) {
        const previous = sales.get(fill.order_id) ?? { qty: 0, amount: 0 };
        previous.qty += Number(fill.quantity); previous.amount += Number(fill.quantity) * Number(fill.price); sales.set(fill.order_id, previous);
    }
    for (const [id, sale] of sales) if (sale.qty > 0) add('sold-' + id, 'Sold', sale.qty, sale.amount / sale.qty);
    const entries = entryOrders(row), attached = new Set(entries.flatMap(order => flattenOrders(order.child_orders).map(child => child.order_id)));
    for (const order of entries) {
        const value = entryPreview(order);
        if (value.qty == null) continue;
        result.push({ key: 'entry-' + order.order_id, kind: 'Entry', ...value, qty: value.qty, pnlPercent: null, pnl: null, cancelId: order.cancelable ? order.order_id : null });
    }
    for (const order of activeOrders(row)) if (order.instruction === 'SELL' && order.order_type === 'STOP' && !attached.has(order.order_id) && numeric(order.quantity) != null) add('stop-' + order.order_id, 'Stop', Number(order.quantity), numeric(order.stop_price), order);
    return result;
}

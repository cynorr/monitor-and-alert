// Native Schwab response fields and read-only account calculations.
export type Execution = { activity_id: string; leg_id: string; quantity: string; price: string; time: string };
export type Order = {
    order_id: string | null; parent_order_id: string | null; symbol: string | null; asset_type: string | null;
    instruction: string | null; order_type: string | null; strategy_type: string | null; status: string | null;
    quantity: string | null; filled_quantity: string | null; stop_price: string | null;
    duration: string | null; session: string | null; entered_at: string | null; release_time: string | null;
    editable: boolean | null; cancelable: boolean | null; executions: Execution[]; child_orders: Order[];
};
export type Position = { symbol: string; asset_type: string; quantity: string; average_price: string | null; market_value: string | null; open_profit_loss: string | null; day_profit_loss: string | null; day_profit_loss_percent: string | null };
export type SoldToday = { quantity: string; amount: string; average_price: string; executions: (Execution & { order_id: string })[] };
export type HistoricalTrade = { order_id: string; side: 'BUY' | 'SELL'; time: string; date: string; quantity: string; price: string; amount: string; pnl: string | null; pnl_percent: string | null; holding_days: number | null };
export type AccountRow = { symbol: string; ticker: string; kind: 'entry' | 'holding' | 'sold' | 'order'; position: Position | null; orders: Order[]; sold_today: SoldToday | null; change_percent: string | null; extended_percent: string | null;
    holding_days: number | null; days_over_year: boolean; sold_percent: string | null; is_new: boolean; trades: HistoricalTrade[] };
type AccountField = 'liquidation_value' | 'long_market_value' | 'cash_balance' | 'available_funds' | 'buying_power' | 'intraday_buying_power' | 'day_trading_buying_power' | 'margin_balance' | 'maintenance_requirement' | 'stock_buying_power';
export type SchwabState = {
    rows: AccountRow[]; orders: Order[]; account: (Record<AccountField, string | null> & { updated_at: string }) | null;
    account_updated_at: string | null; orders_updated_at: string | null;
    health: { service: string; auth_status: string; schwab_rest: string; schwab_stream: string; account_initialized: boolean; orders_initialized: boolean; last_account_update: string | null; last_orders_update: string | null };
    limits: { buy_amount: string; loss: string; stop_ratio: string };
    history_updated_at: string | null;
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
const active = new Set(['WORKING', 'AWAITING_STOP_CONDITION', 'AWAITING_PARENT_ORDER', 'AWAITING_RELEASE_TIME', 'PENDING_ACTIVATION', 'QUEUED', 'PENDING_REPLACE', 'PENDING_CANCEL', 'PARTIALLY_FILLED', 'ACCEPTED', 'PENDING_ACKNOWLEDGEMENT']);
export const activeOrders = (row: AccountRow) => flattenOrders(row.orders).filter(order => order.status != null && active.has(order.status) && order.symbol === row.ticker);
export const entryOrders = (row: AccountRow) => activeOrders(row).filter(order => order.instruction === 'BUY');
export function editableStop(order: Order) {
    return !!order.order_id && (order.editable === true || ['PENDING_ACTIVATION', 'AWAITING_RELEASE_TIME'].includes(order.status ?? '')) && order.instruction === 'SELL' && order.order_type === 'STOP' && order.strategy_type === 'SINGLE' && !order.child_orders.length && ['WORKING', 'AWAITING_STOP_CONDITION', 'QUEUED', 'ACCEPTED', 'PENDING_ACTIVATION', 'AWAITING_RELEASE_TIME'].includes(order.status ?? '');
}
function entryTerms(order: Order) {
    const qty = numeric(order.quantity), price = numeric(order.stop_price);
    const amount = qty != null && price != null ? qty * price : null;
    return { qty, price, amount };
}
export function entryAmount(row: AccountRow) {
    const values = entryOrders(row).map(order => entryTerms(order).amount);
    return values.length && values.every(value => value != null) ? values.reduce<number>((sum, value) => sum + value!, 0) : null;
}
export function holdingTag(row: AccountRow) {
    if (entryOrders(row).length) return row.position ? 'Add' : 'Entry';
    return row.position && row.is_new ? 'NEW' : '';
}
export type HoldingDetail = { key: string; kind: 'Buy' | 'Sold' | 'Stop' | 'Entry'; date: string | null; days: number | null; qty: number; price: number | null; amount: number | null; pnlPercent: number | null; pnl: number | null; cancelId: string | null };
export function holdingDetails(row: AccountRow): HoldingDetail[] {
    const result: HoldingDetail[] = [];
    const addStop = (order: Order, cost: number | null, cancelId: string | null) => {
        const qty = numeric(order.quantity), price = numeric(order.stop_price);
        if (qty == null) return;
        const difference = price != null && cost != null && cost > 0 ? price - cost : null;
        result.push({ key: 'stop-' + order.order_id, kind: 'Stop', date: null, days: null, qty, price,
            amount: price != null ? qty * price : null, pnlPercent: difference != null ? difference / cost! * 100 : null,
            pnl: difference != null ? qty * difference : null, cancelId });
    };
    for (const trade of row.trades ?? []) {
        const sold = trade.side === 'SELL';
        result.push({ key: 'trade-' + trade.order_id, kind: sold ? 'Sold' : 'Buy', date: trade.date,
            days: sold ? trade.holding_days : null, qty: Number(trade.quantity), price: numeric(trade.price),
            amount: numeric(trade.amount), pnlPercent: sold ? numeric(trade.pnl_percent) : null,
            pnl: sold ? numeric(trade.pnl) : null, cancelId: null });
    }
    const orders = activeOrders(row);
    const stops = new Map(orders.filter(order => order.instruction === 'SELL' && order.order_type === 'STOP')
        .map(order => [order.order_id ?? order, order]));
    for (const order of orders.filter(order => order.instruction === 'BUY')) {
        const entry = entryTerms(order);
        if (entry.qty != null) result.push({ key: 'entry-' + order.order_id, kind: 'Entry', date: null, days: null,
            ...entry, qty: entry.qty, pnlPercent: null, pnl: null, cancelId: order.cancelable ? order.order_id : null });
        for (const child of flattenOrders(order.child_orders)) {
            const key = child.order_id ?? child, stop = stops.get(key);
            if (!stop) continue;
            addStop(stop, entry.price, null);
            stops.delete(key);
        }
    }
    const average = numeric(row.position?.average_price);
    for (const stop of stops.values()) addStop(stop, average, stop.cancelable ? stop.order_id : null);
    return result;
}

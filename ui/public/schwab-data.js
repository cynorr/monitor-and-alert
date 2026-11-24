export const numeric = (value) => value == null || value === '' || !Number.isFinite(Number(value)) ? null : Number(value);
export function openPercent(position) {
    const pnl = numeric(position?.open_profit_loss), qty = numeric(position?.quantity), price = numeric(position?.average_price);
    return pnl != null && qty != null && price != null && qty * price > 0 ? pnl / (qty * price) * 100 : null;
}
export function flattenOrders(orders) {
    const found = new Map();
    const visit = (items) => { for (const item of items) {
        const key = item.order_id ?? item;
        if (!found.has(key))
            found.set(key, item);
        visit(item.child_orders);
    } };
    visit(orders);
    return [...found.values()];
}
const active = new Set(['WORKING', 'AWAITING_STOP_CONDITION', 'AWAITING_PARENT_ORDER', 'AWAITING_RELEASE_TIME', 'PENDING_ACTIVATION', 'QUEUED', 'PENDING_REPLACE', 'PENDING_CANCEL', 'PARTIALLY_FILLED', 'ACCEPTED', 'PENDING_ACKNOWLEDGEMENT']);
export const activeOrders = (row) => flattenOrders(row.orders).filter(order => order.status != null && active.has(order.status) && order.symbol === row.ticker);
export const entryOrders = (row) => activeOrders(row).filter(order => order.instruction === 'BUY');
export function editableStop(order) {
    return !!order.order_id && (order.editable === true || ['PENDING_ACTIVATION', 'AWAITING_RELEASE_TIME'].includes(order.status ?? '')) && order.instruction === 'SELL' && order.order_type === 'STOP' && order.strategy_type === 'SINGLE' && !order.child_orders.length && ['WORKING', 'AWAITING_STOP_CONDITION', 'QUEUED', 'ACCEPTED', 'PENDING_ACTIVATION', 'AWAITING_RELEASE_TIME'].includes(order.status ?? '');
}
function entryTerms(order) {
    const qty = numeric(order.quantity), price = numeric(order.stop_price);
    const amount = qty != null && price != null ? qty * price : null;
    return { qty, price, amount };
}
export function entryAmount(row) {
    const values = entryOrders(row).map(order => entryTerms(order).amount);
    return values.length && values.every(value => value != null) ? values.reduce((sum, value) => sum + value, 0) : null;
}
export function holdingTag(row) {
    if (entryOrders(row).length)
        return row.position ? 'Add' : 'Entry';
    return row.position && row.is_new ? 'NEW' : '';
}
export function holdingDetails(row) {
    const result = [];
    const addStop = (order, cost, cancelId) => {
        const qty = numeric(order.quantity), price = numeric(order.stop_price);
        if (qty == null)
            return;
        const difference = price != null && cost != null && cost > 0 ? price - cost : null;
        result.push({ key: 'stop-' + order.order_id, kind: 'Stop', date: null, days: null, qty, price,
            amount: price != null ? qty * price : null, pnlPercent: difference != null ? difference / cost * 100 : null,
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
        if (entry.qty != null)
            result.push({ key: 'entry-' + order.order_id, kind: 'Entry', date: null, days: null,
                ...entry, qty: entry.qty, pnlPercent: null, pnl: null, cancelId: order.cancelable ? order.order_id : null });
        for (const child of flattenOrders(order.child_orders)) {
            const key = child.order_id ?? child, stop = stops.get(key);
            if (!stop)
                continue;
            addStop(stop, entry.price, null);
            stops.delete(key);
        }
    }
    const average = numeric(row.position?.average_price);
    for (const stop of stops.values())
        addStop(stop, average, stop.cancelable ? stop.order_id : null);
    return result;
}

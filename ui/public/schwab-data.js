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
const active = new Set(['WORKING', 'AWAITING_STOP_CONDITION', 'AWAITING_PARENT_ORDER', 'PENDING_ACTIVATION', 'QUEUED', 'PENDING_REPLACE', 'PENDING_CANCEL', 'PARTIALLY_FILLED', 'ACCEPTED', 'PENDING_ACKNOWLEDGEMENT']);
export const activeOrders = (row) => flattenOrders(row.orders).filter(order => order.status != null && active.has(order.status) && order.symbol === row.ticker);
export const entryOrders = (row) => activeOrders(row).filter(order => order.instruction === 'BUY');
export function editableStop(order) {
    return !!order.order_id && order.editable === true && order.instruction === 'SELL' && order.order_type === 'STOP' && order.strategy_type === 'SINGLE' && !order.child_orders.length && ['WORKING', 'AWAITING_STOP_CONDITION', 'QUEUED', 'ACCEPTED'].includes(order.status ?? '');
}
export function entryPreview(order) {
    const qty = numeric(order.quantity), price = numeric(order.stop_price);
    const stop = numeric(flattenOrders(order.child_orders).find(child => child.instruction === 'SELL' && child.order_type === 'STOP')?.stop_price);
    const amount = qty != null && price != null ? qty * price : null;
    const distance = price != null && stop != null ? price - stop : null;
    return { qty, price, stop, amount, riskPercent: distance != null && price && price > 0 ? distance / price * 100 : null, risk: distance != null && qty != null ? distance * qty : null };
}
export function entryAmount(row) {
    const values = entryOrders(row).map(order => entryPreview(order).amount);
    return values.length && values.every(value => value != null) ? values.reduce((sum, value) => sum + value, 0) : null;
}
export function holdingTags(row) {
    return [...(entryOrders(row).length ? ['Entry'] : []), ...(row.position && numeric(row.position.quantity) > 0 && numeric(row.sold_today?.quantity) > 0 ? ['Trim'] : [])];
}
export function holdingDetails(row) {
    const result = [], position = row.position;
    const add = (key, kind, qty, price, order) => {
        result.push({ key, kind, qty, price, stop: null, amount: price != null ? qty * price : null, riskPercent: null, risk: null, cancelId: order?.cancelable && order.order_id ? order.order_id : null });
    };
    if (position && numeric(position.quantity) > 0 && numeric(position.average_price) != null)
        add('buy', 'Buy', Number(position.quantity), Number(position.average_price));
    // Sold Today retains the backend's FILLED scope, grouped by real broker order.
    const sales = new Map();
    for (const fill of row.sold_today?.executions ?? []) {
        const previous = sales.get(fill.order_id) ?? { qty: 0, amount: 0 };
        previous.qty += Number(fill.quantity);
        previous.amount += Number(fill.quantity) * Number(fill.price);
        sales.set(fill.order_id, previous);
    }
    for (const [id, sale] of sales)
        if (sale.qty > 0)
            add('sold-' + id, 'Sold', sale.qty, sale.amount / sale.qty);
    const entries = entryOrders(row), attached = new Set(entries.flatMap(order => flattenOrders(order.child_orders).map(child => child.order_id)));
    for (const order of entries) {
        const value = entryPreview(order);
        if (value.qty == null)
            continue;
        result.push({ key: 'entry-' + order.order_id, kind: 'Entry', ...value, qty: value.qty, cancelId: order.cancelable ? order.order_id : null });
    }
    for (const order of activeOrders(row))
        if (order.instruction === 'SELL' && order.order_type === 'STOP' && !attached.has(order.order_id) && numeric(order.quantity) != null)
            add('stop-' + order.order_id, 'Stop', Number(order.quantity), numeric(order.stop_price), order);
    return result;
}

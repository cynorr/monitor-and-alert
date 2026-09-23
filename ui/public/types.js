export const $ = (id) => document.getElementById(id);
export const money = (n) => n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: n < 1 ? 4 : 2 });
export const compact = (n) => n == null ? '—' : Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(n);
const dayFormat = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' });
export const dayKey = (time) => dayFormat.format(new Date(time * 1000));
export const nyTime = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
export function extendedQuote(quote) {
    if (!quote)
        return undefined;
    const regular = quote.regular;
    return Object.values(quote.extended).filter(q => !regular || q.timestamp > regular.timestamp).sort((a, b) => b.timestamp - a.timestamp)[0];
}

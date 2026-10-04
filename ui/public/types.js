export const $ = (id) => document.getElementById(id);
export const money = (n) => n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: n < 1 ? 4 : 2 });
export const compact = (n) => n == null ? '—' : Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(n);
const dayFormat = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' });
export const dayKey = (time) => dayFormat.format(new Date(time * 1000));
export const nyTime = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
export function defaultTimeframe(now = Date.now()) {
    const [hour, minute] = nyTime.format(new Date(now)).split(':').map(Number);
    const elapsed = Math.max(0, hour * 60 + minute - (9 * 60 + 30));
    const period = [5, 15, 30, 60].find(minutes => elapsed < minutes) ?? 60;
    return period === 60 ? '1h' : `${period}m`;
}
export function scanProgress(value) {
    const labels = { daily: 'Downloading daily', splits: 'Updating splits', bars: 'Building daily bars', features: 'Preparing scan' };
    const stages = Object.entries(labels);
    const ready = value.features.date;
    const completed = value.features.updated_at ? new Date(value.features.updated_at) : null;
    const stamp = completed && Number.isFinite(completed.getTime()) ? ' · ' + nyTime.format(completed) + ' ET' : '';
    const errors = [value.error, ...stages.map(([key]) => value[key].error)].filter((error) => !!error);
    const active = stages.find(([key]) => value[key].status === 'running');
    const progress = active?.[1] ?? (value.running ? 'Preparing scan' : errors.length ? 'Refresh failed' : !ready ? 'Scan not ready' : '');
    const text = [ready ? 'Scan Ready ' + ready + stamp : '', progress].filter(Boolean).join(' · ');
    return { text, error: errors.length > 0, title: errors.join('\n') || 'Latest completed scan; target ' + value.target_date };
}
export function extendedQuote(quote) {
    if (!quote)
        return undefined;
    const regular = quote.regular;
    return Object.values(quote.extended).filter(q => !regular || q.timestamp > regular.timestamp).sort((a, b) => b.timestamp - a.timestamp)[0];
}

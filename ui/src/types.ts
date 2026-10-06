export const $ = (id: string) => document.getElementById(id)!;
export const money = (n?: number | null) => n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: n < 1 ? 4 : 2 });
export const compact = (n?: number | null) => n == null ? '—' : Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(n);
const dayFormat = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' });
export const dayKey = (time: number) => dayFormat.format(new Date(time * 1000));
export const nyTime = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
export function defaultTimeframe(now = Date.now()) {
    const [hour, minute] = nyTime.format(new Date(now)).split(':').map(Number);
    const elapsed = Math.max(0, hour * 60 + minute - (9 * 60 + 30));
    const period = [5, 15, 30, 60].find(minutes => elapsed < minutes) ?? 60;
    return period === 60 ? '1h' : `${period}m`;
}
export type PipelineStage = {
    status: 'idle' | 'running' | 'ready' | 'error';
    target: string | null;
    updated_at: string | null;
    error: string | null;
};
export type MassiveState = {
    target_date: string;
    ready: boolean;
    running: boolean;
    error?: string;
    daily: PipelineStage;
    splits: PipelineStage;
    bars: PipelineStage & { input_revision: string | null };
    features: PipelineStage & { date: string | null; input_revision: string | null };
};
export function scanProgress(value: MassiveState) {
    const labels = { daily: 'Downloading daily', splits: 'Updating splits', bars: 'Building daily bars', features: 'Building features' };
    const stages = Object.entries(labels) as [keyof typeof labels, string][];
    const errors = [value.error, ...stages.map(([key]) => value[key].error)].filter((error): error is string => !!error);
    const active = stages.find(([key]) => value[key].status === 'running');
    const progress = active?.[1] ?? (value.running ? 'Preparing scan' : errors.length ? 'Refresh failed' : !value.ready ? 'Scan not ready' : '');
    const text = progress ? progress + ' · ' + value.target_date : '';
    return { text, error: errors.length > 0, title: errors.join('\n') || text };
}
export type Row = {
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number | null;
};
export type Point = {
    time: number;
    value: number;
};
export type ChartData = {
    revision: number;
    bars?: Row[];
    indicators?: Record<string, Point[]>;
    active: Row | null;
    indicator_preview: Record<string, Point>;
};
export type QuoteValue = {
    last_price: number;
    cumulative_volume: number;
    timestamp: number;
    trade_session: string;
    prev_close?: number | null;
    bid_price?: number;
    ask_price?: number;
};
export type Quote = {
    regular: QuoteValue | null;
    extended: Record<string, QuoteValue>;
    connection_health: string;
    error: string | null;
    current_regular_session?: boolean;
};
export type Ticker = {
    [key: string]: unknown;
    symbol: string;
    ticker: string;
    status: string;
    section?: string;
    tags?: string[];
    tag_ids?: string[];
    manual_tags?: string[];
    excluded_at?: string;
    quote?: Quote;
    errors?: string[];
    close?: number | null;
    adr20?: number | null;
    adv20?: number | null;
};
export type View = {
    type?: string;
    request_id?: number;
    symbol: string;
    security_name?: string | null;
    timeframe: string;
    server_time: number;
    run_id: string;
    mode?: string;
    app_mode?: 'scan' | 'monitor';
    mock?: boolean;
    date?: string;
    read_only_daily?: boolean;
    charts: Record<string, ChartData>;
    quote: Quote;
    summary: {
        adr20: number | null;
        adv20: number | null;
        samples: number;
    };
    status: {
        stage: 'loading' | 'basic' | 'full';
        errors: string[];
    };
};
export function extendedQuote(quote?: Quote) {
    if (!quote)
        return undefined;
    const regular = quote.regular;
    return Object.values(quote.extended).filter(q => !regular || q.timestamp > regular.timestamp).sort((a, b) => b.timestamp - a.timestamp)[0];
}

export const selectionRequest = (symbol: string, timeframe: string, request_id: number, mode: 'scan' | 'monitor', source: 'watchlist' | 'holdings') =>
    ({ type: 'select', symbol, timeframe, request_id, mode, source });

export const $ = (id: string) => document.getElementById(id)!;
export const money = (n?: number | null) => n == null ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: n < 1 ? 4 : 2 });
export const compact = (n?: number | null) => n == null ? '—' : Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(n);
const dayFormat = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' });
export const dayKey = (time: number) => dayFormat.format(new Date(time * 1000));
export const nyTime = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
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
};
export type Ticker = {
    symbol: string;
    ticker: string;
    status: string;
    quote?: Quote;
    errors?: string[];
};
export type View = {
    type?: string;
    request_id?: number;
    symbol: string;
    timeframe: string;
    server_time: number;
    run_id: string;
    mode?: string;
    charts: Record<string, ChartData>;
    quote: Quote;
    summary: {
        adr20: number | null;
        adv20: number | null;
        samples: number;
        estimated: boolean;
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

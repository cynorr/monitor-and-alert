export type TradeUIConfig = { spread_warning_percent: number };
export async function loadTradeConfig(): Promise<TradeUIConfig> {
    const response = await fetch('/trade-ui.json');
    if (!response.ok) throw new Error('Cannot load Trade display configuration');
    const config: TradeUIConfig = await response.json();
    if (!Number.isFinite(config.spread_warning_percent) || config.spread_warning_percent < 0) throw new Error('Invalid Trade spread warning threshold');
    return config;
}

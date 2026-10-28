export async function loadTradeConfig() {
    const response = await fetch('/trade-ui.json');
    if (!response.ok)
        throw new Error('Cannot load Trade display configuration');
    const config = await response.json();
    if (!Number.isFinite(config.spread_warning_percent) || config.spread_warning_percent < 0)
        throw new Error('Invalid Trade spread warning threshold');
    return config;
}

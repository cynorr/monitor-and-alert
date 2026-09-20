# Chart layout and interactions

Updated: 2026-09-20. Approved interaction specification and maintenance reference. The product UI is English only. No localization layer.

## Layout

- Three full-height columns: Daily, Intraday, watchlist. The two charts start at equal widths; the list is narrower (38% / 38% / 24%).
- Two draggable vertical dividers resize adjacent columns. Minimum widths keep charts and the four list columns usable. Remember widths locally; double-click a divider restores the equal-chart default.
- No application header, brand, description, global instrument banner or footer. Each chart owns its symbol, OHLC, current price and ET clock.
- White floating chart cards with generous corners on a neutral background. Black section boundaries and divider handles.
- Search, period selector and its selected button, price-session tags and resize handles are pills. The list count is plain text.

## Chart settings

- Local Lightweight Charts 5.2.0. Main candlestick pane above a smaller volume pane; the built-in pane divider remains draggable.
- No horizontal or vertical grid. Teal up candles/volume (#26a69a), red down candles/volume (#ef5350).
- EMA10 blue (#2962ff), EMA20 yellow (#e4b400), SMA50 red (#e53935). Indicator calculations remain in Python.
- Daily initially shows approximately nine calendar months. Determine the initial pixel spacing from the nine-month window, then retain that spacing across symbols and column resizing. Short histories stay aligned right with blank space on the left; never fitContent to available samples. Resizing changes the number of visible candles, not candle width. User zoom changes spacing intentionally.
- Intraday defaults to 5m; controls: 5m, 15m, 30m, 1h.
- rightOffset=1, rightBarStaysOnScroll=true. Keep about one bar between the latest candle and the price axis.
- CrosshairMode.Normal with dashed horizontal and vertical lines; no magnet/snap mode.
- Native pan, zoom, price scaling, pane resizing and scrollToRealTime are used. Realtime updates preserve a historical viewport.

## Chart information

- First line: symbol, period controls and ET time. Next: OHLC of the hovered candle, falling back to the latest candle.
- Current price is prominent. Only an actual extended-session quote receives a PRE/POST/OVERNIGHT pill.
- Optional Sell/Bid and Buy/Ask prices appear below OHLC only when the data source provides them. Never derive a spread or subscribe to Depth for this UI.
- Next line: ADR20 and ADV20 (Daily-derived values on both charts), followed by compact EMA/SMA values.
- Lightweight Charts does not supply a TradingView-style instrument/OHLC header; these small DOM legends use subscribeCrosshairMove and seriesData.
- No US/USD, No Adjust, Regular, bar counts, chart-bottom information strip or Charts by TradingView footer. Delete their DOM, styling and rendering code. Data-quality sample counts needed by validation remain backend diagnostics, not chart decorations.
- Disable the native canvas logo; preserve third-party LICENSE/NOTICE and attribution on the separate static /licenses.html page. No chart branding/footer logic.

## Linked trading day

- Both charts share one selected New York trading day. Clicking a candle selects that day and reveals it in the peer chart while preserving each chart's zoom.
- A period change keeps that day selected when available in the new period. Go to latest selects the latest available trading day again.
- Hovering synchronizes the peer crosshair for the same trading day through setCrosshairPosition / clearCrosshairPosition. The mouse-driven chart remains unsnapped; peer positioning uses the corresponding candle.
- Daily-to-Intraday maps to that day's first available intraday candle, or the previously selected intraday time on the same day. Intraday-to-Daily maps to that day's Daily candle.
- Do not copy logical/time ranges directly between different periods. Use a reentrancy guard for programmatic crosshair updates.
- Linking only uses loaded history. When the peer has no bars for the selected day, clear its linked crosshair; do not invent data or initiate an unbounded historical download.

## Watchlist and status

- Right panel: search, compact Focus/Wait sections, four columns: Symbol, Last, Chg%, Ext. Rows are 26px high.
- Last is the regular price. Chg% is regular price / previous completed Daily close - 1. Use the previous trading day relative to the quote date, including after today's Daily bar is stored.
- Ext is the newest extended price only when newer than the regular quote, including next-day premarket. Unavailable values show an em dash; older extended values cannot override a newer regular quote.
- Click or ArrowUp/ArrowDown selects the ticker for both charts. Search filters locally. No list editing.
- Quiet normal state. Small Loading/Disconnected labels remain where action is needed. Required data warnings become one compact per-ticker indicator with English details on hover, not a multi-line banner. No raw exception dump in the chart.
- Simulation displays one small SIM badge so generated data cannot be confused with a live account. No extra branding bar.

## Data and simulator boundaries

- Production consumes Data HTTP snapshots and WebSocket updates. Keep request cancellation, request_id checks and reconnect snapshots.
- Simulator now supplies coherent Quote plus closed Daily/5m/15m/30m/1h history. Use the actual DataService downloader, validator and BarScheduler against an isolated temporary SQLite database.
- All periods and cumulative volume follow the same synthetic session price path. Normal count=2 requests produce newly closed bars; startup and multi-boundary recovery use full history requests.
- A simulator-owned exchange clock makes regular-session development possible on weekends; optional speed accelerates bar closure. Do not change system time or globally patch time.time.
- Production does not import simulator and never falls back to it. Simulator never reads credentials or calls Longbridge. Raw Quote WebSocket remains available for consumers.

## Maintenance and checks

UI code lives in ui/src; ui/public contains HTML/CSS, compiled JavaScript and the unchanged vendor library. Rebuild with npm run build after TypeScript edits. Update this document when layout or interaction behavior changes.

Validate drag resizing, short-history spacing, chart-day linking, free crosshair, rapid ticker/period changes, quiet warnings and reconnect. Simulator regression must cross 5m and larger boundaries and session rollover without missing/invalid bars or cumulative-volume mismatch. Offline success is not broker live evidence.

References: [time-scale options](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/TimeScaleOptions), [crosshair synchronization](https://tradingview.github.io/lightweight-charts/tutorials/how_to/set-crosshair-position), [crosshair options](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/CrosshairOptions).

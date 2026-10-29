# Chart UI

Updated: 2026-10-22. This is the only current specification for general chart appearance and interaction. Alert-specific requirements are maintained only in [alert.md](alert.md) and are implemented. [ui.md](ui.md) is the UI entry point; panel widths are defined in [List UI / 宽度与视觉](ui.md#宽度与视觉). Longbridge data requirements are maintained only in [longbridge-data.md](longbridge-data.md); indicator calculations remain in [behavior.md](behavior.md) and [development.md](development.md). The product UI is English only.

## Implementation principle

1. **对 Chart 的调整优先使用 TradingView Lightweight Charts 的 built-in 参数和公开 API。为兼容后续图表库更新，切勿侵入式修改库源码。** 保持 vendor 文件原样，不修改库原型、不调用私有接口、不依赖内部 DOM 结构；库未提供的文字显示使用少量应用层 DOM，通过公开事件和数据更新，不改动库的渲染、坐标或交互实现。

当前蜡烛间距使用内置 [timeScale.barSpacing](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/HorzScaleOptions#barspacing)，主图/成交量比例使用公开 [pane.setStretchFactor](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/IPaneApi#setstretchfactor)。无 grid、右侧空白、参考线、原生缩放和分界拖动均由库的选项/API 控制。右上角 Volume/OHLC 文字属于应用层显示，通过 [subscribeCrosshairMove](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/IChartApi#subscribecrosshairmove) 的 seriesData 和公开 pane 尺寸更新、定位；双图联动使用公开 setCrosshairPosition / clearCrosshairPosition，缺少对应时间时使用公开 createPriceLine 显示独立水平线，不修改库内部实现。

## Layout and shared defaults

- Monitor has Daily and Intraday charts; Scan has Daily only. Use local Lightweight Charts 5.2.0, with a main candlestick pane above a smaller volume pane. The native pane divider remains draggable.
- Daily owns the enlarged symbol; Intraday owns the equally styled headline price and ET clock. Both charts show OHLC. Chart cards follow the shared layout in [ui.md](ui.md#layout).
- Default candle spacing is identical across Scan Daily, Monitor Daily and all Intraday periods. The actual number of visible bars depends on the manually configured spacing and panel width; neither mode enforces a separate fixed month range. The 2px reference spacing shows approximately 12 calendar months in a typical 1280px Scan window; a larger manual value shows fewer months.
- Keep spacing across ticker changes and panel resizing. Short histories stay aligned right with blank space on the left; never use fitContent to fill the panel with the available samples. Resizing changes the number of visible candles, not candle width. Each chart retains intentional user zoom independently.
- The two manual defaults are centralized in [ui/src/chart-settings.ts](../ui/src/chart-settings.ts). Change them there, run `npm run build --prefix ui`, then refresh the page. Do not add a settings screen or saved per-symbol defaults.

| Parameter | Current manual value | Effect |
| --- | --- | --- |
| `BAR_SPACING` | 5px | Passed directly to built-in timeScale.barSpacing; increasing it makes candles wider and shows fewer bars in the same width |
| `VOLUME_PANE_RATIO` | 0.28 | Volume occupies 28% of the chart area by default (main 0.72 / volume 0.28); increasing it makes the volume pane taller and moves the divider upward |

The default volume divider is moderately higher than before; it remains adjustable with the native pane drag handle.

## Colors, margins and reference lines

- No horizontal or vertical grid. Teal up candles/volume **#26a69a**, red down candles/volume **#ef5350**.
- EMA10 blue **#2962ff**, EMA20 yellow **#e4b400**, Daily SMA50 / Intraday SMA65 red **#e53935**. Indicator calculations remain in Python.
- Black chart boundaries and a gray main/volume divider. Hide price-scale vertical borders; retain the main price scale's 7% top and 5% bottom margins.
- `rightOffset=1` and `rightBarStaysOnScroll=true`: keep about one blank bar between the latest candle and the right price axis.
- Hide the persistent last-price horizontal line on candles, moving averages and volume. The reference lines are the freely moving dashed horizontal/vertical crosshair and its native axis labels; do not add a fixed price reference line.
- All dashed chart lines use the same thin segment pattern: **1px width, 6px segment / 6px gap**, with flat ends. Use built-in `LineStyle.LargeDashed` for horizontal/vertical crosshairs and the matching pattern for Alert primitives. Apply this to Scan, Monitor, all periods, main and volume panes; do not use dots or short dotted-looking dashes.
- User-created Alert lines are defined separately in [alert.md](alert.md); saved thresholds do not enable the last-price reference line above.
- Latest-day Scan Daily shows the backend-selected `quote.latest` as a right-axis numeric price label. Monitor Daily and Intraday show the same label when the latest quote comes from an extended session; an Intraday/Regular latest quote keeps Monitor's native live-candle label. Color follows the quote's `trade_session`: Pre uses EMA20 yellow **#e4b400** with dark text, Post uses EMA10 blue **#2962ff**, and Overnight uses black **#000000**. Scan Regular uses teal **#26a69a** or red **#ef5350** against Longbridge's previous close (teal when unavailable). All except Pre use white text. Keep the last received quote when no newer quote exists, including across session boundaries, holidays and weekends; a retained Post quote stays blue during overnight hours. Do not infer source from the clock or add session/staleness text. Reuse one public createPriceLine with lineVisible=false and axisLabelVisible=true; hide the native candle-price label while present and restore it when absent. Clear on missing quotes, symbol/mode/date reset or historical Scan. Automatic scaling includes the price using public autoscaleInfoProvider; native manual scaling remains. This price-only label never changes candles, volume or indicators. Quote selection belongs to [Longbridge data](longbridge-data.md#最新报价与-overnight).
- Use `CrosshairMode.Normal` in both Monitor charts and Scan; no magnet or price snap. The linked peer uses the mouse-driven price or volume value, never candle close or the histogram bar's value.
- Chart branding and attribution follow [Logo / Icon](ui.md#logo--icon).

## Headers and information

- Chart headers are **120px** high with one bottom border. Daily shows the symbol at top-left, with no Daily tag. Optional company name sits immediately to its right, sharing the text baseline, in smaller **15px** muted text. The next **22px** row shows the concise classification at **11px**, matching the EMA/SMA legend size; ADR20/ADV20 move down one row. Optional Daily Sell/Bid and Buy/Ask pills share the metrics row to preserve the header height. Category wording and deduplication are maintained only in Additional Info.
- Earnings text sits immediately to the left of the Daily Go to latest circular button, with **12px** dark **#293341** text and **26px** line height, matching the shared List ET clock. Company name, classification and earnings stay on one line with ellipsis; earnings truncate the report label first and preserve the day countdown. Tooltips provide full text, dates and source timestamps. Missing values and cleared selections hide the corresponding text.
- Scan, Monitor and Holdings share the independent current `.US` Additional Info lookup. Historical Scan does not display historical company metadata. Data sources, Python name cleanup, optionality, refresh and earnings wording/date selection are maintained only in [Additional Info](additional-info.md); selecting or reading a chart never fetches it.
- Intraday shows `quote.latest` at top-left with the same **28px** size, weight and color as the Daily symbol. Go to latest stays at the toolbar's far right; the ET clock is now in the shared [List header](ui.md#宽度与视觉). No session or Last Post pill is shown. Period controls sit on the next row. Optional `Market Cap` sits below these controls, at **11px** in black **#000**, matching the EMA/SMA legend size. Its compact value omits the dollar sign (for example `Market Cap 1.5B`). Intraday Sell/Bid and Buy/Ask pills share this row; there is no Daily market-cap label.
- Only Daily displays ADR20 and ADV20, using the same formulas in both modes: recent up to 20 closed records, mean `(H-L)/L×100` and mean `close×volume`. Available Sell/Bid and Buy/Ask quotes remain optional.
- Chart legends, the List Tag/Filter labels and List column titles share a **4px** label-box-to-rule gap (`--label-rule-gap`); their small text uses a **16px** line height. Header boundaries keep their fixed height.
- EMA/SMA legends pair colored line swatches with concise labels: EMA 10, EMA 20, and SMA 50 for Daily or SMA 65 for Intraday. They do not show current indicator values; unavailable indicator lines and legends remain absent.
- OHLC sits immediately below the aligned black horizontal border on each chart, at **15px**; ADR/ADV also use **15px**. OHLC fields stay together and wrap on narrow panels. Native chart axes use **12px**. Shared CSS font variables keep other small labels at **11px**, list values at **12px** and body text at **13px**.
- Range is `(H-L)/L × 100%`. H/L values and Range value are black; other labels and values retain their original color.
- The volume readout, its five-day comparison and hover behavior follow [Volume comparison](#volume-comparison).
- Active OHLCV comes directly from the corresponding SDK candle; official closed bars replace provisional values. Data handling is maintained in [longbridge-data.md](longbridge-data.md).
- Lightweight Charts does not supply a TradingView-style instrument/OHLC header; the small DOM legends use subscribeCrosshairMove and seriesData.
- Headers omit market/currency, adjustment/session metadata, bar counts and branding/footer strips. Validation sample counts remain backend diagnostics.

## Volume comparison

- Every chart's volume pane shows **`Vol 1.38M · 5D Avg 125%`** at its fixed top-right position. `Vol` and the comparison always refer to the same candle. The position follows native pane resizing. This applies to Monitor Daily/Intraday and Scan Daily.
- Percentage = candle volume / mean reference volume × 100. **100% means the historical average**, 150% means 1.5 times that average. Display only the integer portion, truncating rather than rounding (125.9% → 125%); retain full precision in calculation. Use exactly `5D Avg`.
- Anchor the reference window to the displayed candle's New York trading date: use the **five exchange trading sessions strictly before that date**, excluding the displayed session. Historical hover uses that historical date, not today's date.
- Daily uses the available Daily volumes within those sessions. Intraday uses only the selected period and the same Regular time slot, identified by its New York start time. For example, the second 15m candle compares 09:45–10:00 ET across the prior five sessions. Missing candles do not shift later slots; DST does not change the local-time match.
- Open and closed candles use the same calculation. The current open volume is compared with historical completed candles for the full corresponding window. Do not extrapolate, normalize by elapsed time or use smaller periods to assemble the reference.
- Use the available matching samples within the fixed five-session window; do not count absence as zero or reach farther back to fill five samples. Valid zero volumes count as samples. Shortened session-final candles keep their time slot; absent afternoon candles on early-close days are skipped. No samples or a zero historical average produces `5D Avg —`.
- Hovering candles or volume, including a linked crosshair, shows that candle's Vol and comparison together, matching its OHLC. Clearing or leaving hover restores the last candle, including the current Regular open candle. Live updates refresh a hovered open candle, and preserve a hovered closed candle's readout.
- The tooltip identifies current Daily cumulative volume, current Intraday candle volume or historical candle volume, and includes the historical mean, actual sample count and `100% = average`. Missing volume remains unavailable.
- Calculate in Python with the shared trading calendar and existing history cache; send `volume_comparison: {average, samples, percent}` alongside each displayed row. The frontend formats and selects the corresponding result. Each source uses its own historical data; no new requests, subscriptions, persistence or cross-source comparisons are introduced.

图表上述5D Avg继续使用原有完整窗口比较；独立 [Intraday State](intraday-state.md) 的列表CumVol/LocalVol使用同进度插值，不改变图表成交量口径或vendor。

## Mouse, zoom and periods

- Use native pan, zoom, price scaling, pane resizing and scrollToRealTime. Realtime updates preserve a historical viewport.
- At a closed boundary, keep the elapsed SDK candle visible and append the next SDK candle when available; official history corrects closed values when it arrives. Refresh keeps existing data until replacement is ready. Routine tail replacement/append uses public series updates without clearing candles, rebuilding all history or resetting the viewport. Daily does not wait for a 5m refresh.
- On page load, Intraday defaults by elapsed time since 09:30 America/New_York: before open and `[0,5)` minutes → 5m, `[5,15)` → 15m, `[15,30)` → 30m, and 30 minutes onward → 1h. Manual choices remain in effect across ticker changes; 2h is manual only. Controls: **5m, 15m, 30m, 1h, 2h**.
- `↦` means Go to latest: return to the latest available trading day while retaining the chart's zoom. Period changes preserve the selected day when that day exists in the new period.

## Linked trading day

- Both charts share one selected New York trading day. Clicking a candle selects that day and reveals it in the peer chart while preserving each chart's zoom.
- Hover synchronizes time and the mouse-driven price or volume value. Convert the source pointer's pane-local y with the corresponding series' coordinateToPrice, then pass that value to the peer's main or volume series. Candle/volume data select the matching day and OHLC/Vol readout only; they never supply the crosshair's vertical value.
- Judge the horizontal price/volume line and vertical time line independently in each chart. A missing or offscreen peer time does not hide an in-range horizontal line; an offscreen price/volume value does not hide an available, visible time line. Show each component wherever its own coordinate is within that chart's visible range, with no snap, forced pan or scale change. When only price/volume can be located, show the horizontal line and axis label without a vertical line or invented time label; keep the latest OHLC/Vol readout when there is no matching bar.
- Daily-to-Intraday maps to that day's first available intraday candle, or the previously selected intraday time on the same day. Intraday-to-Daily maps to that day's Daily candle.
- Do not copy logical/time ranges directly between different periods. Use a reentrancy guard for programmatic crosshair updates.
- Linking only uses loaded history. When the peer has no bars for the selected day, omit its vertical time line and retain any in-range horizontal price/volume line; do not invent data or initiate historical downloads. Leaving or clearing hover removes both linked components.

## Data boundaries

- Keep mode, request_id, source and socket identity checks. Mode/date changes reset chart context; backend run_id changes force full history. Indicators are calculated only in Python; reading or selecting charts does not trigger downloads.
- All six Monitor periods use their own SDK candles and authoritative closed-history overlay.
- Each period has its own loaded window. Insufficient SMA65 history leaves the line absent. Longbridge cache freshness and source boundaries follow [longbridge-data.md](longbridge-data.md).
- Scan uses completed local Daily bars without an active candle or Intraday data.

## Alert interaction

Alert 在 Scan/Monitor 的创建、选择、改价、删除与跨图同步只在 [alert.md](alert.md#图表交互) 维护；图形定义见 [Logo / Icon](ui.md#alert-图形)。Alert 使用当前图表鼠标水平线对应价格，不改变两个来源的数据口径。实现为 ui/src/alerts.ts 中的公开 series primitive、pane 坐标与命中检测，保持 vendor 原样。

## Chart status

- Live Monitor: show a muted Refreshing label while any previously loaded period awaits a full refresh; keep existing charts and live prices visible. Otherwise Loading until Daily + 5m complete; yellow Ready while only those are complete; blue Ready when all six official periods complete, hidden after three seconds. These labels describe history readiness and never gate realtime data. Routine closed updates do not restart the timer.
- Exhausted history retries and connection failures use one exclamation icon with reason on hover, retaining existing charts. Finite positive OHLC range contradictions do not produce UI warnings or retries; display official values unchanged.
- Scan uses its local Daily date/status rather than live six-period readiness. Scan's date, preparation status and refresh controls follow [List UI](ui.md#scan-日期与准备状态).

## Trade mode

Trade shares Monitor Daily/Intraday and the same public chart APIs. Its aligned chart/List header height is 192px to fit the ticket at Intraday bottom-right; Monitor/Scan stay at 120px. The Trade Intraday minimum width is 540px; panel sizing remains in layout.ts. Trade line appearance is defined only in [UI / Trade 图形](ui.md#trade-图形), and draft/Send behavior only in [Schwab Trade](schwab-trade.md). Latest price, OHLC, indicators and volume retain their existing Longbridge meaning.

The ticket spans the right-hand header space and ends at the shared label-to-rule gap. Its fixed rows, from top downward, are the quote/feedback area (66px), quantity (34px), total/risk (34px), and actions (35px), with 6px gaps. Quantity moves up 4px and total/risk moves up 2px; the buttons remain fixed. Go to latest is restored to the far right of the top toolbar. Quotes sit immediately to its left, with an 8px gap; their right edge is 34px left of the quantity track's right edge (26px button + 8px gap). The clock is in the shared List header. Period controls keep their original position. The quantity track defines the lower content bounds: total/risk starts at its left edge; the Buy/Sell capsule aligns optically by the start of its top horizontal segment, rather than its leftmost curve point. With 35px capsule height, its curved tip extends 17.5px to the left of the track. The Send capsule ends at the track's right edge. The bare quantity value sits directly above the track's left endpoint, without a Qty label or input frame. Auto sits immediately left of Send; the commit controls and Buy/Sell have at least 24px separation. The track retains its previous length: the ticket's content width is min(64% of the header − 74px, 306px), with a 12px right inset. The grid column has a zero minimum so wider quotes can extend left without resizing the quantity track or actions.

Browse hides quantity/preview content with visibility while reserving these rows; activating Buy/Sell or editing a real Stop never moves the quote row or actions. The spread percentage is the primary 25px value with a 34px line height, vertically centered with the bold Intraday price. It uses one block-level text box starting 10px below the header top, without a nested inline wrapper or fractional vertical offset. To its right, Ask sits above Bid in one 28px-high column, each using normal-weight 12px text and 14px line height. The 11px gray absolute spread uses 14px line height beside the lower Bid, aligned to the stacked column's bottom. Gaps between the three groups remain 8px. Feedback sits beneath the quotes, 42px below the header top, with at most two visible 12px text lines; it does not move the quotes or quantity row. Total uses 28px normal weight and integer formatting. Risk shares the total's text baseline, uses the 15px OHLC size, a vertical separator, two decimal places for its percentage and an integer amount. The quantity value uses the 12px row size. An 8px top inset inside the existing 34px quantity row leaves room above the rail for the number; no other row moves. The ruler retains the straight black 1px track (0.5 CSS px on Retina) and 4×9px thumb. Only the labeled major ticks remain, 3px tall with 9px numeric labels; remove all intervening minor ticks. Tick numbers and density follow actual track width without overlapping and always include zero and the maximum. Quantity uses the native range control with its ordinary pointer at all times. Do not capture range pointers or introduce custom pointer-visibility state; mouse and trackpad dragging remain browser-owned. The browser's :active state freezes the quantity scale while dragging; input events update quantity and preview. Buy/Sell headings use 14px text at weight 700; lowercase stop/market retain 11px text at weight 400. The lower labels align toward their shared boundary, each 6px from its center. The Buy heading occupies the upper 21px and centers in both directions; the mode labels occupy the lower 14px, giving a 60:40 split. Send keeps its 30px outer height: removing the 3px wrapper padding and adding it to the button's own padding fills the former border-like gutter without moving the button. Intraday Ready is omitted in Trade; loading/errors remain above the left legend so buttons do not obscure them. Spread threshold behavior/configuration belongs only to [Schwab Trade](schwab-trade.md).

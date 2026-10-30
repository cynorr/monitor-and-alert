# Chart UI

Updated: 2026-10-30. This is the only current specification for general chart appearance and interaction. Alert-specific requirements are maintained only in [alert.md](alert.md) and are implemented. [ui.md](ui.md) is the UI entry point; panel widths are defined in [List UI / 宽度与视觉](ui.md#宽度与视觉). Longbridge data requirements are maintained only in [longbridge-data.md](longbridge-data.md); indicator calculations remain in [behavior.md](behavior.md) and [development.md](development.md). The product UI is English only.

## Implementation principle

1. **对 Chart 的调整优先使用 TradingView Lightweight Charts 的 built-in 参数和公开 API。为兼容后续图表库更新，切勿侵入式修改库源码。** 保持 vendor 文件原样，不修改库原型、不调用私有接口、不依赖内部 DOM 结构；库未提供的文字显示使用少量应用层 DOM，通过公开事件和数据更新，不改动库的渲染、坐标或交互实现。

当前蜡烛间距使用内置 [timeScale.barSpacing](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/HorzScaleOptions#barspacing)，主图/成交量比例使用公开 [pane.setStretchFactor](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/IPaneApi#setstretchfactor)。无 grid、右侧空白、参考线、原生缩放和分界拖动均由库的选项/API 控制。右上角 Volume/OHLC 文字属于应用层显示，通过 [subscribeCrosshairMove](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/IChartApi#subscribecrosshairmove) 的 seriesData 和公开 pane 尺寸更新、定位；双图联动使用公开 setCrosshairPosition / clearCrosshairPosition，缺少对应时间时使用公开 createPriceLine 显示独立水平线，不修改库内部实现。

## Layout and shared defaults

- Monitor has Daily and Intraday charts; Scan has Daily only. Use local Lightweight Charts 5.2.0, with a main candlestick pane above a smaller turnover pane. The native pane divider remains draggable.
- Daily owns the enlarged symbol; Intraday owns the equally styled headline price and ET clock. Both charts show OHLC. Chart cards follow the shared layout in [ui.md](ui.md#layout).
- Default candle spacing is identical across Scan Daily, Monitor Daily and all Intraday periods. Outside the temporary Daily overview, visible history depends on spacing and panel width; neither mode enforces a separate fixed month range.
- Keep spacing across ticker changes, mode changes and panel resizing. Short histories stay aligned right with blank space on the left. Resizing changes the number of visible candles, not candle width. Daily uses the coupled scale and reset below; Intraday retains its independent native zoom.
- Manual defaults are centralized in [ui/src/chart-settings.ts](../ui/src/chart-settings.ts). Change them there, run `npm run build --prefix ui`, then refresh the page. Do not add a settings screen or saved per-symbol defaults.

| Parameter | Current manual value | Effect |
| --- | --- | --- |
| `BAR_SPACING` | 5px | Passed directly to built-in timeScale.barSpacing; increasing it makes candles wider and shows fewer bars in the same width |
| `DAILY_ANCHOR_BARS` | 5 | Completed Daily closes used for the median anchor |
| `DAILY_ANCHOR_POSITION` | 2/3 | Anchor position measured upward from the bottom of the main price pane |
| `DAILY_PERCENT_BAR_SPACING` | 1 | One percentage point relative to the anchor occupies one candle-center spacing |
| `VOLUME_PANE_RATIO` | 0.28 | Volume occupies 28% of the chart area by default (main 0.72 / volume 0.28); increasing it makes the volume pane taller and moves the divider upward |

The default volume divider is moderately higher than before; it remains adjustable with the native pane drag handle.

## Daily setup scale

### Background and purpose

Swing scanning prioritizes clear recent setups, especially the latest six months, and fast visual comparison across symbols. Fitting every visible high and low to the pane makes an old high or one extreme wick dominate the scale: JBDI's 2026-10-13 spike and the older highs in YMAT/BNC illustrate the problem. It can also make BKYI's roughly 20% ADR and DXC's roughly 5% ADR appear similarly sized. The default Daily view therefore gives recent setups a stable location and a shared percentage-to-candle-spacing ratio. Full historical visibility has lower priority and is available on demand.

### Anchor and linear scale

- Applies to Scan, Monitor and Trade Daily only. Intraday retains its existing native autoscale and independent price scaling. All source data, OHLC, indicators and their calculations remain unchanged.
- The anchor `A` is the median of the latest five **completed** Daily closes, using the available completed records for shorter histories. Even sample counts use the mean of the two middle closes. The active SDK candle and quotes never contribute. No completed records means there is no fixed anchor yet.
- Place `A` at two-thirds of the main price pane's height measured upward from its bottom, excluding the volume pane and axes. New completed bars or official corrections update the anchor; live active-candle/quote changes, hovering and horizontal panning do not.
- Use one **linear** price scale. With candle-center spacing `b`, vertical displacement from the anchor is `b × DAILY_PERCENT_BAR_SPACING × 100 × (price / A − 1)`. The first version uses `1% = 1 spacing`: 5px at default spacing. Percentages refer to `A`, not each individual candle's price. Axis labels remain actual prices. The resulting visible interval can extend below zero when zoomed far out; that coordinate space is blank and does not invent negative-price candles.
- Only this coordinate policy determines the normal Daily price range. Old highs/lows, wicks, moving averages, quotes, Alert and Trade lines do not enlarge it. Price and overlay coordinates stay shared; volume continues to autoscale independently. There are no per-symbol scale gears or automatic scale changes.
- Historical Scan uses completed data through its selected date. Viewing or moving the viewport does not download history, change the selected date or modify the dataset.

### Coupled zoom and Reset

- Retain native horizontal zoom and horizontal panning. A change in candle spacing changes vertical percentage distances by the same factor, preserving shape and angle. Disable independent Daily price-axis stretching, vertical panning and native axis double-click resets. Increasing pane height or window width changes coverage, not the percentage-to-spacing ratio.
- Keep the current Daily spacing across symbols and modes. No saved per-symbol zoom or new settings UI.
- Daily `↦` is **Reset view & go to latest**: leave overview, restore default spacing and the matching vertical ratio, restore the anchor position, and immediately return to the newest available bar with one-bar right offset. Historical Scan stays on the selected date. This action does not fetch or refresh data. Intraday `↦` restores default spacing and native price autoscale, then returns to latest; ordinary Intraday zoom, price-axis scaling, panning and margins remain unchanged.

### Hold F for one-year overview

- Hold unmodified **F** outside text editing/IME to temporarily fit the latest calendar year through the current chart endpoint; short histories use available data. The anchor is not recomputed from the overview. Release F to restore the exact prior logical viewport and spacing, with current data retained.
- The overview is read-only: no chart zoom/pan, Alert creation/editing or Trade-line dragging. Hover/OHLC inspection remains available. Do not enter during an active pointer drag. Reset, symbol/mode/date changes, window blur or page hiding end the preview; releasing F afterward must not restore an old context. Repeated keydown does not resnapshot the view.
- Full view uses native autoscale with the standard 7% top / 5% bottom margins. Its scale is only for inspecting history, not cross-symbol shape comparison.

### Edge clipping cues

- In the normal Daily view, draw a 2 CSS-pixel neutral `palette.tagNeutral` strip on the top/bottom edge at each clipped candle's X position. Use one candle spacing for its width, so adjacent strips merge without stacking. A fully offscreen candle still keeps its time slot. Hide cues during overview.
- Cues indicate offscreen prices only, not validated resistance or supply. Keep official OHLC unchanged and available to hover. Draw with a public series primitive and public time/price coordinates; do not alter candle rendering or vendor internals.

## Colors, margins and reference lines

- No horizontal or vertical grid. Teal up candles/volume **#26a69a**, red down candles/volume **#ef5350**.
- EMA10 blue **#2962ff**, EMA20 yellow **#e4b400**, Daily SMA50 / Intraday SMA65 red **#e53935**. Indicator calculations remain in Python.
- Black chart boundaries and a gray main/volume divider. Hide price-scale vertical borders. Intraday and Daily overview use 7% top / 5% bottom margins; normal Daily uses the exact anchor and scale above without extra scale margins.
- `rightOffset=1` and `rightBarStaysOnScroll=true`: keep about one blank bar between the latest candle and the right price axis.
- Hide the persistent last-price horizontal line on candles, moving averages and volume. The reference lines are the freely moving dashed horizontal/vertical crosshair and its native axis labels; do not add a fixed price reference line.
- All dashed chart lines use the same thin segment pattern: **1px width, 6px segment / 6px gap**, with flat ends. Use built-in `LineStyle.LargeDashed` for horizontal/vertical crosshairs and the matching pattern for Alert primitives. Apply this to Scan, Monitor, all periods, main and volume panes; do not use dots or short dotted-looking dashes.
- User-created Alert lines are defined separately in [alert.md](alert.md); saved thresholds do not enable the last-price reference line above.
- Latest-day Scan Daily shows the backend-selected `quote.latest` as a right-axis numeric price label. Monitor Daily and Intraday show the same label when the latest quote comes from an extended session; an Intraday/Regular latest quote keeps Monitor's native live-candle label. Color follows the quote's `trade_session`: Pre uses EMA20 yellow **#e4b400** with dark text, Post uses EMA10 blue **#2962ff**, and Overnight uses black **#000000**. Scan Regular uses teal **#26a69a** or red **#ef5350** against Longbridge's previous close (teal when unavailable). All except Pre use white text. Keep the last received quote when no newer quote exists, including across session boundaries, holidays and weekends; a retained Post quote stays blue during overnight hours. Do not infer source from the clock or add session/staleness text. Reuse one public createPriceLine with lineVisible=false and axisLabelVisible=true; hide the native candle-price label while present and restore it when absent. Clear on missing quotes, symbol/mode/date reset or historical Scan. Intraday autoscale includes this price using public autoscaleInfoProvider and retains native manual scaling. Normal Daily follows the fixed setup scale above, so this label does not enlarge its range. This price-only label never changes candles, volume or indicators. Quote selection belongs to [Longbridge data](longbridge-data.md#最新报价与-overnight).
- Use `CrosshairMode.Normal` in both Monitor charts and Scan; no magnet or price snap. The linked peer uses the mouse-driven price or volume value, never candle close or the histogram bar's value.
- Show a small crosshair pointer only during ordinary inspection in a plot with visible long crosshair guides. Leaving the plot, hiding guides or having no data removes it. Buttons, axes, pane dividers and editable Alert/Trade lines keep their own action cursors; a linked peer does not change the pointer in another surface. Use the application host's inherited cursor, so native/primitive cursor overrides retain priority; no vendor or internal DOM changes.
- Chart branding and attribution follow [Logo / Icon](ui.md#logo--icon).

## Headers and information

- Chart headers are **120px** high with one bottom border. Daily shows the symbol at top-left, with no Daily tag. Optional company name sits immediately to its right, sharing the text baseline, in smaller **15px** muted text. The next **22px** row shows the concise classification at **11px**, matching the EMA/SMA legend size; ADR20/ADV20 move down one row. Optional Daily Sell/Bid and Buy/Ask pills share the metrics row to preserve the header height. Category wording and deduplication are maintained only in Additional Info.
- Earnings text sits immediately to the left of the Daily Reset view & go to latest circular button, with **12px** dark **#293341** text and **26px** line height, matching the shared List ET clock. Company name, classification and earnings stay on one line with ellipsis; earnings truncate the report label first and preserve the day countdown. Tooltips provide full text, dates and source timestamps. Missing values and cleared selections hide the corresponding text.
- Scan, Monitor and Holdings share the independent current `.US` Additional Info lookup. Historical Scan does not display historical company metadata. Data sources, Python name cleanup, optionality, refresh and earnings wording/date selection are maintained only in [Additional Info](additional-info.md); selecting or reading a chart never fetches it.
- Intraday shows `quote.latest` at top-left with the same **28px** size, weight and color as the Daily symbol. Reset view & go to latest stays at the toolbar's far right; the ET clock is now in the shared [List header](ui.md#宽度与视觉). No session or Last Post pill is shown. Period controls sit on the next row. Optional `Market Cap` sits below these controls, at **11px** in black **#000**, matching the EMA/SMA legend size. Its compact value omits the dollar sign (for example `Market Cap 1.5B`). Intraday Sell/Bid and Buy/Ask pills share this row; there is no Daily market-cap label.
- Only Daily displays ADR20 and ADV20, using the same formulas in both modes: recent up to 20 completed records, mean `(H-L)/L×100` and mean `turnover`. Missing turnover within that window leaves ADV20 unavailable; do not substitute close×volume or silently skip missing values. Available Sell/Bid and Buy/Ask quotes remain optional.
- Chart legends, the List Tag/Filter labels and List column titles share a **4px** label-box-to-rule gap (`--label-rule-gap`); their small text uses a **16px** line height. Header boundaries keep their fixed height.
- EMA/SMA legends pair colored line swatches with concise labels: EMA 10, EMA 20, and SMA 50 for Daily or SMA 65 for Intraday. They do not show current indicator values; unavailable indicator lines and legends remain absent.
- OHLC sits immediately below the aligned black horizontal border on each chart, at **15px**; ADR/ADV also use **15px**. OHLC fields stay together and wrap on narrow panels. Native chart axes use **12px**. Shared CSS font variables keep other small labels at **11px**, list values at **12px** and body text at **13px**.
- Range is `(H-L)/L × 100%`. H/L values and Range value are black; other labels and values retain their original color.
- The turnover readout, its five-day comparison and hover behavior follow [Turnover comparison](#turnover-comparison).
- Active OHLCV comes directly from the corresponding SDK candle; official closed bars replace provisional values. Data handling is maintained in [longbridge-data.md](longbridge-data.md).
- Lightweight Charts does not supply a TradingView-style instrument/OHLC header; the small DOM legends use subscribeCrosshairMove and seriesData.
- Headers omit market/currency, adjustment/session metadata, bar counts and branding/footer strips. Validation sample counts remain backend diagnostics.

## Turnover comparison

Purpose: compare the amount traded, rather than the number of shares, while preserving the existing candle and reference-window semantics. Price changes contribute to turnover ratios; they are not interchangeable with share-volume ratios.

- All three modes use candle `turnover` for the lower histogram, with dollar axis/crosshair labels and **`Dollar Vol $1.38M · 5D Avg 125%`** at the fixed top-right. Colors and pane sizing stay unchanged. Longbridge supplies official historical/realtime candle turnover; Scan consumes the already stored same-bar VWAP×volume amount. Do not multiply by the latest price or mix suppliers.
- Missing turnover is a gap and `—`, never zero or a close×volume fallback. Keep raw `volume`; tooltip shows `Shares` and distinguishes current Daily cumulative turnover, current Intraday turnover and historical turnover.
- Percentage = candle turnover / mean reference turnover × 100. 100% means average; truncate display to integer percent without rounding. Both numerator and denominator use money.
- Use the five exchange sessions strictly before the candle's New York date. Daily compares Daily amounts; Intraday compares the selected period and same Regular start-time slot. Historical hover uses its own date. Do not shift missing slots, backfill from earlier dates or combine periods.
- Open amounts compare with historical completed amounts for the whole corresponding candle, without elapsed-time normalization. Valid zero amounts count as samples; missing amounts and unavailable early-close slots do not. No samples or a zero mean yields `5D Avg —`.
- Hover, linked hover and live updates keep turnover, comparison and OHLC on the same candle; leaving restores the latest readout. The tooltip includes the reference dollar mean, sample count and `100% = average turnover`.
- Python sends `turnover_comparison: {average, samples, percent}` beside each row through the existing cache and API. No new download, subscription or persistence is required. Official corrections invalidate the same calculation cache.
- [Intraday State](intraday-state.md) CumVol/LocalVol, quantity levels, ranking and existing alerts continue to use share volume and their current same-progress interpolation. Chart/ADV20 changes do not migrate those rules.

## Mouse, zoom and periods

- Use native horizontal pan/zoom and pane resizing; Daily couples its vertical scale as specified above, while Intraday retains native price scaling. Realtime updates preserve a historical viewport.
- At a closed boundary, keep the elapsed SDK candle visible and append the next SDK candle when available; official history corrects closed values when it arrives. Refresh keeps existing data until replacement is ready. Routine tail replacement/append uses public series updates without clearing candles, rebuilding all history or resetting the viewport. Daily does not wait for a 5m refresh.
- On page load, Intraday defaults by elapsed time since 09:30 America/New_York: before open and `[0,5)` minutes → 5m, `[5,15)` → 15m, `[15,30)` → 30m, and 30 minutes onward → 1h. Manual choices remain in effect across ticker changes; 2h is manual only. Controls: **5m, 15m, 30m, 1h, 2h**.
- Both `↦` buttons mean **Reset view & go to latest**, and each button resets its own chart. Unmodified **R** resets every visible chart, regardless of pointer position: Daily only in Scan, both in Monitor/Trade. Ignore repeats, text editing/IME and modified shortcuts. During F preview, R exits preview and resets; releasing F must not restore the old view. No download or date change. Period changes preserve the selected day when available.
- Reset changes only its target chart's viewport; it does not select a candle or invoke trading-day linking. A button must leave the peer chart's zoom and position unchanged. In Trade, the Intraday reset button sits above the ticket's transparent header area so it remains clickable without moving any controls.

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

The ticket spans the right-hand header space and ends at the shared label-to-rule gap. Only quantity (34px), total/risk (34px), and actions (35px) participate in its bottom-aligned grid. Its row-gap is currently 12px and affects only these three rows: increasing the gap by d moves total/risk up by d and quantity up by 2d, while the actions stay anchored above the header rule. Quotes and feedback are independently positioned outside this grid flow; changing the gap does not move them. Reset view & go to latest is at the far right of the top toolbar. Quotes sit immediately to its left, with an 8px gap; their right edge is 34px left of the ticket's right edge (26px button + 8px gap). The clock is in the shared List header. Period controls keep their original position. The quantity track defines the lower content bounds: total/risk starts at its left edge; the Buy/Sell capsule retains its existing width and horizontal position, with its leftmost tip 17.5px left of the track. Buy/Sell and Send are both 30px high and centered within the unchanged 35px actions row. The Send capsule stays fixed. Quantity, total/risk and the Buy/Sell capsule translate 15px left together without changing their widths or vertical positions. This uses the radius of the 30px-high Send capsule: the track's right endpoint aligns with the end of Send's straight top edge, excluding its right semicircle. Auto, Send, quotes and feedback retain their positions. The bare quantity value sits directly above the track's left endpoint, without a Qty label or input frame. Auto sits immediately left of Send; the commit controls and Buy/Sell have at least 24px separation. The track retains its previous length: the ticket's content width is min(64% of the header − 74px, 306px), with a 12px right inset. The grid column has a zero minimum so wider quotes can extend left without resizing the quantity track or actions.

Browse hides quantity/preview content with visibility while reserving these rows; activating Buy/Sell or editing a real Stop never moves the quote row or actions. The spread percentage is the primary 24px value with a 34px line height, vertically centered with the bold Intraday price. It uses one block-level text box starting 10px below the header top, without a nested inline wrapper or fractional vertical offset. To its right, Ask sits above Bid in one 28px-high column, each using normal-weight 12px text and 14px line height. The 11px gray absolute spread uses 14px line height beside the lower Bid, aligned to the stacked column's bottom. Gaps between the three groups remain 8px. Feedback sits beneath the quotes, 42px below the header top, with at most two visible 12px text lines; it does not move the quotes or quantity row. Total uses 28px normal weight and integer formatting. Risk shares the total's text baseline, uses the 15px OHLC size, a vertical separator, two decimal places for its percentage and an integer amount. The quantity value uses the 12px row size. An 8px top inset inside the existing 34px quantity row leaves room above the rail for the number; no other row moves. The ruler retains the straight black 1px track (0.5 CSS px on Retina) and 4×9px thumb. Only the labeled major ticks remain, 3px tall with 9px numeric labels; remove all intervening minor ticks. Tick numbers and density follow actual track width without overlapping and always include zero and the maximum. Quantity uses the native range control with its ordinary pointer at all times. Do not capture range pointers or introduce custom pointer-visibility state; mouse and trackpad dragging remain browser-owned. The browser's :active state freezes the quantity scale while dragging; input events update quantity and preview. Buy/Sell headings use 14px text at weight 700; lowercase stop/market retain 11px text at weight 400. The lower labels align toward their shared boundary, each 6px from its center. Both text spans shift up 1px for optical alignment and descender clearance, retaining a shared baseline without moving the heading, divider, button boxes or click targets. The Buy heading occupies the upper 18px and centers in both directions; the mode labels occupy the lower 12px with 12px line height, giving a 60:40 split. Send keeps its 30px outer height: removing the 3px wrapper padding and adding it to the button's own padding fills the former border-like gutter without moving the button. Intraday Ready is omitted in Trade; loading/errors remain above the left legend so buttons do not obscure them. Spread threshold behavior/configuration belongs only to [Schwab Trade](schwab-trade.md).

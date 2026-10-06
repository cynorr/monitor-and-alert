# Chart UI

Updated: 2026-10-06. This is the only current specification for general chart appearance and interaction. Alert-specific requirements are maintained only in [alert.md](alert.md) and are implemented. [ui.md](ui.md) is the UI entry point; panel widths are defined in [List UI / 宽度与视觉](ui.md#宽度与视觉). Data and indicator calculations remain in [behavior.md](behavior.md) and [development.md](development.md). The product UI is English only.

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
- Use `CrosshairMode.Normal` in both Monitor charts and Scan; no magnet or price snap. The linked peer uses the mouse-driven price or volume value, never candle close or the histogram bar's value.
- Chart branding and attribution follow [Logo / Icon](ui.md#logo--icon).

## Headers and information

- Chart headers are **120px** high with one bottom border. Daily shows the symbol at top-left, with no Daily tag, followed by the optional Nasdaq Trader Security Name in smaller **15px** muted text. Long names stay on one line with ellipsis and a full-name tooltip; missing names and cleared selections hide the name. Scan, Monitor, Review and Holdings selections share the local `.US` name lookup. Selecting or reading a chart never fetches names.
- Intraday shows the current price at top-left with the same **28px** size, weight and color as the Daily symbol. Its ET clock is **15px**. The extended-session pill sits immediately to the clock's left, both **26px** high; regular sessions show no pill. Period controls sit on the next row.
- Only Daily displays ADR20 and ADV20, using the same formulas in both modes: recent up to 20 closed records, mean `(H-L)/L×100` and mean `close×volume`. Intraday displays the current price and any extended-session pill. Available Sell/Bid and Buy/Ask quotes remain optional.
- EMA/SMA legends pair colored line swatches with concise labels: EMA 10, EMA 20, and SMA 50 for Daily or SMA 65 for Intraday. They do not show current indicator values; unavailable indicator lines and legends remain absent.
- OHLC sits immediately below the aligned black horizontal border on each chart, at **15px**; ADR/ADV also use **15px**. OHLC fields stay together and wrap on narrow panels. Native chart axes use **12px**. Shared CSS font variables keep other small labels at **11px**, list values at **12px** and body text at **13px**.
- Range is `(H-L)/L × 100%`. H/L values and Range value are black; other labels and values retain their original color.
- The volume value uses **`Vol` + compact value** (for example `Vol 1.38M`) at a fixed top-right position within the volume pane. Hover or a linked crosshair shows the volume of the corresponding bar, matching the OHLC bar. Leaving or clearing the crosshair restores the latest bar's volume. Quote refreshes must not replace the hovered value. The label position follows native pane resizing.
- Active volume comes from the backend's estimate; missing initialization after startup/recovery remains empty until usable, and closed official bars replace estimates. Data formulas are maintained in [behavior.md](behavior.md#图表周期与指标).
- Lightweight Charts does not supply a TradingView-style instrument/OHLC header; the small DOM legends use subscribeCrosshairMove and seriesData.
- Headers omit market/currency, adjustment/session metadata, bar counts and branding/footer strips. Validation sample counts remain backend diagnostics.

## Mouse, zoom and periods

- Use native pan, zoom, price scaling, pane resizing and scrollToRealTime. Realtime updates preserve a historical viewport.
- On page load, Intraday defaults by elapsed time since 09:30 America/New_York: before open and `[0,5)` minutes → 5m, `[5,15)` → 15m, `[15,30)` → 30m, and 30 minutes onward → 1h. Manual choices remain in effect across ticker changes; 2h/4h are manual only. Controls: **5m, 15m, 30m, 1h, 2h, 4h**.
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
- 2h/4h derive from official closed 5m bars. Missing official 15m/30m/1h history uses the same in-memory conversion; official data replaces it on the next update.
- 1000 5m bars span roughly 13 full sessions; derived periods share that coverage. Insufficient SMA65 history leaves the line absent.
- Scan and Review use completed local Daily bars without an active candle or Intraday data. Review's disabled Intraday controls and Add to Focus prompt follow [List UI](ui.md#展示范围与控件).

## Alert interaction

Alert 在 Scan/Monitor 的创建、选择、改价、删除与跨图同步只在 [alert.md](alert.md#图表交互) 维护；图形定义见 [Logo / Icon](ui.md#alert-图形)。Alert 使用当前图表鼠标水平线对应价格，不改变两个来源的数据口径。实现为 ui/src/alerts.ts 中的公开 series primitive、pane 坐标与命中检测，保持 vendor 原样。

## Chart status

- Live Monitor: Loading until Daily + 5m complete; yellow Ready while only those are complete; blue Ready when all five official periods complete, hidden after three seconds. Routine closed updates do not restart the timer.
- Exhausted history retries and connection failures use one exclamation icon with reason on hover, retaining existing charts. Finite positive OHLC range contradictions do not produce UI warnings or retries; display official values unchanged.
- Scan and Review use their local Daily date/status rather than live five-period readiness. Scan's separate Ready date and refresh controls follow [List UI](ui.md#scan-日期与-ready).

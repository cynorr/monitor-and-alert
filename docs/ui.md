# Chart layout and interactions

Updated: 2026-10-04. Approved interaction specification and maintenance reference. The product UI is English only. No localization layer.

## Layout

- Monitor has three full-height columns: Daily, Intraday, watchlist. Measure the table's natural content width plus its padding/scrollbar allowance, use that compact width for the list, and divide all remaining space equally between the charts. Each chart keeps a 320px minimum. Window enlargement adds space to the charts, without expanding the default list. Smaller viewports preserve the minima and allow the whole workspace to overflow.
- Two draggable vertical dividers resize adjacent columns. The list cannot shrink below its measured content width. Manual widths apply only to the current page; a new page or double-click restores the compact list and equal-chart default. Ignore the previous proportional localStorage settings. Scan retains a 400px list minimum. Measure again only when content structure/character widths change, grow when needed to preserve all columns, and avoid quote-driven shrinking. Holdings session changes remeasure from scratch to reclaim the hidden Ext column in regular trading.
- No application header, brand, description, global instrument banner or footer. Daily owns the enlarged symbol; Intraday owns the equally styled headline price and ET clock. Both charts show OHLC.
- White floating chart cards with generous corners on a neutral background. Black section boundaries and divider handles; the main/volume separator is gray and price-scale vertical borders are hidden.
- Search, period selector and its selected button, price-session tags and resize handles are pills. The list count is plain text.

## Scan mode

- Mode buttons live inside the watchlist panel. Switching changes the displayed mode for all open clients; live quote and account tasks keep running in the background in the real workspace. Monitor shows Daily/Intraday/Focus; Scan shows the same Daily Panel plus a wider list, with Intraday and its divider hidden.
- Scan uses upstream closed Daily bars up to the selected trading date. Focus rows use this same source while in Scan. No live candle, intraday periods or broker lookup; the selected date appears in chart status. A compact Scan Ready line shows the latest completed feature date and completion time to the second in ET, independently of the selected historical date. Background preparation/error retains the previous Ready date, with details in hover text.
- Date selector and Refresh Scan appear above Discover/Focus/Hidden buttons. Refresh runs the same Massive preparation as startup and opens the latest completed day, regardless of the currently selected date; the explicit external-db/mock path only regenerates features. Automatic completion does not change display mode or steal a historical selection. Preparation disables duplicate Refresh but leaves mode switching available. The selector lists generated days only. Same-day regeneration retains manual list state; a new day inherits Focus. Historical dates are read-only for list edits.
- Scan row columns are Symbol, Price, ADR20, ADV20. A second line shows RFL1M/3M/6M and NEW/RETURNED. Membership checkbox is independent of the chart selection. Exclude moves Discover/Focus to Excluded/Hidden; Release removes exclusion and immediately reapplies saved rules. Review has Add to Focus, no Dismiss/Delete action.
- Filters have 38 fields, grouped by Market, MA arrangement and atomic feature families. Numeric Any/≥/≤/range and classification options use the one catalog. Conditions are AND, choices within a classification are OR, and missing values only match Any or the explicit Missing classification.
- Atomic features are built for candidates, Focus and non-Hidden Excluded. Hidden skips shape scanning. Other non-candidate market rows retain light metrics. RFL values are available only for members passing ADR/ADV eligibility. A filtered member keeps its underlying membership; missing features do not imply Broken.
- Tags preserve filters and a stable role (Setup / Extended / Broken / Label). Renaming does not change role. Daily matches label rows; manual tags apply only to the current day. Default always exists; maximum ten, unique names. Create clones saved filters; edit previews immediately; Save persists and folds the editor, Cancel restores saved values. Unsaved tag switching needs an explicit discard action. Failed save keeps the draft.
- List/sort preference writes preserve unsaved filter drafts. RFL1M/3M/6M sorting changes display only; Default order preserves saved within-section order; new section members lead. Manual Focus/Discover ordering is available only under Default sort.
- Select all checks visible filtered results; destination buttons move that selection as a single block at the top. Date/list/filter changes clear checkboxes. Read-only history disables membership controls. Search and chart keyboard navigation reuse the same list implementation.
- Synthetic Scan data carries a MOCK badge. The standalone Monitor simulator uses SIM and disables mode switching. Neither fixture is a live validation result.

## Chart settings

- Local Lightweight Charts 5.2.0. Main candlestick pane above a smaller volume pane; the built-in pane divider remains draggable.
- No horizontal or vertical grid. Teal up candles/volume (#26a69a), red down candles/volume (#ef5350).
- EMA10 blue (#2962ff), EMA20 yellow (#e4b400), Daily SMA50 / Intraday SMA65 red (#e53935). Indicator calculations remain in Python.
- Daily initially shows approximately nine calendar months. Determine the initial pixel spacing from the nine-month window, then retain that spacing across symbols and column resizing. Short histories stay aligned right with blank space on the left; never fitContent to available samples. Resizing changes the number of visible candles, not candle width. User zoom changes spacing intentionally.
- On page load, Intraday defaults by elapsed time since 09:30 America/New_York: before open and [0,5) minutes → 5m, [5,15) → 15m, [15,30) → 30m, and 30 minutes onward → 1h. Manual choices remain in effect across ticker changes; 2h/4h are manual only. Controls: 5m, 15m, 30m, 1h, 2h, 4h.
- rightOffset=1, rightBarStaysOnScroll=true. Keep about one bar between the latest candle and the price axis.
- CrosshairMode.Normal with dashed horizontal and vertical lines; no magnet/snap mode.
- Native pan, zoom, price scaling, pane resizing and scrollToRealTime are used. Realtime updates preserve a historical viewport.

## Chart information

- Both chart headers and the watchlist header share a 120px height and one bottom border, aligning all three panels. The watchlist column labels have no top border. Daily shows only the symbol at top-left (no Daily tag); Intraday shows the current price there with the same 28px size, weight and color. Its ET clock is 15px. The extended-session pill sits immediately to the clock’s left, both 26px high; regular sessions show no pill. Period controls sit on the next row.
- Only Daily displays ADR20 and ADV20, using the same formulas in both modes: recent up to20 closed records, mean (H-L)/L×100 and mean close×volume. Intraday displays the current price and any extended-session pill. Available Sell/Bid and Buy/Ask quotes remain optional.
- EMA/SMA legends pair colored line swatches with concise labels: EMA 10, EMA 20, and SMA 50 for Daily or SMA 65 for Intraday. They do not show current indicator values.
- OHLC sits immediately below the aligned black horizontal border on each chart, at 15px; ADR/ADV also use 15px. OHLC fields stay together and wrap on narrow panels. Native chart axes use 12px. Shared CSS font variables keep other small labels at 11px, list values at 12px and body text at 13px. Add Range = (H-L)/L × 100%; H/L values and Range value are black, other labels/values retain their original color.
- Intraday active volume uses a cached official closed portion plus the current 5m Quote-counter delta. Missing initialization after startup/recovery shows no volume until a usable boundary; closed official bars replace estimates. Daily retains the regular cumulative volume.
- Current/latest candle volume appears at a fixed top-right position within the volume pane, independently of the hovered OHLC candle. The position follows native pane resizing.
- Hide the persistent last-price horizontal line on both charts; retain the freely moving dashed crosshair.
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

## List, tags and sections

- Requirements: [list-design.md](list-design.md). Scan tabs are Discover / Focus / Excluded; Monitor shows Focus setup sections plus Review. Holdings remains independent above the list.
- Tag/Filter controls are shared by Scan and Monitor; date, list tabs, RFL sort and batch moves remain Scan-only. Filter does not alter subscriptions or membership. Saved Tag filters also include matching manual labels; draft previews evaluate the draft conditions.
- Discover/Focus sections follow saved Setup Tag order, followed by Unclassified. Excluded sections are Review / Broken / Extended / Hidden. One symbol has one primary section and multiple compact Tag badges; manual badges are blue and expire next trading day. A row's Tags button edits only its manual additions.
- Sections collapse independently in Scan and Monitor. Review defaults collapsed in Monitor and expanded in Scan. New section arrivals lead; retained members keep manual order. Drag within/between setup sections or Shift+Up/Down under Default order; Excluded sections are assigned by rules. Header drops insert first.
- Review previews local Massive Daily with its date, disables Intraday period controls and shows Add to Focus for live data. Its Add to Focus action starts normal live monitoring. No Dismiss action or daily clearing. A Holding with the same symbol continues to use live charts via its independent selection source.
- Row Exclude moves Focus/Discover to Hidden for seven days. Hidden/Extended/Broken offer Release; current rules can immediately reexclude a released negative setup. Batch Move to Discover explicitly ends Focus membership. Hidden has no manual Tag editor while skipped.
- Search and + share the existing inline Search, / resets to Focus, Esc cancels. + on a setup section adds into that section's first position. Lookup does not write or subscribe; Enter confirms. Existing exact results are selected, not moved. Queries remain local Daily in Scan and official static_info in Monitor. Busy/error and stale-query handling stay unchanged.
- List rows show prices/metrics on the first line and compact tags on the second (Scan also retains RFL/NEW/RETURNED); Holdings keeps its existing single-line table. Selected rows retain the black outline. Native drag drop lines, keyboard navigation and quote-only value updates are retained.
- Historical Scan and bounded --symbols sessions disable edits. Simulator changes only temporary workspace. No new live requests for UI previews, tags or filters.

## Data and simulator boundaries

- One same-origin WebSocket carries initial/selection/reconnect snapshots and subsequent updates. HTTP serves assets, universe and read-only diagnostics; POST /v1/list performs edits. POST /v1/mode, /v1/scan and /v1/preferences handle mode, generation/date and saved tags. Independent list messages on the existing WebSocket refresh membership even without a chart selection. A chart GET must not change selection priority.
- Keep mode, request_id and socket identity checks. Mode/date changes reset chart context; backend run_id changes force full history. Switching periods preserves the selected trading day and native viewport behavior. Indicators are calculated only in Python.
- 2h/4h are always converted from official closed 5m bars. Missing official 15m/30m/1h history uses the same 5m conversion; official rows replace the display at the next stream update. All conversions remain in memory.
- 5m history spans roughly 13 full sessions at the 1000-response limit. Larger derived periods share that time coverage; insufficient SMA65 history means the line is absent.
- Simulator uses the same UI, scheduler, validation and conversion against temporary data, with an instance exchange clock. It never reads credentials or falls back to a broker.
- Only the full simulator HTTP/WS endpoint remains; the old extra raw-Quote listener was removed.

## Status

- Loading until Daily + 5m complete.
- Yellow Ready remains visible while only Daily + 5m are complete.
- Blue Ready when all five official periods complete; hide after three seconds. Routine successful closed updates do not restart the timer.
- Errors after exhausted history retries use one exclamation icon with reason on hover. Connection failure also remains visible; existing charts remain on screen.
- Finite positive OHLC range contradictions do not produce UI warnings or retries. Keep official prices exactly as returned.
- List rows are retained between quote updates. Search/list membership changes rebuild the visible structure; quote updates only change values.

## Checks

Check splitters, native pane resizing, short-history spacing, free crosshairs, linked days, historical viewport preservation, rapid selections, 2h/4h, reconnect snapshots and Ready timing. See [development.md](development.md) and [validation.md](validation.md).

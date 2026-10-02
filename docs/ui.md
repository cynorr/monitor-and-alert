# Chart layout and interactions

Updated: 2026-10-02. Approved interaction specification and maintenance reference. The product UI is English only. No localization layer.

## Layout

- Monitor has three full-height columns: Daily, Intraday, watchlist. Measure the table's natural content width plus its padding/scrollbar allowance, use that compact width for the list, and divide all remaining space equally between the charts. Each chart keeps a 320px minimum. Window enlargement adds space to the charts, without expanding the default list. Smaller viewports preserve the minima and allow the whole workspace to overflow.
- Two draggable vertical dividers resize adjacent columns. The list cannot shrink below its measured content width. Manual widths apply only to the current page; a new page or double-click restores the compact list and equal-chart default. Ignore the previous proportional localStorage settings. Scan retains a 400px list minimum. Measure again only when content structure/character widths change, grow when needed to preserve all columns, and avoid quote-driven shrinking.
- No application header, brand, description, global instrument banner or footer. Daily owns the enlarged symbol; Intraday owns the equally styled headline price and ET clock. Both charts show OHLC.
- White floating chart cards with generous corners on a neutral background. Black section boundaries and divider handles; the main/volume separator is gray and price-scale vertical borders are hidden.
- Search, period selector and its selected button, price-session tags and resize handles are pills. The list count is plain text.

## Scan mode

- Mode buttons live inside the watchlist panel. Switching changes the global backend mode and all open clients. Monitor shows Daily/Intraday/Focus/Wait; Scan shows the same Daily Panel plus a wider list, with Intraday and its divider hidden.
- Scan uses upstream closed Daily bars up to the selected trading date. Focus/Wait rows use this same source while in Scan. No live candle, intraday periods, broker lookup or realtime Ready state; the selected date appears in chart status.
- Date selector and Refresh Scan appear above Discover/Focus/Wait/Hidden buttons. Refresh recomputes the selected completed day and retains its manual list state. Historical dates are read-only for list edits.
- Scan row columns are Symbol, Price, ADR20, ADV20. A second line shows RFL1M/3M/6M and NEW/RETURNED. Membership checkbox is independent of the chart selection. Hide moves Discover to Hidden; Return moves Hidden to Discover; Focus/Wait Delete removes its saved status.
- Filters have 38 fields, grouped by Market, MA arrangement and atomic feature families. Numeric Any/≥/≤/range and classification options use the one catalog. Conditions are AND, choices within a classification are OR, and missing values only match Any or the explicit Missing classification.
- Tags preserve filters. Default always exists; maximum ten, unique names. Create clones saved filters; edit previews immediately; Save persists and folds the editor, Cancel restores saved values. Unsaved tag switching needs an explicit discard action. Failed save keeps the draft.
- List/sort preference writes preserve unsaved filter drafts. RFL1M/3M/6M sorting changes display only; Default order uses saved list order or Discover priority/rank order. Manual Focus/Wait ordering is available only under Default sort.
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

## Watchlist and status

- Monitor displays an independent Holdings section above Focus/Wait. Its entire table can collapse; remember that choice locally. It owns ten columns: Symbol, Net Liq, Days, P/L %, P/L, Sold, Trade Price, Chg%, Ext, P/L Day, plus Account Value and totals. Compact padding and the measured sidebar width keep all columns visible by default. Focus/Wait column labels sit below Holdings and retain their own grid. All table rows occupy one line, without subtitles for shares, sold/bought counts or dates. Net Liq, P/L and P/L Day, including their totals, show rounded integers; P/L %, Chg%, Ext and prices retain two decimals, while main-row Sold retains its integer percentage. All ticker names align, with a separate 10px disclosure arrow in their left gutter.
- Each Holdings header is a keyboard-accessible sort button: click for descending, click the same header again for default order, or click another header to replace the sort. Exactly one header has aria-sort=descending and a compact downward marker. Symbol sorts Z–A; numeric metrics use original values before display rounding, with missing/nonfinite values last and stable default-order ties. Sold uses the sold percentage, Trade Price the buy-sequence price. Trades stay attached to their parent. Quote updates retain/reapply the active sort, keyboard arrows follow displayed order, and sorting preserves chart selection and expanded trades. Sorting is local to the page and resets on reload.
- Holdings rows represent buy sequences. Click a row to select the existing Daily/Intraday pair; every sequence has a separate disclosure arrow, even without sales. Expanded details list each Buy first, followed by each Sold, with no extra heading. Each trade has one line: date under the Net Liq column, quantity only under Sold (retaining fractional shares), and actual execution price under Trade Price. Buy rows leave Days/P/L %/P/L blank; Sold rows retain holding days and realized profit. PNG export has been removed. The existing natural-width measurement automatically adapts to the simpler main rows and grows if expanded dates/details need more room. Arrow navigation stays within the selected list; holdings have no membership checkbox, add, delete, drag or Shift reorder. Duplicate symbols remain visible in both lists, with selection highlighting belonging only to the selected source/sequence. Refreshing or folding either list must not steal a holding's chart selection.
- Holdings Net Liq/P/L and Account Value use the latest Longbridge price by timestamp, including extended sessions; a missing valid quote uses the last accepted SnapTrade price. Net Liq hover identifies the source/session/time. Trade Price shows the historical sequence buy average on main rows and each trade's actual price on detail rows. Chg%/Ext match the watchlist. P/L Day uses shares still held times the latest Longbridge price change from the previous regular close; pre/overnight use the last regular price, regular/post use the regular quote's corrected previous Daily close. Its hover exposes the baseline/session/time; missing data shows — and prevents a partial total. Trade rows leave these three current-market columns blank. Cash uses SnapTrade; Account Value is current position value plus cash. Account refresh time and positions source time remain distinct from quote times. Failed refresh keeps the table and timestamps, with a concise failure status and error in hover text; the next 30-second cycle retries.
- Holdings appears only in Monitor with configured credentials. Startup refresh begins immediately. Scan, Scan Mock, standalone SIM and bounded `--symbols` sessions do not access the real account. The independent Holdings UI can be verified with an explicitly injected offline fixture, marked SIM.
- Right panel: search, compact Focus/Wait sections, four columns: Symbol, Last, Chg%, Ext. Rows are 28px high, with a shared grid reserving a separate 36px action column.
- Last is the regular price. Chg% is regular price / previous completed Daily close - 1. Use the previous trading day relative to the quote date, including after today's Daily bar is stored.
- Ext is (latest extended price / regular close - 1) × 100%, with up/down coloring. Only use extended quotes newer than the regular quote, including next-day premarket. During regular trading or when extended data/baseline is unavailable, leave Ext blank.
- Click or ArrowUp/ArrowDown selects the ticker for both charts. Outside search, Shift+ArrowUp/ArrowDown swaps the selected ticker with the adjacent row in its own section, retaining selection; boundaries do nothing. Arrow navigation skips collapsed sections.
- Search and Add share the single inline search input and list. Press / in any state, including while typing, to clear the input and begin a fresh Focus search. Each section’s + uses the same flow with that section as the add destination. Esc exits, clears the input and restores the full list. There is no dialog or separate add form.
- The placeholder is always Search. Filter existing tickers immediately; during search show only sections with matches, with no empty sections or No matches message. Hide quote column labels when no local rows match. With no exact local ticker, one second of idle input triggers a static_info lookup. Show a valid candidate (blue ticker, security name, Add) directly above any matching list sections; omit destination and keyboard hints. Do not save on lookup. Discard results belonging to previous input or an exited search.
- Enter selects an exact existing ticker, otherwise the first displayed local result. A displayed new candidate takes precedence over partial local matches; Enter validates and inserts it first in the destination section, selects it, then exits search. Enter with no local match can start the lookup immediately or await the same pending request. Clicking a candidate uses the same commit action. A ticker not found leaves the results blank; request/save failures retain an inline error. Existing tickers are never moved by searching.
- Outside search, Focus and Wait remain visible, including when empty. Their order is fixed. Search temporarily reveals matching collapsed sections; selecting a result expands its section so the selected row is visible. Market suffixes are not displayed.
- Drag a row within or between sections. A line shows before/after row placement; dropping on a header inserts first, and an empty section accepts drops. Search uses visible rows as anchors into the full list. Mouse release submits immediately; no delayed persistence. Only the dragged ticker receives the current workspace date as status_at.
- The selected row has a rounded black inset border and no background change; only unselected hovered rows get a gray background. Each row has a round Delete button with a line-drawn trash icon, revealed on hover or keyboard focus. Delete removes it from Focus/Wait; it never moves to hidden. If the selection disappears, select the first remaining ticker; an empty list clears both charts and keeps both + controls available.
- Incoming workspace changes and new trading-day files refresh the list automatically. No refresh button. Editing is disabled for bounded --symbols sessions. Simulator edits a temporary copy and labels successful additions as simulated, without broker validation.
- Use the Loading / yellow Ready / blue Ready / error-icon rules below; no multi-line banner. Keep details in hover text.
- Simulation displays one small SIM badge so generated data cannot be confused with a live account. No extra branding bar.

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

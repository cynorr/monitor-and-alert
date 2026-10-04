# UI layout and interactions

Updated: 2026-10-04. This file is the only current UI specification. The product UI is English only. List lifecycle and classification rules are maintained in [list-design.md](list-design.md); backend behavior is maintained in [behavior.md](behavior.md).

## Layout

- Monitor has Daily, Intraday and List panels; Scan has Daily and List. Panel width rules are defined once in **List UI / 宽度与视觉** below.
- No application header, brand, global instrument banner or footer. Daily owns the enlarged symbol; Intraday owns the equally styled headline price and ET clock. Both charts show OHLC.
- White floating cards with generous corners on a neutral background. Black section boundaries and divider handles; the main/volume separator is gray and price-scale vertical borders are hidden.
- Search, period selector, price-session labels and resize handles use pills.

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

- Chart headers are 120px high with one bottom border. Daily shows only the symbol at top-left (no Daily tag); Intraday shows the current price there with the same 28px size, weight and color. Its ET clock is 15px. The extended-session pill sits immediately to the clock’s left, both 26px high; regular sessions show no pill. Period controls sit on the next row.
- Only Daily displays ADR20 and ADV20, using the same formulas in both modes: recent up to20 closed records, mean (H-L)/L×100 and mean close×volume. Intraday displays the current price and any extended-session pill. Available Sell/Bid and Buy/Ask quotes remain optional.
- EMA/SMA legends pair colored line swatches with concise labels: EMA 10, EMA 20, and SMA 50 for Daily or SMA 65 for Intraday. They do not show current indicator values.
- OHLC sits immediately below the aligned black horizontal border on each chart, at 15px; ADR/ADV also use 15px. OHLC fields stay together and wrap on narrow panels. Native chart axes use 12px. Shared CSS font variables keep other small labels at 11px, list values at 12px and body text at 13px. Add Range = (H-L)/L × 100%; H/L values and Range value are black, other labels/values retain their original color.
- Intraday active volume uses a cached official closed portion plus the current 5m Quote-counter delta. Missing initialization after startup/recovery shows no volume until a usable boundary; closed official bars replace estimates. Daily retains the regular cumulative volume.
- Current/latest candle volume appears at a fixed top-right position within the volume pane, independently of the hovered OHLC candle. The position follows native pane resizing.
- Hide the persistent last-price horizontal line on both charts; retain the freely moving dashed crosshair.
- Lightweight Charts does not supply a TradingView-style instrument/OHLC header; these small DOM legends use subscribeCrosshairMove and seriesData.
- Chart headers omit market/currency, adjustment/session metadata, bar counts and branding/footer strips. Validation sample counts remain backend diagnostics.
- Disable the native canvas logo; preserve third-party LICENSE/NOTICE and attribution on the separate static /licenses.html page. No chart branding/footer logic.

## Linked trading day

- Both charts share one selected New York trading day. Clicking a candle selects that day and reveals it in the peer chart while preserving each chart's zoom.
- A period change keeps that day selected when available in the new period. Go to latest selects the latest available trading day again.
- Hovering synchronizes the peer crosshair for the same trading day through setCrosshairPosition / clearCrosshairPosition. The mouse-driven chart remains unsnapped; peer positioning uses the corresponding candle.
- Daily-to-Intraday maps to that day's first available intraday candle, or the previously selected intraday time on the same day. Intraday-to-Daily maps to that day's Daily candle.
- Do not copy logical/time ranges directly between different periods. Use a reentrancy guard for programmatic crosshair updates.
- Linking only uses loaded history. When the peer has no bars for the selected day, clear its linked crosshair; do not invent data or initiate an unbounded historical download.

## List UI

本章是唯一当前 List UI 规范，覆盖 Scan、Monitor 和独立 Holdings。名单分类与生命周期见 [list-design.md](list-design.md)；显示、筛选和格式化不改变名单归属或行情订阅。

### 宽度与视觉

- 扣除工作区内边距和面板分隔条后，两模式 List 默认占可用面板宽度 **40%**，最小 **680px**；每个图表最小 **320px**，Monitor 双图均分剩余空间。数值统一放在 `layout.ts`，方便单点调整比例。
- 面板分隔条和 List 数据列间距均为 **12px**。拖动只调整相邻面板并保留最小宽度；打开页面、切换模式或双击分隔条恢复默认。小窗口保持最小宽度，允许工作区整体溢出。
- Holdings 内容测量仅在必要时提高 Monitor 最小宽度以容纳表格，不把默认比例改成固定自然内容宽度。报价更新不能让侧栏反复缩窄或抖动。
- List 与图表头部保持 120px 对齐。模式、总数、数据标记、Scan Ready 和 Search 均位于 List 面板内；名单列头不增加顶部分隔线。
- 计数使用独立 `span.count-badge`：**10px、黑色、不加粗**，与标题留小间距。适用于列表按钮、section、symbol 总数、Holdings、Filter 与结果数。数字本身不统一加背景；选中 pill 中的数字仍为黑色，所在 pill 使用浅背景保证可读。

### 展示范围与控件

| 模式 | 名单 | 数据与控件 |
| --- | --- | --- |
| Scan | Discover / Focus / Excluded 三个入口 | 本地 Massive Daily；日期、Refresh Scan、RFL 排序、批量选择/移动，以及共用 Tag/Filter |
| Monitor | Focus setup sections、折叠 Review、上方独立 Holdings | Focus/Holdings 实时图；Review 本地 Daily 预览；共用 Tag/Filter |

- Discover 和 Excluded 的 Hidden / Extended / Broken 仅 Scan 展示。Review 不订阅 Longbridge：选择后显示 Daily 日期，禁用 Intraday 周期按钮，提示 `Add to Focus for live data`；加入 Focus 后才开始实时监控。
- 同 ticker 的 Holdings 仍为独立实时选择。WS 选择携带 `source=holdings` 或 `source=watchlist`；名单刷新、折叠和筛选不得抢走已选持仓的图表。
- 切换模式同步已打开客户端的展示，后台 Focus 行情和账户刷新持续运行。合成 Scan 标记 MOCK，独立模拟器标记 SIM。
- 历史 Scan 与有界 `--symbols` 会话禁用名单编辑；模拟器只修改临时 workspace。

### 行与格式

| 位置 | Scan | Monitor |
| --- | --- | --- |
| 1 | Symbol | Symbol |
| 2 | Price | Last |
| 3 | ADR20 | Chg% |
| 4 | ADV20 | Ext |
| 5 | Growth | Growth |
| 6 | Tags | Tags |
| 7 | 行操作 | 行操作 |

- 同 ticker 只有一行，主体数据列保持同一水平行，不再增加副标题/RFL 第二行。多个 Tag 在独立 Tags 列内竖向排列，行高随标签自然增加，不能覆盖相邻行。
- Growth 依次显示 **1m / 3m / 6m** 三个值，不显示周期 key，以浅色 `|` 分隔。原始 `rfl=(close/low-1)×100`：小于 100 显示最多一位小数的百分比、去掉 `.0`；大于等于 100 显示 `(1+rfl/100)`，保留一位小数和小写 `x`。例如 `65%`、`12.3%`、100% 显示 `2.0x`、130% 显示 `2.3x`。空值和非有限值显示 `—`；只改变显示，不改变原始数据、排序和筛选。
- Tags 显示当前所有匹配标签；人工补充为蓝色、仅当前交易日有效。名称过长可省略显示，悬停保留完整名称。Tags 编辑按钮位于该单元右上角，不额外占一条数据行；展开编辑仅修改人工补充。Hidden 不提供人工 Tag 编辑。
- NEW / RETURNED 使用 Symbol 旁的小标记；ticker 不显示 `.US`。Scan 的成员勾选与图表选中互相独立。
- Scan Price 是完成日收盘价，ADR20/ADV20 用共用日线定义。Monitor Last 是 regular 价格，Chg% 使用前一完成交易日 regular 收盘价；Ext 使用更新的 extended 报价相对 regular 收盘价，regular 时段或缺数据时留空。Review 显示本地 Daily close，实时涨幅列留空。
- 选中行保留圆角黑色内边框，不改变背景；仅未选中 hover 行使用灰背景。操作与 Tag 编辑按钮 hover/键盘 focus 时可见；报价更新保留行结构，仅刷新值。

### Section、顺序与选择

- Discover/Focus 按保存的 **Setup** Tag 顺序分组，最后是 Unclassified；Excluded 固定 **Review / Broken / Extended / Hidden**。一只股票可有多个 Tag、一个主 section。
- Scan 与 Monitor 的折叠状态独立。Review 在 Monitor 默认折叠、Scan 默认展开。非搜索状态 setup 空组也显示；搜索只显示有结果的组。
- 新进入 section 的成员放**队首**，留在同组的成员保留人工顺序。人工主 section 仅当天有效，名单归属和保存顺序按 List 设计执行。
- Default order 下，允许在 Discover/Focus setup 组内及组间拖动。落点显示行前/行后线；落在组头或空组插入队首。筛选/搜索可见行作为完整组顺序的锚点，松手立即保存。
- RFL1M/3M/6M 排序仅改变显示，禁用 Scan 人工重排；Excluded 分组由规则决定，不提供人工排序。
- 点击或上下方向键按显示顺序选图，跳过折叠组。非搜索状态 Shift+上下在同一 setup 组内交换相邻成员并保留选择，到边界不移动。Holdings 使用独立导航、不参与 Shift 重排。

### Tag 与 Filter 编辑

- 两模式使用同一套保存的 Tag/Filter。38 字段目录包含 Market、MA arrangement 和 atomic feature 各组。使用 **CSS 两列 columns** 布局，每组保持完整；不使用横向对齐的 grid，避免短组下面出现空白。
- 数值条件支持 Any / ≥ / ≤ / range；不同条件 AND，分类多选 OR。缺失值匹配 Any 或显式 Missing。Filter 不移动名单、不改变订阅，被筛掉的成员保留底层归属。
- Tag 用途固定为 Setup / Extended / Broken / Label，与名称独立；Setup 提供潜力 section，其余按 List 设计处理。Default 始终存在、用途 Label、不可改名或删除；Tag 名称唯一，最多十个。
- 新建克隆已保存条件，用途默认 Setup。条件编辑即时预览；Save 保存并折叠，Cancel 恢复。未保存时切 Tag 需明确丢弃，保存失败保留草稿；名单/排序偏好写入不得覆盖未保存的 Filter 草稿。
- 已保存 Tag 的筛选包含人工补 Tag 成员；未保存条件预览只按草稿条件判断。保存规则由后端重评已有本地数据，UI 筛选不触发下载。

### 名单操作与批量移动

- `Add to Focus` 清除排除状态并开始实时监控。行 Exclude 将 Discover/Focus 移到 Hidden 七天；Hidden / Extended / Broken 提供 `Release`，当前规则仍可立即重新排除。Review 只有 Add to Focus，可留待处理或规则重分类，没有 Dismiss/Delete。
- 批量 `Move to Discover` 明确结束 Focus 归属，`Move to Excluded` 表示 Hidden。Select all 勾选当前筛选结果，移动时整块插入队首。日期/名单/Filter 改变清空勾选；Space 切换选中 Scan 行的勾选。
- 操作即时写入，保存失败保留原名单并显示简短行内错误。workspace/新日变更自动刷新，不增加 Refresh Workspace 按钮。名单选择消失时改选首个可用成员，空名单清图但保留 Search 和新增入口。

### Search 与 Add

- Search 与可编辑 Focus setup 组的 `+` 共用唯一行内输入，placeholder 始终为 `Search`，不使用新增弹窗。`/` 随时清空并开始 Focus 搜索；Focus 组内 `+` 指定该 section 为新增目标。Esc 退出并恢复全名单。
- 即时筛选本地 ticker，仅显示匹配组，无空组或 No matches；没有本地结果时隐藏报价列头。搜索临时展示折叠组，选中结果只展开当前模式的对应组。
- 没有精确本地 ticker 时，停输一秒发起精确查询：Scan 读本地 Daily，Monitor 经后端官方 static_info。查询不保存、不订阅；输入变化或退出后丢弃旧响应。
- 有效新候选位于本地匹配前，显示蓝色 ticker、公司名和 Add。Enter 优先选择精确已有 ticker；已展示的新候选优先于局部匹配，否则选择首个本地匹配或发起/等待查询。确认新候选后插入目标队首、选图并退出；已有 ticker 只选择、不移动。
- 未找到 ticker 保持空结果，查询/保存失败保留行内错误。只支持美股正股，不新增模糊查询和其他市场入口。

### 独立 Holdings 表

- Holdings 在 Focus 上方，独立只读表、整体折叠、Account Value、刷新时间和 Total；折叠选择本地记忆。主行按买入 sequence 展示，同 ticker 的不同批次及与 Focus/Review 重复均保留，不参与名单勾选、增删、拖动或 Tag 筛选。
- 列为 Symbol、Net Liq、Days、P/L %、P/L、Sold、Chg%、Ext、P/L Day。regular 时段隐藏整列 Ext，取消该列排序并回收测量宽度；使用已有服务端时段状态，不新增前端日历或请求。
- 主行单行。Net Liq/P/L/P/L Day 与 Total 显示整数，P/L % 和 Chg% 一位小数，Ext 与成交价两位。Sold 显示整数百分比；零留空且无展开箭头，实际非零但四舍五入为零显示 `<1%` 并可展开。ticker 统一对齐，左侧独立箭头空隙。
- 明细先 Buy 后 Sold，每笔单行、无新增列头：日期在 Net Liq 列、股数在 Sold 列并保留碎股、成交价在 Chg% 列。Buy 的 Days/P/L 留空，Sold 保留持有天数与已实现盈亏。
- 列头只在降序/默认间切换，换列替换排序。Symbol Z–A，数值按原值、缺失/非有限置后、同值稳定排序。报价更新保留排序、选择和展开明细；明细跟随主行。排序仅本页面有效，重开恢复默认。
- 点击和键盘导航选择现有图表对。选中批次消失时改选首条持仓，再无持仓才回名单。刷新失败保留上次表格与时间、显示简短状态，详情悬停查看；价格来源和 P/L Day 基准保留 tooltip，计算见 [behavior.md](behavior.md)。

### Scan 日期与 Ready

- Scan 使用截至所选日的完成 Daily，Focus 也用同一来源，无活跃 candle 或 Intraday。图表显示所选日期；独立 Scan Ready 显示最新 feature 完成日和精确到秒的 ET 完成时间。
- 日期下拉仅列已生成日。Refresh Scan 准备并打开最新完成日，与正在查看的历史日期无关；自动完成保留历史选择和展示模式。同日重算保留人工状态，新日按 List 生命周期继承。
- 准备中禁用重复 Refresh，但允许切换模式；失败/后台准备保留旧 Ready 日期，详情放悬停。GET、选图、Filter 和切页不触发下载。

## Data and simulator boundaries

- One same-origin WebSocket carries initial/selection/reconnect snapshots and subsequent updates. HTTP serves assets, universe and read-only diagnostics; POST /v1/list performs edits. POST /v1/mode, /v1/scan and /v1/preferences handle mode, generation/date and saved Tags. Independent list messages refresh membership even without chart selection. A chart GET must not change selection priority.
- Keep mode, request_id, source and socket identity checks. Mode/date changes reset chart context; backend run_id changes force full history. Switching periods preserves selected trading day and viewport. Indicators are calculated only in Python.
- 2h/4h derive from official closed 5m bars. Missing official 15m/30m/1h history uses the same in-memory conversion; official data replaces it on the next update.
- 1000 5m bars span roughly 13 full sessions; derived periods share that coverage. Insufficient SMA65 history leaves the line absent.
- Simulator uses the same UI, scheduler and validation against temporary data with an instance exchange clock. It never reads credentials or falls back to a broker. SIM and MOCK are offline fixtures, not live evidence.

## Chart status

- Live Monitor: Loading until Daily + 5m complete; yellow Ready while only those are complete; blue Ready when all five official periods complete, hidden after three seconds. Routine closed updates do not restart the timer.
- Exhausted history retries and connection failures use one exclamation icon with reason on hover, retaining existing charts. Finite positive OHLC range contradictions do not produce UI warnings or retries; display official values unchanged.
- Scan and Review use their local Daily date/status rather than live five-period readiness.

## Checks

Run `npm run build --prefix ui` after TypeScript edits and only the related offline checks. Validate affected layout, List interactions or chart gestures; do not broaden to a live/full workflow without authorization. Record coverage and limitations in [validation.md](validation.md).

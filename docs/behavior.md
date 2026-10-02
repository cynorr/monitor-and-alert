# 看盘服务运行逻辑

更新：2026-10-02。面向使用者；实现入口见 [development.md](development.md)，布局和交互见 [ui.md](ui.md)。

## 启动与接收

Monitor 启动选择 `runtime/days/` 下目录名为 YYYY-MM-DD 且含 workspace.json 的最新日期，读取 focus/wait，开始接收当前名单的 Quote，同时加载历史；配置SnapTrade后也接收当前Holdings的行情。显式 `--workspace` 则固定使用该文件。每个 ticker 获取 Daily、5m、15m、30m、1h 最近 1000 根。正在形成的 candle 被过滤，盘中可能剩 999 根；短历史照常显示。没有分页，不连接旧历史，不追查历史断档（包括返回窗口内部的旧空档）。

Quote 统一接收和校验，regular 与 extended 按时段保存最新值，两者均不落盘。Regular 更新活跃 candle；extended 更新最新价格与持仓估值。页面选股不改变券商订阅范围。关闭网页不停止后端。

## Holdings

Holdings为独立的只读持仓列表，位于Monitor的Focus/Wait上方，独立列头并可整体折叠。保留Symbol、Net Liq、Days Held、P/L %、P/L、Sold、Trade Price及账户总值、Total、卖出明细和PNG导出。按买入sequence显示，允许同ticker多个买入批次，也允许与Focus/Wait重复；它不检查或修改观察名单归属，不参与新增/删除/移动/排序。点击行复用现有Daily/Intraday；名单刷新、折叠或从Focus/Wait删除同ticker不会抢走持仓选中状态。被选持仓批次消失时改选第一条持仓，持仓为空则回到观察名单。

配置SnapTrade时，启动Monitor及从Scan返回Monitor立即发起刷新，首轮前不等待30秒；之后按30秒周期串行刷新。每轮请求指定账户的positions、details、balances、executed orders；activities仅无缓存或流水同步截止变化时获取并保留原分页。这是成交流水获取，与Longbridge K线禁止分页的规则无关。所有账户请求共用10次/滚动分钟预算，触及额度或慢请求时周期可能延长，不重叠请求。30秒是应用轮询频率，不保证券商持仓/资金每30秒更新；不调用付费连接refresh。

成功获取并完成原买卖归属核对后，整体替换持仓与唯一原始缓存。网络失败、规则错误、歧义或数量不一致均保留上次成功的列表、时间戳与行情范围，提示刷新失败，下一周期再获取；不终止Monitor、不猜测买卖归属。保持单账户USD股票/ETF多头、同日买入先于卖出、明确TXT关联优先、税费前成交价及Decimal计算。持仓天数仍计算到positions快照日期，已结清批次不返回。

Longbridge按quote时间戳取regular/pre/post/overnight最新有效价格，重算price、市值、浮盈亏、总P/L及其百分比。仅该ticker缺少有效Longbridge报价时，回退最后成功SnapTrade持仓快照中的price；来源/时段/时间放在市值悬停信息中。Trade Price仍是买入成交均价，已实现盈亏和买卖记录不随行情变化。cash保持SnapTrade最近成功值，Account Value = 当前所有持仓估值 + cash，不再直接展示details返回的账户总值。混合来源和不同更新时间可能与券商官方净值不同。

底层Longbridge范围为Focus/Wait与已接受Holdings的并集，同ticker共用一个Quote订阅与一份五周期任务。只有从两类来源都移除才退订/撤下任务；UI和workspace归属仍完全独立。HTTP/WS读取不触发SnapTrade刷新或扩展下载。进入Scan停止持仓轮询与Monitor行情，离开Scan恢复并立即刷新；Scan Mock、独立模拟器与`--symbols`有界验收不读SnapTrade凭证、不获取真实账户。

## Scan 与互斥模式

启动默认 Monitor，可用 --mode scan。页面在列表面板内切换模式，整个进程同时只有一种模式；所有浏览器会话跟随这个选择。进入 Scan 前确认已有截面；停止持仓轮询并等待 Monitor 下载/Quote 任务结束，取消订阅，释放 SDK context。Scan 不读凭证、不请求券商；切回 Monitor 才按最新 Focus/Wait及已接受Holdings创建行情连接，并立即更新持仓。

Scan 读取上游 runtime/daily.sqlite3，截至选择日期最近最多1000根日 K，只有closed日图，没有实时active或分钟线。Focus/Wait 在Scan中也使用该上游来源；切回Monitor才使用runtime/bars.sqlite3与实时Quote。两者复用同一Daily图表和计算，不拼接两个供应商的历史。

两种来源统一使用 NoAdjust 原始价格与原始成交量；入库、指标及图表没有后续复权，也不读取 adjust table。拆股前后真实价格跳变会进入均线、ATR、RFL 等计算，这是当前选择的口径。上游已复权数据不能仅改表结构或元信息后视为 NoAdjust。

全市场完成日期必须显式发布。scan --date D 或 Scan 模式下 POST /v1/scan 生成一份截面，页面Refresh重算当前选择日；GET和图表选择不生成。候选要求Price≥5、ADR20≥5%、ADV20≥$5M，再取RFL1M/3M/6M任一排名前50；排名仅在eligible截面执行，不因Tag或列表改变。

同日生成保留名单；新日期第一次生成才继承Focus/Wait。Discover由candidate与carried派生，Hidden按7个自然日：小于7天隐藏，等于7天且仍是candidate返回Discover并标记Returned；后续新日清除过期状态。Hidden继承要求前后两日candidate交集。NEW是当前候选减上一份截面的候选。

Scan提供四列表、RFL排序和38项Filters。数值支持≥/≤/范围；条件之间AND，同一分类选项OR；有条件的缺失值不匹配，Any不排除缺失。Tag是保存的条件集合，Default常驻、最多10个；修改即时预览，Save才持久化，Cancel恢复保存值，失败保留草稿。RFL不作为过滤条件，Tag不自动修改名单。

复选与当前图表行独立，全选只选可见结果；日期/条件/列表切换清空勾选。整批移动一次保存，按提交顺序插入目标顶部。Focus/Wait共享同一workspace；Discover/Hidden只在Scan显示。历史日期名单只读，Monitor始终使用最新名单。Mock使用独立runtime与MOCK标记，真实上游契约见upstream-daily-data.md。

## Focus / Wait 列表

原始需求记录：[List Module V0](list-module-v0.md)，当前行为以本文为准。

Monitor 与 Scan 共用当前 workspace.json，保留 schema 和 version。Focus、Wait 固定顺序，可折叠；数组顺序就是显示顺序。搜索与新增共用列表上方输入框，没有新增弹窗。按 / 随时进入搜索并清空输入，默认新增到 Focus；Section 右侧 + 进入同一搜索模式，只把新增目标改为该 Section。再次按 / 会清空并重置为 Focus。Esc 退出、清空输入并恢复完整列表。

输入 ticker 时先过滤现有名单；输入停止 1 秒后，若无完全匹配 ticker，Monitor 则通过同一 Longbridge context 的 static_info 查询美国证券；Scan 只查询本地上游 SQLite，候选直接显示在列表中。查询不写 workspace、不订阅、不下载。回车选中完全匹配的现有 ticker（否则选当前显示的首个现有匹配）；若显示的是有效新候选，回车才验证、加入目标 Section 首位并选中。无现有结果时提前按回车会立即发起或等待同一候选查询。选中后退出搜索、展开对应 Section 并显示双图；已有 ticker 不改变位置、状态或日期。候选查不到或验证失败不添加；输入变化或退出后忽略旧查询结果。

搜索框始终提示 Search；搜索时只显示有匹配项的 Section，全部无结果时留白，不显示 No matches。Longbridge 新候选使用蓝色 symbol，右侧只显示 Add，不再显示新增目标或回车提示。请求/保存失败仍显示错误。regular 时段 Ext 单元格留空，不用横线占位。

可拖动排序或跨 Section 移动；正常列表模式下，Shift+上/下将选中 ticker 与当前 Section 相邻项交换，保持该 ticker 选中，Section 边界不跨组。快捷键复用现有移动保存规则。删除直接移出数组并删除对应 statuses 记录。新增、移动和排序只更新主动操作 ticker 的 status_at，使用当前 workspace 的交易日日期；被动移位 ticker 不变。所有操作同步直接写回文件，完成即保存，无 debounce、队列、原子替换或文件锁。

新增到 Focus/Wait 时从旧 hidden 顺序移除该 ticker；保留 statuses 的其他字段。删除清除该 ticker 的保存归属和各组排序；如果仍是 candidate/carried，Scan 的 Discover 会再次显示它。需要隐藏时使用明确的 Hide 动作。

一个 watchdog 原生文件事件 watcher 递归监听 days：Scan 修改当前文件后自动重读；出现更大日期的 workspace.json 自动切换。外部更新只读、不回写，无轮询、合并或并发冲突处理。读取/保存失败显示简单错误。

名单增加会立即安排五个官方周期最近 1000 根，并订阅 Quote；移除且该ticker也不在Holdings时，撤下下载任务、停止后续请求并取消 Quote 订阅，已有 SQLite 历史不删除。排序和 Focus/Wait 互移不重下载、不重订阅。Quote 订阅变更在现有 context 上执行；网络请求仍受现有预算约束。文件切换保留仍在行情范围中的状态。观察名单选中 ticker 被删除时选择第一项；两类列表都为空时清空图表、保留新增入口和 WebSocket。

`--symbols` 验收会话始终限制在指定子集，禁用列表编辑；文件更新不会扩大该范围。模拟器仅编辑临时 workspace 副本，新增使用明确标记的模拟证券信息，不调用真实验证。

## 请求顺序与恢复

订阅恢复和到期 closed 更新优先；选中 ticker 的 5m、Daily 优先于其他历史，然后所选官方分钟周期。其余按 5m、Daily、15m、30m、1h 推进。

全局每秒最多 10 次、最多 5 个请求在途（[官方额度](https://open.longbridge.com/docs#rate-limit)）。10 是总量，不与 5 相乘；count=2 的一次调用仍只算一个请求。后台历史最多每秒 8 次、占 3 个槽，给交互保留 2 个请求/秒和 2 个在途位置。在途请求不强制取消，同一个 ticker/周期不会重复下载。

正常每根收盘后 2 秒调用最近 K 线 count=2，覆盖“最新一根还在形成”的情况；只保存已闭合数据。启动、检测到重连/休眠、跨过多个边界以及失败补缺，均使用 count=1000。没有第二个历史 API。

本轮缺失或请求失败后再重试 3 次（间隔 2/5/10 秒）。仍失败则显示错误并等待下一个 5m 收盘后 2 秒，再最多尝试 3 次。每轮对每个失败周期单独执行，其他 ticker 继续运行。成功后清除错误。只要求最新应闭合的目标存在；历史空档可能来自无成交或停牌，直接接受，不扫描连续性、不触发补缺。

SDK 负责底层连接恢复；应用保留 30 秒 snapshot、开市无全名单推送 watchdog。应用重新订阅成功时触发统一回补；SDK 内部不可见的短重连由 snapshot 与 closed 目标检查补足。

## OHLC 原值与比较日志

如果价格正数且有限，但 Open/Close 超出 Low/High，或 High 小于 Low，原值仍入库和绘图。上下界检测只追加到 runtime/invalid_ohlc.jsonl：ticker、周期、交易时段、bar 起止 Unix 秒与 ET、获取时间、原始 OHLCV。每次获取重复追加，不去重、不修复、不回补、不显示感叹号。

不使用 max/min 强制修正官方 OHLC。非数字、非法时间戳、负 volume 等无法正常使用的数据仍被拒绝；必要位置没有可用 bar 时按缺失恢复。turnover 缺失不影响日 K；ADV 统一使用 close × volume。

## 图表周期与指标

官方闭合数据存 SQLite。Quote 产生的临时 5m、所有合成周期和指标仅在内存。

页面打开时按美东 09:30 起的开盘时长选择 Intraday 默认周期：[0,5) 分钟为 5m、[5,15) 为 15m、[15,30) 为 30m，30 分钟起为 1h；开盘前为 5m。只计算初始默认值，之后保留手动选择（切换 ticker 也保留）；2h/4h 仅手动选择。

2h/4h 始终从 5m 合成。15m/30m/1h 缺少官方 bar 时，用相同函数合成替代；官方到达后随下一次现有 WebSocket 更新直接替换，不另等收盘。按实际开盘时间分组，不跨日，尾根按收盘时间结束。闭合合成 candle 的 5m 前缀缺失时不编造完整结果。

合成只改变周期，不扩展历史时间跨度：1000 根 5m 约覆盖 13 个普通交易日，2h/4h 也只有这段历史。均线样本不足时不显示该线。

两模式共用 EMA10/20，Daily SMA50、Intraday SMA65，以及 Daily ADR20/ADV20。ADR20 是最近最多20根已收盘记录的 `(H-L)/L × 100` 均值，ADV20 是同窗口 `close × volume` 均值；停牌/稀疏记录按实际根数取窗口，不使用 turnover 改变公式。Intraday active volume = 本根内已闭合部分的量 + 当前 5m 内 Quote 累计量的增量。已闭合部分优先按 1h → 30m → 15m → 5m 无重叠拼接，只使用完整落在本根起点到当前 5m 起点之间的官方 bar。结果缓存为标量，Quote 更新不重新求和。不能用全天 Quote 累计量减历史 K 线总量，因为两者累计差异会全部堆到 active。盘中启动、恢复、跳过时间桶或累计量回退时，没有可靠起点的 active volume 暂空；跨入下一连续 5m 后恢复。Daily 仍使用官方累计量。active 是按 Quote 观测时刻估算的临时量，收盘后由官方 K 线替换。上下界矛盾也可能体现在图表及派生指标中，因为本版保留官方原值。

## Monitor 页面状态

- Loading：Daily + 5m 尚未完成。
- 黄色 Ready：Daily + 5m 验证通过，保持到五周期完成。
- 蓝色 Ready：五个官方周期验证通过，3 秒后隐藏。正常每根收盘更新不会反复闪烁。
- 感叹号：回补重试耗尽，悬停查看缺失/请求失败等原因；连接中断也明确显示。

2h/4h 和临时合成结果不算官方周期下载完成。错误仍在重试时保留已有图表；成功即恢复。OHLC 上下界矛盾不影响 Ready、不进入错误提示。

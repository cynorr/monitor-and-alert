# 看盘服务运行逻辑

更新：2026-10-06。面向使用者；实现入口见 [development.md](development.md)，布局和交互见 [ui.md](ui.md)。

## 启动与接收

正式服务启动选择 `runtime/days/` 下目录名为 YYYY-MM-DD 且含 workspace.json 的最新日期，读取 focus，开始接收当前名单的 Quote，同时加载历史；配置SnapTrade后也接收当前Holdings的行情。显式 `--workspace` 则固定使用该文件。每个 ticker 获取 Daily、5m、15m、30m、1h 最近 1000 根。正在形成的 candle 被过滤，盘中可能剩 999 根；短历史照常显示。没有分页，不连接旧历史，不追查历史断档（包括返回窗口内部的旧空档）。

Quote 统一接收和校验，regular 与 extended 按时段保存最新值，两者均不落盘。Regular 更新活跃 candle；extended 更新最新价格与持仓估值。页面选股不改变券商订阅范围。关闭网页不停止后端。

## Holdings

Holdings 是独立的只读持仓来源，按买入 sequence 显示，允许同 ticker 多个买入批次，也允许与 Focus 重复。它不检查或修改观察名单归属，不参与名单新增、排除、移动或排序。点击持仓复用现有 Daily/Intraday；名单刷新、折叠或从 Focus 删除同 ticker 不改变持仓的选择来源。被选持仓批次消失时改选第一条持仓，持仓为空则回到观察名单。

持仓排序只影响当前页面，不修改账户数据或 workspace；行情更新沿用当前排序。布局、列、数值格式、排序按钮和买卖明细的唯一要求见 [ui.md 的 List UI 章节](ui.md#list-ui)。持仓表的自然内容宽度参与 Monitor 列表的最小宽度测量。

配置SnapTrade时，正式服务启动立即发起刷新，首轮前不等待30秒；之后按30秒周期串行刷新，Scan/Monitor切换不停止或重建任务。每轮请求指定账户的positions、details、balances、executed orders；activities仅无缓存或流水同步截止变化时获取并保留原分页。这是成交流水获取，与Longbridge K线禁止分页的规则无关。所有账户请求共用10次/滚动分钟预算，触及额度或慢请求时周期可能延长，不重叠请求。30秒是应用轮询频率，不保证券商持仓/资金每30秒更新；不调用付费连接refresh。

成功获取并完成原买卖归属核对后，整体替换持仓与唯一原始缓存。网络失败、规则错误、歧义或数量不一致均保留上次成功的列表、时间戳与行情范围，提示刷新失败，下一周期再获取；不终止Monitor、不猜测买卖归属。保持单账户USD股票/ETF多头、同日买入先于卖出、明确TXT关联优先、税费前成交价及Decimal计算。持仓天数仍计算到positions快照日期，已结清批次不返回。

Longbridge按quote时间戳取regular/pre/post/overnight最新有效价格，重算price、市值、浮盈亏、总P/L及其百分比。仅该ticker缺少有效Longbridge报价时，回退最后成功SnapTrade持仓快照中的price；来源/时段/时间放在市值悬停信息中。成交价仅在展开买卖明细中显示，为该笔成交金额/股数，已实现盈亏和买卖记录不随行情变化。cash保持SnapTrade最近成功值，Account Value = 当前所有持仓估值 + cash，不再直接展示details返回的账户总值。混合来源和不同更新时间可能与券商官方净值不同。

Chg%与Focus共用修正后的前一已完成Daily收盘价，计算regular涨跌幅。Holdings的Ext仅显示比regular更新的扩展时段相对regular收盘价的涨跌幅，盘中隐藏整列（含列头和Total占位），并重新测量持仓内容的宽度下限；若原先按Ext排序则取消排序。离开盘中后恢复整列。常规时段使用服务已有current_regular_session标记，不根据旧盘前报价推断。P/L Day = 当前剩余股数 ×（最新Longbridge价 − 前一常规收盘价）：盘前/夜盘使用最近regular收盘价作基准，盘中/盘后使用regular对应的前一交易日收盘价；盘后保留整个常规交易日以来的变动。该列衡量当前剩余仓位的价格变动，不包含已卖出部分、现金或手续费。缺报价/基准时显示—；总计只有所有批次都有有效值时才显示合计，不输出部分总额。SnapTrade兜底仍用于原市值/P/L，不编造当天盈亏。

底层Longbridge范围为Focus与已接受Holdings的并集，同ticker共用一个Quote订阅与一份五周期任务。只有从两类来源都移除才退订/撤下任务；UI和workspace归属仍完全独立。HTTP/WS读取不触发SnapTrade刷新或扩展下载。进入Scan继续持仓轮询与Monitor行情，切回Monitor直接使用已有状态；Scan Mock、独立模拟器与`--symbols`有界验收不读SnapTrade凭证、不获取真实账户。

## Scan 与后台数据任务

启动默认 Monitor，可用 --mode scan。页面在列表面板内切换展示，所有浏览器会话跟随这个选择。正式服务的Longbridge与SnapTrade任务仅在整体退出时停止；Scan使用Massive数据，后台仍只跟踪最新Focus及已接受Holdings。切回Monitor复用连接、任务和缓存。Mock Scan仍离线；只有明确切入Monitor才启用Longbridge，回到Mock Scan时停止。

Scan 读取上游 runtime/massive/daily.sqlite3，截至选择日期最近最多1000根日 K，只有closed日图，没有实时active或分钟线。Focus 在Scan中也使用该上游来源；切回Monitor才使用runtime/longbridge/bars.sqlite3与实时Quote。两者复用同一Daily图表和计算，不拼接两个供应商的历史。

Massive 数据要求、拆股/整数成交量、来源时段与筛选配置统一见 [massive-data.md](massive-data.md)。Longbridge仍显式请求NoAdjust、regular并保存整数成交量。读取、指标和图表不再做复权；两源共享格式与计算，但不拼接或交叉验证。Longbridge复权不在本版本范围。Daily Symbol右侧可以显示本地Nasdaq目录名称，缺失正常留空，两模式共用。

全市场完成日期由上游提交 metadata.completed_date 发布；不从 MAX(ts) 猜测完成状态。页面 Refresh Scan 和不带 --date 的 scan 命令生成并打开最新完成日，按钮不重算日期下拉框当前选中的旧日。显式 scan --date D 或 POST /v1/scan 指定 date 仍可重算指定日；GET和图表选择不生成。内置Massive准备成功后自动生成截面；显式外部SQLite入口仍只读。日期下拉框仅显示已生成的日期。

正式服务启动触发一次Massive后台准备，依次完成Daily、split、SQLite和features；已有目标日及匹配行情版本的完整产物则跳过。免费Nasdaq目录由独立脚本维护；缺失/损坏或配置错误先于Massive请求失败，保留旧结果并提示。网络获取按数据要求有界重试；本地构建失败直接报错，派生SQLite删除后在下次运行重建。没有定时轮询。手动脚本与页面Refresh复用同一流程，GET、图表和切页不触发下载；同一时刻仅一份准备任务。

Daily与split获取范围见数据要求。SQLite普通新日直接追加；旧raw或split结果变化则删除后全量重建。构建失败报错并删除不完整库，不做失败回滚。状态统一写runtime/pipeline-status.json；Daily、split、bars、features分别记录当前状态和成功产物。Scan Ready以features完成日及匹配的行情版本为准，完成时间显示到秒。候选配置/目录修改后手动刷新应用，不做自动版本重算。自动完成只让跟随最新日的页面继续跟随，历史日期保持不变；后台忙不阻止展示切换。

## List、Tag 与 Filter

需求背景与归属设计见 [list-design.md](list-design.md)，显示与交互的唯一规范见 [ui.md 的 List UI 章节](ui.md#list-ui)。

Scan 使用 Discover、Focus、Excluded 三个列表；Focus 跨日保留、两模式共享。Monitor 展示 Focus、独立 Holdings 和折叠 Review；Discover / Hidden / Extended / Broken 不订阅 Longbridge。Review 预览来自本地 Massive Daily，加入 Focus 后才实时订阅；Excluded 盘中恢复依赖下一个完成日扫描或人工加入。

候选按 [Massive 数据要求](massive-data.md#独立配置与处理顺序) 完成初筛和RFL排名。候选、Focus和全部Excluded（含Hidden）均计算完整特征与Growth所用RFL数值，即使继承成员不在候选或前50也继续计算，不为名单另行排名；详细范围见 [名单完整特征范围](massive-data.md#名单完整特征范围)。已有人工成员不因候选门槛自动删除，短历史/缺数据不推断为Broken。启动在后台从本地Daily补齐旧截面缺少的成员特征，随后按名单规则分类，不触发下载。新日和重算发布后更新规则结果。

Tag 保存条件与用途：Setup用于潜力section/Review，Extended和Broken用于淘汰，Label仅辅助观察；名称不决定用途。数值条件AND、分类选项OR，缺失值不匹配，Any不排除缺失。每只股票可以匹配多个Tag，按Setup定义顺序选一个主section；未匹配为Unclassified。

Tag 图案与颜色独立保存，只影响展示；改名保留已有图案绑定。编辑外观草稿继续使用已指派及人工补充的匹配结果，只有修改条件才进入条件预览，不因调颜色改变名单归属或订阅。

Discover、Focus及非Hidden Excluded匹配负面规则立即进入Excluded对应section，Broken优先Extended；非Hidden Excluded不满足负面规则且匹配Setup进入Review。Review不强制每日清空，无Dismiss。Hidden表示人工未分类排除，七天内不参与规则判断。Hidden/Extended/Broken七个自然日到期后解除本次排除、再次按规则分类；仍匹配负面条件继续排除，无释放保护期；重复匹配不每日续期。Review保留到人工处理或新负面判断。

规则Tag每天重算；人工补Tag、主section和保留Focus例外仅当天有效。Focus成员及同section内部人工排序跨日保留，新进入section成员置顶。没有匹配Tag不淘汰Focus。人工入选Focus当天优先，仍显示机器负面标签，次日重新接受规则。临时Filter只改变显示，不移动名单或改变订阅；修改草稿预览，Save才更新条件并重新分类已有本地截面。

Add to Focus清除排除状态并开始订阅；Exclude for 7 days（包括行删除）进入Hidden；Move to Discover/Release解除归属，仅当日候选返回Discover并立即按已有规则分类。扫描初筛和RFL排名不受Tag影响。批量操作一次同步落盘，历史日期名单只读。旧Focus/Wait合并为Focus，旧Hidden转Excluded/Hidden并保留期限。

搜索仍使用列表上方Search与/入口。Monitor通过同一Longbridge context的static_info验证新股票；Scan只读本地Daily。查询不写名单、不订阅。确认 Add 后默认加入 Focus，Focus section 的 + 使用指定组；具体入口与排序交互统一见 List UI。盘中可以调整 section，本次不新增 Quote 形态规则。保存失败回退内存并显示错误。

一个watchdog原生事件监听days，新日期workspace出现自动跟随；Monitor始终使用最新名单，历史Scan只读。外部修改自动重读，Focus变更立即同步行情范围；已有行情状态复用，排序/主section移动不重下载。只有同时不在Focus和Holdings才退订；历史SQLite不删除。两类实时列表都为空时清空图表并保留搜索入口。`--symbols`会话始终限制指定Focus子集并禁用编辑；模拟器只写临时名单。

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

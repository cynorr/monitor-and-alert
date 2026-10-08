# 看盘服务运行逻辑

更新：2026-10-09。面向使用者；实现入口见 [development.md](development.md)，UI 总入口为 [ui.md](ui.md)，图表交互见 [chart-ui.md](chart-ui.md)，持仓显示见 [holdings-ui.md](holdings-ui.md)。

## Alert 与入选规则

Alert 的范围、Regular 触发、Scan/Monitor 共用、持久化、图表操作、卡片与后台声音只在 [alert.md](alert.md) 维护。手动及 Alert 移入 Focus 的重新分类与 section 首位规则只在 [list-design.md](list-design.md#统一移入-focus) 维护。两项已接入现有后台；实际验证范围见 [validation.md](validation.md)。

Alert 悬停价格胶囊、双图改价及其删除操作见 [Alert 图表交互](alert.md#图表交互)；图表统一线段虚线、横纵独立的自由十字线和 Vol 显示只在 [Chart UI](chart-ui.md) 维护。

## 启动与接收

正式服务启动选择 `runtime/days/` 下目录名为 YYYY-MM-DD 且含 workspace.json 的最新日期，读取 focus，开始接收当前名单的 Quote 与 SDK 实时 candle，同时初始化近期行情缓存；配置SnapTrade后也接收当前Holdings的行情。显式 `--workspace` 则固定使用该文件。Longbridge 的定位、官方前复权、Regular 范围、缓存替换与刷新时机只在 [longbridge-data.md](longbridge-data.md) 维护。

Quote 统一接收和校验，regular 与 extended 按时段保存最新值，两者均不落盘。Quote 更新最新价格、持仓估值与 Alert；各周期活跃 candle 独立接收 SDK 推送。页面选股不改变券商订阅范围。关闭网页不停止后端。

## Additional Info

公司名、行业大类/小类、市值和财报日期独立于行情、筛选和账户，允许缺失，不等待或影响系统 Ready。后台单独刷新并保留成功缓存；页面选择只读本地内存。Scan 历史日期也显示当前参考信息。数据源、处理、刷新及财报文字的唯一需求见 [additional-info.md](additional-info.md)，位置见 [Chart UI](chart-ui.md#headers-and-information)。

## Holdings

Holdings 是独立的只读持仓来源，按买入 sequence 显示，允许同 ticker 多个买入批次，后端可与 Focus 重复，常规 List 前端屏蔽 Holdings 已有 ticker。它不检查或修改观察名单归属，不参与名单新增、排除、移动或排序。点击持仓复用现有 Daily/Intraday；名单刷新、折叠或从 Focus 删除同 ticker 不改变持仓的选择来源。被选持仓批次消失时改选第一条持仓，持仓为空则回到观察名单。

持仓排序只影响当前页面，不修改账户数据或 workspace；行情更新沿用当前排序。Holdings固定在下方名单滚动区之外，可整体折叠。布局、列、数值格式、排序按钮和买卖明细的唯一要求见 [holdings-ui.md](holdings-ui.md)。

账户刷新、买卖归属、余仓P/L、当日建仓P/L Day基准、短期Days与当日清仓记录的唯一数据需求见 [holdings-data.md](holdings-data.md)。P/L与P/L %总计仅计剩余仓位，P/L Day总计加入当天清仓的已实现日盈亏。当日新仓NEW、整数账户总值与延迟时才显示的刷新时间见Holdings UI。它与Focus共用既有行情任务和图表，数据获取仍在单进程中独立维护。

## Scan 与后台数据任务

启动默认 Monitor，可用 --mode scan。页面在列表面板内切换展示，所有浏览器会话跟随这个选择。正式服务的Longbridge与SnapTrade任务仅在整体退出时停止；Scan使用Massive数据，后台仍只跟踪最新Focus及已接受Holdings。切回Monitor复用连接、任务和缓存。Mock Scan仍离线；只有明确切入Monitor才启用Longbridge，回到Mock Scan时停止。

Scan 读取上游 runtime/massive/daily.sqlite3，截至选择日期最近最多1000根日 K，只有closed日图，没有实时active或分钟线。Focus 在Scan中也使用该上游来源；切回Monitor才使用runtime/longbridge/bars.sqlite3与SDK实时candle。两者复用同一Daily图表和计算，不拼接两个供应商的历史。

Massive 数据要求、拆股/整数成交量、来源时段与筛选配置统一见 [massive-data.md](massive-data.md)。Longbridge 数据要求统一见 [longbridge-data.md](longbridge-data.md)。读取、指标和图表不再做复权；两源共享格式与计算，数据互不干涉。Daily Symbol右侧可以显示本地Nasdaq目录名称，缺失正常留空，两模式共用。

全市场完成日期由上游提交 metadata.completed_date 发布；不从 MAX(ts) 猜测完成状态。页面 Refresh Scan 补齐并打开最新可用日，完成的步骤跳过，也不重算日期下拉框当前选中的旧日。指定日重算只由 CLI 的 scan --date D 执行；不带 --date 的 scan 命令重算本地库最新完成日。GET和图表选择不生成。内置Massive准备成功后自动生成截面；显式外部SQLite入口仍只读，普通Refresh仅生成缺失的最新日截面。日期下拉框仅显示已生成的日期。

正式服务启动触发一次Massive后台准备，依次完成Daily、split、SQLite和features；已有目标日及匹配行情版本的完整产物则跳过。免费Nasdaq目录由独立脚本维护；缺失/损坏或配置错误先于Massive请求失败，保留旧结果并提示。网络获取按数据要求有界重试；本地构建失败直接报错，派生SQLite删除后在下次运行重建。没有定时轮询。手动脚本与页面Refresh复用同一流程，GET、图表和切页不触发下载；同一时刻仅一份准备任务。

Daily与split统一按最新成熟交易日判断，保留ET18点门槛；周末/休市日不重复获取或构建。获取范围见数据要求。SQLite普通新日直接追加；旧raw或split结果变化则删除后全量重建。构建失败报错并删除不完整库，不做失败回滚。状态统一写runtime/pipeline-status.json；Daily、split、bars、features分别记录当前状态和成功产物。正常时日期下拉即可表示已生成日，不重复显示Ready日期/完成时间；仅未完成、处理中或失败时提示目标日及状态。候选配置/目录修改由CLI主动重算，不做自动版本重算，操作见 [Massive 操作](../README.md#massive-操作)。自动完成只让跟随最新日的页面继续跟随，历史日期保持不变；手动Refresh即使跳过全部步骤，也打开最新可用日。后台忙不阻止展示切换。

## List、Tag 与 Filter

需求背景与归属设计见 [list-design.md](list-design.md)，显示与交互的唯一规范见 [ui.md 的 List UI 章节](ui.md#list-ui)。

Scan 使用 Discover、Focus、Excluded 三个列表；Focus 跨日保留、两模式共享。Monitor 展示 Focus、独立 Holdings 和折叠 Review；Discover / Hidden / Extended / Broken / Under-50 不订阅 Longbridge。Review 预览来自本地 Massive Daily，加入 Focus 后才实时订阅；Excluded 盘中恢复依赖下一个完成日扫描或人工加入。

候选按 [Massive 数据要求](massive-data.md#独立配置与处理顺序) 完成初筛和RFL排名。候选、Focus和全部Excluded（含Hidden）均计算完整特征与Growth所用RFL数值，即使继承成员不在候选或前50也继续计算，不为名单另行排名；详细范围见 [名单完整特征范围](massive-data.md#名单完整特征范围)。已有人工成员不因候选门槛自动删除，短历史/缺数据不推断为Broken。启动在后台从本地Daily补齐旧截面缺少的成员特征，随后按名单规则分类，不触发下载。新日和重算发布后更新规则结果。

Tag 保存条件与用途：Setup用于潜力section/Review，Extended、Broken和Under-50用于淘汰，Label仅辅助观察；名称不决定用途。数值条件AND、分类选项OR，缺失值不匹配，Any不排除缺失。每只股票可以匹配多个Tag，按Setup定义顺序选一个主section；未匹配为Unclassified。

Tag 选择可为空，点击已选 Tag 再次取消；空选择不应用保存 Tag 筛选，全部定义仍参与自动分类。

Tag 图案与颜色独立保存，只影响展示；改名保留已有图案绑定。编辑外观草稿继续使用已指派及人工补充的匹配结果，只有修改条件才进入条件预览，不因调颜色改变名单归属或订阅。

Discover、Focus及非Hidden Excluded匹配负面规则立即进入Excluded对应section，优先级为Broken → Extended → Under-50；非Hidden Excluded不满足负面规则且匹配Setup进入Review。Review不强制每日清空，无Dismiss。Hidden表示人工未分类排除，七天内不参与规则判断。Hidden/Extended/Broken/Under-50七个自然日到期后解除本次排除、再次按规则分类；仍匹配负面条件继续排除，无释放保护期；重复匹配不每日续期。Review保留到人工处理或新负面判断。

规则Tag每天重算；人工补Tag、主section和保留Focus例外仅当天有效。Focus成员及同section内部人工排序跨日保留，新进入section成员置顶。没有匹配Tag不淘汰Focus。人工入选Focus当天优先，仍显示机器负面标签，次日重新接受规则。当日置顶独立于Tag和section，顺序跨Scan/Monitor共享；新置顶后黑框和图表移到下一个可见成员，取消置顶保留当前选择并回原section，跨List取消，新完成日继承时清空，同日刷新/重启保留。临时Filter只改变显示，不移动名单或改变订阅；修改草稿预览，Save才更新条件并重新分类已有本地截面。

Add to Focus清除排除状态并开始订阅；Exclude for 7 days（包括行删除）进入Hidden；Move to Discover/Release解除归属，仅当日候选返回Discover并立即按已有规则分类。扫描初筛和RFL排名不受Tag影响。批量操作一次同步落盘，历史日期名单只读。旧Focus/Wait合并为Focus，旧Hidden转Excluded/Hidden并保留期限。

搜索仍使用列表上方Search与/入口。Monitor通过同一Longbridge context的static_info验证新股票；Scan只读本地Daily。查询不写名单、不订阅。确认 Add 后默认加入 Focus，Focus section 的 + 使用指定组；具体入口与排序交互统一见 List UI。盘中可以调整 section，本次不新增 Quote 形态规则。保存失败回退内存并显示错误。

一个watchdog原生事件监听days，新日期workspace出现自动跟随；Monitor始终使用最新名单，历史Scan只读。外部修改自动重读，Focus变更立即同步行情范围；已有行情状态复用，排序/主section移动不重下载。只有同时不在Focus和Holdings才退订；已有行情缓存保留；重新加入按 Longbridge 数据要求初始化。两类实时列表都为空时清空图表并保留搜索入口。`--symbols`会话始终限制指定Focus子集并禁用编辑；模拟器只写临时名单。

## 行情同步与数据质量

Longbridge 调度、重试、恢复与窗口状态统一见 [longbridge-data.md](longbridge-data.md)。各来源的共用 Bar 字段、结构校验与 OHLC 原值规则见 [upstream-daily-data.md](upstream-daily-data.md)。

## 图表周期与指标

官方六周期 closed 数据存 SQLite，各周期 SDK open candle 和指标仅在内存。Daily 与 Intraday 的数据来源、成交量口径、初始化与恢复统一见 [Longbridge 数据说明](longbridge-data.md)。

Intraday 初始周期按美东开盘经过时间选择，之后保留手工选择。所有 chart 使用统一、可人工调整的初始 bar spacing；可见历史长度随间距与面板宽度变化。参数、周期控件、参考线和交互只在 [chart-ui.md](chart-ui.md) 维护。

所有图表的 Vol 同时显示后端计算的五交易日成交量比较；当前、历史悬停与缺失样本的统一需求只在 [Volume comparison](chart-ui.md#volume-comparison) 维护。

两模式共用 EMA10/20，Daily SMA50、Intraday SMA65，以及 Daily ADR20/ADV20。ADR20 是最近最多20根已收盘记录的 `(H-L)/L × 100` 均值，ADV20 是同窗口 `close × volume` 均值；停牌/稀疏记录按实际根数取窗口，不使用 turnover 改变公式。均线样本不足时不显示该线；上下界矛盾保留官方原值，也可能体现在派生指标中。

跨 closed 边界和回补期间保留上一份完整图表；本周期 closed 与 open 就绪后一次更新。Daily 不依赖 5m 刷新，报价与账户后台持续运行。

## Monitor 页面状态

刷新与 Ready 的数据含义见 [Longbridge 数据要求](longbridge-data.md#调度失败与状态)；Loading、Refreshing、Ready 与错误的显示只在 [Chart status](chart-ui.md#chart-status) 维护。

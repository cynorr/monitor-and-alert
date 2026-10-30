# 看盘服务运行逻辑

更新：2026-10-30。面向使用者；实现入口见 [development.md](development.md)，UI 总入口为 [ui.md](ui.md)，图表交互见 [chart-ui.md](chart-ui.md)，持仓显示见 [holdings-ui.md](holdings-ui.md)。

## Alert 与入选规则

Alert 的范围、Regular 触发、Scan/Monitor 共用、持久化、图表操作、统一未读提醒与后台声音只在 [alert.md](alert.md) 维护。手动及 Alert 移入 Focus 的重新分类与 section 首位规则只在 [list-design.md](list-design.md#统一移入-focus) 维护。两项已接入现有后台；实际验证范围见 [validation.md](validation.md)。

Alert 悬停价格胶囊、双图改价及其删除操作见 [Alert 图表交互](alert.md#图表交互)；图表统一线段虚线、横纵独立的自由十字线和 Vol 显示只在 [Chart UI](chart-ui.md) 维护。

## Intraday State

盘中状态是现有后台中的独立监控，Focus候选与当前余仓共享symbol计算，手动Alert生命周期保持独立。已读时Regular底色表达当前事实，未读时以最新一次报警方向／等级的边缘波浪提示；新报警覆盖旧记录，不保存通知历史。声音只随规则进入/升级发出，降级和恢复不补报。持仓未进入预警时，ADR数值仍按较强的上下行方向显示，不固定为上行；数值方向不等于报警等级。In Play自动聚集只改变展示顺序，不改workspace、section或Tag；全部报警共享仅显示于symbol row的未读提醒，section与Holdings标题不参与闪烁或驻留，任何方式选图或更新当前chart都标记该symbol已读，不区分主动/自动或等待加载，灰线不变。未读仅在所属Regular内有效，实际收盘即失效，睡眠跨收盘在唤醒后清理；不依赖Massive或Refresh。Focus/Holdings未读导航见[List交互](list-interactions.md#未读-alert-导航)。当前Scan Focus共用同一份Longbridge状态，历史Scan不显示当前状态。完整公式、参数、范围、量比与排序规则只在 [intraday-state.md](intraday-state.md) 维护。

## 启动与接收

正式服务启动选择 `runtime/days/` 下目录名为 YYYY-MM-DD 且含 workspace.json 的最新日期，读取 focus，开始接收当前名单的 Quote 与 SDK 实时 candle，同时初始化近期行情缓存；配置SnapTrade后也接收当前Holdings的行情。显式 `--workspace` 则固定使用该文件。Longbridge 的定位、官方前复权、Regular 范围、缓存替换与刷新时机只在 [longbridge-data.md](longbridge-data.md) 维护。

Quote 统一接收和校验，regular 与 extended 按时段保存最新值，quote.latest按timestamp统一提供最后报价，均不落盘；最新价格、ADR盘中状态、持仓估值与手动Alert直接使用Quote。同日重启复用各周期已确认历史；下一交易日准备由现有后台持续调度，不依赖解锁操作。当天各周期SDK序列先用于图表和盘中计算，官方历史随后覆盖已闭合同timestamp，所有下游消费同一份最新值。价格状态与分钟量比独立显示，开盘不重建行情，刷新期间保留有效显示；页面选择只调整待加载数据优先级，不扩大订阅或触发下载。切模式复用三名单Quote订阅与缓存，Focus/Holdings后台持续运行。关闭网页不停止后端。

## Additional Info

公司名、行业大类/小类、市值和财报日期独立于行情、筛选和账户，允许缺失，不等待或影响系统 Ready。后台单独刷新并保留成功缓存；页面选择只读本地内存。Scan 历史日期也显示当前参考信息。数据源、处理、刷新及财报文字的唯一需求见 [additional-info.md](additional-info.md)，位置见 [Chart UI](chart-ui.md#headers-and-information)。

## Holdings

Holdings 是独立的只读持仓来源，按买入 sequence 显示，允许同 ticker 多个买入批次，后端可与 Focus 重复，常规 List 前端屏蔽 Holdings 已有 ticker。它不检查或修改观察名单归属，不参与名单新增、排除、移动或排序。点击持仓复用现有 Daily/Intraday；名单刷新、折叠或从 Focus 删除同 ticker 不改变持仓的选择来源。被选持仓批次消失时改选第一条持仓，持仓为空则回到观察名单。

持仓排序只影响当前页面，不修改账户数据或 workspace；行情更新沿用当前排序。Holdings固定在下方名单滚动区之外，可整体折叠。布局、列、数值格式、排序按钮和买卖明细的唯一要求见 [holdings-ui.md](holdings-ui.md)。

账户刷新、买卖归属、余仓P/L、当日建仓P/L Day基准、短期Days与当日清仓记录的唯一数据需求见 [holdings-data.md](holdings-data.md)。P/L与P/L %总计仅计剩余仓位，P/L Day总计加入当天清仓的已实现日盈亏。当日新仓NEW、整数账户总值、延迟时才显示的刷新时间及点击查看错误原因/处理建议的轻量入口见Holdings UI；成功刷新自动清除当前错误，不主动弹出通知。它与Focus共用既有行情任务和图表，数据获取仍在单进程中独立维护。

## Scan 与后台数据任务

启动默认 Monitor，可用 --mode scan。页面在列表面板内切换展示，所有浏览器会话跟随这个选择。正式服务的Longbridge与SnapTrade任务仅在整体退出时停止；Scan使用Massive数据，后台仍只跟踪最新Focus及已接受Holdings。切回Monitor复用连接、任务和缓存。Mock Scan仍离线；只有明确切入Monitor才启用Longbridge，回到Mock Scan时停止。

Scan 读取上游 runtime/massive/daily.sqlite3，截至选择日期最近最多1000根日 K，只有closed日图，没有实时active或分钟线。Focus 在Scan中也使用该上游来源；切回Monitor才使用runtime/longbridge/bars.sqlite3与SDK实时candle。两者复用同一Daily图表和计算，不拼接两个供应商的历史。

Massive 数据要求、拆股/整数成交量、来源时段与筛选配置统一见 [massive-data.md](massive-data.md)。Longbridge 数据要求统一见 [longbridge-data.md](longbridge-data.md)。读取、指标和图表不再做复权；两源共享格式与计算，数据互不干涉。Daily Symbol右侧可以显示本地Nasdaq目录名称，缺失正常留空，两模式共用。

全市场完成日期由上游提交 metadata.completed_date 发布；不从 MAX(ts) 猜测完成状态。页面 Refresh Scan 补齐并打开最新可用日，完成的步骤跳过，也不重算日期下拉框当前选中的旧日。指定日重算只由 CLI 的 scan --date D 执行；不带 --date 的 scan 命令重算本地库最新完成日。GET和图表选择不生成。内置Massive准备成功后自动生成截面；显式外部SQLite入口仍只读，普通 Refresh 仅生成缺失的最新日截面，但即使准备跳过仍清理人工状态并重新分类。日期下拉框仅显示已生成的日期。

正式服务启动触发一次Massive后台准备，依次完成Daily、split、SQLite和features；已有目标日及匹配行情版本的完整产物则跳过。免费Nasdaq目录由独立脚本维护；缺失/损坏或配置错误先于Massive请求失败，保留旧结果并提示。网络获取按数据要求有界重试；本地构建失败直接报错，派生SQLite删除后在下次运行重建。没有定时轮询。手动脚本与页面Refresh复用同一流程，GET、图表和切页不触发下载；同一时刻仅一份准备任务。

Daily与split统一按最新成熟交易日判断，保留ET18点门槛；周末/休市日不重复获取或构建。获取范围见数据要求。SQLite普通新日直接追加；旧raw或split结果变化则删除后全量重建。构建失败报错并删除不完整库，不做失败回滚。状态统一写runtime/pipeline-status.json；Daily、split、bars、features分别记录当前状态和成功产物。正常时日期下拉即可表示已生成日，不重复显示Ready日期/完成时间；仅未完成、处理中或失败时提示目标日及状态。候选配置/目录修改由CLI主动重算，不做自动版本重算，操作见 [Massive 操作](../README.md#massive-操作)。自动完成只让跟随最新日的页面继续跟随，历史日期保持不变；手动Refresh即使跳过全部步骤，也打开最新可用日。后台忙不阻止展示切换。

## List、Tag 与 Filter

需求背景与归属设计见 [list-design.md](list-design.md)，显示见 [List UI](ui.md#list-ui)，交互的唯一规范见 [List 交互](list-interactions.md)。

Scan 使用 Discover、Focus、Excluded 三个列表；Focus 跨日保留、两模式共享。Monitor 展示 Focus 与独立 Holdings；Discover 与全部 Excluded 的日 K 和分类使用本地 Massive Daily，Scan/Monitor均为完整三名单保留Quote；最新Scan日显示最新报价，Monitor双图也显示扩展报价价格轴标签（规则见Longbridge数据要求），不启动其完整行情或Alert。自动Excluded仅显示当天候选的规则结果、不保存成员身份；跨日只继承Focus和有效Hidden，Focus每日自动淘汰保留，非候选淘汰后退出当前名单。盘中明确入选Focus才开始完整实时监控。Scan 全局搜索确认后进入当日 Discover 置顶，不建立临时预览或跨日保存；新增与继承细则见 [List 设计](list-design.md#三个列表)。

候选按 [Massive 数据要求](massive-data.md#独立配置与处理顺序) 完成初筛和RFL排名。候选、当日人工Discover、Focus和有效Hidden计算完整特征与Growth所用RFL数值，继承成员不另行排名；详细范围见 [名单完整特征范围](massive-data.md#名单完整特征范围)。历史机器Excluded不扩大计算范围；Focus不因候选门槛、短历史或缺数据直接淘汰。启动在后台从本地Daily补齐旧截面缺少的有效成员特征，随后按名单规则分类，不触发下载。新日和重算发布后更新规则结果。

Tag 保存条件与用途：Setup用于Discover/Focus分组，Extended、Broken和Under-50用于机器排除，Label仅辅助观察；名称不决定用途。数值条件AND、分类选项OR，缺失值不匹配，Any不排除缺失。每只股票可匹配多个Tag，按Setup定义顺序选主section；未匹配为Unclassified。人工补充仅允许Setup/Label。

Tag 选择可为空，点击已选 Tag 再次取消；空选择不应用保存 Tag 筛选，全部定义仍参与自动分类。

Tag 图案与颜色独立保存，只影响展示；改名保留已有图案绑定。编辑外观草稿继续使用已指派及人工补充的匹配结果，只有修改条件才进入条件预览，不因调颜色改变名单归属或订阅。

完成日Daily和feature准备后，按 [每日规则](list-design.md#每日规则) 统一计算候选归属和Focus淘汰；机器分类不落盘。有效Hidden继续屏蔽，到期仅当天候选重新分类。分类复用已有算子和Tag匹配，不增加定时扫描。

规则 Tag 每日重算；人工调整在普通更新/重启时保留，显式 Refresh 与新日首次分类共用清理逻辑，再执行 Focus 淘汰和候选分类。清理范围、Hidden 期限及入选规则只在 [List 设计](list-design.md#每日规则) 维护。Filter 仅影响显示，不改变归属或订阅。

名单操作直接作用于单只 symbol；机器 Excluded 禁止人工释放，Hidden/Focus 释放后重新分类。快捷键、行按钮和限定自动下一只见 [List 交互](list-interactions.md)。Holdings 与 Monitor 的名单删除按键维持既有边界。

搜索仍使用列表上方Search与/入口。Monitor通过同一Longbridge context的static_info验证新股票；Scan只读本地Daily。查询不写名单、不订阅。确认 Add 后默认加入 Focus，Focus section 的 + 使用指定组；具体入口与排序交互统一见 List UI。盘中可以调整 section，本次不新增 Quote 形态规则。保存失败回退内存并显示错误。

一个watchdog原生事件监听days，新日期workspace出现自动跟随；Monitor始终使用最新名单，历史Scan只读。外部修改自动重读，Focus变更立即同步行情范围；已有行情状态复用，排序/主section移动不重下载。只有同时不在Focus和Holdings才退订；已有行情缓存保留；重新加入按 Longbridge 数据要求初始化。两类实时列表都为空时清空图表并保留搜索入口。`--symbols`会话始终限制指定Focus子集并禁用编辑；模拟器只写临时名单。

## 行情同步与数据质量

Longbridge 调度、重试、恢复与窗口状态统一见 [longbridge-data.md](longbridge-data.md)。各来源的共用 Bar 字段、结构校验与 OHLC 原值规则见 [upstream-daily-data.md](upstream-daily-data.md)。

## 图表周期与指标

官方六周期 closed 数据存 SQLite，各周期 SDK open candle 和指标仅在内存。Daily 与 Intraday 的数据来源、成交量口径、初始化与恢复统一见 [Longbridge 数据说明](longbridge-data.md)。

Intraday 初始周期按美东开盘经过时间选择，之后保留手工选择。所有 chart 使用统一、可人工调整的初始 bar spacing；常规可见历史长度随间距与面板宽度变化。Daily使用近期已完成收盘中位数锚点和统一线性百分比/间距比例，横纵等比缩放；远端历史、报价和价格线不扩大常规视图。Daily的Reset与按住F临时全貌只改变显示，历史Scan不跳日期，也不触发下载；Intraday保留原生缩放。背景、参数、周期控件、参考线和完整交互只在 [Chart UI / Daily setup scale](chart-ui.md#daily-setup-scale) 维护。

所有图表下方面板显示成交额及后端计算的五交易日成交额比较，tooltip保留原始股数；显示与缺失规则只在 [Turnover comparison](chart-ui.md#turnover-comparison) 维护。Intraday State 的量比、等级、排序和现有报警继续使用原始 volume，本轮不迁移报警。

两模式共用 EMA10/20，Daily SMA50、Intraday SMA65，以及 Daily ADR20/ADV20。ADR20 是最近最多20根已收盘记录的 `(H-L)/L × 100` 均值，ADV20 是同窗口 turnover 均值；停牌/稀疏记录按实际根数取窗口，缺少成交额则 ADV20 缺失，不用 close×volume 补值。均线样本不足时不显示该线；上下界矛盾保留官方原值，也可能体现在派生指标中。

跨 closed 边界和回补期间保留上一份完整图表；本周期 closed 与 open 就绪后一次更新。Daily 不依赖 5m 刷新，报价与账户后台持续运行。

## Monitor 页面状态

刷新与 Ready 的数据含义见 [Longbridge 数据要求](longbridge-data.md#调度失败与状态)；Loading、Refreshing、Ready 与错误的显示只在 [Chart status](chart-ui.md#chart-status) 维护。

## Schwab Trade

Monitor / Scan / Trade 为互斥的全局展示模式。Trade 复用 Monitor 图表和 Focus，使用独立 Schwab Holdings，Monitor 继续使用 SnapTrade；账户数据、估值与成本不拼接。两个账户源和行情任务持续后台运行。Trade 的字段、隐式 Entries/Holdings/Sold Today、汇总 Buy/当天 Sold/活动 Stop、明细参考盈亏、Entry/Trim、固定交易卡片、单次 Send、盘外止损改单、独立短暂 Accepted 反馈与网关边界只在 [Schwab Trade MVP](schwab-trade.md) 维护。

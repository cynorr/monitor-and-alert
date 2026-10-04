# 开发维护手册

更新：2026-10-03。此文件供 Codex/Claude Code 和维护者使用；产品行为以 [behavior.md](behavior.md) 为准，UI 以 [ui.md](ui.md) 为准。历史证据见 [validation.md](validation.md)。

## 文件与依赖

| 文件 | 唯一职责 |
| --- | --- |
| data_service/__main__.py | CLI、单实例锁、生命周期、有限运行报告 |
| workbench.py | 同一 Workspace、Scan/Monitor展示、持续后台行情/账户及本地Scan API |
| paths.py / network.py | 唯一runtime布局、显式共用HTTP代理/session与Massive凭证读取 |
| massive/daily.py / splits.py / build.py | 原始Daily补文件、两年split覆盖、流式拆股复权SQLite发布 |
| pipeline.py | 一次准备任务、阶段重试、产物核对及统一Ready状态 |
| scan.py | 上游只读连接、完成日截面/发布、Scan 日图 |
| features/atomic.py / screening.py / snapshot.py | 原子纯算子、初筛/排名、每只一次截面组装 |
| preferences.py | Tag 保存契约；读取唯一 filter-catalog.json |
| config.py | 当前 focus/wait 解析、凭证读取、错误脱敏 |
| workspace.py | 最新日期选择、内存 JSON、同步直接写入、单个原生文件事件 watcher |
| broker.py | 单 SDK context、static_info 添加验证、最近 K 线、Quote 请求、全局/后台请求预算 |
| snaptrade.py | 独立异步签名GET、指定账户、10次/滚动分钟预算、原始快照获取与成功提交；不提供HTTP服务、不调用Longbridge |
| holdings.py | 原买卖关联/Decimal会计、30秒刷新任务、失败保留完整结果、Quote重估值；不含网页/端口/券商SDK |
| calendar.py | UTC/ET、XNYS、实际闭合边界、5m 到 4h 时间网格 |
| downloader.py | 每次一页 fetch/parse/validate/写入，追加 OHLC 比较日志 |
| store.py | 官方 bars、最近窗口批次、事务及 revision |
| validator.py | 最近窗口完整性检查与缓存；不联网、不写状态文件 |
| service.py | 每个 ticker/官方周期一份 SyncState，排序、执行、重试、恢复；API 组合 |
| quotes.py | 共用 Quote 标准化入口、时段最新值、snapshot/watchdog、恢复通知 |
| resample.py | 所有内存周期合成的唯一算法 |
| charts.py / indicators.py | 活跃 candle、官方/合成显示、图表缓存；唯一指标公式 |
| http_api.py | aiohttp 静态页面、诊断 HTTP、List mutation、WebSocket/Origin 校验 |
| ui/src/main.ts / types.ts | WS 选择与重连、显示状态、契约 |
| ui/src/list.ts | 统一内联搜索/新增、输入查询生命周期、拖动/快捷键移动、折叠和报价行更新 |
| ui/src/holdings.ts | 独立九列/盘中八列单行表格、单列降序/取消、自然宽度测量、整体折叠、批次选中、逐笔Buy/Sold日期/数量/实际成交价明细 |
| ui/src/scan.ts / filters.ts / tags.ts | 日期/四列表、唯一条件匹配、Tag 草稿与保存 |
| scripts/build_scan_mock.py | 明确指定目录的合成日 K/截面/测试名单 |
| ui/src/chart.ts / layout.ts | Lightweight Charts、日联动、列宽和原生交互 |
| simulator/market.py / server.py | 隔离历史/Quote/时钟，复用正式流程，单一网站入口 |
| scripts/live_check.py | 明确执行的有界 live 验收；临时库、单连接 |

依赖方向：UI → Data API → Workbench → Scan或DataService → store/indicators/quotes。正式data不import simulator，Scan算子不依赖SDK。pandas/numpy用于共用指标与特征；Quote preview仍使用缓存标量，不逐次重建DataFrame。不增加 services 层、指标数据库或事件日志协议。

持仓排序仅在ui/src/holdings.ts中将原账户顺序扁平化为买入批次，按原始标量稳定降序；不修改服务器数据。仅顺序变化时移动已有主行/买卖行DOM，保留选中与焦点，键盘按显示顺序导航。Net Liq、P/L、P/L Day整数为显示格式，后端Decimal契约不变。展开直接使用既有sequence.buys/sells，所有Buy先于Sold；日期/数量/金额与买卖记录均纳入结构签名，刷新后更新明细。Sold=0隐藏主行数值及展开箭头；已卖批次明细成交价为value/quantity，放在第七列Chg%对应位置，主表无Trade Price。P/L %/Chg%使用一位小数，Ext仍两位；无副标题DOM或PNG生成/下载逻辑。表格以同样CSS的临时隐藏副本测量自然内容宽度，onWidth经main.ts交给layout.setHoldingsWidth；字符位数与结构未变时不重复克隆，不在每次Quote上重新测量。layout默认锁定内容所需列表宽度、双图平分余量，不读写旧列宽localStorage；展开所需宽度增加时自动增长，收起不引起宽度抖动。main.ts复用board与当前view中既有Quote.current_regular_session，任一为true即进入常规时段；前端不新增交易日历或券商请求。Holdings用同一CSS隐藏第八列Ext，取消隐藏列排序；时段显隐切换清空测量宽度下限，使盘中能够回收该列空间、扩展时段重新测量。手动拖动仅本页面有效，双击/新页面恢复默认。没有新增HTTP、券商请求或后台任务。

## 模式与上游数据

同一个服务、同一个Workspace、一个全局展示模式。正式serve在HTTP可响应后启动一次Broker/DataService与Holdings；切Scan不停止它们，服务关闭才cancel/await并释放context/store/session。Mock Scan与有界--symbols禁用Massive与真实账户；Mock明确切Monitor才构造Longbridge，回到Mock Scan时释放。后台准备与展示切换分离，仅禁止重复生成，不建立第二个服务或通用source接口。

bars契约见 [upstream-daily-data.md](upstream-daily-data.md)。RuntimePaths统一所有正式路径：massive/daily原始文件、massive/splits.json、massive/daily.sqlite3、longbridge/bars.sqlite3、holdings与days；继续接受--runtime。正式Workbench和reconcile/verify注入Longbridge新路径；DataService独立/模拟器默认临时bars路径保持。两库共用BAR_SCHEMA、Bar、read_bars与指标，Daily ts为ET零点转Unix秒；不混库或拼接历史。显式--daily-db是只读外部入口，不运行内置Massive。

build_day仅对D当日有bar的symbol生成截面，分三步：全市场每只read_bars最多20根，用indicators.adr_adv计算ADR/ADV并初筛；仅eligible每只最多126根，用return_from_low计算三组RFL并排名；仅candidate每只最多1000根，由feature_row建立EMA/SMA/ATR及原子特征。daily_metrics组合相同两个纯算子，图表与特征不重复维护公式。候选初筛只有ADR/ADV，取消Price≥5门槛；并列仍按symbol顺序、rank(method=first)，各取前50的并集。非候选快照只保留轻量指标，不补算原子特征。

每步只保留单只历史与全市场标量，避免全市场历史fetchall；读到的bar均验证闭合/结构。checked_history复用Bar.validate，OHLC范围矛盾保留原值；后续阶段仅为上一窗口起点之前的矛盾追加日志，避免一次生成内重叠窗口重复记录。阶段耗时和证券/候选数量写普通日志，不新增指标持久化或性能框架。真实样本线程对照：单线程1000只约0.46秒、四线程约1.12秒；不添加更慢的线程池。全日生成继续在现有asyncio.to_thread中执行，不阻塞HTTP/WS事件循环。

latest_completed_date只读取上游metadata.completed_date，禁止用MAX(ts)回退推断；缺少完成日则失败并保留原状态。CLI scan未传--date、页面Refresh未传date时用该完成日，build_day继续拒绝未收盘日或无当日bar。成功后同步publish_day、reload workspace并明确选中新生成日期，首次才创建workspace。相同日期重算不重新继承；生成失败释放busy并保留原日期/名单。离线scan和serve共用runtime单实例锁，运行中的生成通过POST /v1/scan。

只保存days/D/scan.json一份截面，不保存逐根指标序列或Parquet。Scan板只传四列表实际成员，snapshot按mtime缓存，前一候选与图表按日期缓存；重算/修订清缓存。run_id在模式/日期/生成变化时更新，WS据此重发完整历史；UI保留mode/request_id/socket身份检查。Scan没有Quote active、Intraday或Ready实时状态；Daily复用同一个Panel。

indicators.py是唯一EMA/SMA/TR/Wilder ATR/ADR/ADV/RFL入口。ADR/ADV窗口统一最近最多20根实际记录；ADV固定close×volume均值，turnover不参与该公式。指标只消费已选来源的价格，Massive拆股复权与Longbridge NoAdjust结果允许不同。

复权契约：Longbridge broker.py继续显式请求AdjustType.NoAdjust与TradeSessions.Intraday，保持官方原始OHLC与整数成交量。Massive raw文件adjusted=false，build按split快照对事件之前的价格/VWAP乘累计split_from/split_to、成交量除同因子，最终用Decimal ROUND_HALF_UP保存整数量；turnover仅使用同根VWAP乘未取整的复权量，否则NULL。Massive metadata明确split_adjusted/half_up/massive_daily，两源不互相验证。读取、指标和图表不再复权；Longbridge未来复权未实现。pandas ewm(adjust=False)仅是加权算法参数。

38项条件目录仅ui/src/filter-catalog.json一份，后端读取该文件验证保存契约，前端filters.ts唯一执行匹配。保存值不取整；旧maxExclusive语义保留到主动编辑。Tag草稿不写盘，Save写完整preferences后才更新内存，失败保留草稿；不建立长期多版本猜测/迁移框架。

## Massive准备与统一状态

正式serve启动一次MassivePipeline.run；手动massive命令/脚本及页面Refresh复用它，无周期定时器。单任务串行执行Daily→split→bars→features；仅正在执行的阶段做首次加三次重试(2/5/10秒)，失败保留旧产物并在状态中报错。网络失败不回退直连。HTTP/WS/图表读取不安排任务。

network.proxy_url统一读取MARKET_PROXY，默认http://127.0.0.1:7899，显式空值直连；create_session禁用trust_env。Massive和SnapTrade显式传proxy，但各自保留限流、签名、解析和session。Massive凭证读取MASSIVE_API_KEY或单行massive-token.txt，日志不得包含值、带key的URL或任意上游响应体。

Daily保持原始文件不变，最近14天只补文件缺失，ET18点之前不取当天，目标交易日由XNYS决定。Split每次完整分页获取target_end往前两年窗口，保留窗口之前记录，用本次窗口替换旧窗口，验证覆盖与唯一ID后atomic_json提交。两者共用Massive请求预算，开始请求间隔至少15秒。SQLite逐个日期解析并写临时库，复用Bar验证/原值上下界日志，保留每symbol最近最多1000根，不使用全历史DataFrame或进程池；完成日与input_revision元数据一起发布，成功才替换旧库。

pipeline-status.json仅维护daily/splits/bars/features，不保留extended字段。Ready从已提交文件、SQLite metadata及scan.json的输入版本核对，遗留running不当作成功，Ready跳过下载时也重写规范状态。input_revision标识原始文件和split快照对应版本；features与bars版本一致才是本轮Ready。Scan截面和首次继承的workspace用atomic_json发布，同日已有人工workspace不改写；普通人工编辑仍保持原直接写入流程。自动完成通过Workbench回调清缓存和重读workspace，不切展示模式，不抢历史日期；手动Refresh可以打开生成日期。features状态经现有WS list传输，UI不另起轮询或连接。首份scan缺失但有workspace时页面返回空Scan与准备状态。

三个复制项目均只作参考，正式代码不import或执行它们。Daily、SQLite、状态、账户缓存、凭证与临时文件Git忽略，唯一放行runtime/massive/splits.json。旧库和原始参考数据保留；正式服务不连接或合并旧库历史，新Longbridge库按既有最近1000根流程初始化。

## Workspace 与动态名单

watchdog 6 使用平台 Observer（macOS 为 FSEvents），只建一个递归 watcher；线程仅把事件派发回 asyncio loop。默认跟随 days 最新文件；显式 --workspace 监听该文件父目录并固定文件。创建、修改、移动、删除事件触发重读，无定时扫描。自身写入产生的事件在 JSON 相同情况下不重复更新。

Workspace 直接维护原始 JSON，读取 focus/wait 和 statuses（statuses 决定观察名单行情范围，Holdings另由账户快照提供；数组负责排序）；普通Focus/Wait移动修改相应数组和主动ticker的status/status_at；新增/删除移除该ticker旧hidden排序，删除清status。Scan批量移动验证当前来源归属后一次写入三组orders、status与必要的carried/discover_order。status_at使用所操作workspace日期。保留所有其他数据。无 schema migration/validation 层、repository 层、锁、临时文件或写队列。文件为空或无法解析时显示读取错误，下一文件事件再读取，不建立恢复协议。

Workbench持有唯一workspace回调，Monitor通过update_tickers接收变更；独立模拟器继续使用DataService.attach_workspace。update_tickers 同步更新当前白名单、调度任务及选择。删除任务取消并在退出时收尾；保留成员复用 SyncState。QuoteService 用内存事件唤醒现有 Quote loop，按 subscribed 与当前成员差集增删订阅；失败沿用重连/30 秒重试。Broker 在等待额度后再次检查请求范围；unsubscribe 允许清理已移出白名单的 symbol。static_info 是搜索/添加前唯一可查询候选 ticker 的例外，验证本身不扩大行情白名单，仍共用全局限流及同一 context。

Holdings另由Workbench持有单个controller与轮询task，正式服务两种展示均持续启用；服务退出时先cancel并await持仓任务及其aiohttp session，再退出Monitor。SnapTrade凭证工厂在正式后台启动时使用，mock/only禁用工厂。原项目代码迁入维护路径，不import `schwab-review`。凭证文件与规则/账户缓存均git忽略，凭证权限600；CLI缺少凭证文件时不启用持仓。后台启动的第一个refresh位于timer sleep之前；展示切换不重建刷新任务；失败不调用成员更新、不提交raw缓存，下一周期再执行，没有额外即时重试。

DataService.tickers仍只包含workspace成员，board只输出Focus/Wait；holdings_symbols独立接收当前已接受持仓。唯一_update_symbols按两来源并集更新store/broker.allowed、Quote范围和SyncState，同ticker保持既有任务。它不调用static_info、不检查workspace归属、不写workspace。Holdings只在账户成功刷新时重建买卖关联；约1Hz list_state读取用已有Decimal批次标量与Quote重新估值，不重复匹配流水。前端selectionSource与buy_ids批次key分离于symbol，Watchlist更新不得覆盖持仓选择，HTTP/WS图表继续用原request_id/mode/socket保护。

SnapTrade固定请求配置account_id，不通过/accounts假设仅一个账户。成功核对后原始缓存只保存runtime/holdings/latest.json一份；activities分页仅属于SnapTrade成交历史，不改变K线count=1000约束。每轮重读sequences.txt/merge_buys.txt，明确关联与原错误检查不变。SnapTrade及Longbridge拥有独立额度，均在同一Python进程内运行，不新增监听端口或服务。

## 同步与状态

`service.sync[(symbol, timeframe)]` 是唯一任务记录。首次 pending+refresh；执行时 refresh 为 count=1000，其余 count=2。请求返回后使用同一窗口验证。正常完成记录 target，调度器发现新闭合目标时入队；跨多个闭合边界、Quote 恢复或循环暂停超过 30 秒重新请求最近 1000。

失败原地重试，首次最多 4 次请求，耗尽后下一个实际 5m 收盘+2 秒开启最多 3 次的新一轮。状态查询不改变任务。重连到达在途请求期间不能被该请求完成覆盖。reconcile 共用调度器，所有任务完成或本轮耗尽即退出。

全局滑动窗口 10 次/秒、5 在途；后台历史 8 次/秒、3 在途。等待后台额度不持有 limiter 锁；后台信号量在全局信号量之前取得。调度器也不提前发起超过 3 个后台历史任务，保留两个可插队槽。Quote 请求和正常到期更新走全局预算。

UI 契约仅 `status: {stage: loading|basic|full, errors: string[]}`。stage 根据五份任务最近的成功状态派生；每根正常新 bar 的 2 秒等待不会重置 Ready。未完成/恢复失败不宣称已验证。详细 `complete/target/latest/count/missing/errors` 只在诊断接口提供，不再暴露旧六组 readiness 标记。

## 存储与数据校验

Longbridge SQLite WAL/NORMAL，bars 主键 (symbol,timeframe,ts)，只允许 1d/5m/15m/30m/1h。OHLC 必须正数有限；volume 必须非负整数；必须 regular 且已经闭合。唯一range检测是`Bar.invalid_range`，用于downloader/Scan生成的JSONL追加。不得 clamp 原值。

旧库保留，turnover 缺列时仅 ALTER ADD COLUMN。batches 继续使用旧表结构，run_id 列留空字符串以兼容旧表；payload 仅保存最近窗口起点、请求/返回数量、as_of 和无法使用的返回项。旧 metadata 表不再读取/维护，也不破坏已有表。旧 data_ready.json / history_symbol_usage.json 均不再读取或更新。

count=1000 返回确定新的 window_start；count=2 延续窗口。实际读取最多最近 1000 根并过滤起点之前的旧记录。历史空档不检查；缺失仅检查最新应闭合目标。重复/无法绘制的修订撤下旧值，合法新值可恢复；仅 range 矛盾永不撤下。

官方数据值实际改变才增加 bars revision；批次/质量变化增加质量 revision。图表比较最终显示序列，内容未变不重发。validator 按质量 revision 和当前目标缓存结果，HTTP 不重复扫描不变数据。返回数据逐根合法性检查在数据变化后执行；不建立持久化完整性水位。

## 合成和时段

resample 接受统一 5m 行结构，按 calendar 网格分组，O首/H最大/L最小/C末，量与额相加。闭合组必须有齐全的 5m 槽；活跃组可展示当前近似值。按交易日分组，处理 DST、提前收盘、常规尾根。2h/4h 从不读取官方 1h 作为基础，也不发额外历史请求。

15m/30m/1h 显示按 timestamp 合并“5m 合成 + 官方优先”，官方到达即通过现有 revision 消息替换。5m 临时 candle 从本进程收到的第一条 Quote 起算；更大活跃 candle 也复用 resample。合成和临时 candle 绝不写入官方 bars。

Quote 接收不按 UI 选择筛选；regular/pre/post/overnight 共用 apply，按时段保留最新值。snapshot 归一化后走同一入口。倒序拒绝、旧 callback 代次保护继续保留。扩展时段只改价格展示，不改 regular candle。

### Active 成交量

`ChartCache.volume_baselines[symbol]` 仅存当前 5m 的 Quote 起点累计量。跨入相邻桶时取上一条 regular Quote；每次新 Quote 做一次减法，重复推送不累加。首次盘中启动、跨桶缺失、恢复或累计量回退时清空基准；无基准显示 null，不用全天累计量兜底。恢复同时清掉旧 Quote，避免把断线期间的增量归给新桶。

`closed_volume(symbol, tf, start, end)` 只算 active 所在周期内 `[start, 当前5m起点)` 的官方 closed 量，按 1h/30m/15m/5m 贪心覆盖，每段恰好使用一次，缺口不能跳过。较大周期可覆盖缺少的 5m；跨越 end 的 bar 不参与。每个 symbol/tf 缓存一个总量（或 null），签名为起止时间及四个官方周期的 store revision；新柱、修订、撤回或换桶自动失效。不为每次 Quote 读库或重算历史 sum，OHLC 的统一 resample 不重复计算这份成交量。

Daily 保持累计量；2h/4h 的闭合 OHLCV 仍只由 5m 合成。这里的大周期优先只用于 active 成交量的已闭合部分。临时量基于收到的 Quote，推送跨边界合并或口径差异可能导致其与最终官方量有差别，闭合后以官方数据为准。

## 传输

同源 HTTP 静态资源与 `/v1/universe`；`/health`、`/v1/quotes`、`/v1/bars`、`/v1/readiness`、`/v1/chart` 为只读诊断。`/v1/chart` 不改变优先级。

UI 图表只通过 `/v1/stream`：select消息含symbol/timeframe/request_id/mode；旧模拟器仍可省略mode。初次、选择、重连为完整 bars+指标；常规只传 active/indicator_preview/status，历史改变才重发。约 5Hz 图表预览、1Hz 独立 list 消息。list 不依赖选中 symbol/request_id，所以删空、删当前项或重连时仍可刷新名单；图表继续保留 request_id 校验。run_id标识后端实例和当前数据上下文，request_id 与 socket identity 防止串图。保留 heartbeat、慢客户端独立发送任务和 Origin 校验；不新增差量重放协议。

list_state增加独立holdings字段：未启用或Scan为null；启用为{data,loading,error}。data保留旧fetched_at/source_timestamps/positions_as_of/pnl_basis/funds/summary/holdings契约和Decimal字符串，holding增加price_source/price_timestamp/price_session、change_percent/extended_percent/day_reference_price；sequence与summary增加可空day_pnl。Workbench通过monitor.quote读取与观察名单相同的Daily修正基准，再由holdings.py用Decimal重算日盈亏；缺基准不返回部分总额。无新增SDK请求、下载任务或缓存文件。GET /v1/holdings返回同一只读状态；请求不刷新账户、不安排历史。Account Value从估值市值加SnapTrade现金计算，原details账户总值仍在原始缓存，不冒充相同时刻的券商官方净值。本机WS关闭可选压缩，避免大图表/持仓快照发送时快速重载遗留aiohttp压缩后台task。

List 动作接口：`POST /v1/list`，Content-Type 为 application/json，接受只读候选查询 `{action:"lookup",ticker}`（返回 `{ticker,name}`，不修改 workspace/白名单/订阅/调度）及 `{action:"add",ticker,section}`、`{action:"delete",ticker}`、`{action:"move",ticker,section,index}`。index 为移除主动 ticker 后目标数组的零基位置。修改动作返回 `{board,editable,mode,workspace_error,notice?}`，成功响应前已同步落盘；WS `{type:"list",...}` 复用同一结构。校验同源 Origin；诊断 GET 继续只读。`--symbols` 仅跟踪指定子集，禁用 mutation 以保持验收范围。

Scan批量动作同样使用POST /v1/list：`{action:"move",tickers:[...],source:"discover",target:"focus"}`。列表状态增加app_mode、date、dates、preferences和mock；历史Scan日期或--symbols不可写。POST /v1/mode切换模式，POST /v1/scan选择/生成日期，POST /v1/preferences同步保存完整偏好；所有写入复用同源检查，body上限64KiB。生成不会改已有日期的人工workspace。

新日继承Focus/Wait并写carried；Hidden保留原Scan的7个自然日/前后candidate交集规则，derive_day_view派生Discover/New/Returned。正式默认days改为runtime/days；本次一次复制15份旧正式workspace和7个现有Tag，原数据保留。原始拷贝目录仅参考并被git忽略，正式模块不import它。

前端只有一套 Search 状态（目标 Section、候选、提示与在途 lookup）。/ 和 + 共用入口，唯一差别是目标Section；Scan查询本地只读SQLite，Monitor使用static_info。输入后 1 秒延迟只用于 lookup，写文件仍同步立即执行。输入变化/退出会取消等待及 fetch，并以 Search 对象身份忽略迟到结果；Enter 复用正在执行的 lookup。最终 add 仍由后端验证，不能信任前端传来的证券名称。Shift 换序复用 move，目标 index 为移除主动 ticker 后的位置，不新增 swap 接口。

## 检查与真实测试

```bash
.venv/bin/python -m pytest -q
npm run check --prefix ui
npm run build --prefix ui
npm run test --prefix ui
```

默认测试全部离线，只绑定本机 HTTP/WS，覆盖白名单、日历、OHLC 原值/日志、无法绘制的输入、最近窗口、次数/5m 重试、恢复、限流、合成、指标和模拟器跨边界/交易日。测试数量会随删除旧需求测试而变化，不与历史通过数量直接比较。

live 需确认没有另一正式实例占用账户连接，再明确当前 focus/wait 子集与时限：

```bash
.venv/bin/python scripts/live_check.py --symbols PAYS --duration 60
```

脚本使用当前白名单、一个 context、独立临时 SQLite 和 JSONL，输出 report.json 路径；只读行情，不交易。默认不会自动执行。不要把模拟通过描述成 live 通过，不把历史记录当本轮证据。

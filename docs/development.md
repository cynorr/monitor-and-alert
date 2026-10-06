# 开发维护手册

更新：2026-10-06。开发先遵循 [development-principles.md](development-principles.md)。此文件供 Codex/Claude Code 和维护者使用；产品行为以 [behavior.md](behavior.md) 为准，Alert 独立需求见 [alert.md](alert.md)。UI 总入口为 [ui.md](ui.md)，通用图表详细要求只在 [chart-ui.md](chart-ui.md)、持仓 UI 只在 [holdings-ui.md](holdings-ui.md) 维护。历史证据见 [validation.md](validation.md)。

## 文件与依赖

| 文件 | 唯一职责 |
| --- | --- |
| data_service/__main__.py | CLI、单实例锁、生命周期、有限运行报告 |
| workbench.py | 同一 Workspace、Scan/Monitor展示、持续后台行情/账户及本地Scan API |
| paths.py / network.py | 唯一runtime布局、显式共用HTTP代理/session与Massive凭证读取 |
| massive/daily.py / splits.py / build.py | 原始Daily补文件、两年split覆盖、新日增量追加；输入修订或失败后从raw全量重建派生SQLite |
| symbol_directory.py / scripts/pull_symbol_directory.py | 独立免费Nasdaq目录获取/校验/原子发布；分类及可空名称均为.US |
| massive/settings.py / config/massive.json | 直接读取候选配置，不做自动版本跟踪 |
| pipeline.py | 一次准备任务、阶段重试、产物核对及统一Ready状态 |
| scan.py | 上游只读连接、完成日截面/发布、Scan 日图 |
| features/atomic.py / screening.py / snapshot.py | 原子纯算子、初筛/排名、每只一次截面组装 |
| preferences.py / list_rules.py | Tag 用途和保存契约（含独立外观 metadata）；共享字段目录；纯匹配与自动三名单分类，外观不参与分类 |
| config.py | 当前 Focus 解析、凭证读取、错误脱敏 |
| workspace.py | 最新日期选择、内存 JSON、同步直接写入、单个原生文件事件 watcher |
| broker.py | 单 SDK context、static_info 添加验证、最近 K 线、Quote 请求、全局/后台请求预算 |
| snaptrade.py | 独立异步签名GET、指定账户、10次/滚动分钟预算、原始快照获取与成功提交；不提供HTTP服务、不调用Longbridge |
| holdings.py | 买卖归属、余仓与当日清仓、Decimal估值/日基准/Days、30秒刷新与失败保留；唯一数据需求见holdings-data.md |
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
| ui/src/scan.ts / filters.ts / tags.ts / board.ts | 日期/三列表、显示筛选、Tag 条件与外观草稿、角色与section分组 |
| ui/src/tag-appearance.ts | 内置轮廓图案、旧 Tag 外观默认值与共用 SVG 渲染 |
| scripts/build_scan_mock.py | 明确指定目录的合成日 K/截面/测试名单 |
| ui/src/chart.ts / chart-settings.ts / layout.ts | Lightweight Charts、共用初始图形参数、日联动、列宽和原生交互 |
| simulator/market.py / server.py | 隔离历史/Quote/时钟，复用正式流程，单一网站入口 |
| scripts/live_check.py | 明确执行的有界 live 验收；临时库、单连接 |
| data_service/alerts/ | 独立 Alert Engine、业务 SQLite、最小 macOS 通知；先读本目录 AGENTS.md |

依赖方向：UI → Data API → Workbench → Scan或DataService → store/indicators/quotes。正式data不import simulator，Scan算子不依赖SDK。pandas/numpy用于共用指标与特征；Quote preview仍使用缓存标量，不逐次重建DataFrame。不增加 services 层、指标数据库或事件日志协议。

持仓数据需求只在 [holdings-data.md](holdings-data.md) 维护，显示交互见 [holdings-ui.md](holdings-ui.md)。ui/src/holdings.ts把账户批次扁平化用于显示，排序不修改服务器数据；仅顺序变化时复用主行/买卖行DOM，日期、数量、金额与买卖记录变化时更新明细。自然内容宽度使用同样CSS的临时隐藏副本测量，onWidth经main.ts交给layout.setHoldingsWidth；字符位数与结构未变时不重复克隆，不在每次Quote上重新测量。Holdings位于名单滚动容器之外，沿用整体折叠与水平overflow。main.ts复用已有Quote.current_regular_session，前端不新增日历、HTTP、券商请求或后台任务，金额仍为后端Decimal字符串，计算语义以Holdings数据需求为准。

图表显示与交互的唯一规范见 [chart-ui.md](chart-ui.md)。chart-settings.ts集中维护所有图表的默认bar spacing和volume区比例；修改后npm构建并刷新，不增加设置界面。chart.ts保留用户缩放与历史视口，用十字线对应bar更新OHLC和Vol，刷新不覆盖悬停值；双图联动的价格/成交量值来自鼠标所在 pane 的公开 coordinateToPrice，不取 candle close/volume。有对应时间时用 setCrosshairPosition；没有对应时间时，在相应 candles/volume series 上复用一条公开 createPriceLine 来显示水平线，恢复对应时间、离开、清空或 reset 时移除。成交量计算仍只在后端。

List UI 的唯一要求入口为 [ui.md 的 List UI 章节](ui.md#list-ui)，局部 AI 约束见 ui/src/AGENTS.md。list.ts 保持七个行单元与 main.ts/index.html 列头一致；board.growthValue 仅格式化 RFL，原始百分比及排名不变。CSS 维护独立 Growth/Tags 列与12px间距，filter-rules 用两列 CSS columns、group 用 break-inside:avoid，不引入布局依赖或脚本测高。

Tag 外观 metadata 为独立的 `{icon,color,background:'transparent'|'frosted',backgroundColor}`，不从显示名称反推已保存外观，也不影响 role、filters、分类与订阅。前端只为旧偏好中缺失的外观初始化默认值，下次偏好保存持久化；后端校验内置 icon、背景枚举与六位 HEX 颜色，不接收任意 SVG/URL/CSS。列表和编辑 preview 复用 `tag-appearance.ts`，无外部图标依赖。固定展示数量不引入测宽监听。Save/Cancel 检查完整 Tag 草稿，筛选预览只检查条件变化，外观编辑保留人工匹配成员。图形要求统一见 [Logo / Icon](ui.md#logo--icon)，名单排布见 [List UI](ui.md#list-ui)。

后续客户端明确包含 Android 原生 App，iOS 可能接入。迁移时以 behavior/list-design 的产品语义、本文件的接口与保存契约、ui 的设计要求为入口；保留 Tag Icon ID、外观和名单操作含义，按平台重做绘制、密度与触摸交互。Web 的 DOM/CSS/SVG 和 px 仅是当前实现参考；不提前建设移动端原生工程或通用适配层。Alert 所需最小 macOS 通知应用按下节实现。

## Alert 实现

实现：2026-10-06；完整功能要求见 [alert.md](alert.md)，模块 AI 入口见 [data_service/alerts/AGENTS.md](../data_service/alerts/AGENTS.md)。本节只维护职责、调用和保存契约，不重复生命周期或 UI 数值。

- Workbench 持有唯一 Alert Engine，并在正式后台启动/关闭时创建和释放。UI → 同源 Data API → Workbench → Alert Engine → SQLite/macOS 通知；Alert 不依赖 Scan 算子或图表渲染，不建立第二个进程服务、端口或消息协议。
- `quotes.py` 继续承担 Quote 的唯一标准化与校验入口，在现有 callback 处派发有效 Regular 最新价。Engine 只接标准化值、报价时间与接收顺序；借用现有 calendar/恢复信号判断交易窗口和重新建立起点，不直接访问 SDK。`pipeline.py` 仍只管理 Massive 准备，与 Alert 检测无关。
- 当前 scope 由最新 workspace Focus 和按当前纽约日期有效的已接受 Holdings 提供，不能用带 Review 的 `Workbench.symbols` 或 Scan 时返回 null 的显示字段作为白名单。复用 Holdings 现有日期/批次语义，不建第二份账户归属缓存。
- `alerts/engine.py` 直接管理状态、检测、操作和业务 SQLite，`alerts/macos.py` 管权限、通知、声音和回调；函数直接互调，不引入通用 repository、adapter、rules 或恢复框架。UI Alert 交互在 `ui/src/alerts.ts` 内维护：公开 series primitive 的 paneViews 绘制虚线，priceAxisPaneViews 绘制进入价格轴的右箭头，不提供 priceAxisViews 数字标签；应用层 DOM 胶囊使用公开 pane HTMLElement/尺寸/坐标与 primitive.updateAllViews 定位。胶囊与横线共用拖动/删除动作，两图共用 controller 中的改价预览，松手提交一次；不依赖 vendor 内部 DOM。
- RuntimePaths.alerts_db 为独立 Alert 数据库路径。Alert 与 events 两张业务表保存用户设置及处理状态；前者有独立 ID；Engine 按 symbol 建立内存索引，后者有事件 ID 及 Alert/generation 关联。模式、周期、来源、Scan 日期不参与持久化身份；UI 上下文仍使用原有 request_id/source/socket 检查。
- SQLite 使用 WAL/FULL，所有修改在同一后台 asyncio loop 内串行提交；触发状态和事件一并提交，之后才发原生通知/WS。每份行情仅检查该 symbol 的内存 Active 集合，有实际修改才写库；不保存行情回放日志。事件保留到处理，不以 UI 暂时不可见推断已处理。
- Workbench 的 Alert 创建动作先验证输入，再复用统一 Focus 入选动作，最后调用 Engine.create；入选清理/分类/顺序细则只在 [List 入选规则](list-design.md#统一移入-focus) 维护。`workspace.py` 管一次同步保存，`list_rules.py` 管现有匹配；手动入选和 Alert 入选不得分别实现。
- `_focus`/`add_ticker`/`move_members` 已清理来源人工 Tag/section，接收共用匹配结果并一次保存；不能仅在 Alert 入口清理，不能依赖稍后的 `prepare_lists` 去消除中间状态。现有 Focus 内的人工调整与全新 symbol 指定 section 新增按原契约保留。
- workspace JSON 与 Alert SQLite 沿用各自的直接保存方式，不新增跨存储事务协调。入选失败中止；入选已保存但 Alert 保存失败，保留已成功的 Focus 入选并返回明确部分结果，不伪造成功横线。GET/图表选择仍只读，真实行情范围仅随已提交的名单变化。
- 最小 macOS `.app` 建立固定应用身份；使用 PyObjC 12.2 与 py2app 0.28.10；打包依赖固定 setuptools <81。主线程运行 AppKit/通知事件循环，单个后台线程运行现有 asyncio Workbench；原生操作通过线程安全调度返回后台 loop，后台通知通过主线程调度调用 macOS。这是同一 Python 进程，不把 `.app` 做成另一个行情服务。
- 应用打包只包含程序/UI/声音资源，现有 runtime、workspace 与凭证继续留在工程运行目录。开发可使用 alias bundle，发布使用完整 bundle；升级不新建用户数据库，保持应用身份并验证权限保留。最小应用提供打开工作台、通知设置与退出入口，明确退出才关闭原有服务。当前为本机 alias bundle，固定在工程 dist/Market Monitor.app，代码与 .venv 留在原目录；不宣称是可拷走的独立发行包。构建和启动方式见 README。Finder 的 C locale 在 launcher 中设为 UTF-8；通知冷启动的 Open/Close 等待 Workbench ready/bind 后进入同一业务处理。

当前函数/传输接口：

| 入口 | 职责 |
| --- | --- |
| `Workbench.action("alerts", payload)` | 校验、必要时入 Focus、提交操作并返回 Alert 快照；名单经独立 list 同步 |
| `AlertEngine.create(symbol, price)` | 在已允许范围内建立持久化 Alert，供统一入口及后续程序调用 |
| `AlertEngine.rearm(alert_id, price, expected_generation)` | 提交改价/重新设置，保护已被另一操作重新设置的版本 |
| `AlertEngine.delete(alert_id)` | 删除用户选中的 Alert |
| `AlertEngine.acknowledge(event_id)` | 处理事件，只在 generation 对应当前 Triggered 时删除 Alert |
| `POST /v1/alerts` | 同源 JSON mutation，动作 create/rearm/delete/acknowledge/notifications，复用 Origin 与错误处理 |
| `GET /v1/alerts` | 只读当前 Alert、未处理事件及原生通知状态，不安排行情请求 |
| `WS /v1/stream` 的独立 `type=alerts` | 初次/重连及实际业务变化发完整 Alert/待处理快照，不依赖选中 symbol |
| `/health` 的 alerts 状态 | enabled/count/error；通知授权、声音和投递错误在 GET /v1/alerts 与 WS 快照中 |

仅留后续程序调用入口，不接入 Atomic feature 或新增自动设置测试。Mock/模拟器只能使用自己的临时名单/库，不能读取真实凭证或自动改为真实 API；离线会话不投递真实桌面通知。

## 模式与上游数据

同一个服务、同一个Workspace、一个全局展示模式。正式serve在HTTP可响应后启动一次Broker/DataService与Holdings；切Scan不停止它们，服务关闭才cancel/await并释放context/store/session。Mock Scan与有界--symbols禁用Massive与真实账户；Mock明确切Monitor才构造Longbridge，回到Mock Scan时释放。后台准备与展示切换分离，仅禁止重复生成，不建立第二个服务或通用source接口。

Massive唯一要求见 [massive-data.md](massive-data.md)，共用bars契约见 [upstream-daily-data.md](upstream-daily-data.md)。RuntimePaths统一所有正式路径：symbol-directory.json、massive/daily原始文件、massive/splits.json、massive/daily.sqlite3、longbridge/bars.sqlite3、holdings与days；继续接受--runtime。正式Workbench和reconcile/verify注入Longbridge新路径；DataService独立/模拟器默认临时bars路径保持。两库共用BAR_SCHEMA、Bar、read_bars与指标，Daily ts为ET零点转Unix秒；不混库或拼接历史。显式--daily-db是只读外部入口，不运行内置Massive，筛选仍消费指定runtime的本地目录。

build_day仅对D当日有bar的symbol生成截面，重读配置和本地目录，按 [Massive 数据要求](massive-data.md) 完成候选筛选与全市场排名。随后对候选、Focus及全部Excluded（含Hidden）读取最多1000根建立完整特征，包含Growth使用的三种RFL数值；完整特征补算不改变资格、candidate或已有市场名次，不为继承名单另行排名。其他非候选仅保留轻量指标、资格标记及可空security_name。daily_metrics复用共用纯算子，不重复维护公式。workspace_scope读取同日或最近前日的全部Focus/Excluded；enrich_snapshot为本地成员补齐旧截面缺少的完整特征及RFL数值，记录feature_scope，不重跑全市场排名或下载。详细计算范围见 [名单完整特征范围](massive-data.md#名单完整特征范围)。

每步只保留单只历史与全市场标量，避免全市场历史fetchall；读到的bar均验证闭合/结构。checked_history复用Bar.validate，OHLC范围矛盾保留原值；后续阶段仅为上一窗口起点之前的矛盾追加日志，避免一次生成内重叠窗口重复记录。阶段耗时和证券/候选数量写普通日志，不新增指标持久化或性能框架。真实样本线程对照：单线程1000只约0.46秒、四线程约1.12秒；不添加更慢的线程池。全日生成继续在现有asyncio.to_thread中执行，不阻塞HTTP/WS事件循环。

latest_completed_date只读取上游metadata.completed_date，禁止用MAX(ts)回退推断；缺少完成日则失败并保留原状态。CLI scan未传--date、页面Refresh未传date时用该完成日，build_day继续拒绝未收盘日或无当日bar。成功后同步publish_day、reload workspace并明确选中新生成日期，首次才创建workspace。相同日期重算不重新继承；生成失败释放busy并保留原日期/名单。离线scan和serve共用runtime单实例锁，运行中的生成通过POST /v1/scan。

只保存days/D/scan.json一份截面，不保存逐根指标序列或Parquet。Scan板只传三列表实际成员，snapshot按mtime缓存，前一候选与图表按日期缓存；重算/修订清缓存。run_id在模式/日期/生成变化时更新，WS据此重发完整历史；UI保留mode/request_id/socket身份检查。Scan没有Quote active、Intraday或Ready实时状态；Daily复用同一个Panel。

indicators.py是唯一EMA/SMA/TR/Wilder ATR/ADR/ADV/RFL入口。ADR/ADV窗口统一最近最多20根实际记录；ADV固定close×volume均值，turnover不参与该公式。指标只消费已选来源的价格，Massive拆股复权与Longbridge NoAdjust结果允许不同。

复权契约：Longbridge broker.py继续显式请求AdjustType.NoAdjust与TradeSessions.Intraday，保持官方原始OHLC与整数成交量。Massive复权/量/turnover的唯一要求见massive-data.md。两源不互相验证，读取、指标和图表不再复权；Longbridge未来复权未实现。pandas ewm(adjust=False)仅是加权算法参数。

38项条件目录仅ui/src/filter-catalog.json一份，后端读取该文件验证保存契约，后端list_rules.matches_filters执行名单分类，前端filters.ts执行草稿显示筛选，二者共享相同边界/缺失语义。保存值不取整；旧maxExclusive语义保留到主动编辑。Tag草稿不写盘，Save写完整preferences后才更新内存，失败保留草稿；不建立长期多版本猜测/迁移框架。

## Massive准备与统一状态

正式serve启动一次MassivePipeline.run；手动massive命令/脚本及页面Refresh复用它，无周期定时器。单任务串行执行Daily→split→bars→features；Daily/split网络获取保持既有有界重试；bars/features本地失败直接报错，不自动重试。网络失败不回退直连。HTTP/WS/图表读取不安排任务。

network.proxy_url统一读取MARKET_PROXY，默认http://127.0.0.1:7899，显式空值直连；create_session禁用trust_env。Massive和SnapTrade显式传proxy，但各自保留限流、签名、解析和session。Massive凭证读取MASSIVE_API_KEY或单行massive-token.txt，日志不得包含值、带key的URL或任意上游响应体。

Daily/split下载、重试及复权要求集中在massive-data.md。symbol_directory独立脚本仅取两个免费文本，不由pull_massive/服务/GET触发；缺目录或坏配置在任何Massive请求之前检查。Mock构建器先写明确合成目录。开发验证遵循独立准则，优先真实数据，只做本次必要检查。

build.py保留input_revision/metadata/build入口。metadata.raw_files保存已消费文件大小/mtime，split_revision保存实际split结果摘要。旧文件清单匹配且只有较新日期、split结果未变时直接追加；已有raw修订/移除、补入较早日或split结果变化时，删除SQLite后merge全部raw。旧库没有清单也直接重建。使用普通批量写入和commit，不增加事务协调、读快照、逐ticker修复、版本迁移或输入竞态校验。写入失败删除派生库并报错，下次运行重建；原始JSON始终保留。普通日志只记录模式、处理文件数、证券数和耗时。

pipeline-status.json维护daily/splits/bars/features，目标均为daily.target_date给出的成熟交易日；split覆盖包含目标日及两年窗口则Ready，不按自然日重复更新。Ready只核对已完成日及既有行情input_revision，不维护目录/配置feature_revision。启动、普通CLI和页面Refresh使用非force流程，逐步跳过已完成产物；配置/目录修改后从CLI显式重算，每次生成直接读取，不自动监听或重算。操作命令只在 [README Massive 操作](../README.md#massive-操作) 维护。内置库的scan命令保留SQLite行情input_revision与生成时间，使最新日重算后仍为Ready。Scan与人工名单维持既有保存/继承流程；自动发布更新页面缓存，手动刷新即使run返回None也从features.date打开最新可用日，并在日期变化时更新run_id。指定日生成不经POST入口。无新增GET下载、连接或轮询。

Workbench.view及Monitor图表GET带可空security_name，来源仅为RuntimePaths.symbol_directory；按mtime/大小/inode缓存，文件变化无需bar revision变化也能刷新名称。缺失或损坏返回null，禁止名称查询扩大券商白名单或触发网络。前端用textContent显示并在清图时隐藏，具体绘制统一见ui.md。

两个Scan复制项目已完成数据与功能迁移并删除；保留的schwab-review只作参考，正式代码不import或执行它。Daily、SQLite、状态、账户缓存、凭证与临时文件Git忽略，唯一放行runtime/massive/splits.json。正式服务不连接或合并旧库历史，新Longbridge库按既有最近1000根流程初始化。

## Workspace 与动态名单

watchdog 6 使用平台 Observer（macOS 为 FSEvents），只建一个递归 watcher；线程仅把事件派发回 asyncio loop。默认跟随 days 最新文件；显式 --workspace 监听该文件父目录并固定文件。创建、修改、移动、删除事件触发重读，无定时扫描。自身写入产生的事件在 JSON 相同情况下不重复更新。

List完整需求见 [list-design.md](list-design.md)。Workspace V3直接维护JSON，statuses包含discover/focus/excluded、主section和当日匹配tags，orders是三名单扁平顺序。旧wait一次归Focus，旧hidden归Excluded/Hidden；读取迁移只在内存，下一次实际分类或编辑同步保存。只需这个明确旧版本迁移，不建立通用migration/repository层。Focus与Excluded跨候选空档继承，Discover只保留当日candidate。Hidden七天内不匹配；非Hidden Excluded可恢复Review，Review不强制过期。七天到期后仍匹配负面即可重新排除，不检查历史条件变化。新section成员放队首，同section人工顺序保留。

Tag role为setup/extended/broken/label，负面Broken优先，Setup顺序决定主section。manual_tags_date/manual_section_date/manual_focus_date只在当前名单交易日有效；旧手动标签不驱动新日。删除Tag或修改role后，失效的人工section回归当前有效setup或unclassified。写失败恢复原内存；沿用同步直接写文件与单watcher，不增加锁、临时文件或写队列。数据缺失不淘汰Focus。

Workbench.start_background先异步补本地成员feature、重新分类，再启动正式Focus行情；本地准备失败保留名单、显示错误并继续原行情与Massive准备。新截面发布、Tag保存和显式编辑后重评；list_state/GET不写盘、不请求下载。DataService只接收Focus，Workbench在Monitor board额外拼Review本地行。Review只用Massive Daily，加入Focus才扩订阅。HTTP/WS选股source区分watchlist与holdings，同symbol持仓仍能看实时图；成员/Review身份变化更新run_id，清WS revision，避免本地预览切实时图时沿用旧来源bars。

Workbench持有唯一workspace回调，Monitor通过update_tickers接收变更；独立模拟器继续使用DataService.attach_workspace。update_tickers 同步更新当前白名单、调度任务及选择。删除任务取消并在退出时收尾；保留成员复用 SyncState。QuoteService 用内存事件唤醒现有 Quote loop，按 subscribed 与当前成员差集增删订阅；失败沿用重连/30 秒重试。Broker 在等待额度后再次检查请求范围；unsubscribe 允许清理已移出白名单的 symbol。static_info 是搜索/添加前唯一可查询候选 ticker 的例外，验证本身不扩大行情白名单，仍共用全局限流及同一 context。

Holdings另由Workbench持有单个controller与轮询task，正式服务两种展示均持续启用；服务退出时先cancel并await持仓任务及其aiohttp session，再退出Monitor。SnapTrade凭证工厂在正式后台启动时使用，mock/only禁用工厂。原项目代码迁入维护路径，不import `schwab-review`。凭证文件与规则/账户缓存均git忽略，凭证权限600；CLI缺少凭证文件时不启用持仓。后台启动的第一个refresh位于timer sleep之前；展示切换不重建刷新任务；失败不调用成员更新、不提交raw缓存，下一周期再执行，没有额外即时重试。

DataService.tickers仍只包含workspace成员，board只输出Focus；holdings_symbols独立接收已接受余仓与当日清仓复盘批次。唯一_update_symbols按两来源并集更新store/broker.allowed、Quote范围和SyncState，同ticker保持既有任务。它不调用static_info、不检查workspace归属、不写workspace。Holdings只在账户成功刷新时重建买卖关联；约1Hz list_state读取用已有Decimal批次标量与Quote重新估值，不重复匹配流水。前端selectionSource与buy_ids批次key分离于symbol，Watchlist更新不得覆盖持仓选择，HTTP/WS图表继续用原request_id/mode/socket保护。

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

UI 图表只通过 `/v1/stream`：select消息含symbol/timeframe/request_id/mode/source；source为watchlist或holdings，省略时按watchlist；旧模拟器仍可省略mode。初次、选择、重连为完整 bars+指标；常规只传 active/indicator_preview/status，历史改变才重发。约 5Hz 图表预览、1Hz 独立 list 消息。list 不依赖选中 symbol/request_id，所以删空、删当前项或重连时仍可刷新名单；图表继续保留 request_id 校验。run_id标识后端实例和当前数据上下文，request_id 与 socket identity 防止串图。保留 heartbeat、慢客户端独立发送任务和 Origin 校验；不新增差量重放协议。

list_state增加独立holdings字段：未启用或Scan为null；启用为{data,loading,error}。data保留旧fetched_at/source_timestamps/positions_as_of/pnl_basis/funds/summary/holdings契约和Decimal字符串，holding增加price_source/price_timestamp/price_session、change_percent/extended_percent/day_reference_price；sequence与summary包含可空day_pnl；sequence增加closed_today、day_reference_price/day_reference_source，日期由Workbench现有时钟转纽约日期传入。total_pnl/total_pnl_percent字段名保留，余仓值改为仅未实现盈亏，summary以余仓成本为分母且排除清仓复盘记录。build从positions加当日SELL发现显示范围，同一current_trades/sequences完成数量与归属核对；不靠上次页面状态保留清仓。Workbench通过monitor.quote读取与观察名单相同的Daily修正基准，再由holdings.py用Decimal重算日盈亏；缺基准不返回部分总额。无新增SDK请求、下载任务或缓存文件。GET /v1/holdings返回同一只读状态；请求不刷新账户、不安排历史。Account Value从估值市值加SnapTrade现金计算，原details账户总值仍在原始缓存，不冒充相同时刻的券商官方净值。本机WS关闭可选压缩，避免大图表/持仓快照发送时快速重载遗留aiohttp压缩后台task。

List 动作接口：`POST /v1/list`，Content-Type 为 application/json，接受只读候选查询 `{action:"lookup",ticker}`（返回 `{ticker,name}`，不修改 workspace/白名单/订阅/调度）及 `{action:"add",ticker,section}`、`{action:"delete",ticker}`、`{action:"move",ticker,list_name,section,index}`（section为潜力Tag ID或unclassified），以及`{action:"tag",ticker,tags:[人工ID]}`、`{action:"keep",ticker}`。index 为移除主动ticker后目标section的零基位置。修改动作返回 `{board,editable,mode,workspace_error,notice?}`，成功响应前已同步落盘；WS `{type:"list",...}` 复用同一结构。校验同源 Origin；诊断 GET 继续只读。`--symbols` 仅跟踪指定子集，禁用 mutation 以保持验收范围。

Scan批量动作同样使用POST /v1/list：`{action:"move",tickers:[...],source:"discover",target:"focus"}`。列表状态增加app_mode、date、dates、preferences和mock；历史Scan日期或--symbols不可写。POST /v1/mode切换模式，POST /v1/scan选择/生成日期，POST /v1/preferences同步保存完整偏好；所有写入复用同源检查，body上限64KiB。生成保留同日人工覆盖，同时更新规则标签/分类。

新日继承Focus与Excluded，Hidden期限跨候选空档保留。publish_day读取同日人工状态或继承上一日，读取preferences，再apply_rules；同日重算不清人工覆盖。正式默认days为runtime/days，三个拷贝参考目录不import。旧人工数据保留，当前读取采用V3。

前端只有一套 Search 状态（目标 Section、候选、提示与在途 lookup）。/ 和 + 共用入口，唯一差别是目标Section；Scan查询本地只读SQLite，Monitor使用static_info。输入后 1 秒延迟只用于 lookup，写文件仍同步立即执行。输入变化/退出会取消等待及 fetch，并以 Search 对象身份忽略迟到结果；Enter 复用正在执行的 lookup。最终 add 仍由后端验证，不能信任前端传来的证券名称。Shift 换序复用 move，目标 index 为移除主动 ticker 后的位置，不新增 swap 接口。

## 必要验证

遵循 [development-principles.md](development-principles.md)，仅验证本轮修改。优先直接使用真实本地数据和正常运行的服务；确需停/重启时可直接执行。真实接口检查写清当前范围及结束条件，不使用历史记录代替本轮证据。

只选有关的用例，例：`.venv/bin/python -m pytest -q tests/test_massive_incremental_build.py`。TypeScript改变后运行`npm run build --prefix ui`。不默认执行整个项目回归或全流程检查，不为罕见边界建立故障注入/并发/回放框架。已有模拟器保持隔离，不自动读凭证或回退真实API。

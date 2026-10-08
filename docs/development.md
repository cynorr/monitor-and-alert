# 开发维护手册

更新：2026-10-08。开发先遵循 [development-principles.md](development-principles.md)。此文件供 Codex/Claude Code 和维护者使用；产品行为以 [behavior.md](behavior.md) 为准；Longbridge 数据要求只在 [longbridge-data.md](longbridge-data.md) 维护，Alert 独立需求见 [alert.md](alert.md)。UI 总入口为 [ui.md](ui.md)，通用图表详细要求只在 [chart-ui.md](chart-ui.md)、持仓 UI 只在 [holdings-ui.md](holdings-ui.md) 维护。历史证据见 [validation.md](validation.md)。

## 文件与依赖

| 文件 | 唯一职责 |
| --- | --- |
| data_service/__main__.py | CLI、单实例锁、生命周期、有限运行报告 |
| workbench.py | 同一 Workspace、Scan/Monitor展示、持续后台行情/账户及本地Scan API |
| paths.py / network.py | 唯一runtime布局、显式共用HTTP代理/session与Massive凭证读取 |
| massive/daily.py / splits.py / build.py | 原始Daily补文件、两年split覆盖、新日增量追加；输入修订或失败后从raw全量重建派生SQLite |
| symbol_directory.py / scripts/pull_symbol_directory.py | 独立免费Nasdaq目录获取/校验/原子发布；仅保存.US官方ETF标记，用于扫描资格 |
| massive/settings.py / config/massive.json | 直接读取候选配置，不做自动版本跟踪 |
| pipeline.py | 一次准备任务、阶段重试、产物核对及统一Ready状态 |
| scan.py | 上游只读连接、完成日截面/发布、Scan 日图 |
| features/atomic.py / screening.py / snapshot.py | 原子纯算子、初筛/排名、每只一次截面组装 |
| preferences.py / list_rules.py | Tag 用途和保存契约（含独立外观 metadata）；共享字段目录；纯匹配与自动三名单分类，外观不参与分类 |
| config.py | 当前 Focus 解析、凭证读取、错误脱敏 |
| workspace.py | 最新日期选择、三名单归属/顺序与当日置顶、内存 JSON、同步直接写入、单个原生文件事件 watcher |
| broker.py | 单 SDK context、static_info、原生六周期历史/实时订阅、Quote / Trade、请求预算 |
| snaptrade.py | 独立异步签名GET、指定账户、10次/滚动分钟预算、原始快照获取与成功提交；不提供HTTP服务、不调用Longbridge |
| holdings.py | 买卖归属、余仓与当日清仓、Decimal估值/日基准/Days、30秒刷新与失败保留；唯一数据需求见holdings-data.md |
| calendar.py | UTC/ET、XNYS、交易日刷新阶段、实际闭合边界、5m 到 2h 时间网格 |
| downloader.py | 历史/实时共用 parse/validate；最新目标成功后提交、拒绝行诊断、OHLC 比较日志 |
| store.py | 逐根官方 bars、最新成功批次、单窗口普通提交及 revision |
| validator.py | 最近窗口完整性检查与缓存；不联网、不写状态文件 |
| service.py | 每个 ticker/官方周期一份 SyncState，排序、执行、重试、恢复；API 组合 |
| quotes.py | Quote 标准化、六周期 candle 订阅生命周期、callback 代次、snapshot/watchdog、恢复通知 |
| charts.py / indicators.py | 原生 candle 显示与图表缓存；唯一指标公式 |
| http_api.py | aiohttp 静态页面、诊断 HTTP、List mutation、WebSocket/Origin 校验 |
| ui/src/main.ts / types.ts | WS 选择与重连、显示状态、契约 |
| ui/src/list.ts | 统一内联搜索/新增、输入查询生命周期、置顶与拖动/快捷键移动、折叠、共用列定义和按字段更新行 |
| ui/src/holdings.ts | 独立九列/盘中八列单行表格、单列降序/取消、自然宽度测量、整体折叠、批次选中、逐笔Buy/Sold日期/数量/实际成交价明细 |
| ui/src/scan.ts / filters.ts / tags.ts / board.ts | 日期/三列表、统一可见结果与持仓屏蔽、Tag 条件/外观草稿、分组/列定义和Scan格式化 |
| ui/src/tag-appearance.ts | 内置轮廓图案、旧 Tag 外观默认值与共用 SVG 渲染 |
| scripts/build_scan_mock.py | 明确指定目录的合成日 K/截面/测试名单 |
| ui/src/chart.ts / chart-settings.ts / layout.ts | Lightweight Charts、共用初始图形参数、日联动、列宽和原生交互 |
| simulator/market.py / server.py | 隔离历史/Quote/时钟，复用正式流程，单一网站入口 |
| scripts/live_check.py | 明确执行的有界 live 验收；临时库、单连接 |
| data_service/additional_info/ / scripts/pull_additional_info.py | 独立Nasdaq公司资料/财报获取、Python清理、业务SQLite/内存缓存和后台调度；先读模块AGENTS.md |
| ui/src/additional-info.ts | 附加信息选择身份校验、分类显示精简、可空字段格式化和纽约自然日倒计时；不操作图表bars |
| data_service/alerts/ | 独立 Alert Engine、业务 SQLite、后台声音；先读本目录 AGENTS.md |

依赖方向：UI → Data API → Workbench → Scan或DataService → store/indicators/quotes。正式data不import simulator，Scan算子不依赖SDK。pandas/numpy用于共用指标与特征；candle preview仍使用缓存标量，不逐次重建DataFrame。不增加 services 层、指标数据库或事件日志协议。

持仓数据需求只在 [holdings-data.md](holdings-data.md) 维护，显示交互见 [holdings-ui.md](holdings-ui.md)。ui/src/holdings.ts把账户批次扁平化用于显示，排序不修改服务器数据；仅顺序变化时复用主行/买卖行DOM，日期、数量、金额与买卖记录变化时更新明细。自然内容宽度使用同样CSS的临时隐藏副本测量，onWidth经main.ts交给layout.setHoldingsWidth；字符位数与结构未变时不重复克隆，不在每次Quote上重新测量。Holdings位于名单滚动容器之外，沿用整体折叠与水平overflow。Workbench.list_state用已有calendar.is_open与服务时钟提供current_regular_session，main.ts同时交给Watchlist与Holdings，前端不新增日历、HTTP、券商请求或后台任务，金额仍为后端Decimal字符串，计算语义以Holdings数据需求为准。

图表显示与交互的唯一规范见 [chart-ui.md](chart-ui.md)。chart-settings.ts集中维护所有图表的默认bar spacing和volume区比例；修改后npm构建并刷新，不增加设置界面。chart.ts保留用户缩放与历史视口，用十字线对应bar更新OHLC和Vol，刷新不覆盖悬停值；双图联动的价格/成交量值来自鼠标所在 pane 的公开 coordinateToPrice，不取 candle close/volume。有对应时间时用 setCrosshairPosition；没有对应时间时，在相应 candles/volume series 上复用一条公开 createPriceLine 来显示水平线，恢复对应时间、离开、清空或 reset 时移除。成交量计算仍只在后端。

成交量五日比较的唯一需求见 [Volume comparison](chart-ui.md#volume-comparison)。`calendar.previous_days` 按 candle 日期返回前五个交易日；`indicators.volume_context / volume_comparison` 为同周期建立时间槽索引及均值缓存。Monitor 在历史 revision 变化时重建，open 更新仅读取均值并计算比例；Scan/Review Daily 复用同一函数及已有图表缓存。显示行附带 `volume_comparison: {average: number | null, samples: number, percent: number | null}`，不改 SQLite Bar。chart.ts 在公开十字线回调后按时间戳取得原始显示行，保持比较结果与 Vol 一致；前端只做整数截取和显示。

chart.ts 的 syncSeries 用公开 data/update API 比较已显示数据：相同时间序列的尾部替换/追加只更新变化项，较早官方修订用 update(row, true)。只有新窗口、时间序列变化或删除点时使用 setData；正常 closed 更新不调用滚动重定位，未知 active volume 只更新 histogram 的 whitespace，不重建 candles/MA。保持 vendor 原样。

List UI 的唯一要求入口为 [ui.md 的 List UI 章节](ui.md#list-ui)，局部 AI 约束见 ui/src/AGENTS.md。board.listColumns分别定义Scan/Monitor列和宽度，list.ts共用它创建标题和行，按data-field更新单元，不依赖children位置；Monitor无Growth渲染。board.growthValue仅供Scan格式化RFL，原始百分比及排名不变。ScanControls.available统一屏蔽holding_symbols，供筛选/计数/搜索/导航/批量操作使用；原board仍保留完整后端成员。CSS维护独立列与12px间距，filter-rules 用两列 CSS columns、group 用 break-inside:avoid，不引入布局依赖或脚本测高。

Tag 外观 metadata 为独立的 `{icon,color,background:'transparent'|'frosted',backgroundColor}`，不从显示名称反推已保存外观，也不影响 role、filters、分类与订阅。前端只为旧偏好中缺失的外观初始化默认值，下次偏好保存持久化；后端校验内置 icon、背景枚举与六位 HEX 颜色，不接收任意 SVG/URL/CSS。列表和编辑 preview 复用 `tag-appearance.ts`，无外部图标依赖。固定展示数量不引入测宽监听。Save/Cancel 检查完整 Tag 草稿，筛选预览只检查条件变化，外观编辑保留人工匹配成员。图形要求统一见 [Logo / Icon](ui.md#logo--icon)，名单排布见 [List UI](ui.md#list-ui)。

后续客户端明确包含 Android 原生 App，iOS 可能接入。迁移时以 behavior/list-design 的产品语义、本文件的接口与保存契约、ui 的设计要求为入口；保留 Tag Icon ID、外观和名单操作含义，按平台重做绘制、密度与触摸交互。Web 的 DOM/CSS/SVG 和 px 仅是当前实现参考；不提前建设移动端原生工程或通用适配层。Alert 后台声音按下节实现。

## Alert 实现

更新：2026-10-07；完整功能要求见 [alert.md](alert.md)，模块 AI 入口见 [data_service/alerts/AGENTS.md](../data_service/alerts/AGENTS.md)。本节只维护职责、调用和保存契约，不重复生命周期或 UI 数值。

- Workbench 持有唯一 Alert Engine，并在正式后台启动/关闭时创建和释放。UI → 同源 Data API → Workbench → Alert Engine → SQLite/后台声音；Alert 不依赖 Scan 算子或图表渲染，不建立第二个进程服务、端口或消息协议。
- `quotes.py` 继续承担 Quote 的唯一标准化与校验入口，在现有 callback 处派发有效 Regular 最新价。Engine 只接标准化值、报价时间与接收顺序；借用现有 calendar/恢复信号判断交易窗口和重新建立起点，不直接访问 SDK。`pipeline.py` 仍只管理 Massive 准备，与 Alert 检测无关。
- 当前 scope 由最新 workspace Focus 和按当前纽约日期有效的已接受 Holdings 提供，不能用带 Review 的 `Workbench.symbols` 或 Scan 时返回 null 的显示字段作为白名单。复用 Holdings 现有日期/批次语义，不建第二份账户归属缓存。
- `alerts/engine.py` 直接管理状态、检测、操作和业务 SQLite，`alerts/sound.py` 管本地声音；函数直接互调，不引入通用 repository、adapter、rules 或恢复框架。UI Alert 交互在 `ui/src/alerts.ts` 内维护：公开 series primitive 的 paneViews 绘制虚线，priceAxisPaneViews 绘制进入价格轴的右箭头，不提供 priceAxisViews 数字标签；应用层 DOM 胶囊使用公开 pane HTMLElement/尺寸/坐标与 primitive.updateAllViews 定位。胶囊与横线共用拖动/删除动作，两图共用 controller 中的改价预览，松手提交一次；不依赖 vendor 内部 DOM。
- RuntimePaths.alerts_db 为独立 Alert 数据库路径。Alert 与 events 两张业务表保存用户设置及处理状态；前者有独立 ID；Engine 按 symbol 建立内存索引，后者有事件 ID 及 Alert/generation 关联。模式、周期、来源、Scan 日期不参与持久化身份；UI 上下文仍使用原有 request_id/source/socket 检查。
- SQLite 使用 WAL/FULL，所有修改在同一后台 asyncio loop 内串行提交；触发状态和事件一并提交，之后才播放声音/发送 WS。每份行情仅检查该 symbol 的内存 Active 集合，有实际修改才写库；不保存行情回放日志。事件保留到处理，不以 UI 暂时不可见推断已处理。
- Workbench 的 Alert 创建动作先验证输入，再复用统一 Focus 入选动作，最后调用 Engine.create；入选清理/分类/顺序细则只在 [List 入选规则](list-design.md#统一移入-focus) 维护。`workspace.py` 管一次同步保存，`list_rules.py` 管现有匹配；手动入选和 Alert 入选不得分别实现。
- `_focus`/`add_ticker`/`move_members` 已清理来源人工 Tag/section，接收共用匹配结果并一次保存；不能仅在 Alert 入口清理，不能依赖稍后的 `prepare_lists` 去消除中间状态。现有 Focus 内的人工调整与全新 symbol 指定 section 新增按原契约保留。
- workspace JSON 与 Alert SQLite 沿用各自的直接保存方式，不新增跨存储事务协调。入选失败中止；入选已保存但 Alert 保存失败，保留已成功的 Focus 入选并返回明确部分结果，不伪造成功横线。GET/图表选择仍只读，真实行情范围仅随已提交的名单变化。
- 正式 Python 启动入口直接启用 AlertSound；Workbench.start_background/close 管理同一 asyncio loop 内的播放任务。每个新事件入内存队列，按顺序用 macOS 自带 `/usr/bin/afplay` 播放 `alerts/sounds/up.wav` 或 `down.wav`，循环规则遵循 [Alert 后台声音](alert.md#后台声音与运行)。资源保存单次原声，每次播放完成立即启动下一次，不主动等待。这是短时播放子进程，不是独立后台服务；通过异步 subprocess 等待，失败报告后继续处理下一事件。退出时终止在播子进程，丢弃内存队列，不重播历史事件。
- WAV 随 Python package-data 安装，不依赖应用包、签名、通知授权、PyObjC 或 py2app。Mock/模拟器默认不创建播放器，明确声音验收时才注入；平台声音状态只包含 enabled/error。UI 只显示实际声音错误，删除通知设置入口及原生通知跳转逻辑。

当前函数/传输接口：

| 入口 | 职责 |
| --- | --- |
| `Workbench.action("alerts", payload)` | 校验、必要时入 Focus、提交操作并返回 Alert 快照；名单经独立 list 同步 |
| `AlertEngine.create(symbol, price)` | 在已允许范围内建立持久化 Alert，供统一入口及后续程序调用 |
| `AlertEngine.rearm(alert_id, price, expected_generation)` | 提交改价/重新设置，保护已被另一操作重新设置的版本 |
| `AlertEngine.delete(alert_id)` | 删除用户选中的 Alert |
| `AlertEngine.acknowledge(event_id)` | 处理事件，只在 generation 对应当前 Triggered 时删除 Alert |
| `POST /v1/alerts` | 同源 JSON mutation，动作 create/rearm/delete/acknowledge，复用 Origin 与错误处理 |
| `GET /v1/alerts` | 只读当前 Alert、未处理事件及 sound.enabled/error，不安排行情请求或播放 |
| `WS /v1/stream` 的独立 `type=alerts` | 初次/重连及实际业务变化发完整 Alert/待处理快照，不依赖选中 symbol |
| `/health` 的 alerts 状态 | enabled/count/error；声音状态与播放错误在 GET /v1/alerts 与 WS 快照中 |

仅留后续程序调用入口，不接入 Atomic feature 或新增自动设置测试。Mock/模拟器只能使用自己的临时名单/库，不能读取真实凭证或自动改为真实 API；声音验收必须明确启用实际播放。

## 模式与上游数据

同一个服务、同一个Workspace、一个全局展示模式。正式serve在HTTP可响应后启动一次Broker/DataService与Holdings；切Scan不停止它们，服务关闭才cancel/await并释放context/store/session。Mock Scan与有界--symbols禁用Massive与真实账户；Mock明确切Monitor才构造Longbridge，回到Mock Scan时释放。后台准备与展示切换分离，仅禁止重复生成，不建立第二个服务或通用source接口。

Massive唯一要求见 [massive-data.md](massive-data.md)，共用bars契约见 [upstream-daily-data.md](upstream-daily-data.md)。RuntimePaths统一所有正式路径：symbol-directory.json、massive/daily原始文件、massive/splits.json、massive/daily.sqlite3、longbridge/bars.sqlite3、holdings、additional-info/info.sqlite3与days；继续接受--runtime。正式Workbench和reconcile/verify注入Longbridge新路径；DataService独立/模拟器默认临时bars路径保持。两库共用BAR_SCHEMA、Bar、read_bars与指标，Daily ts为ET零点转Unix秒；不混库或拼接历史。显式--daily-db是只读外部入口，不运行内置Massive，筛选仍消费指定runtime的本地目录。

build_day仅对D当日有bar的symbol生成截面，重读配置和本地目录，按 [Massive 数据要求](massive-data.md) 完成候选筛选与全市场排名。随后对候选、Focus及全部Excluded（含Hidden）读取最多1000根建立完整特征，包含Growth使用的三种RFL数值；完整特征补算不改变资格、candidate或已有市场名次，不为继承名单另行排名。其他非候选仅保留轻量指标和资格标记。截面不再嵌入公司名称；旧截面遗留字段不用于UI。daily_metrics复用共用纯算子，不重复维护公式。workspace_scope读取同日或最近前日的全部Focus/Excluded；enrich_snapshot为本地成员补齐旧截面缺少的完整特征及RFL数值，记录feature_scope，不重跑全市场排名或下载。详细计算范围见 [名单完整特征范围](massive-data.md#名单完整特征范围)。

每步只保留单只历史与全市场标量，避免全市场历史fetchall；读到的bar均验证闭合/结构。checked_history复用Bar.validate，OHLC范围矛盾保留原值；后续阶段仅为上一窗口起点之前的矛盾追加日志，避免一次生成内重叠窗口重复记录。阶段耗时和证券/候选数量写普通日志，不新增指标持久化或性能框架。真实样本线程对照：单线程1000只约0.46秒、四线程约1.12秒；不添加更慢的线程池。全日生成继续在现有asyncio.to_thread中执行，不阻塞HTTP/WS事件循环。

latest_completed_date只读取上游metadata.completed_date，禁止用MAX(ts)回退推断；缺少完成日则失败并保留原状态。CLI scan未传--date、页面Refresh未传date时用该完成日，build_day继续拒绝未收盘日或无当日bar。成功后同步publish_day、reload workspace并明确选中新生成日期，首次才创建workspace。相同日期重算不重新继承；生成失败释放busy并保留原日期/名单。离线scan和serve共用runtime单实例锁，运行中的生成通过POST /v1/scan。

只保存days/D/scan.json一份截面，不保存逐根指标序列或Parquet。Scan板只传三列表实际成员，snapshot按mtime缓存，前一候选与图表按日期缓存；重算/修订清缓存。run_id在模式/日期/生成变化时更新，WS据此重发完整历史；UI保留mode/request_id/socket身份检查。Scan没有实时active、Intraday或Ready实时状态；Daily复用同一个Panel。

indicators.py是唯一EMA/SMA/TR/Wilder ATR/ADR/ADV/RFL入口。ADR/ADV窗口统一最近最多20根实际记录；ADV固定close×volume均值，turnover不参与该公式。指标直接消费已选来源的价格；不同供应商的结果允许不同。

来源契约分别只在 [longbridge-data.md](longbridge-data.md) 与 [massive-data.md](massive-data.md) 维护。broker.py落实Longbridge请求口径；读取、指标和图表直接使用所属来源的数据。pandas ewm(adjust=False)仅是加权算法参数。

38项条件目录仅ui/src/filter-catalog.json一份，后端读取该文件验证保存契约，后端list_rules.matches_filters执行名单分类，前端filters.ts执行草稿显示筛选，二者共享相同边界/缺失语义。保存值不取整；旧maxExclusive语义保留到主动编辑。Tag草稿不写盘，Save写完整preferences后才更新内存，失败保留草稿；不建立长期多版本猜测/迁移框架。

## Massive准备与统一状态

正式serve启动一次MassivePipeline.run；手动massive命令/脚本及页面Refresh复用它，无周期定时器。单任务串行执行Daily→split→bars→features；Daily/split网络获取保持既有有界重试；bars/features本地失败直接报错，不自动重试。网络失败不回退直连。HTTP/WS/图表读取不安排任务。

network.proxy_url统一读取MARKET_PROXY，默认http://127.0.0.1:7899，显式空值直连；create_session禁用trust_env。Massive、SnapTrade和Additional Info显式传proxy，但各自保留限流、签名、解析和session。Massive凭证读取MASSIVE_API_KEY或单行massive-token.txt，日志不得包含值、带key的URL或任意上游响应体。

Daily/split下载、重试及复权要求集中在massive-data.md。symbol_directory独立脚本仅取两个免费文本，不由pull_massive/服务/GET触发；缺目录或坏配置在任何Massive请求之前检查。Mock构建器先写明确合成目录。开发验证遵循独立准则，优先真实数据，只做本次必要检查。

build.py保留input_revision/metadata/build入口。metadata.raw_files保存已消费文件大小/mtime，split_revision保存实际split结果摘要。旧文件清单匹配且只有较新日期、split结果未变时直接追加；已有raw修订/移除、补入较早日或split结果变化时，删除SQLite后merge全部raw。旧库没有清单也直接重建。使用普通批量写入和commit，不增加事务协调、读快照、逐ticker修复、版本迁移或输入竞态校验。写入失败删除派生库并报错，下次运行重建；原始JSON始终保留。普通日志只记录模式、处理文件数、证券数和耗时。

pipeline-status.json维护daily/splits/bars/features，目标均为daily.target_date给出的成熟交易日；split覆盖包含目标日及两年窗口则Ready，不按自然日重复更新。Ready只核对已完成日及既有行情input_revision，不维护目录/配置feature_revision。启动、普通CLI和页面Refresh使用非force流程，逐步跳过已完成产物；配置/目录修改后从CLI显式重算，每次生成直接读取，不自动监听或重算。操作命令只在 [README Massive 操作](../README.md#massive-操作) 维护。内置库的scan命令保留SQLite行情input_revision与生成时间，使最新日重算后仍为Ready。Scan与人工名单维持既有保存/继承流程；自动发布更新页面缓存，手动刷新即使run返回None也从features.date打开最新可用日，并在日期变化时更新run_id。指定日生成不经POST入口。无新增GET下载、连接或轮询。

附加信息定位与数据规则只在 [additional-info.md](additional-info.md) 维护；代码入口为 [additional_info/AGENTS.md](../data_service/additional_info/AGENTS.md)。Workbench独立持有AdditionalInfo，核心任务安排完成后create_task(run)，不await可选缓存/请求。正式serve启用自动刷新，Mock和--symbols关闭联网。解析/SQLite工作通过to_thread执行；内存读取不访问文件、SDK或行情库。

`GET /v1/additional-info` 返回独立状态，带symbol返回可空company_name/sector/industry/market_cap、earnings.last/next、来源更新时间和server_time。`POST /v1/additional-info` 的action=refresh只安排后台任务并立即返回，复用Origin/JSON规则。WS的additional_info消息带symbol、request_id、mode、source，独立revision控制推送，完全不改变bars revision。前端检查socket和选择身份，用textContent显示；倒计时按服务器时钟及纽约自然日计算。

service.py负责独立SQLite及内存缓存、每日/每周调度；nasdaq.py负责固定公开接口、全响应校验与Python名称处理。每份公司表或每个财报日期成功后普通提交，失败保留原数据。独立CLI与正式服务共用runtime锁，避免同时写缓存；命令维护在README。

Daily、SQLite、状态、账户缓存、凭证与临时文件Git忽略，唯一放行runtime/massive/splits.json。正式服务的Longbridge缓存按唯一数据要求初始化。

## Workspace 与动态名单

watchdog 6 使用平台 Observer（macOS 为 FSEvents），只建一个递归 watcher；线程仅把事件派发回 asyncio loop。默认跟随 days 最新文件；显式 --workspace 监听该文件父目录并固定文件。创建、修改、移动、删除事件触发重读，无定时扫描。自身写入产生的事件在 JSON 相同情况下不重复更新。

List完整需求见 [list-design.md](list-design.md)。Workspace V3直接维护JSON，statuses包含discover/focus/excluded、主section和当日匹配tags，orders是三名单扁平顺序。旧wait一次归Focus，旧hidden归Excluded/Hidden；读取迁移只在内存，下一次实际分类或编辑同步保存。只需这个明确旧版本迁移，不建立通用migration/repository层。Focus与Excluded跨候选空档继承，Discover只保留当日candidate。Hidden七天内不匹配；非Hidden Excluded可恢复Review，Review不强制过期。七天到期后仍匹配负面即可重新排除，不检查历史条件变化。新section成员放队首，同section人工顺序保留。

preferences 的 activeTag 为 Tag ID 或 null，tags 可为空、最多十个；初始偏好为空选择与空 Tag 数组。前端草稿与基线独立比较，未选 Tag 也可编辑空筛选并保存命名定义；点击已选 Tag 保存 null，规则分类仍读取全部定义。Tag role为setup/extended/broken/under50/label，负面优先级为broken → extended → under50，Setup顺序决定主section。manual_tags_date/manual_section_date/manual_focus_date只在当前名单交易日有效；旧手动标签不驱动新日。删除Tag或修改role后，失效的人工section回归当前有效setup或unclassified。写失败恢复原内存；沿用同步直接写文件与单watcher，不增加锁、临时文件或写队列。数据缺失不淘汰Focus。

Workbench.start_background先异步补本地成员feature、重新分类，再启动正式Focus行情；本地准备失败保留名单、显示错误并继续原行情与Massive准备。新截面发布、Tag保存和显式编辑后重评；list_state/GET不写盘、不请求下载。DataService只接收Focus，Workbench在Monitor board额外拼Review本地行。Review只用Massive Daily，加入Focus才扩订阅。HTTP/WS选股source区分watchlist与holdings，同symbol持仓仍能看实时图；成员/Review身份变化更新run_id，清WS revision，避免本地预览切实时图时沿用旧来源bars。

Workbench持有唯一workspace回调，Monitor通过update_tickers接收变更；独立模拟器继续使用DataService.attach_workspace。update_tickers 同步更新当前白名单、调度任务及选择。删除任务取消并在退出时收尾；保留成员复用 SyncState。QuoteService 用内存事件唤醒现有行情循环，按当前成员增删 Quote / Trade 与六周期 candle 订阅；移除时先清 candle，再退订底层行情；失败沿用重连/30 秒重试。Broker 在等待额度后再次检查请求范围；unsubscribe 允许清理已移出白名单的 symbol。static_info 是搜索/添加前唯一可查询候选 ticker 的例外，验证本身不扩大行情白名单，仍共用全局限流及同一 context。

Holdings另由Workbench持有单个controller与轮询task，正式服务两种展示均持续启用；服务退出时先cancel并await持仓任务及其aiohttp session，再退出Monitor。SnapTrade凭证工厂在正式后台启动时使用，mock/only禁用工厂。凭证文件与规则/账户缓存均git忽略，凭证权限600；CLI缺少凭证文件时不启用持仓。后台启动的第一个refresh位于timer sleep之前；展示切换不重建刷新任务；失败不调用成员更新、不提交raw缓存，下一周期再执行，没有额外即时重试。

DataService.tickers仍只包含workspace成员，board只输出Focus；holdings_symbols独立接收已接受余仓与当日清仓复盘批次。唯一_update_symbols按两来源并集更新store/broker.allowed、Quote范围和SyncState，同ticker保持既有任务。它不调用static_info、不检查workspace归属、不写workspace。Holdings只在账户成功刷新时重建买卖关联；约1Hz list_state读取用已有Decimal批次标量与Quote重新估值，不重复匹配流水。前端selectionSource与buy_ids批次key分离于symbol，Watchlist更新不得覆盖持仓选择，HTTP/WS图表继续用原request_id/mode/socket保护。

SnapTrade固定请求配置account_id，不通过/accounts假设仅一个账户。成功核对后原始缓存只保存runtime/holdings/latest.json一份；activities分页仅属于SnapTrade成交历史，不改变Longbridge数据要求。每轮重读sequences.txt/merge_buys.txt，明确关联与原错误检查不变。SnapTrade及Longbridge拥有独立额度，均在同一Python进程内运行，不新增监听端口或服务。

## Longbridge 同步与缓存实现

获取、刷新时机、替换、失败与 Ready 的完整规则只在 [longbridge-data.md](longbridge-data.md) 维护。`service.sync[(symbol, timeframe)]` 是唯一任务记录；`calendar.window_session` 给出美东交易日与开盘前/开盘后刷新阶段。scheduler先处理阶段变化，再处理closed目标；同一任务在途时不重复请求，阶段变化或恢复到达不能被旧请求完成覆盖。reconcile复用调度器，所有任务完成或本轮耗尽即退出；诊断GET不改变任务。

`downloader.fetch` 在请求前后核对刷新阶段，响应通过逐根校验及最新closed目标检查后才提交。`store.upsert(replace=True)` 用已有SQLite连接的一次普通提交替换单个symbol/周期，普通增量按主键覆盖。bars保持共用逐根结构；batches仅含symbol、timeframe和payload，payload记录成功请求的阶段、时间与数量。数据库采用WAL/NORMAL；不设行数裁剪、历史水位、迁移或备份框架。

bars revision在行内容变化或窗口替换后递增。validator按revision、closed目标及刷新阶段缓存结果，不扫描历史连续性；共用Bar校验只在 [upstream-daily-data.md](upstream-daily-data.md) 定义。图表历史仅依赖本周期 revision，比较最终显示序列，内容未变不重发。未刷新周期的旧窗口继续独立展示，不参与当前 active 和本地 Daily 报价基准修正。

ChartCache.views 每个 symbol/周期只保留最近一份完整显示，沿用 revision/bars/active/indicator_preview 契约。跨桶时检查本周期最新 closed 已到达及下一 SDK open 可用；等待时返回上一份快照。官方替换与新 active 同一条 WS view 发布，Daily 无 5m 依赖。移出范围清掉 active/views；GET 不下载。

UI契约为 `status: {stage: loading|basic|full, errors: string[], refreshing: boolean}`。正常closed等待不重置Ready；刷新状态由现有任务派生。详细complete/target/latest/count/missing/errors只在诊断接口提供。显示规范见 [Chart status](chart-ui.md#chart-status)。

## 实时 candle 与时段

QuoteService 在同一 SDK context 注册 Quote 与 candle callback，通过现有 asyncio loop 派发并检查 callback 代次和当前白名单。`candle_subscribed[(symbol, tf)]` 管理六周期订阅，`candle_errors` 保留独立错误；Quote 成功不能清掉 candle 错误。订阅返回的尾根以 initial 标记进入同一处理入口，已到达的新推送不能被较旧初始化覆盖。

`downloader.parse_candle` 是历史与实时共用的 Bar 转换/校验；closed 校验用于落盘，实时只接受当前网格时间桶。历史响应拒绝非法行并写入当前 batch 的 rejected；最新 closed 目标无效或缺失仍失败回补。上下界矛盾照常保留与记录。DataService.apply_candle 将原始完整 OHLCV 交给 `ChartCache.active[(symbol, tf)]`，不读取其他周期或 Quote。SDK confirmed 不落盘，closed 仅由 downloader 提交。

DataService.recover 清掉 active，刷新窗口并唤醒行情循环；先退订 candle 再重新订阅，保证 SDK 取得新起点。connect 的 on_reset 同时重置 Alert 起点，on_reconnect 只刷新 closed 任务，避免递归恢复。历史请求仍共用同一 broker/context。行情基础与限制见 [Longbridge 数据说明](longbridge-data.md)。

Quote 接收不按 UI 选择筛选；regular/pre/post/overnight 共用 apply，snapshot 归一化后走同一入口，时段报价与 candle 独立。active preview 只用本周期已缓存的指标标量。

## 传输

同源 HTTP 静态资源与 `/v1/universe`；`/health`、`/v1/quotes`、`/v1/bars`、`/v1/readiness`、`/v1/chart` 为只读诊断。`/v1/chart` 不改变优先级。

UI 图表只通过 `/v1/stream`：select消息含symbol/timeframe/request_id/mode/source；source为watchlist或holdings，省略时按watchlist；旧模拟器仍可省略mode。初次、选择、重连为完整 bars+指标；常规只传 active/indicator_preview/status，历史改变才重发。约 5Hz 图表预览、1Hz 独立 list 消息。list 不依赖选中 symbol/request_id，所以删空、删当前项或重连时仍可刷新名单；图表继续保留 request_id 校验。run_id标识后端实例和当前数据上下文，request_id 与 socket identity 防止串图。保留 heartbeat、慢客户端独立发送任务和 Origin 校验；不新增差量重放协议。

list_state增加独立holdings字段：未启用或Scan为null；启用为{data,loading,error}。data保留旧fetched_at/source_timestamps/positions_as_of/pnl_basis/funds/summary/holdings契约和Decimal字符串，holding增加price_source/price_timestamp/price_session、change_percent/extended_percent/day_reference_price；sequence与summary包含可空day_pnl；sequence增加closed_today、day_reference_price/day_reference_source，日期由Workbench现有时钟转纽约日期传入。total_pnl/total_pnl_percent字段名保留，余仓值改为仅未实现盈亏，summary以余仓成本为分母且排除清仓复盘记录。build从positions加当日SELL发现显示范围，同一current_trades/sequences完成数量与归属核对；不靠上次页面状态保留清仓。Workbench通过monitor.quote读取与观察名单相同的Daily修正基准，再由holdings.py用Decimal重算日盈亏；缺基准不返回部分总额。无新增SDK请求、下载任务或缓存文件。GET /v1/holdings返回同一只读状态；请求不刷新账户、不安排历史。Account Value从估值市值加SnapTrade现金计算，原details账户总值仍在原始缓存，不冒充相同时刻的券商官方净值。本机WS关闭可选压缩，避免大图表/持仓快照发送时快速重载遗留aiohttp压缩后台task。

workspace.json 的根字段 `pinned:[ticker,...]` 为当日有序软状态；按 ticker 当前归属投影到各 List，保留原 statuses/section/orders。inherit_workspace 在新日清空；apply_rules 去掉消失或跨 List 的成员。pin_ticker/move_pin 使用原同步保存与错误回滚，置顶动作不重跑分类或获取数据。Workbench board 返回 pinned:boolean、pin_index:number|null；独立 DataService 仅在自身附带 Workspace 时提供置顶字段，不覆盖 Workbench 持有的名单状态；list_state 增加 holding_symbols（两模式均提供、含当日清仓）与 current_regular_session（calendar.is_open，不依赖个股Quote）。两字段只提供显示信息，不改变后端名单。

List 动作接口：`POST /v1/list`，Content-Type 为 application/json，接受只读候选查询 `{action:"lookup",ticker}`（返回 `{ticker,name}`，不修改 workspace/白名单/订阅/调度）及 `{action:"add",ticker,section}`、`{action:"delete",ticker}`、`{action:"move",ticker,list_name,section,index}`（section为潜力Tag ID或unclassified），以及`{action:"tag",ticker,tags:[人工ID]}`、`{action:"keep",ticker}`、`{action:"pin",ticker,pinned:boolean}`、`{action:"pin_move",ticker,index}`。pin_move的index为移除主动ticker后、同List完整置顶区的零基位置（含当前筛选不可见成员）。index 为移除主动ticker后目标section的零基位置。修改动作返回 `{board,editable,mode,workspace_error,notice?}`，成功响应前已同步落盘；WS `{type:"list",...}` 复用同一结构。校验同源 Origin；诊断 GET 继续只读。`--symbols` 仅跟踪指定子集，禁用 mutation 以保持验收范围。

Scan批量动作同样使用POST /v1/list：`{action:"move",tickers:[...],source:"discover",target:"focus"}`。列表状态增加app_mode、date、dates、preferences和mock；历史Scan日期或--symbols不可写。POST /v1/mode切换模式，POST /v1/scan选择/生成日期，POST /v1/preferences同步保存完整偏好；所有写入复用同源检查，body上限64KiB。生成保留同日人工覆盖，同时更新规则标签/分类。

新日继承Focus与Excluded，Hidden期限跨候选空档保留。publish_day读取同日人工状态或继承上一日，读取preferences，再apply_rules；同日重算不清人工覆盖。正式默认days为runtime/days。旧人工数据保留，当前读取采用V3。

前端只有一套 Search 状态（目标 Section、候选、提示与在途 lookup）。/ 和 + 共用入口，唯一差别是目标Section；Scan查询本地只读SQLite，Monitor使用static_info。输入后 1 秒延迟只用于 lookup，写文件仍同步立即执行。输入变化/退出会取消等待及 fetch，并以 Search 对象身份忽略迟到结果；Enter 复用正在执行的 lookup。最终 add 仍由后端验证，不能信任前端传来的证券名称。Shift 换序复用 move，目标 index 为移除主动 ticker 后的位置，不新增 swap 接口。

## 必要验证

遵循 [development-principles.md](development-principles.md)，仅验证本轮修改。优先直接使用真实本地数据和正常运行的服务；确需停/重启时可直接执行。真实接口检查写清当前范围及结束条件，不使用历史记录代替本轮证据。

只选有关的用例，例：`.venv/bin/python -m pytest -q tests/test_massive_incremental_build.py`。TypeScript改变后运行`npm run build --prefix ui`。不默认执行整个项目回归或全流程检查，不为罕见边界建立故障注入/并发/回放框架。已有模拟器保持隔离，不自动读凭证或回退真实API。

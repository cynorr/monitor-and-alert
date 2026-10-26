# 开发维护手册

更新：2026-10-26。开发先遵循 [development-principles.md](development-principles.md)。此文件供 Codex/Claude Code 和维护者使用；产品行为以 [behavior.md](behavior.md) 为准；Longbridge 数据要求只在 [longbridge-data.md](longbridge-data.md) 维护，Alert 独立需求见 [alert.md](alert.md)。UI 总入口为 [ui.md](ui.md)，通用图表详细要求只在 [chart-ui.md](chart-ui.md)、持仓 UI 只在 [holdings-ui.md](holdings-ui.md) 维护。历史证据见 [validation.md](validation.md)。

## 文件与依赖

数据源直接按实际规模组织：`longbridge/`集中SDK访问、实时订阅与历史处理，`massive/`包含获取、构建及准备流程；SnapTrade保持单文件。`additional_info/`同时收纳公司/财报服务和独立证券目录。Monitor与Workbench留在顶层做业务编排，共用Bar、持久化、图表缓存与网络基础也各保留一个明确模块。包入口不启动网络，不增加中间目录或旧路径转发层。

| 文件 | 唯一职责 |
| --- | --- |
| data_service/__main__.py | CLI、单实例锁、生命周期、有限运行报告 |
| workbench.py | 同一Workspace、Scan/Monitor展示、两种模式共用的名单Quote范围、持续后台行情/账户及本地Scan API |
| paths.py / network.py | 唯一runtime布局、共用HTTP session创建与显式代理配置；各数据源自行管理连接和额度 |
| massive/daily.py / splits.py / build.py | 原始Daily补文件、两年split覆盖、新日增量追加；输入修订或失败后从raw全量重建派生SQLite |
| additional_info/symbol_directory.py / scripts/pull_symbol_directory.py | 独立免费Nasdaq目录获取/校验/原子发布；仅保存.US官方ETF标记，用于扫描资格 |
| massive/settings.py / config/massive.json | Massive凭证、目录定位与候选配置读取，不做自动版本跟踪 |
| massive/pipeline.py | 一次准备任务、阶段重试、产物核对及统一Ready状态 |
| scan.py | 上游只读连接、完成日截面/发布、Scan 日图 |
| features/atomic.py / screening.py / snapshot.py | 原子纯算子、初筛/排名、每只一次截面组装 |
| preferences.py / list_rules.py | Tag 用途和保存契约（含独立外观 metadata）；共享字段目录；纯匹配与自动三名单分类，外观不参与分类 |
| config.py | 当前 Focus 解析与共用错误脱敏；供应商凭证由各自模块读取 |
| workspace.py | 最新日期选择、三名单归属/顺序与当日置顶、内存 JSON、同步直接写入、单个原生文件事件 watcher |
| longbridge/client.py | LongbridgeClient：凭证、单SDK context、static_info、原生历史/实时订阅与请求预算 |
| snaptrade.py | 独立异步签名GET、指定账户、10次/滚动分钟预算、原始快照获取与成功提交；不提供HTTP服务、不调用Longbridge |
| holdings.py | 买卖归属、余仓与当日清仓、Decimal估值/日基准/Days、30秒刷新与失败保留；唯一数据需求见holdings-data.md |
| calendar.py | UTC/ET、XNYS、交易日与时段、实际闭合边界、5m 到 2h 时间网格 |
| longbridge/history.py | BarDownloader获取/转换历史并提交；HistoryValidator只读检查近期窗口；实时candle复用同一转换函数 |
| storage.py | 共用Bar及结构校验、表结构/读取、行序列化、OHLC诊断、JSON原子保存；BarStore维护官方closed、成功批次和revision |
| monitor.py | 每个 ticker/官方周期一份 SyncState，排序、执行、重试、恢复；API 组合 |
| longbridge/realtime.py | Quote 标准化与批量订阅、六周期 candle 起点/推送、callback 代次、snapshot/watchdog与恢复 |
| chart_cache.py / indicators.py | SDK当天序列与官方closed统一读取、revision/指标缓存；唯一指标公式 |
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
| data_service/intraday_state/ | 独立盘中状态、规则穿越、分钟量区间/插值与离散排序等级；先读本目录AGENTS.md |
| data_service/alerts/ | 独立 Alert Engine、业务 SQLite、后台声音；先读本目录 AGENTS.md |

依赖方向：UI → Data API → Workbench → Scan或MonitorService。MonitorService调用longbridge包并组合ChartCache与盘中状态；Scan/Massive只使用共用storage、指标和特征，不从Longbridge包获取共用工具。正式data不import simulator，Scan算子不依赖SDK。pandas/numpy用于共用指标与特征；candle preview仍使用缓存标量，不逐次重建DataFrame。不增加 services 层、指标数据库或事件日志协议。

持仓数据需求只在 [holdings-data.md](holdings-data.md) 维护，显示交互见 [holdings-ui.md](holdings-ui.md)。ui/src/holdings.ts把账户批次扁平化用于显示，排序不修改服务器数据；仅顺序变化时复用主行/买卖行DOM，日期、数量、金额与买卖记录变化时更新明细。自然内容宽度使用同样CSS的临时隐藏副本测量，onWidth经main.ts交给layout.setHoldingsWidth；字符位数与结构未变时不重复克隆，不在每次Quote上重新测量。Holdings位于名单滚动容器之外，沿用整体折叠与水平overflow。Workbench.list_state用已有calendar.is_open与服务时钟提供current_regular_session，main.ts同时交给Watchlist与Holdings，前端不新增日历、HTTP、券商请求或后台任务，金额仍为后端Decimal字符串，计算语义以Holdings数据需求为准。后端is_new随纽约日期变化，前端复用List标记；账户更新时间显隐由Holdings.tick复用main.ts已有秒级时钟更新，不重排表格或增加账户请求。圆圈错误按钮与Chart共用绘制CSS，使用独立holdings-warning状态标记；详情面板只在点击时打开，保持相同文本节点以允许复制，成功/关闭操作收起，不建立通知或错误历史框架。

图表显示与交互的唯一规范见 [chart-ui.md](chart-ui.md)。chart-settings.ts集中维护所有图表的默认bar spacing和volume区比例；修改后npm构建并刷新，不增加设置界面。chart.ts保留用户缩放与历史视口，用十字线对应bar更新OHLC和Vol，刷新不覆盖悬停值；双图联动的价格/成交量值来自鼠标所在 pane 的公开 coordinateToPrice，不取 candle close/volume。有对应时间时用 setCrosshairPosition；没有对应时间时，在相应 candles/volume series 上复用一条公开 createPriceLine 来显示水平线，恢复对应时间、离开、清空或 reset 时移除。成交量计算仍只在后端。

成交量五日比较的唯一需求见 [Volume comparison](chart-ui.md#volume-comparison)。`calendar.previous_days` 按 candle 日期返回前五个交易日；`indicators.volume_context / volume_comparison` 为同周期建立时间槽索引及均值缓存。Monitor 在历史 revision 变化时重建，open 更新仅读取均值并计算比例；Scan Daily 复用同一函数及已有图表缓存。显示行附带 `volume_comparison: {average: number | null, samples: number, percent: number | null}`，不改 SQLite Bar。chart.ts 在公开十字线回调后按时间戳取得原始显示行，保持比较结果与 Vol 一致；前端只做整数截取和显示。

chart.ts 的 syncSeries 用公开 data/update API 比较已显示数据：相同时间序列的尾部替换/追加只更新变化项，较早官方修订用 update(row, true)。只有新窗口、时间序列变化或删除点时使用 setData；正常 closed 更新不调用滚动重定位，未知 active volume 只更新 histogram 的 whitespace，不重建 candles/MA。保持 vendor 原样。

List 显示要求见 [List UI](ui.md#list-ui)，操作规则只在 [List 交互](list-interactions.md) 维护，局部 AI 约束见 ui/src/AGENTS.md。board.listColumns分别定义Scan/Monitor列和宽度，list.ts共用它创建标题和行，按data-field更新单元，不依赖children位置；Monitor无Growth渲染。ScanControls持有唯一sortControl及其事件，list.ts在Scan列头中挂载，模式切换重建列头时复用同一控件。board.growthValue仅供Scan格式化RFL，原始百分比及排名不变；三个值用等宽CSS grid及子列边框对齐。ScanControls.available统一屏蔽holding_symbols，供筛选/计数/搜索/导航/单只操作使用；原board仍保留完整后端成员。导航与日期控件用单行flex布局，CSS维护独立列与12px间距，filter-rules 用两列 CSS columns、group 用 break-inside:avoid，不引入布局依赖或脚本测高。

共享语义配色的唯一代码来源为 `ui/src/palette.ts`，Chart/Alert/Tag默认值直接引用，main启动安装对应CSS变量；名称和用途只在[Color palette](ui.md#color-palette)维护。Symbol共用模板见[UI](ui.md#symbol-row-template)，不复制行绘制、波浪或默认色值。

Tag 外观 metadata 为独立的 `{icon,color,background:'transparent'|'frosted',backgroundColor}`，不从显示名称反推已保存外观，也不影响 role、filters、分类与订阅。前端只为旧偏好中缺失的外观初始化默认值，下次偏好保存持久化；后端校验内置 icon、背景枚举与六位 HEX 颜色，不接收任意 SVG/URL/CSS。列表和编辑 preview 复用 `tag-appearance.ts`，无外部图标依赖。固定展示数量不引入测宽监听。Save/Cancel 检查完整 Tag 草稿，筛选预览只检查条件变化，外观编辑保留人工匹配成员。图形要求统一见 [Logo / Icon](ui.md#logo--icon)，名单排布见 [List UI](ui.md#list-ui)。

后续客户端明确包含 Android 原生 App，iOS 可能接入。迁移时以 behavior/list-design 的产品语义、本文件的接口与保存契约、ui 的设计要求为入口；保留 Tag Icon ID、外观和名单操作含义，按平台重做绘制、密度与触摸交互。Web 的 DOM/CSS/SVG 和 px 仅是当前实现参考；不提前建设移动端原生工程或通用适配层。Alert 后台声音按下节实现。

## Alert 实现

需求只在 [alert.md](alert.md)，模块入口见 [alerts/AGENTS.md](../data_service/alerts/AGENTS.md)。Workbench持有AlertEngine与AlertSound，MonitorService只把校验后的Regular Quote交给手动检测，把Intraday State转换交给同一notify入口；不创建第二个行情context。

- runtime/alerts/alerts.sqlite3保存alerts和unread。未读以symbol为主键，只保留direction(up/down)、level(1/2)、fired_at；新报警直接覆盖，无历史或聚合。旧unread表启动时追加level，保留有方向的普通提醒；旧urgent没有方向，迁移时清理该记录，不猜测方向，不影响价格线。
- AlertEngine共用_clean_unread，用已有_regular_day同时校验当前时刻和fired_at是否属于同一Regular，并合并原scope清理。构造、maintain和state输出都经过此入口；跨收盘清理不等待scope_known，不改价格线，不增加期限字段、任务或Massive/Refresh依赖。
- create/rearm/delete仍管理手动线；read(symbol)只删除当前symbol的unread，不改变任何线条或generation。触发后灰线保留，无点击后倒计时；只有拖动重新激活、主动删除、到期或出范围改变线生命周期。
- notify(symbol,direction,level=1,alert=...)是唯一报警入口：手动触发时将Triggered和未读写在同一事务，自动规则只覆盖未读；提交成功后交给sound.play(symbol,direction,level,fired_at)。Intraday State保留触发方向和等级，不把两种紧急方向提前压成urgent。读取与恢复不播放。
- sound.py每次play建立独立任务，一次afplay播放完整两段WAV。beat_offsets是资源生成与播放节拍的共同来源；播放器启动后按实际本机时钟发布pulse_at，沿用现有Alert WS。playing每symbol仅输出最新任务的symbol/fired_at/pulse_at；旧任务仍可自然播放完，前端只响应当前未读fired_at的节拍。没有队列、抢占、历史或逐帧消息。退出取消任务并终止播放器；scripts/build_alert_sounds.py只用于离线准备资源。
- GET /v1/alerts及WS alerts包含revision/alerts/unread/eligible_symbols/scope_known/sound/error；unread为最新提醒对象数组，sound包含enabled/error/playing，字段如上。POST接受create/rearm/delete/read，read仅携带symbol；没有通知历史、事件ack或跳转API。
- 每个WS连接把自己的asyncio.Event登记到AlertEngine.watchers；持久化或播放状态变化唤醒既有发送循环，退出移除登记。沿用同源校验与唯一stream，不建立消息总线或新服务。
- ui/src/symbol-row.ts为Grid名单和Table持仓创建同一price-surface/price-wave；attention.ts仅应用最新提醒方向／等级及本次pulse_at，通过Web Animations短暂改变同一波浪亮度，不聚合标题。main.ts所有select及当前chart更新仍直接read。列表表面用Grid列范围定位；持仓表面挂在首个td，宽度由现有列几何计算，table ResizeObserver只同步这一个范围。选中轮廓、状态底色与提醒独立。
- Command+G/U在main.ts路由到各名单jumpUnread。Watchlist.sections同时供render与完整Focus导航使用；ScanControls.visible可指定Focus并忽略显示筛选，showList可保留Tag草稿。Watchlist.update仅在成员退出当前List或转入Holdings时自动候补，Tag遮住的已选chart不因后台推送跳走；用户主动修改筛选仍沿用原反馈。Holdings复用ordered与choose，不增加已访问集合。

## 模式与上游数据

同一个服务、同一个Workspace、一个全局展示模式。正式serve在HTTP可响应后启动一次LongbridgeClient/MonitorService与Holdings；切Scan不停止它们，服务关闭才cancel/await并释放context/store/session；三名单Quote-only范围不随展示模式改变。Mock Scan与有界--symbols禁用Massive与真实账户；Mock明确切Monitor才构造Longbridge，回到Mock Scan时释放。后台准备与展示切换分离，仅禁止重复生成，不建立第二个服务或通用source接口。

Massive唯一要求见 [massive-data.md](massive-data.md)，共用bars契约见 [upstream-daily-data.md](upstream-daily-data.md)。RuntimePaths统一所有正式路径：symbol-directory.json、massive/daily原始文件、massive/splits.json、massive/daily.sqlite3、longbridge/bars.sqlite3、holdings、additional-info/info.sqlite3与days；继续接受--runtime。正式Workbench和reconcile/verify注入Longbridge新路径；MonitorService独立/模拟器默认临时bars路径保持。两库共用BAR_SCHEMA、Bar、read_bars与指标，Daily ts为ET零点转Unix秒；不混库或拼接历史。显式--daily-db是只读外部入口，不运行内置Massive，筛选仍消费指定runtime的本地目录。

build_day仅对D当日有bar的symbol生成截面，重读配置和本地目录，按 [Massive 数据要求](massive-data.md) 完成候选筛选与全市场排名。随后对候选、Focus、有效Hidden及当日人工Discover读取最多1000根建立完整特征，包含Growth使用的三种RFL数值；完整特征补算不改变资格、candidate或已有市场名次，不为继承名单另行排名。其他非候选仅保留轻量指标和资格标记。截面不再嵌入公司名称；旧截面遗留字段不用于UI。daily_metrics复用共用纯算子，不重复维护公式。workspace_scope读取同日或最近前日的Focus和有效Hidden，并纳入同日manual_discover_date成员；enrich_snapshot为本地成员补齐旧截面缺少的完整特征及RFL数值，记录feature_scope，不重跑全市场排名或下载。详细计算范围见 [名单完整特征范围](massive-data.md#名单完整特征范围)。

每步只保留单只历史与全市场标量，避免全市场历史fetchall；读到的bar均验证闭合/结构。checked_history复用Bar.validate，OHLC范围矛盾保留原值；后续阶段仅为上一窗口起点之前的矛盾追加日志，避免一次生成内重叠窗口重复记录。阶段耗时和证券/候选数量写普通日志，不新增指标持久化或性能框架。真实样本线程对照：单线程1000只约0.46秒、四线程约1.12秒；不添加更慢的线程池。全日生成继续在现有asyncio.to_thread中执行，不阻塞HTTP/WS事件循环。

latest_completed_date只读取上游metadata.completed_date，禁止用MAX(ts)回退推断；缺少完成日则失败并保留原状态。CLI scan未传--date、页面Refresh未传date时用该完成日，build_day继续拒绝未收盘日或无当日bar。成功后同步publish_day、reload workspace并明确选中新生成日期，首次才创建workspace。相同日期重算不重新继承；生成失败释放busy并保留原日期/名单。离线scan和serve共用runtime单实例锁，运行中的生成通过POST /v1/scan。

只保存days/D/scan.json一份截面，不保存逐根指标序列或Parquet。Scan板只传三列表实际成员，snapshot按mtime缓存，前一候选与图表按日期缓存；重算/修订清缓存。run_id在模式/日期/生成变化时更新，WS据此重发完整历史；UI保留mode/request_id/socket身份检查。Scan没有实时active、Intraday或Ready实时状态；Daily复用同一个Panel。Workbench.scan_quote只读同一RealtimeFeed.output，最新Scan日与Monitor共用quote.latest；历史日期返回latest=null，行情K线revision不变也随WS更新报价。Panel复用一个价格轴标签，有最新报价时隐藏原closed价标签；报价选择与外观分别见Longbridge数据要求和Chart UI。

indicators.py是唯一EMA/SMA/TR/Wilder ATR/ADR/ADV/RFL入口。ADR/ADV窗口统一最近最多20根实际记录；ADV固定close×volume均值，turnover不参与该公式。指标直接消费已选来源的价格；不同供应商的结果允许不同。

来源契约分别只在 [longbridge-data.md](longbridge-data.md) 与 [massive-data.md](massive-data.md) 维护。longbridge/client.py落实Longbridge请求口径；读取、指标和图表直接使用所属来源的数据。pandas ewm(adjust=False)仅是加权算法参数。

38项条件目录仅ui/src/filter-catalog.json一份，后端读取该文件验证保存契约，后端list_rules.matches_filters执行名单分类，前端filters.ts执行草稿显示筛选，二者共享相同边界/缺失语义。保存值不取整；旧maxExclusive语义保留到主动编辑。Tag草稿不写盘，Save写完整preferences后才更新内存，失败保留草稿；不建立长期多版本猜测/迁移框架。

## Massive准备与统一状态

正式serve启动一次MassivePipeline.run；手动massive命令/脚本及页面Refresh复用它，无周期定时器。单任务串行执行Daily→split→bars→features；Daily/split网络获取保持既有有界重试；bars/features本地失败直接报错，不自动重试。网络失败不回退直连。HTTP/WS/图表读取不安排任务。

network.proxy_url统一读取MARKET_PROXY，默认http://127.0.0.1:7899，显式空值直连；create_session禁用trust_env。Massive、SnapTrade和Additional Info显式传proxy，但各自保留限流、签名、解析和session。massive/settings.py读取MASSIVE_API_KEY或单行massive-token.txt；Longbridge及SnapTrade凭证分别由longbridge/client.py、snaptrade.py读取。日志不得包含值、带key的URL或任意上游响应体。

Daily/split下载、重试及复权要求集中在massive-data.md。symbol_directory独立脚本仅取两个免费文本，不由pull_massive/服务/GET触发；缺目录或坏配置在任何Massive请求之前检查。Mock构建器先写明确合成目录。开发验证遵循独立准则，优先真实数据，只做本次必要检查。

build.py保留input_revision/metadata/build入口。metadata.raw_files保存已消费文件大小/mtime，split_revision保存实际split结果摘要。旧文件清单匹配且只有较新日期、split结果未变时直接追加；已有raw修订/移除、补入较早日或split结果变化时，删除SQLite后merge全部raw。旧库没有清单也直接重建。使用普通批量写入和commit，不增加事务协调、读快照、逐ticker修复、版本迁移或输入竞态校验。写入失败删除派生库并报错，下次运行重建；原始JSON始终保留。普通日志只记录模式、处理文件数、证券数和耗时。

pipeline-status.json维护daily/splits/bars/features，目标均为daily.target_date给出的成熟交易日；split覆盖包含目标日及两年窗口则Ready，不按自然日重复更新。Ready只核对已完成日及既有行情input_revision，不维护目录/配置feature_revision。启动、普通CLI和页面Refresh使用非force流程，逐步跳过已完成产物；配置/目录修改后从CLI显式重算，每次生成直接读取，不自动监听或重算。操作命令只在 [README Massive 操作](../README.md#massive-操作) 维护。内置库的scan命令保留SQLite行情input_revision与生成时间，使最新日重算后仍为Ready。Scan与人工名单维持既有保存/继承流程；自动发布更新页面缓存，手动刷新即使run返回None也从features.date打开最新可用日，并在日期变化时更新run_id。指定日生成不经POST入口。无新增GET下载、连接或轮询。

附加信息定位与数据规则只在 [additional-info.md](additional-info.md) 维护；代码入口为 [additional_info/AGENTS.md](../data_service/additional_info/AGENTS.md)。Workbench独立持有AdditionalInfo，核心任务安排完成后create_task(run)，不await可选缓存/请求。正式serve启用自动刷新，Mock和--symbols关闭联网。解析/SQLite工作通过to_thread执行；内存读取不访问文件、SDK或行情库。

`GET /v1/additional-info` 返回独立状态，带symbol返回可空company_name/sector/industry/market_cap、earnings.last/next、来源更新时间和server_time。`POST /v1/additional-info` 的action=refresh只安排后台任务并立即返回，复用Origin/JSON规则。WS的additional_info消息带symbol、request_id、mode、source，独立revision控制推送，完全不改变bars revision。前端检查socket和选择身份，用textContent显示；倒计时按服务器时钟及纽约自然日计算。

additional_info/service.py负责独立SQLite及内存缓存、每日/每周调度；同目录nasdaq.py负责固定公开接口、全响应校验与Python名称处理，symbol_directory.py保持独立的证券目录CLI流程，不并入附加信息刷新。每份公司表或每个财报日期成功后普通提交，失败保留原数据。独立CLI与正式服务共用runtime锁，避免同时写缓存；命令维护在README。

Daily、SQLite、状态、账户缓存、凭证与临时文件Git忽略，唯一放行runtime/massive/splits.json。正式服务的Longbridge缓存按唯一数据要求初始化。

## Workspace 与动态名单

watchdog 6 使用平台 Observer（macOS 为 FSEvents），只建一个递归 watcher；线程仅把事件派发回 asyncio loop。默认跟随 days 最新文件；显式 --workspace 监听该文件父目录并固定文件。创建、修改、移动、删除事件触发重读，无定时扫描。自身写入产生的事件在 JSON 相同情况下不重复更新。

List完整需求见 [list-design.md](list-design.md)。Workspace V3继续直接维护JSON。内存statuses包含完整当日分类；persistent_workspace供Workspace.save和publish_day共用，落盘时移除机器Excluded成员身份、section和计算Tag，只保留人工Tag注记及独立Pin。Discover/Focus/Hidden的状态和人工顺序沿用现有字段，excluded_at仅属于Hidden。inherit_workspace只继承Focus和有效Hidden；apply_rules统一匹配Tag并生成当天候选归属，保留Focus自动淘汰，非候选淘汰后删除。无需保存历史机器section或未知特征恢复状态。derive_day_view只投影已分类结果及NEW。新section成员置前，同section人工顺序保留。Workspace.reload比较同一持久投影，忽略自身保存引发的文件事件；外部变化由Workbench.workspace_changed同步重建分类并更新行情范围。旧wait/hidden的V2读取迁移仍只在内存。


preferences的activeTag为Tag ID或null，tags可为空、最多十个。前端草稿独立，空选择仍可编辑并保存新Tag；点击已选Tag保存null，全部定义仍参与分类。role为setup/extended/broken/under50/label；负面优先级broken → extended → under50，Setup顺序决定主section。manual_tags只允许setup/label，Workbench同时校验，apply_rules清理失效或负面人工ID。manual_tags_date/manual_section_date/manual_focus_date仅当前名单交易日有效；删除或改用途后的人工section回归有效setup/unclassified。写失败恢复原内存，沿用同步保存与单watcher。数据缺失不淘汰Focus。

Workbench.start_background先异步补本地成员feature并分类，再启动正式Focus行情；本地准备失败保留名单、显示错误并继续原行情与Massive准备。新截面成功发布、Tag保存及显式编辑后重评；list_state/GET不写盘、不下载，不增加定时分类。Monitor board只输出Focus，图表统一来自实时MonitorService；Scan图表使用本地Massive Daily。HTTP/WS保留watchlist/holdings选择来源隔离；_list_context使用日期与Focus成员变化更新run_id并清WS revision。

Workbench持有唯一workspace回调，Monitor通过update_tickers接收变更；独立模拟器继续使用MonitorService.attach_workspace。update_tickers 同步更新当前白名单、调度任务及选择。删除任务取消并在退出时收尾；保留成员复用 SyncState。RealtimeFeed 用内存事件唤醒现有行情循环，按当前成员增删 Quote / Trade 与六周期 candle 订阅；移除时先清 candle，再退订底层行情；失败沿用重连/30 秒重试。LongbridgeClient 在等待额度后再次检查请求范围；unsubscribe 允许清理已移出白名单的 symbol。static_info 是搜索/添加前唯一可查询候选 ticker 的例外，验证本身不扩大行情白名单，仍共用全局限流及同一 context。

Workbench.refresh_list_quotes将最新workspace完整三名单交给MonitorService.update_quote_symbols，正式Scan/Monitor共用，Mock与symbol子集保持隔离。MonitorService.symbols、store.allowed、LongbridgeClient.candle_allowed和SyncState仍只包含Focus/Holdings；quote_symbols记录三名单，LongbridgeClient.allowed是两者并集。RealtimeFeed.extra_symbols排除完整行情重复成员；subscribed与quote_subscribed分别管理完整订阅及Quote-only。切模式不改变集合、不重置context或generation，名单变化才唤醒既有循环按差集批量订阅/快照；入选Focus才增加Trade/candle。单只不可用按既有方式隔离，Quote-only超时独立重试，不中断核心行情。

Workspace.add_ticker的discover分支原子保存当日manual_discover_date及Pin，重复已有归属不迁移。derive_day_view/apply_rules把同日人工Discover纳入成员范围并保留人工归属、如实计算Tag；inherit_workspace删除Discover与全部Pin，只有明确加入Focus才按原生命周期跨日。Scan新增补特征复用enrich_snapshot，保持candidate和rank；不增加预览缓存或独立保存文件。

Holdings另由Workbench持有单个controller与轮询task，正式服务两种展示均持续启用；服务退出时先cancel并await持仓任务及其aiohttp session，再退出Monitor。SnapTrade凭证工厂在正式后台启动时使用，mock/only禁用工厂。凭证文件与规则/账户缓存均git忽略，凭证权限600；CLI缺少凭证文件时不启用持仓。后台启动的第一个refresh位于timer sleep之前；展示切换不重建刷新任务；失败不调用成员更新、不提交raw缓存，下一周期再执行，没有额外即时重试。

MonitorService.tickers仍只包含workspace成员，board只输出Focus；holdings_symbols独立接收已接受余仓与当日清仓复盘批次。唯一_update_symbols按两来源并集更新store/broker.allowed、Quote范围和SyncState，同ticker保持既有任务。它不调用static_info、不检查workspace归属、不写workspace。Holdings只在账户成功刷新时重建买卖关联；约1Hz list_state读取用已有Decimal批次标量与Quote重新估值，不重复匹配流水。前端selectionSource与buy_ids批次key分离于symbol，Watchlist更新不得覆盖持仓选择，HTTP/WS图表继续用原request_id/mode/socket保护。

SnapTrade固定请求配置account_id，不通过/accounts假设仅一个账户。成功核对后原始缓存只保存runtime/holdings/latest.json一份；activities分页仅属于SnapTrade成交历史，不改变Longbridge数据要求。每轮重读sequences.txt/merge_buys.txt，明确关联与原错误检查不变。SnapTrade及Longbridge拥有独立额度，均在同一Python进程内运行，不新增监听端口或服务。

## Longbridge 同步与缓存实现

完整数据规则只在 [longbridge-data.md](longbridge-data.md) 维护。`service.sync[(symbol, timeframe)]` 是唯一历史任务记录；启动及成员加入从同日成功batch与`store.latest`恢复complete和权威closed目标，scheduler只补实际缺少的闭合边界。水位仅查SQLite，不读含SDK暂定行的ChartCache。新交易日由现有scheduler零点后整窗准备，Regular开盘不重建订阅；没有9:25额外刷新或解锁监听。恢复复用同一检查，同日成功在途结果不重复排队，跨日新要求不能被旧结果抹掉。reconcile复用调度器，任务完成或本轮耗尽即退出；GET不改变任务。

`downloader.fetch`请求前后只核对交易日，允许跨盘前/Regular；校验最新closed目标及每根结构后提交。`store.upsert(replace=True)`在一次SQLite事务内替换单symbol/周期旧窗口，增量按主键覆盖。bars只含官方closed；batches记录成功请求日期、时间、数量与拒绝行。数据库采用WAL/NORMAL，不裁剪行数或管理旧历史。

`ChartCache.live`保存当天SDK全序列，`closed`先取其中已结束根，再由`store.window`覆盖同timestamp。依赖为store revision、SDK已结束序列revision及当前closed目标；只有最终显示序列变化才递增对外revision、重建指标和成交量参考。`forming`独立读取本周期当前SDK根，不等待历史Ready。`chart`沿用revision/bars/active/indicator_preview契约，不再缓存整份等待中的显示快照。

历史官方修正只改变统一数据；图表、量比、EMA和ADR按同一合并revision失效。价格Quote独立直接可用，不拿历史close替代最新价。`/v1/bars`读取统一closed序列；`/v1/readiness`检查官方历史任务，状态不拦住实时数据。

UI契约仍为 `status: {stage: loading|basic|full, errors: string[], refreshing: boolean}`，由现有历史任务派生。显示规则见 [Chart status](chart-ui.md#chart-status)。

## 实时 candle 与时段

`RealtimeFeed`在同一context注册Quote/candle callback，经既有asyncio loop派发并检查回调代次和当前范围。Quote/Trade和快照按批建立；`candle_subscribed`、`candle_errors`分别管理周期注册与错误。MonitorService提供初始化优先级，规则只在Longbridge数据要求维护。

`subscribe_candlesticks`返回的序列及callback统一以list送入`MonitorService.apply_candles`，由`longbridge.history.parse_candle`复用Bar校验；只接收当天有效行。初始化期间用短暂字典接住新推送，返回时按timestamp覆盖起点。全量起点成功后替换该SDK窗口，普通push覆盖单根；volume始终覆盖。NoAdjust隔日行不进入应用缓存，SDK confirmed不写SQLite。

`MonitorService.recover`重置报警比较起点、核对历史closed边界并唤醒既有RealtimeFeed循环。循环逐周期本地退订再注册，期间不关闭Quote/Trade或callback，保留已有应用数据直至新起点到达。真正连接失败才进入disconnect/connect；connect的on_reset重置比较起点，on_reconnect只检查历史任务，避免递归恢复。只有实际网络请求经过LongbridgeClient公共限流，本地candle删除不消耗请求额度。

LongbridgeClient显式enable_overnight=True。Quote的regular/pre/post/overnight统一标准化；snapshot与push走同一入口，快照不增加push_count。RealtimeFeed.output按timestamp返回quote.latest，同时保留regular/extended；Scan与Monitor不再分别过滤时段。MonitorService.quote修正Regular前收盘基准时同步更新指向该Regular的latest。Panel.setQuotePrice、Intraday顶部价格和Ext直接消费latest，不在前端排序或读取时钟；模拟器遵循同一latest契约。Quote推送计数表示应用收到的有效Quote消息数，不代表Trade或candle总数。各时段报价与candle分别存内存；preview只使用本周期缓存标量。validator的complete是官方历史诊断，不是SDK显示开关。

## 传输

同源 HTTP 静态资源与 `/v1/universe`；`/health`、`/v1/quotes`、`/v1/bars`、`/v1/readiness`、`/v1/chart` 为只读诊断。`/v1/chart` 不改变优先级。

UI 图表只通过 `/v1/stream`：select消息含symbol/timeframe/request_id/mode/source；source为watchlist或holdings，省略时按watchlist；旧模拟器仍可省略mode。初次、选择、重连为完整 bars+指标；常规只传 active/indicator_preview/status，历史改变才重发。约 5Hz 图表预览、1Hz 独立 list 消息。list 不依赖选中 symbol/request_id，所以删空、删当前项或重连时仍可刷新名单；图表继续保留 request_id 校验。run_id标识后端实例和当前数据上下文，request_id 与 socket identity 防止串图。保留 heartbeat、慢客户端独立发送任务和 Origin 校验；不新增差量重放协议。

list_state增加独立holdings字段：未启用或Scan为null；启用为{data,loading,error,error_kind}。error_kind为当前失败阶段request/accounting/storage或null，由Holdings刷新边界统一设置；成功时与error一同清除，前端集中映射简短原因/建议，详情用脱敏error原文，不逐层传UI文案、不解析异常字符串猜分类。data保留旧fetched_at/source_timestamps/positions_as_of/pnl_basis/funds/summary/holdings契约和Decimal字符串，holding增加price_source/price_timestamp/price_session、change_percent/extended_percent/day_reference_price；sequence与summary包含可空day_pnl；sequence增加is_new、closed_today、day_reference_price/day_reference_source，日期由Workbench现有时钟转纽约日期传入。total_pnl/total_pnl_percent字段名保留，余仓值改为仅未实现盈亏，summary.pnl/pnl_percent只统计余仓，百分比以余仓成本为分母；summary.day_pnl合计所有显示批次（含当日清仓），任一缺值则整体为空。build从positions加当日SELL发现显示范围，同一current_trades/sequences完成数量与归属核对；不靠上次页面状态保留清仓。Workbench通过monitor.quote读取与观察名单相同的Daily修正基准，再由holdings.py用Decimal重算日盈亏；缺基准不返回部分总额。无新增SDK请求、下载任务或缓存文件。GET /v1/holdings返回同一只读状态；请求不刷新账户、不安排历史。Account Value从估值市值加SnapTrade现金计算，原details账户总值仍在原始缓存，不冒充相同时刻的券商官方净值。本机WS关闭可选压缩，避免大图表/持仓快照发送时快速重载遗留aiohttp压缩后台task。

workspace.json 的根字段 `pinned:[ticker,...]` 为当日有序软状态；按 ticker 当前归属投影到各 List，保留原 statuses/section/orders。reset_daily_workspace 统一清理当日人工层，inherit_workspace 新日调用并设置 carried，Workspace.reclassify(reset=True) 在显式 Refresh 调用但保留当日 carried；apply_rules 去掉消失或跨 List 的成员。pin_ticker/move_pin 使用原同步保存与错误回滚，置顶动作不重跑分类或获取数据。Workbench board 返回 pinned:boolean、pin_index:number|null；独立 MonitorService 仅在自身附带 Workspace 时提供置顶字段，不覆盖 Workbench 持有的名单状态；list_state 增加 holding_symbols（两模式均提供、含当日清仓）与 current_regular_session（calendar.is_open，不依赖个股Quote）。两字段只提供显示信息，不改变后端名单。

List 动作接口：`POST /v1/list`，Content-Type 为 application/json，接受只读候选查询 `{action:"lookup",ticker}`（返回 `{ticker,name}`，不修改 workspace/白名单/订阅/调度）及 `{action:"add",ticker,list_name,section}`、`{action:"hide",ticker}`、`{action:"move",ticker,list_name,section,index}`（section为潜力Tag ID或unclassified），以及`{action:"move",ticker,target}`（target 为 discover/focus，来源取当前 workspace；机器 Excluded 不能手动释放，Hidden 可释放，任一 Excluded 可入 Focus）、`{action:"tag",ticker,tags:[Setup/Label ID]}`、`{action:"keep",ticker}`、`{action:"pin",ticker,pinned:boolean}`、`{action:"pin_move",ticker,index}`。pin_move的index为移除主动ticker后、同List完整置顶区的零基位置（含当前筛选不可见成员）。index 为移除主动ticker后目标section的零基位置。修改动作返回 `{board,editable,mode,workspace_error,notice?}`，成功响应前已同步落盘；WS `{type:"list",...}` 复用同一结构。校验同源 Origin；诊断 GET 继续只读。`--symbols` 仅跟踪指定子集，禁用 mutation 以保持验收范围。

单只跨 List 使用 Workspace.move_member；删除批量 tickers/source 协议与 move_members。列表状态增加 app_mode、date、dates、preferences 和 mock；历史 Scan 或 --symbols 不可写。POST /v1/mode 切换模式，POST /v1/scan 选择/准备日期，POST /v1/preferences 同步保存完整偏好；写入共用同源检查和 64KiB body 限制。

新日 inherit_workspace 与显式 Refresh 共用 reset_daily_workspace，去掉当日人工层及排序，然后 apply_rules；机器 Excluded 不落盘。新日额外更新 carried，同日不改其含义。Workbench 在准备成功（包括 Ready 跳过）后重读当前 workspace，并 reclassify(reset=True)；不新增获取或准备状态。普通 publish_day 同日发布仍保留人工层，GET、报价更新、启动准备和保存 Tag 不触发用户 Refresh 的清理。正式默认 days 为 runtime/days。

Watchlist.handleKey 维护观察名单键盘入口，ScanControls 仅管理 Tag/Filter、日期与显示偏好，不再持有成员勾选状态。行按钮和快捷键通过 actOnTicker/togglePin 共用单只动作；mutate 的可选 advance 参数仅由确认的三类动作传入。提交前保存可见顺序，等待期间阻止本次删除引起的首行候补，成功后 advanceSelection 选后项或末行；用户换股/切 List/模式后不抢选择。其余选择路径不改。Page 导航使用已渲染非空 section 的首个 symbol，展开目标；不引入全局事件或选择框架。

前端只有一套 Search 状态（目标 Section、候选、提示与在途 lookup）。/ 和 + 共用入口；Scan全局Search目标为Discover置顶，显式Focus section的+保留目标。Scan查询本地只读SQLite并截断到所选日，Monitor使用static_info。输入后 1 秒延迟只用于 lookup，写文件仍同步立即执行。输入变化/退出会取消等待及 fetch，并以 Search 对象身份忽略迟到结果；Enter 复用正在执行的 lookup。最终 add 仍由后端验证，不能信任前端传来的证券名称。Shift 换序复用 move，目标 index 为移除主动 ticker 后的位置，不新增 swap 接口。

## 必要验证

遵循 [development-principles.md](development-principles.md)，仅验证本轮修改。优先直接使用真实本地数据和正常运行的服务；确需停/重启时可直接执行。真实接口检查写清当前范围及结束条件，不使用历史记录代替本轮证据。

只选有关的用例，例：`.venv/bin/python -m pytest -q tests/test_massive_incremental_build.py`。TypeScript改变后运行`npm run build --prefix ui`。不默认执行整个项目回归或全流程检查，不为罕见边界建立故障注入/并发/回放框架。已有模拟器保持隔离，不自动读凭证或回退真实API。

## Intraday State 实现

唯一需求见 [intraday-state.md](intraday-state.md)，模块维护见 [AGENTS.md](../data_service/intraday_state/AGENTS.md)。MonitorService在正式Workbench完整会话创建IntradayState；Quote、SDK candle及官方历史提交统一调用update，立即计算当前价格状态、量比与等级；现有scheduler秒级tick处理经过时间与边界rank。不创建新任务服务，不依赖HTTP或图表选择。Mock默认没有声音，--symbols子集不创建状态模块。

Workbench.refresh_alert_scope同时传入Focus候选与当前余仓角色，排除仅当天清仓的ticker；不改变原手动Alert与行情白名单。状态/穿越/截至昨日ADR与排序等级由engine.py维护，ADR缓存键包含日线revision。盘中ADR直接使用Quote的Regular开高低和最新价，不等待SDK Daily；EMA仍复用Daily preview。价格状态和分钟量比独立就绪，统一接口中缺价格字段为null，volume仍可用；前端按字段显示缺失。恢复只清比较起点，保留有效显示，首份新价格状态静默；派生状态不另存业务库，不逐份Quote落盘。

volume.py只读ChartCache统一closed及SDK open，按合并revision缓存多周期分钟volume索引；区间覆盖只返回标量，每个历史日期独立覆盖后再平均。配置直接读取config/intraday-state.json，启动校验阈值顺序，不增加配置监听或规则编辑器。

GET /v1/intraday-state只读返回enabled和symbols；现有list快照增加同名intraday字段，Scan历史关闭该字段。symbol状态含role/state、ADR20、上下行倍数/等级、above_open、price/timestamp、cum_vol/local_vol和rank。量比含ratio/actual/average/samples/level，LocalVol另含window；缺值为null。rank是价格/CumVol/LocalVol三个离散整数，前端不重新计算业务阈值。

ui/src/intraday-state.ts集中格式化、Badge和rank比较；quiet参数仅供Focus隐藏低倍数，Holdings保留完整数值，缺失仍为—；ADR数值方向独立于预警阈值，持仓neutral时选择较大的一项。list.ts直接使用In Play section，复用标题/折叠/空组隐藏，删除Grouped/Dynamic状态与偏好。holdings.ts保持独立风险排序和清仓尾部；重排复用节点、恢复焦点和滚动位置。全部报警及未读通过AlertEngine.notify/read共用上述Alert契约，Intraday State不自行播放声音或存另一份通知。

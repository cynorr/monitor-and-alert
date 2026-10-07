# 验证记录

本文件只记录各次验证事实，不定义 UI 要求；当前规范统一见 [ui.md](ui.md)。

## 2026-10-08：Longbridge 六周期 SDK 实时 candle

环境：macOS、Python 3.13、Longbridge SDK 5.0.0；美东 2026-10-07 Regular。正式服务按当前 Focus 与 Holdings 白名单验证，未新增或运行 Mock，未录屏。

- 当前周期为 Daily、5m、15m、30m、1h、2h；SDK 映射、日历、调度、Ready 与 UI 入口一致。全部 56 个 symbol 的 336 个 closed 窗口完成初始化，pending=0、无耗尽任务错误，Quote CONNECTED，已收到 3,424 次 Quote 推送；Holdings 后台任务运行。
- closed 与 SDK 订阅初始化完成后，连续观察 MU 20 秒：六周期 open 均有整数 volume，六周期均持续更新；2h WebSocket 收到 94 次图表更新，active 未清空。
- 已撤下周期的图表与 bars 请求均返回 400，页面只提供五个 Intraday 周期；正式缓存已清理对应 48,254 根 bar 和 56 个 batch，复查没有残留或重新写入。代码、脚本、测试和文档无已撤下周期的引用。
- SECZ Daily 的官方重复时间戳仍明确拒绝并显示诊断；Ready 不表示原始历史无异常。没有新增数据补偿或跨周期组合。
- TypeScript build、Python 编译与 git diff --check 通过，正式服务保持运行。

证据：[正式服务验收](</var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/monitor-period-removal-omog7as1/report.json>)。

未覆盖：整日运行、实际断网/休眠、收盘、DST/提前收盘；本轮未重复浏览器帧率测量或全量离线回归。数据口径与处理规则统一见 [Longbridge 数据说明](longbridge-data.md)。

## 2026-10-07：Alert 连续播放原声

环境：本机 macOS 26.7、Python 3.13.1。只验证声音资源与播放任务，没有运行其他业务测试或前端构建。

- `tests/test_alert_sound.py`：4 项通过，覆盖上穿/下穿各调用播放器4次、事件串行、播放失败与后续新事件恢复，以及退出清理。
- 两份 WAV 恢复为原始单次声音，每份46,788字节；每次 afplay 完成立即调用下一次，没有合成音频或主动等待。
- 实际仅试听上穿、下穿各一组，每组调用原始音频4次，均播放完成，error=null；没有测试其他业务功能。
- 后台沿用原 runtime 重启加载修改；需求与实现契约同步 alert.md、development.md。本轮没有创建正式 Alert、修改名单或测试行情触发、卡片、图表与持久化。

## 2026-10-07：Alert 改用后台声音与持久卡片

环境：本机 macOS 26.7 arm64、Python 3.13.1、TypeScript、Chrome 与正式 Safari Charts。按本轮要求使用临时 SQLite 和 mock Regular 最新价验证触发，没有等待开盘或修改正式名单、Alert、账户。

- `.venv/bin/python -m pytest -q tests/test_alert_sound.py tests/test_alerts.py`：28 项通过。覆盖新事件提交后才播放、同条不重复播放、失败写入不播放、恢复/处理卡片不重播、Mock默认静音、任务启动/退出，以及串行音频、播放错误和后续新事件恢复。localhost 用例在沙箱外运行，所有数据写临时目录。
- `npm run build --prefix ui`、改动 Python 编译、文档链接和 `git diff --check` 通过。离线构建 wheel 确认包含两个 WAV 及 sound.py，不含旧 macos.py 或原生通知依赖；刷新本地 editable 安装后 `pip check` 通过。
- 明确启用实际声音，用 CHECK.US 的临时 Regular 最新价经 AlertEngine 依次触发上穿和下穿，间隔约两秒，两个事件均持久化、声音状态 error=null。用户确认“两次都听到，声音不同”。没有读取行情凭证或在正式 Alert 中制造触发，临时库已清理。
- Chrome 使用 Scan Mock 副本、临时库和既有 FakeBroker，localhost:8767 限时120秒。两张未处理卡片在刷新前后均存在，原通知按钮为0个，页面无 console error。完整截图保存在 `/tmp/alert-cards-refresh-2026-10-07.png`；临时服务、目录与页面已关闭。
- 正常退出旧原生进程，实际删除 `dist/Market Monitor.app`、macos 构建目录、launcher/setup/build脚本及 PyObjC/py2app 和其专用依赖；原 WAV 移入 Alert 模块。正式 runtime 改用现有 Python CLI 启动，/health 为 running、Quote 为 CONNECTED；Alert sound 为 enabled=true、error=null。切换前后正式库均为3条 Alert、2条历史事件、0条未处理事件。Safari Charts 已刷新，恢复 Monitor 与 PLSE 选择。
- Alert 需求、职责/契约、产品行为、UI 总入口、README 与模块 AGENTS 已同步为后台声音和持久卡片。

未覆盖：真实 Regular 行情穿越、Mac 重启/睡眠与 macOS 27 实机运行。当前听辨只证明本机当前音量和输出设备下的两种声音，不把子进程成功退出当作其他设备的听辨证据。

## 2026-10-07：Additional Info 显示精简与位置微调

环境：本机 macOS、TypeScript、现有正式服务与 Chrome，使用本轮已有 Nasdaq 缓存及真实图表。只修改前端显示和维护文档，不重启服务或安排额外供应商请求。

- `npm run build --prefix ui` 和前端28项用例通过。新增分类精简用例覆盖括号说明、冒号后细节、重复首级/大小写/空白和可空分类；可空显示用例同步 Intraday 市值及无美元符号。未重复运行未改动的 Python 数据/调度用例。
- 实际 Scan 的 USDE 显示 `Finance`，没有重复 `Finance: Consumer Services`；2026-10-06 日图、ADR/ADV及三条指标正常显示。既有Massive准备完成后，本次成功切换和读取不再遇到上一条记录中的重建写锁。
- 实际 Monitor 的 AGEN 显示 `Health Care · Biotechnology`，分类与EMA/SMA均为11px；`Market Cap 394.26M`位于 Intraday 周期按钮下方，11px、黑色且不带美元符号。财报与ET时间均为12px、#293341；两个头部实测均120px，指标行及下边界对齐。浏览器已刷新为本轮生成文件，结束保留Monitor、AGEN与1h。
- 完整原分类及美元金额仍保留在独立数据契约中；显示规则、职责入口和唯一图表规范已同步。`git diff --check`通过。

未覆盖：Regular时段真实bid/ask同时出现的布局、全部行业逐个浏览和移动端；没有把本轮前端显示验证作为刷新调度或上游可用性验证。

## 2026-10-07：独立 Additional Info

环境：本机 macOS、Python 3.13.1、正式 Longbridge SDK 5.0.0、TypeScript 5.9.3、Chrome；真实 Nasdaq 请求使用工程既有代理，不读任何券商或 Massive 凭证。新增模块规则只在 [additional-info.md](additional-info.md) 维护。

- 本轮有界公开接口验收：一份 Screener 整表和四个财报日期（2026-10-01、10-04、10-07、2027-02-04）。新模块真实解析出6,628个可匹配`.US`证券，分别取得5、0、4、0条财报事件，全部成功写入临时独立SQLite。验证AAPL/AAOI分类与市值、ACN已发布报告、未来预估事件及空日期；QCML未覆盖字段为null。当前整表的Common Stock/Ordinary Shares/Class A/B/Preferred Stock/Depositary/Voting后缀均通过Python清理，原行保留。
- Python定向102项通过，覆盖名称清理、零/负EPS、日历请求日期、成功替换某日及取消事件、失败保留旧数据、缓存重读、首次/每日/每周窗口与续做、冻结旧历史、缺失/损坏缓存、Mock不联网、启动不等待附加任务、选择身份、独立WS更新不重发bars及原ETF/Scan流程。旧名称用例迁到新模块；同步一个旧Scan测试的失效断言：指定日重建原本只允许CLI，HTTP仍拒绝。补验独立GET/POST、Origin限制及立即安排刷新后，3项集成用例再次通过；临时CLI同日`--companies-only`成功跳过已有公司表，无新请求。
- `npm run build --prefix ui`通过，前端27项通过；包括最近报告优先、七日后转下次、缺事件、纽约跨日/DST、单数/Today、选择身份及缺失显示。Python编译与`git diff --check`通过。没有升级SDK或新增依赖。
- 正常退出旧原生实例后，把本轮成功Nasdaq缓存作为首次缓存并重启正式Market Monitor。独立首次任务完成2026-06-09至2027-02-04共241个日期，成功跳过已缓存4日，errors全部为空；公司表未重复获取。Monitor Quote为CONNECTED、Holdings持续刷新，附加信息下载中实际图表已显示。没有改名单、账户或Alert；页面结束恢复Monitor、AGEN与1h。
- Chrome实际验证公司名与symbol同基线、下一行sector/industry及市值、ADR/ADV下移、120px头部保留。AGEN显示Next earnings report / In 33 days，MU显示Last earnings report / 7 days ago；名单和Holdings选择共用信息。QCML四项隐藏而行情指标正常。窄Daily面板省略财报说明文字，保留天数；完整日期、预估说明及更新时间在tooltip。
- 重启同时触发既有Massive新交易日2026-10-06准备，滚动split文件按原流程更新，bars全量重建期间切Scan遇到既有行情SQLite写锁，WS图表暂时关闭。已恢复Monitor；该问题来自Massive写库/Scan读库路径，未修改其行为，不能把本次短暂切换计为成功的真实Scan图表验收。附加信息GET、缓存和独立刷新不读取该库。

未覆盖：持续运行时真实纽约跨日/七日定时刷新（用定向用例覆盖计划）、公开接口实际失败/schema变更、历史Scan/Review的浏览器完整验收、Regular时段bid/ask布局和移动端。失败/缺失路径只用临时缓存的相关用例验证，没有故障注入、通知或交易操作。

## 2026-10-06：Massive 状态与 Refresh 简化

环境：本机 macOS，Python 3.13.1、TypeScript 5.9.3；真实输入为正式runtime的2026-10-05 Daily SQLite、raw、split和已生成截面。没有启动/重启正式服务，没有调用Massive、Longbridge或SnapTrade接口。

- Python定向12项通过，其余40项未运行：已完成阶段跳过、节假日/周末统一交易日、较宽的旧split覆盖复用、特征失败后续做、强制维护的交易日窗口、普通Refresh返回最新日期与run_id更新、CLI重算后的Ready标记、CLI强制入口与单实例锁。用例只写临时目录，不运行HTTP/WS或全链路验收。
- `npm run build --prefix ui`通过；只运行Scan准备状态的1项UI用例，覆盖正常隐藏Ready、旧截面不能冒充新目标Ready、运行/失败目标日期和错误详情。未运行其他UI测试或浏览器验收。
- 真实数据验证使用临时runtime：只读链接正式行情输入，复制2026-10-02/05名单及截面；直接调用两次Refresh，从10/02返回10/05，耗时0.345s/0.339s。四个下载/构建阶段均未执行，没有创建券商或网络session；正式586个数据/名单/偏好文件的大小与mtime保持不变，状态和临时业务SQLite仅写临时目录，结束清理。

未覆盖：真实下载/分页重试、新交易日完整生成、前端浏览器交互与实时行情/账户链路；这些不是本轮验证范围。

## 2026-10-06：Alert 需求与统一 Focus 入选文档

环境：本机项目工作树；本轮仅修改 Markdown 与 AGENTS.md，不修改 Python/TypeScript、运行数据或凭证，不启动/重启服务，不调用真实行情或账户接口。

- 对照本轮用户修订、quotes.py、workspace.py、list_rules.py、workbench.py、现有 List/Chart/UI/开发文档，建立独立 alert.md 和 data_service/alerts/AGENTS.md，并同步总入口及局部维护约束。新需求和新入选规则均明确标为已确认待实现。
- 核对 Regular-only、鼠标水平线价格、到达算触发、无停机补报、symbol 共用身份、Scan Discover/全部 Excluded 创建先入 Focus，以及手动/Alert 共用清理来源 Tag、重新匹配与组首插入规则；清除旧入口中禁止开发 Alert 的过时约束。
- 进行文档差异、相对链接/锚点与入口一致性检查。未修改 TypeScript，未运行 npm build 或产品测试；这些文档检查不是运行功能验收。

未覆盖：Alert Engine、SQLite、名单入选代码改动、图表交互、真实行情触发、macOS 通知权限/投递/声音、任何平台运行兼容性。后续开发须分别取得必要证据，既有记录不能冒充本轮 live 结果。

## 2026-10-06：Holdings 余仓盈亏、当日建仓与清仓复盘

环境：macOS、现有 Python3.13 虚拟环境、TypeScript 与正式 Monitor 服务。纽约市场日期为2026-10-05，本机日期为2026-10-06。真实接口验证仅限既有11只持仓、当日成交及既有Focus行情范围，成功读取并核对后结束；未修改账户、人工关联规则或名单，未请求额外历史ticker。

- 相关Python定向用例38项通过，前端Holdings定向用例7项通过，`npm run build --prefix ui`通过。覆盖部分卖出后的余仓P/L与百分比/Total分母、四时段当日建仓、混合新旧买入日基准、次日基准切换、周末与7/8自然日边界、从已成交订单发现零持仓、清仓后同ticker重新建仓、歧义报错及清仓固定尾部排序。未运行全项目测试。
- 按原命令重启正式服务，仍为Monitor及56个去重行情标识。首轮SnapTrade返回HTTP429，已接受快照保留；后续正常30秒周期成功，无额外即时重试。17:38:07 UTC成功快照的11条持仓全部使用Longbridge，逐条余仓P/L、成本口径百分比与汇总核对通过。TEAM建仓价194.10、最新价195.81、100余股，P/L与P/L Day均171；PURR建仓价12.92、最新价12.80、1,000余股，两者均-120。报价后续正常变化，浏览器中的两列继续一致。
- 1280×720默认浏览器核验TEAM持仓选择复用Daily/Intraday，PAYS Days=3、PBF Days=2、当日TEAM/PURR Days=0，tooltip明确entry price；未改本轮之外的图表参数或布局。浏览器无error/warn。
- 当前真实账户没有当日全部清仓批次。另用已有EFOR 2026-10-01买入/10-02卖出实际成交只读构建历史样本：零持仓、最终已实现P/L=-987.35、清仓不计入Total。临时离线展示页导入正式Holdings组件/样式，明确标注历史样本；Sold降序时EFOR的100%仍置底，主行/Buy/Sold均为灰色，500股、买入价36.35与卖出价34.37、两笔日期均完整显示。验证结束删除临时页面和样本文件。此项是实际历史输入与当前组件验证，不是本轮实时stop-out事件。

未覆盖新的真实清仓事件、真实跨午夜/周末长期运行、跨日期分批成交的同一订单；本轮当前真实订单没有跨日期fills。相关日期规则由定向用例补足。正式服务保持运行，账户轮询、行情范围与既有图表机制继续使用原流程。独立数据需求已写入holdings-data.md，数据/前端AGENTS及唯一文档入口同步。

## 2026-10-06：Chart 公共 API 与 vendor 核对

本轮只读核对当前前端及已安装 Lightweight Charts 5.2.0 类型声明，并对照 TradingView 官方 API 文档；只修改需求与维护文档，不构建前端或操作服务。

- barSpacing、panes/setStretchFactor、pane 尺寸、subscribeCrosshairMove/seriesData、程序 crosshair 与 viewport/scroll 方法均为公开参数/API。未发现私有接口调用、原型修改或对库内部 DOM 结构的选择器依赖；OHLC/Volume 文字及交易日联动属于使用公开 API 的应用层代码。
- 本地 vendor JS 与 Git HEAD、已安装包的官方 standalone production JS 逐字节一致，SHA-256 为 `c0992580867c4912cc9385b3c2728315bcc1a76c7f1087dca908430fccdf31d7`；vendor/依赖文件无改动。Chart 需求文档第一条已明确优先内置参数/公开 API，保持库源码原样以便后续更新。
- 当前源码与生成文件均已由人工设为 BAR_SPACING=5，本轮保持原值；文档同步当前人工值，并明确 2px/约12个月是前轮窗口条件下的参考，不是修改间距后仍固定的时间范围。未用前轮截图或交互记录冒充本轮 live 验证。

## 2026-10-06：统一 Chart 默认值与固定 Holdings

环境：macOS、现有 TypeScript/Lightweight Charts 5.2.0、正式本机服务和 1280×720 浏览器窗口。仅修改前端与需求文档；服务未重启，未改行情计算、人工名单或账户数据。图表验证只选择既有 GPRO/PAYS，未扩大 Focus/Holdings 行情范围。

- `npm run build --prefix ui` 通过；最终 3 项 chart 交互用例通过，覆盖旧 candle 悬停跨 Quote 更新保留、同根数据修订、active volume/缺失值、双图联动及离开恢复最新值。测试中的程序 crosshair API 按本地真实库的“不触发 move 回调”行为实现；最终代码显式同步 peer 数值。未执行全项目、全流程或并发测试。
- 所有 Panel 使用集中 `BAR_SPACING=5` 和 `VOLUME_PANE_RATIO=0.28`。实际 Scan 日图宽 568px，完整 PAYS 历史默认约一年；短历史 USDE 保持右对齐及左侧空白。Monitor 两图默认间距一致，手动拖动成交量分界向上 30px 后 label 的 top 同步减少 30px。最终刷新恢复两图一致默认分界。
- Scan PAYS 2026-03-25 悬停显示 V 9.45M，与本地 Massive 的 9,453,218 一致；离开恢复最新日 V 862.48K，对应 862,481。Monitor GPRO 2026-09-23 日图显示 V 17.07M，联动首根 1h 显示 V 1.8M，对应本地 Longbridge 17,069,379 和 1,799,413。持续 Quote 更新保留历史悬停值；最终离开两图均恢复最新 volume。在 Intraday volume 区悬停也能读取垂直对应 candle。
- 实际 11 条 Holdings 自然高度 407px。名单滚动 720px 后 Holdings top 仍为 220px、Filter top 仍为 130px，外层 scrollTop=0；整体折叠后持仓高度 66px，下方名单高度由 83px 增为 424px。NEW 的实际 CSS 颜色为 rgb(41,98,255)，与 EMA10 #2962ff 一致。固定容器使用 min-height:0 与 overflow:clip，避免 grid 的内容最小高度或程序 scrollIntoView 带动顶部区域。
- 浏览器无 error/warn。验证结束恢复 Monitor 模式、Holdings 展开及空 Search；保存本轮 Scan/Monitor 截图。Chart 与 Holdings 全部 UI 要求已迁入 chart-ui.md / holdings-ui.md，List 的 NEW 要求保留 ui.md；README、AGENTS 与职责/行为入口同步。

未覆盖所有窗口尺寸、全部 Intraday 周期逐一验收、持仓远超屏幕高度或大量明细同时展开。固定区域使用自然高度，整体折叠释放名单空间；没有增加独立竖滚、高度上限或布局框架。

## 2026-10-06：Massive 继承名单完整特征

环境：macOS、现有 Python3.13 虚拟环境、正式 runtime 的 2026-10-02 Massive Daily 和人工名单。本轮按开发准则使用真实数据与现有服务，未获取新的 Massive/Nasdaq 数据，未改写原始 Daily 或重建 SQLite。

- 定向 Scan 生成、筛选和 Pipeline 用例 34 项通过；增强前日继承用例后单独验证通过，另验证 Hidden 七天内仍跳过分类的相关用例通过。覆盖候选外与不满足初筛的成员完整 RFL、ETF/短历史成员不占名次、全部 Excluded/Hidden 的计算范围、旧截面已有 EMA 但 RFL 为空时补算一次、排名保持、当日无 bar 不冒用前日特征及相关生成错误。未跑全项目或全流程测试；无 TypeScript 改动，未重复前端构建。
- 真实名单共 87 个 Focus/Excluded，其中 24 个缺少完整特征或三种 RFL。旧截面补算耗时 1.263 秒，新生成耗时 6.886 秒；两条路径均补齐所有 87 个成员，全部三种 RFL 与本地最近 21/63/126 根日 K 直接计算一致。85 个候选及全市场 eligible/candidate/三组名次与原截面一致；再次补算结果不变。
- 00:30（Asia/Shanghai）停止原正式进程，并以原命令恢复 Monitor 服务。启动的本地名单准备已保存修复后的截面；本轮 HTTP 确认 Monitor 模式、Massive Ready=true、52 个 Focus 行均有完整特征及三种 RFL。本地 Scan 展示读取确认 87 个保留成员全部补齐，其中 Hidden 的 AMUU/APPS/XRPN 也完整计算，名单规则仍保留屏蔽。

本轮只验收本地特征和名单展示数据；未执行完整券商/账户验收、浏览器交互、长期运行或性能框架。正式服务按原 Focus/当前 Holdings 范围恢复后台工作，未额外授权 Excluded 的实时行情请求。

## 2026-10-05：按单人本机准则简化 Massive

环境：macOS、现有Python3.13虚拟环境及本机正式Scan服务。本轮用户明确授权使用真实数据和现有服务、必要时停止并重启。开发准则独立保存为development-principles.md；以下简化取代同日上一轮的事务恢复/版本自动失效方案，其历史通过记录不代表当前代码。

- 移除逐ticker拆股/删除日修复、状态表、临时库替换、显式事务协调、只读快照、输入竞态检查和失败保留旧SQLite的保证。build.py从278行降至162行；仅保存文件清单和实际split摘要，普通新日追加，旧输入变化删除后全量重建，写入失败删除派生库并报错。
- 配置/目录不再维护feature_revision或自动重算；手动Refresh读取当前配置。去掉额外Test Issue条件、协议别名映射、目录schema/hash及自动重试。免费目录只使用两文件主符号，实际原文重新导入为13,289个.US标识，原97个候选均有主符号匹配。ETF和50根有效日K仍先于RFL排名；核心行情校验/拆股/HALF_UP保持。
- 仅运行本次相关的26项定向用例，覆盖增量、新旧输入变化、失败删库、直接本地报错、ETF/50根与排名顺序；最终简化预检查后再跑3个相关错误用例，均通过。目录/名称/网络相关20项通过。不执行全项目、并发压力或全流程验收。本轮没有TypeScript改动，未重复前端构建。
- 暂停现有正式服务后，用实际558份raw重建至2026-10-01（83.365秒），再增量追加10-02一份raw（0.702秒）。当前SQLite共6,397,228根，与重建前总行数一致；NVDA/AAPL/PAYS/TQQQ两个日期的8条OHLCV/turnover逐值一致。未重复逐行遍历全库或构建第二份全量对照。原始JSON未改写。
- 实际生成并发布2026-10-02截面，85个候选均非ETF且满足历史门槛；筛选与特征共4.382秒。恢复同一正式服务的Scan模式，现有Focus/已接受Holdings范围继续后台接收；仅对Scan Ready和PAYS.US图表做约一分钟内的HTTP读取检查，Ready=true，名单132条，PAYS有559根日K及名称“Paysign, Inc. - Common Stock”。未调用额外live验收脚本、修改持仓或增加订阅范围。

当前速度数字是本机缓存条件下的普通新增日；旧raw或split修订的全量重建预期较慢。未覆盖物理断电、长期并发、完整券商/账户验证和浏览器手势，不为这些场景新增恢复或测试框架。

## 2026-10-05：Massive 目录过滤、配置与 SQLite 增量

环境：macOS、项目现有 Python3.13 虚拟环境、Node/TypeScript。正式服务的 runtime 锁仍被占用；没有重启服务、修改正式 bars/截面/人工名单、调用 Massive/Longbridge/SnapTrade 或读取它们的凭证。真实行情文件只读，建库验收在 /private/tmp 临时库执行，结束后删除。

- 相关核心离线检查首轮105项通过，覆盖候选过滤/排名、准备阶段、增量构建、名称、网络、指标与名单规则；最终修改后目录/配置/准备相关63项重跑通过。Scan/Holdings/Volume/Workspace集成68项通过，HTTP/WS仅用临时localhost及fake。UI check/build及17项Node测试通过，最终TypeScript构建、git diff --check和9份Markdown文件的本地链接检查通过。没有运行全项目回归或浏览器截图/手势验收。
- 过滤用例覆盖 ETF/未知分类/Test Issue 在RFL计算与排名前拒绝，49/50根边界、未来bar不计入、缺名称允许、低价仍入选、人工保留成员维护、Hidden跳过。目录用例覆盖官方表头/末行完整性、空名称、显式别名/无歧义归属、UWMC^#、坏schema/revision、失败保留缓存及重试。配置或目录单独修改仅重算特征、不请求Massive或更新bars；准备过程中目录变化后的Ready版本也通过。
- 增量用例覆盖新日只解析一文件、输入未变不写、修正日撤销旧bar、拆股新增/修订/删除只重算受影响ticker、HALF_UP原始重算、1000根稀疏窗口及删除日恢复、旧库迁移、早日重建、输入竞态/写后失败回滚，以及同时读写时bars与完成metadata的一致快照。
- 真实只读输入559份原始Daily（2024-07-12至2026-10-02，约672.7MB）：先建2026-10-01临时基线，再增量追加10-02耗时0.936秒，仅读1份文件且SQLite inode保持；独立完整10-02重建87.549秒/559份文件，增量约快93.5倍。两库6,397,228根bars按主键流式逐行完全一致，metadata完全一致，成交量均为SQLite integer。比较摘要SHA-256为 `6aa4b2800b0ed48e3447306a5271841616f7e3161a2d97c7d603a566dbcf5a28`；逐行比较本身229.243秒，不计入建库耗时。此结果只证明本机缓存条件下普通新增日的速度，首次迁移和拆股修订仍需读取更多历史。
- 实际获取两份免费Nasdaq Trader文件共892,343字节，源文件创建日均为2026-10-05；初次实际解析发现官方别名UWMC^#后补齐格式支持，用同一下载文件离线导入。当前本地目录14,261个.US标识（含明确别名），已原子保存runtime/symbol-directory.json。使用项目代理，没有回退直连；没有新增Massive类型/名称/IPO请求。
- 当前正式2026-10-02库的12,601只证券只读试算：已确认ETF 5,751、目录未知19、确认非ETF但不足历史200；新规则eligible 651、候选85（旧截面97），候选ETF与不足历史均为0，完整feature范围129（含保留人工成员）。耗时10.648秒，期间同时进行大库逐行比较，未作为独立Scan速度基准；没有发布覆盖正在运行服务的原截面。

未覆盖：真实Massive获取/拆股分页、券商/账户、当前运行进程的重新加载与正式首次迁移、物理断电/休眠、长期并发读写、冷缓存速度及原生端。当前代码与已缓存目录在下次服务重启后参与准备/刷新，旧进程和已保存截面未冒充新规则生效。

## 2026-10-05：Logo / Icon 规范整理

环境：macOS、现有项目源码。仅整理文档与 AI 维护入口：核对 Tag 图形、名单操作、折叠/排序、图表图标及品牌现状，区分通用设计和 Web 实现，记录 Android 原生与可能的 iOS 迁移约束。42 个文档链接/锚点检查及 `git diff --check` 通过；未改应用代码，未运行构建、回归、浏览器或真实 API 验收，未验证原生端。

## 2026-10-05：Extended 图案微调

环境：macOS、现有 Node/TypeScript。仅将 Extended SVG 改为起点更低、平缓段延长、右侧末段接近竖直上冲的单条三次曲线，同步唯一 UI 规范；`npm run build --prefix ui` 与 `git diff --check` 通过。保留原尺寸、颜色与背景，无名单/数据改动；未重复运行回归或真实 API 检查。

## 2026-10-05：Tag 轮廓图形与外观编辑

环境：macOS、现有 Python 虚拟环境、Node/TypeScript、Codex 浏览器。交互验收仅使用临时本机合成名单，导入正式 UI 组件和样式，POST 调用正式 preferences 校验函数；没有新建券商连接、修改正式 runtime、重启现有服务或运行全流程测试。结束后只读打开现有项目页面展示新图形，不作为 live 验收。

- `npm run build --prefix ui` 与 `git diff --check` 通过；`node --test ui/tests/scan.test.mjs` 12 项通过，覆盖外观草稿保存、独立克隆、改名保持绑定，以及仅改外观时人工匹配成员继续可见、改条件后转入条件预览。
- Python 仅选择 preferences appearance 与既有未知条件检查，10 项通过、16 项未运行；覆盖旧定义兼容、透明/毛玻璃外观往返、非法字段/图案/颜色拒绝。
- 浏览器实测七列行高约 32px，glyph 约 16.2×10.8px，前景 MA10 蓝/MA20 黄，背景浅灰 20% alpha、无边框；680px List 内容无横向溢出。三个图案后以 `+N` 显示剩余标签，人工来源保留 tooltip，Orderly-pullback 为 steps。
- 验证外观 preview、Cancel 恢复、Save 后折叠、刷新恢复自选图案/颜色/透明背景和改名；自选毛玻璃背景颜色呈现低 alpha，透明模式禁用背景色输入。仅改外观时，三个人工匹配成员保持可见。Scan/Monitor 使用相同图形与行高。
- 未覆盖真实行情/账户、全局拖拽/图表手势、移动触控或长期运行。临时检查脚本和服务已清理。

## 2026-10-04：List UI 单行与独立列

环境：macOS、Node 25.3.0 / TypeScript；现有本机8765服务的 Scan 页面。只改前端显示与文档，未启动、重启服务，未修改名单、Tag 规则、账户数据或行情范围。

- `npm run build --prefix ui`与`node --test ui/tests/scan.test.mjs`通过，11项定向检查；新增增长显示边界、缺失/非有限值检查。RFL排序和底层百分比保持原值，130%显示2.3x、65%显示65%、100%显示2.0x。
- 浏览器检查七个行单元、独立Growth/Tags列、淡色分隔线、Tag竖排、计数10px/黑色/正常字重，以及Filter两列完整分组竖向交错。1280px视口Scan列表为680px，前八行无横向溢出；无Tag/单Tag行最低32px、实测双Tag行38px。隐藏的Tags按钮不占额外一行，Hidden不提供人工Tag编辑。
- List默认占扣除工作区内边距与分隔条后宽度的40%；680px下限与Holdings所需内容宽度优先。Scan实测因下限占54.5%，日图568px；分隔条ArrowLeft把列表调至692px，双击恢复680px。只读代码复核Monitor双图均分、模式切换重置临时比例及拖动最小宽度约束。
- 页面无error/warn。未执行全部Python/Node回归、名单拖动/批量写入全流程、Monitor账户交互、真实API或长期运行；此前live记录不作本轮证据。

## 2026-10-04：List / Tag / Filter 重构

环境：macOS、Python 3.13.1（现有虚拟环境）、Node 25.3.0 / TypeScript。仅运行改动相关离线检查，行情使用 fake，未读取券商凭证或连接真实 API。

- Python 定向检查70项通过：List/Workspace 23项，Scan生成/Massive准备31项，Workbench相关非HTTP场景及名单读取16项。覆盖三名单迁移、负面优先、Hidden跳过与跨候选空档、七天到期重评、Review持久保留、人工当日覆盖、队首插入、删除/改用途后的section恢复、存盘回滚、本地scope补算与失败保持、规则发布、背景行情/展示切换、Review不订阅，以及同ticker Holdings实时图/Review本地预览来源隔离。
- UI相关Node检查10项通过；`npm run build --prefix ui`通过。覆盖字段/边界匹配、Tag草稿、用途/section、人工标签筛选、独立折叠及同symbol选择来源。`git diff --check`通过。
- 现有2026-10-02本地截面只读核对：旧Focus/Wait合并共55只；按现有规则得到Focus47、Discover65、Excluded29（Broken2、Extended25、Hidden2）；Hidden2只跳过形态扫描。只在内存补齐特征、分类，不修改正式名单或数据库。
- 未运行全量回归、浏览器手势、真实API、原生FSEvents/本机HTTP全流程、长时间运行或物理休眠。有关真实接收/启动的历史记录不能当作本轮live证据。

## 2026-09-24：默认周期与搜索显示微调

- 环境：macOS、现有真实服务 `127.0.0.1:8765`。TypeScript build 通过；Node 直接检查构建后的默认周期函数，10 个开盘前、5/15/30 分钟边界、1h 上限及冬夏令时样例通过。
- 页面只读检查：当前美东 15:07 默认选中 1h；搜索 PAYS 只显示 Focus，Wait 隐藏，无回车提示；regular 报价的 Ext 留白。未修改正式名单或创建券商连接。
- 未跑全量/Python 测试；未重新查询真实 Longbridge 候选或验证无效 ticker 返回。候选配色等纯样式留待肉眼验收。

## 2026-09-24：统一内联搜索与新增

- TypeScript check/build、git diff --check 通过；仅运行候选查询/HTTP 与列表修改规则两个相关离线测试，2 项通过（2.60 秒），未跑全量测试。
- 查询成功返回 ticker/name，不写文件、不扩展白名单、不创建下载任务；无效查询返回错误且文件不变。原移动测试覆盖主动项日期、被动项不变、跨组和同步落盘。
- 用户现有真实服务页面：/ 后输入、搜索中再次 / 清空、回车选中 PAYS 并恢复完整列表、Wait + 使用同一输入框、Esc 退出均通过。未修改正式名单，未新建券商连接。
- 现有隔离模拟器临时名单：Shift+下使 PAYS 与 NVDA 换序，选中仍为 PAYS；AMD 停输后候选出现在列表，回车后位于 Focus 首位、选中 AMD 并清空搜索；Wait + 输入 TSLA 后直接回车，添加到 Wait 并选中。临时服务已停止。
- 本轮未对真实 Longbridge 重新验收新的 lookup 动作；其复用既有 static_info 验证。当前已运行 Python 服务需重启一次加载新动作。样式数值未测试，按用户要求留待肉眼验收。

## 2026-09-24：前端样式与搜索快捷键微调

- 仅前端改动：合并重复 CSS，统一字号、圆形图标按钮、三栏标题分割线；调整选中行、指标文字、时段胶囊位置和新增框。
- TypeScript check/build、git diff --check 通过。未运行 Python/全量测试，纯样式数值按用户要求不做自动化测试，交由用户肉眼验收。
- 在用户现有 `127.0.0.1:8765` 服务检查：按 / 后直接输入 PAYS 可过滤列表；新增框为空；新增框内 / 不抢焦点。未提交名单修改、未另建券商连接、未重启现有服务。
- 当前为 regular 时段，扩展时段胶囊未做现场验证；本轮只调整其 DOM 位置和高度，不改变时段判定。

## 2026-09-24：List Module V0

环境：macOS、Python 3.13、Longbridge SDK 5.0.0、watchdog 6.0.0。此段仅为当次验证事实，当前规格见 [list-design.md](list-design.md)。

- 最终离线回归：83 项通过（4.57 秒）；TypeScript check/build 与 git diff --check 通过。HTTP/WS 仅绑定本机，文件事件使用临时目录。
- 新增覆盖：同步落盘、主动/被动 status_at、重复添加不变、hidden/carried/其他字段保留、验证失败不写入、写入失败可重试、排队请求重新检查白名单、动态成员增删、空名单、原生文件修改/rename/新日期切换、Origin 校验及列表独立 WS 消息。
- 浏览器（隔离模拟器）：新增原 hidden 中的 ticker 到首位、同组指针拖动排序、跨组拖动、拖入折叠 Section、展开顺序、删除选中 ticker 后双图自动切换均通过；最终构建再次验证排序成功，未观察到 JavaScript 错误。模拟操作只修改临时 workspace 副本。
- 本轮真实 Longbridge：北京时间 2026-09-24 01:28:55 开始，65.04 秒，范围严格限定最新正式 Focus/Wait 中 WGS.US、NOWL.US、PAYS.US。单一 context、临时 workspace 和 SQLite；未修改正式 Scan 名单（前后 SHA-256 一致），测试连接已关闭。
- 实际 static_info 返回 PAYS/Paysign，空名单后添加 WGS 也验证成功。初始两股五周期就绪；PAYS 新增后五周期和 Quote 就绪。跨组、排序保持既有 SyncState/订阅，被动 ticker 日期不变，重复添加文件不变。删除 NOWL 后实际 unsubscribe，并撤下下载任务。
- 原生外部写入将名单改为 PAYS/NOWL，自动订阅/退订；更大日期的空 workspace 自动切换并退订全部，WS 继续发送空名单。重新添加 WGS 后恢复五周期 full，重连收到完整图表快照。
- 该轮记录 23 次 recent-1000 历史调用、2 次 static_info、4 次 subscribe、4 次 unsubscribe（含退出清理），收到 14 次 Quote 推送；结束时无耗尽错误，WGS stage=full，4 项正常收盘任务处于等待节点。未将等待正常更新表述为数据缺失。
- 首次尝试已验证增删/移动/外部更新，但验收脚本比较 /var 与 /private/var 别名导致超时；修正测试路径后以上完整重跑通过。首次记录不作为完整验收依据。
- 完整通过证据：`/private/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/list-v0-live-8_z3b6a3/report.json`。
- 未覆盖：全名单长时间运行、物理断网/休眠、移动触屏。错误路径使用离线测试；未额外查询真实无效 ticker，未操作生产名单。

## 2026-10-06 Alert 外观与自由十字线

环境：同日本机 macOS，Chrome 与正式 Safari Charts 窗口；Lightweight Charts 5.2.0、TypeScript 5.9.3。仅修改前端交互/显示，Alert Engine、行情、名单与通知契约保持原有实现。

- `npm run build --prefix ui` 通过，22 项 UI 用例通过。既有双图/成交量用例补充验证鼠标价格双向传递、成交量 pane 使用对应 series、programmatic 更新不回传覆盖鼠标价格；Vol 的悬停保持、刷新与清空继续通过。
- 使用 Scan Mock 副本、临时 SQLite 与既有 FakeBroker，localhost:8767 最长300秒。PAYS 验证细线段虚线、箭头紧贴价格轴边缘、无 Alert 价格轴标签；悬停价格胶囊包含两位小数与线性垃圾桶，拖动11.40→11.74重新激活，垃圾桶立即删除。Monitor 验证 Command+Option 创建66.45、双图共用横线、悬停胶囊与 Backspace 删除。未修改正式 Alert/名单，也未投递系统通知；临时服务、目录与浏览器页已清理。
- Monitor 实际绘制确认 Daily→Intraday 两侧十字线显示67.33，独立于对应 candle close；超出 peer 价格范围时不吸附到可见 candle。所有图使用内置1px LargeDashed及匹配的Alert primitive线段；两张图的Vol显示正确。
- 正式 Safari Charts 窗口已刷新加载构建，恢复刷新前 BAND 选择，确认 Daily/Intraday 均显示 Vol。没有重启或扩大真实行情订阅。
- 需求分别同步 alert.md（悬停/删除）、chart-ui.md（共用虚线/十字线/Vol）、ui.md（图形），职责与入口同步 development.md、behavior.md。相对链接/锚点及git diff --check通过；vendor未修改。
- 本轮未重新覆盖真实 Regular 触发、macOS 通知、全部六周期/价格轴缩放/pane resize，以及 macOS 27；这些不作为本轮浏览器验收结论。

## 2026-10-06 Alert 定位与横纵独立联动

环境：本机 macOS、Chrome 离线验证页和正式 Safari Charts；Lightweight Charts 5.2.0、TypeScript 5.9.3。本轮只修改 UI 与相应文档。

- `npm run build --prefix ui` 通过，23 项 UI 用例通过。新增定向用例覆盖无对应日期时水平线保留与复用、重新匹配日期时切回原生十字线、价格超出范围时仍传递时间、成交量 pane、离开与清空后的移除；程序更新不回传覆盖鼠标值的既有用例继续通过。
- 浏览器使用 Scan Mock 副本、临时 SQLite 与现有 FakeBroker，localhost:8767 限时300秒，不读取凭证或投递系统通知。Scan 验证胶囊位于绘图区约2/3处、无重复上下箭头、右箭头左侧竖边对齐原生价格标签左缘并进入价格轴。
- Monitor 实际验证：Daily 悬停旧日期（Intraday 无该日数据），两图仍显示67.33水平线，Intraday不显示虚构时间线；同一Alert在两图可见。Intraday拖动66.46→66.68，Daily同步；Daily继续拖动66.68→67.12，Intraday同步，悬停胶囊显示相同已保存价格。另用同样临时环境限时60秒保存完整截图 `/tmp/alert-ui-final.png`，显示旧日期的Daily胶囊与Intraday独立水平线。
- 正式 Charts 窗口已刷新加载构建并恢复刷新前BTGO选择；未重启真实服务或修改正式Alert。临时页已关闭，验证服务按时结束并清除临时库。
- 需求和职责同步 alert.md、chart-ui.md、ui.md、development.md、behavior.md；相对链接/锚点及 `git diff --check` 通过。未修改 vendor。未重新覆盖真实Regular触发、macOS通知、全部周期/价格轴缩放/pane resize或macOS27；离线UI证据不替代这些验收。

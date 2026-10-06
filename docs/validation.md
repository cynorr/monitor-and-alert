# 验证记录

本文件只记录各次验证事实，不定义 UI 要求；当前规范统一见 [ui.md](ui.md)。

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
- 1280×720默认浏览器核验TEAM持仓选择复用Daily/Intraday，PAYS Days=3、PBF Days=2、当日TEAM/PURR Days=0，tooltip明确entry price；未改本轮之外的图表参数或布局。保存本轮真实界面截图`runtime/holdings-data-live.png`，浏览器无error/warn。
- 当前真实账户没有当日全部清仓批次。另用已有EFOR 2026-10-01买入/10-02卖出实际成交只读构建历史样本：零持仓、最终已实现P/L=-987.35、清仓不计入Total。临时离线展示页导入正式Holdings组件/样式，明确标注历史样本；Sold降序时EFOR的100%仍置底，主行/Buy/Sold均为灰色，500股、买入价36.35与卖出价34.37、两笔日期均完整显示。保存`runtime/holdings-closed-history-ui.png`，验证结束删除临时页面和样本文件。此项是实际历史输入与当前组件验证，不是本轮实时stop-out事件。

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

## 2026-10-03：Massive 合并、统一路径和持续后台接收

环境：macOS、现有Python3.13虚拟环境及Node/TypeScript。只验证本次数据模块、代理、状态和生命周期改动；没有运行全量回归或连接真实Massive、Longbridge、SnapTrade。以下历史记录的互斥模式/NoAdjust约定已由本轮用户要求替代。

- 数据/代理/生成定向离线检查共30项通过：`tests/test_massive_pipeline.py`、`tests/test_network.py`、`tests/test_scan_generation.py`。覆盖拆股生效边界、HALF_UP、原始文件保留、交易日目标、split窗口替换/旧历史保留/分页失败不覆盖、构建失败保留旧库、OHLC原值日志、Ready重启跳过凭证与网络并删除extended、阶段四次失败、输入读取失败、状态落盘失败、中断/重复任务、force更新、人工名单保留、共享代理/直连及HTTP错误脱敏。
- Scan/Holdings只选择相关12项检查并通过，18项未运行；覆盖正式Scan启动后台任务、切页保留连接/缓存/账户任务、生成不锁定展示模式和历史日期、缺少首份截面时的HTTP/WS状态、当前名单变更、mock/有界隔离、手动Massive入口与runtime锁，以及SnapTrade签名/代理/错误/下轮重试。HTTP/WS使用临时本机端口，行情与账户均为fake。
- `npm run build --prefix ui`通过；只运行新增Scan状态显示测试1项，核对ET精确到秒、保留最后Ready日、准备进度和状态写入失败提示。`git diff --check`通过。未跑完整Node测试或浏览器手势验收。
- 558份本地原始文件离线重建产生6,384,627根拆股复权日K；最新完成日2026-10-01有12,594只证券，volume均为SQLite integer。重建76.947秒、特征生成2.634秒；855只eligible、96只candidate。18根代表性旧库记录的OHLC、整数volume及turnover对照通过，未做全库逐根等价检查。
- 原始558份文件SHA-256未变，16份已有人工workspace逐文件SHA-256未变；旧runtime/daily.sqlite3未改写。split复制与原参考文件逐字节一致；全部原始参考数据和旧库保留。仅runtime/massive/splits.json被Git规则放行，原始Daily/SQLite/状态/凭证及三个参考目录均忽略；三个原已跟踪参考脚本已从索引移除，磁盘文件保留。
- 入库及特征成功后校验Ready重启不读取凭证或联网；再以真实时钟检查当前目标与完成日均为2026-10-01。正式手动脚本在移除环境凭证且指定不存在凭证文件时返回Ready并成功退出，未构造Longbridge或SnapTrade。

报告：`runtime/massive_merge_report.json`。统一状态：`runtime/pipeline-status.json`，含daily/splits/bars/features和输入版本，不含extended。未覆盖：真实供应商获取/分页/代理联通、Longbridge新库的实际初始化、账户实际刷新、物理断电/休眠与长期运行。Massive保留供应商Daily时段口径，不宣称regular-only；Longbridge继续原regular/NoAdjust契约。

## 2026-10-02：Holdings 零出售隐藏、成交价仅明细与盘中 Ext

环境：macOS、现有Node/TypeScript及真实8765服务；仅前端与文档变更，未改账户/行情获取。真实只读验收预先限定当前11个Holdings（LITE、IOVA、EFOR、PAYS、TXG、ABCL、VSTM、MU、PBF、MRNA、CDNA）与最多2分钟，现场约09:56 ET处于regular。无新增ticker、账户/workspace写入、模式切换或服务重启；临时页面关闭、viewport恢复。

- `npm run build --prefix ui`、`git diff --check`与仅定向的`node --test ui/tests/holdings.test.mjs`通过（5项）。原始数值排序保留精度；删除Trade Price排序列后测试范围改为八个数值列。未运行全局Node/Python测试。
- 临时SIM网页只导入生产HoldingsList/layout，不加载main、不建WS、不访问券商。覆盖Sold=0的空值/隐藏箭头、实际非零0.1%显示<1%并保留展开、P/L %和Chg%一位小数（含Total/卖出明细），Ext保持两位；Buy/Sold成交价在Chg%位置。
- SIM点击Ext排序后切regular：表头/主行/明细/Total第八列均隐藏，排序恢复默认；成交价仍可见。列表由489px收回至436px、双图等宽；切回扩展时段恢复489px与Ext。各状态scrollWidth=clientWidth。临时fixture已删除，未保留测试专用产品界面或新增服务。
- 真实盘中有8个Sold为0的主行，均无数值及可见三角；IOVA/TXG/MRNA保留出售比例与展开箭头。主表九个结构单元、八个可见列，无Trade Price列；所有主行P/L %/Chg%均一位小数，Ext全列隐藏。
- IOVA明细为Buy 2026-09-02/1,000股/8.61，Sold 2026-09-04/500股/8.73、2026-09-24/200股/10.36；卖出P/L %为+1.4%/+20.3%，日期/数量位置保持，Daily/Intraday选择联动正常。当前视口列表413px、展开后434px，双图等宽，scrollWidth=clientWidth。控制台无error/warn。截图 `runtime/holdings-compact-regular-live.png`。

未覆盖：真实开盘/收盘边界长期观察、真实扩展时段、无任何当日regular Quote时的开盘初始等待、全局Scan/图表手势、后台会计/调度及移动触屏。Ext显隐依赖既有current_regular_session（已到当日regular Quote且交易日历is_open），不会新增客户端时钟/交易日历。历史记录不作为本轮live证据。

## 2026-10-02：Scan 分阶段提速与最新完成日刷新

环境：macOS、现有Python3.13/pandas/numpy虚拟环境、TypeScript5.9.3。使用真实runtime/daily.sqlite3，完成日metadata.completed_date=2026-10-01。只验证本次Scan计算/刷新改动；没有全量回归、前端交互测试、全链路测试或券商/账户请求。

- 针对性离线测试15项通过、5项无关测试未运行（1.96秒）；覆盖ADR/ADV与均线/ATR/特征既有公式、指定日截断、短历史、候选低于5美元、仅候选计算原子特征、无候选、小数volume拒绝、OHLC原值与阶段重叠仅记录一次、新完成日生成/选择、历史选择后刷新最新、Focus/Wait继承、同日保留人工文件、显式旧日重算、缺少完成日失败保留状态并释放busy。没有HTTP/WS模拟全链路。npm run build --prefix ui通过；git diff --check通过。
- 真实12594只证券：855只ADR≥5%/ADV≥$5M eligible，三组RFL各前50并集96只candidate；恰好96行含EMA/ATR/原子字段。与先读全市场126根的对照流程比较：全市场ADR/ADV、eligible/candidate标记、eligible三组RFL/排名及96个候选的完整特征行一致。源SQLite只读、mtime未变。
- 无profiler的完整计算：筛选2.586秒、候选特征/序列化0.737秒，总3.323秒（包含日历创建的外部计时3.425秒）。正式CLI再次生成时筛选2.619秒、特征0.748秒，总3.367秒。日志同时输出证券/候选数和两阶段耗时，没有新增性能框架。
- 同一1000只真实样本、各线程独立只读SQLite连接：单线程0.460秒，四线程1.123秒；四线程更慢，未引入线程池。正式服务继续通过既有asyncio.to_thread在后台运行生成，主要收益来自20→126→1000根分阶段读取和只计算96只候选的原子特征。
- 10/1未显示根因：上游已完成，但旧按钮发送当前9/30日期，日期下拉框又仅列已生成快照。改为无date生成请求，消费上游完成日标记；成功明确选择生成日期。CLI不传--date采用同一规则，不用MAX(ts)推断完成。
- 当前8765原处Scan、broker_active=false；停止旧Python进程后用正式CLI生成并发布2026-10-01，再恢复同端口Scan服务。只读GET确认日期10/1、可编辑、无券商连接；Discover84/Focus35/Wait20/Hidden1。新日Focus/Wait顺序与statuses逐项等于9/30，未覆盖旧日期人工文件。页面需重载一次加载新Refresh按钮逻辑。

报告：runtime/scan_performance_report.json。未覆盖：Monitor/SnapTrade/Longbridge实际请求、前端手势/Tag操作、长期运行、冷文件缓存耗时。上游metadata仍标注split_adjusted/half_up/massive_daily；本轮按用户提供的真实输入验证计算与速度，不修改源数据、不宣称已完成NoAdjust/原始成交量/regular来源验收。

## 2026-10-02：Holdings 单行与 Buy/Sold 明细

环境：macOS、Node 25.3.0、TypeScript 5.9.3、现有真实8765服务（Monitor）；只改前端与文档。live预先限定当前11个Holdings（LITE、IOVA、EFOR、PAYS、TXG、ABCL、VSTM、MU、PBF、MRNA、CDNA）与最多3分钟，页面交互验收实际44秒。没有新增ticker、账户/workspace写入、模式切换或服务重启；结束后关闭临时页并恢复viewport。

- `npm run build --prefix ui` 与 `git diff --check` 通过；仅运行 `node --test ui/tests/holdings.test.mjs`，5项通过，确认原始数值排序精度仍保留。没有全局Node/Python测试。
- 真实DOM确认所有主行/明细无small副标题，单行nowrap；主行26px。P/L、P/L Day和两项Total均无小数，P/L %与成交价保留原精度。Save PNG按钮、监听、SVG/canvas生成与下载代码及对应样式均移除。
- 展开尚未卖出的LITE显示三笔Buy：2026-06-01的5股/841.75、10股/875.00及2026-06-15的10股/951.50，未合并丢失记录。IOVA先显示Buy（2026-09-02、1,000股、8.61），再显示Sold（2026-09-04、500股、8.73及2026-09-24、200股、10.36）；日期均在Net Liq对应列，股数均在Sold对应列且无百分比，无额外标题或第二行。卖出P/L为整数+60、+349。
- P/L降序时Buy/Sold明细跟随所属主行，IOVA选择及Daily/Intraday联动保持；再次点击恢复原始主行顺序。前端控制台无error/warn。
- 1440×1000 CSS视口主列表自然宽度557px、双图各419.5px；展开后列表自动增长到577px、双图各409.5px。1920×1080时列表保持577px、双图各649.5px；两种视口下holdings-scroll的scrollWidth等于clientWidth，完整显示十列。沿用现有自动测量逻辑，无新增固定列宽。截图 `runtime/holdings-single-line-live.png`。

未覆盖：全局Scan/图表手势、后台会计/轮询、真实长时间刷新/断网、碎股现场样本、移动触屏；未新增或运行这些范围的测试。历史记录不作为本轮live证据。

## 2026-10-02：Holdings 降序切换与紧凑宽度

环境：macOS、Node 25.3.0、TypeScript 5.9.3、现有真实8765服务；只改前端与文档，无后端或券商获取改动。live验收范围为当前11个Holdings，预先限定最多3分钟，实际96秒；服务原处Scan，临时切到Monitor，结束后恢复Scan。没有账户或workspace写入，没有新增ticker。

- 仅运行 `node --test ui/tests/holdings.test.mjs`：5项通过。覆盖全部九个数值列降序与负数、Symbol Z–A、切列与恢复默认数组、缺失/非法值置后、稳定同值、同ticker不同批次及附属卖出数据、Net Liq按未取整数值排序；原数据不变。没有全局Node/Python测试。
- `npm run build --prefix ui` 与 `git diff --check` 通过。Net Liq主行/Total显示整数，股数副标题无shares；实际市值与后端Decimal精度不变。
- 真实浏览器点击Net Liq后金额降序；改点Days仅Days为descending，天数123、93、30、24、18、17、15、3、2、1、1；再次点击Days所有列恢复none，行顺序与点击前一致。
- 1440×1000与1920×1080 CSS视口均完整显示十列，holdings-scroll的scrollWidth等于clientWidth。列表实测约621–633px，视口加宽只增加两个图表且双图宽度相等。键盘调整分隔条后列表645px，重载恢复按当前内容测量的紧凑宽度621px及等宽双图，未恢复旧比例。
- IOVA选中与Daily保持；展开两条卖出后再排序，卖出紧随所属主行，实际卖价/日期保留。前端控制台无error/warn。截图 `runtime/holdings-sort-compact-live.png`。排序标记随后改为列名下方3px三角，补充只读验收预先限定60秒、页面操作约5秒；同样完整显示所有列、双图等宽，保存最终截图并通过GET /health确认回到Scan。临时页面关闭并恢复viewport；没有重启正式服务。

未覆盖：全局Scan/图表手势、PNG导出、真实长时间行情更新/断网、移动触屏；极端长数字或新持仓宽度增长路径未做真实验收。仅验证本轮排序、宽度与Net Liq显示，历史数据记录不作为本轮live证据。

## 2026-10-02：Holdings 十列与实际卖价

环境：macOS、Python 3.13.1、现有Longbridge SDK 5.0.0、Node 25.3.0、TypeScript 5.9.3。用户明确授权使用正在运行的真实服务并重启；沿用当前Focus/Wait与已接受Holdings范围，未增加ticker。真实只读验收窗口约07:28–07:37 ET，服务在验收结束后按用户要求继续运行。

- 仅定向执行 `tests/test_holdings_integration.py -k 'daily_metrics or corrected_daily_close or latest_session_reprices or missing_or_invalid_longbridge'`：8项通过（0.98秒），8项未选中。覆盖盘前/盘中/盘后/夜盘基准、旧扩展报价不覆盖新regular、剩余股数、Decimal精度、已实现盈亏/原快照保持、缺基准与非法基准、禁止部分总额、观察名单共用基准及既有缺价回退。没有运行全局Python或Node测试。
- `npm run build --prefix ui` 与 `git diff --check` 通过。实际卖价直接使用原成交金额/数量；未修改成交流水、账户余额或买卖关联。
- 从用户现有8765服务读取到11个持仓：LITE、IOVA、EFOR、PAYS、TXG、ABCL、VSTM、MU、PBF、MRNA、CDNA。重启同一服务后，11个均采用Longbridge最新Pre报价；逐批次核对P/L Day与最新价/基准/剩余股数一致，总额等于所有批次之和。无需新增券商接口调用；HTTP读取不触发账户刷新。
- 真实浏览器核对1440×1000及1920×1080 CSS视口：十列完整显示，holdings-scroll的scrollWidth与clientWidth相等；所有ticker的左坐标相同，包括选中行。IOVA卖出明细显示8.73、10.36及对应日期，买入行保留8.61；Sold副标题不再有shares，Days列缩短、日期位于Trade Price下。点击IOVA联动既有Daily/Intraday，整体折叠/展开正常。控制台无error/warn。截图为 `runtime/holdings-columns-live.png`。

未覆盖：本轮真实环境处于盘前，真实盘中/盘后/夜盘切换未观察（相应计算由定向离线测试覆盖）；未测试Scan、全局图表交互、PNG下载、长期运行、断网/休眠。低于1424px的视口保留面板最小宽度，工作区允许整体横向溢出；不声称小屏能同时容纳两个图表与十列表格。

## 2026-10-02：Holdings 独立持仓合并

环境：macOS、Python 3.13.1、现有 Longbridge SDK 5.0.0（未连接）、Node 25.3.0、TypeScript 5.9.3。账户/行情测试使用离线替身，HTTP/WS只绑定本机临时端口；预览使用临时SQLite、合成持仓和SIM标记。没有读取真实账户或重启既有正式服务。

- 最终Python完整离线回归：134项、11个subtests通过（7.22秒）。新增/迁入24项持仓测试覆盖原买卖批次、合并/明确卖出归属、数量错误、Decimal精度，最新regular/extended/overnight择价、缺价/非法价回退、已实现盈亏和历史成交保持、负cash及账户总值、市值/总P/L百分比、空仓位。
- 拉取/调度覆盖：指定account_id直接获取、启动立即请求、失败保持最后成功快照并等下一周期、成功才提交缓存、历史缓存复用、滚动10次/分钟预算、HTTP429脱敏、坏缓存/其他账户缓存不阻止启动。HTTP/WS读取不额外请求SnapTrade；有界/Mock会话不构造真实持仓客户端。
- 成员/图表覆盖：独立持仓与观察名单重复时共用SyncState；只在两个来源都移除时撤下行情，board仍只包含workspace成员；持仓专有ticker有Daily/4h历史，WS选择复用双图；失败不退出Monitor；Scan停止持仓task/session，返回Monitor立即请求，workspace文件保持不变。
- TypeScript check/build、现有Node Filters/Tags6项及git diff --check通过。原持仓HTML迁入独立TypeScript模块，保留七列及买入/卖出字段；更新值不重建不变行。浏览器核对并修正金额与股数副标题共存的渲染，验证Enter选中、持仓与观察名单选中独立、仅持仓ticker双图、4h、卖出明细及整体折叠。从Wait删除重复ticker后持仓及图表仍保留；该操作只写临时workspace。
- 最新夜盘14.5的离线样例：持仓估值1377.50，SnapTrade现金-200，Account Value1177.50，总P/L552.50；Intraday显示同一夜盘价和OVERNIGHT，市值悬停标识来源/时段/时间。前端控制台未观察到error/warn。预览截图：`runtime/holdings-preview.jpg`。快速重载暴露aiohttp压缩后台发送的关闭传输错误，已对本机WS关闭可选压缩，并再次通过完整HTTP/WS回归。
- 本机已保存SnapTrade凭证并迁移原sequences.txt/merge_buys.txt，文件权限600；凭证、规则、账户缓存及原参考项目均git忽略。单进程/8765入口，未新增服务或端口；临时预览停止后无后台验收服务。

未覆盖：真实凭证/账户有效性、当前持仓及规则能否对平、持仓证券Longbridge支持/行情权限、真实30秒长期运行、断网/休眠、移动触屏。Save PNG保留原表格生成/下载流程；内置浏览器未提供下载完成事件，本轮不宣称PNG文件交付已验证。折叠状态持久化依赖浏览器允许localStorage；本轮只确认当前页面折叠行为。离线与历史记录均不作为本轮live证据。

## 2026-10-02：Holdings 合并前可行性核对

环境：macOS、现有 Python 3.13 虚拟环境。只检查根目录 `schwab-review` 的源码、字段、买卖关联配置及主项目接入点；本轮尚未合并功能，未读取或保存真实凭证，未调用 SnapTrade 或 Longbridge。

- 原 Holdings 的标准库离线测试：15 项通过，覆盖买入合并、部分卖出、历史订单覆盖活动、明确买卖关联、歧义/超卖/数量不一致、ETF、Decimal 精度、历史缓存复用和单快照覆盖。
- 主项目离线回归首次运行：106 项及 11 个 subtests 通过；另 3 项 HTTP/WS 测试被沙箱禁止绑定本机临时端口，1 项 macOS FSEvents 测试无法启动事件流。这 4 项在沙箱外单独复核全部通过（3.71 秒）；没有修改测试或运行代码。
- 核对 SnapTrade 官方当前认证、签名、限流和数据新鲜度文档：Personal key 省略 userId/userSecret；账户接口共用默认 10 请求/滚动分钟；原四接口每 30 秒一轮常态约 8 请求/分钟。初始化/流水变化仍需计入活动请求；轮询周期不代表券商数据每 30 秒更新。
- 已定位合并边界：数据拉取与 HTTP 服务需拆开；Holdings 需独立列表及选择状态；现有行情白名单仅 Focus/Wait，持仓接入需扩展动态范围并去重；估值改用 Longbridge 时需明确账户总值、扩展时段、无报价和刷新错误的处理。

未覆盖：真实凭证有效性、指定账户当前持仓/买卖关联、持仓 ticker 的 Longbridge 支持及行情权限、30 秒长期轮询、合并后的估值/图表/布局/错误隔离。本轮没有前端改动，未运行 TypeScript 构建或浏览器验收。

## 2026-10-02：真实上游库核心测试与复权口径确认

环境：macOS、现有 Python3.13 虚拟环境、pandas/numpy。只读用户新交付的 `runtime/bars.sqlite3`；6372033 根日 K、16365 个历史 symbol，metadata 明确完成日为 2026-09-30。未启动后端或浏览器，未调用券商，未跑前端测试、全量回归或全链路。

- 九列、主键、时间索引符合结构契约；完成日12613行，symbol 均含 .US、OHLC 正数、volume 实际存储为非负 integer。全市场生成按生产 build_day 读取每只截至完成日最多1000根，逐根验证价格、成交量、turnover、实际交易日/ET时间戳与闭合边界。源库大小/修改时间未变。
- 六个真实样本：NVDA、TSLA、AAPL、AAAA、ACCV、ACIG，覆盖557/305根及仅1根日 K。ADR/ADV/RFL与独立公式核算一致；EMA及Wilder ATR与手工递推一致；Scan 日图的均线/ADR/ADV一致，无active。35个原子字段逐一与原 Scan 算子比较，值及缺失语义一致。
- 完整2026-09-30截面：12613只，622只eligible，90只candidate；三个RFL排名（含并列symbol顺序）和前三组各50名的候选并集与独立排序一致。生成及截面核对耗时94.45秒；JSON可序列化。结果写在临时目录，没有发布到正式days，也没有覆盖人工名单。
- 本轮实际数据口径尚未通过正式验收：metadata 是 split_adjusted、volume half_up，session 是 massive_daily，不能据此确认 regular-only。用户再次确认最终维持NoAdjust与原始成交量，所以上游需重新提供原始OHLCV到runtime/daily.sqlite3；本轮计算通过不等于两来源口径一致。
- 核实broker.py直接请求NoAdjust，没有后续adjust table处理。补充README与上游交接文件：默认serve进入Monitor；直接Scan用serve --mode scan；首次须scan --date D生成截面。上游日库与Monitor运行库物理分离。

报告：`runtime/scan_core_report.json`。未覆盖：真正NoAdjust原始成交量交付、regular时段来源确认、真实Longbridge请求及与上游逐根比较；此次不执行这些网络或全链路验收。

## 2026-10-02：Scan 合并与互斥模式

环境：macOS，Python3.13，Longbridge SDK5.0.0（未连接），pandas3.0.6、numpy2.5.3，Node25.3.0、TypeScript5.9.3。本轮全部运行使用合成SQLite、临时目录或离线券商替身。

- Python完整离线回归：110项、11个subtests通过；包含既有行情/日历/重试/恢复/合成回归和迁入原子算子、指标种子/空值、指定日截断、统一ADR/ADV/EMA、小数volume拒绝、形成日拒绝、OHLC原值/日志、Hidden6/7/8天、carried、批量写入/同日重算、HTTP/WS/Origin、历史只读、切换失败保留Monitor、偏好保存失败保留内存、互斥模式/白名单收缩。
- TypeScript check/build通过；Node Filters/Tags6项通过：38字段唯一、数值闭区间/严格上界、AND/分类OR、Any与缺失、非有限值、滑杆异常范围和小数阈值保留、草稿/保存隔离、Tag唯一名和十个上限。git diff --check通过。
- 浏览器离线替身：Scan日 K与ADR/ADV显示；新Tag编辑、阈值即时过滤、排序保留草稿、Save、重载恢复；两只候选批量移入Focus后，Monitor立即显示同一份成员，隐藏Discover/Hidden，切回Scan恢复上游日图；历史日期禁用名单编辑。该Monitor为FakeBroker，不是Longbridge live。
- 正式CLI的Scan Mock另验：用不存在的凭证路径启动并成功退出，明确不读取凭证；Hide → Hidden → Return Discover置顶、同日Refresh保留人工顺序，页面控制台无error/warn。截图：`runtime/scan-mock/preview.png`。所有验收服务已停止。
- 数据迁移：从原正式`~/qull-scan-workspace`复制15份workspace与7个Tag，保留字节内容和源文件；最新2026-09-30，Focus34/Wait20/Hidden5。universe离线解析54个Focus/Wait。未生成正式NoAdjust截面、未改原来源或Monitor bars的市场行。
- 上游交接文件：upstream-daily-data.md。复制Scan数据库的列/行数/小数volume已只读核实；没有将旧复权未知数据自动转换为正式NoAdjust输入。

未覆盖：真实上游NoAdjust全市场发布、类别股symbol映射、小数volume根因、两个供应商的逐根等价、全市场生成耗时、Longbridge连接释放的真实账户验收、物理断网/休眠/长时间运行和移动触屏。现有Monitor实时算法使用离线回归覆盖；历史live记录不作为本轮证据。

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

## 2026-09-23：Intraday active volume 修复（当日美东上午）

- 离线回归：68 项通过，2.26 秒。覆盖全天累计差异不进入 active、大周期无重叠覆盖、缺少 5m、缓存复用及修订失效、六个分钟周期、跨日/跳桶/恢复/计数回退。前端代码未修改。
- 本轮 live 仅观察现有服务的 MRNA.US 最新 5m：美东 2026-09-23 10:55–11:00；未新建券商连接、未请求旧交易日测试集。
- 22 次只读观测确认：桶内 `Quote累计量 - active量` 基准不变，active 量始终非负；首个观测 113,633，最后一个收盘前观测 214,853；官方 closed 返回后替换为 161,673，下一桶观测为 7,629，没有把全天累计差异堆到新柱。
- active 是 Quote 采样估算，不承诺等于官方分钟量；本轮预估与官方仍有差异。闭合后使用官方量，不能通过任意缩放或修正价格/成交量伪造一致。
- 证据：`/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/mrna-volume-final-ugv35ac3/report.json`。本轮只验收成交量修复，不宣称全名单所有周期无错误或全天稳定运行。

## 2026-09-23：架构精简

当前实现规则见 [behavior.md](behavior.md)，开发入口见 [development.md](development.md)。下面记录本轮执行证据，不代表持续在线状态。

环境：macOS、Python 3.13、Longbridge SDK 5.0.0。测试使用当前 workspace 白名单及临时 SQLite；未修改生产数据库，临时服务均已停止。

- 离线：58 项通过（2.23 秒）；TypeScript check/build 通过。最后将模拟器 HTTP 启动改为复用正式入口后，相关 5 项再通过（1.12 秒）。
- 覆盖：OHLC 原值与重复追加日志、最新目标缺失/请求失败的重试轮次、历史断档接受、重连期间在途任务、8/2 限流和 3+2 并发、官方替换合成、2h/4h、DST/提前收盘、Quote 恢复、HTTP/WS 与模拟器跨周期。
- 浏览器：保留矛盾 OHLC 后图表可绘制，无 JavaScript 错误；2h/4h 切换正常。黄色 Ready 跨多次观察持续显示；官方 15m 延迟时已有 5m 合成显示。蓝色 Ready 的 3 秒隐藏已在较短延迟的前一次模拟验收中验证。
- 最终全名单 live：美东 2026-09-22 13:39:50 起运行 150 秒，45/45 ticker 的五个官方周期 full，pending=0、errors={}。收到 1,799 次 Quote 推送、737 条图表消息；WS 重连收到完整快照。
- 同轮请求：225 次 count=1000、44 次正常 count=2；跨过 13:40 收盘节点。没有额外补缺请求。1000 请求允许返回更短历史，最短存储窗口 158 根。OHLC JSONL 追加 466 条，均未造成错误状态或重试。
- 真实 Quote 重订阅：PAYS/HTFL/PLTU，首次各五周期共 15 次 count=1000；主动取消再订阅后，全部 15 项进入统一恢复，再请求 15 次 count=1000，恢复 full、无错误，随后收到新推送。此测试不等同于物理断网或操作系统休眠。

最终全名单证据：`/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/longbridge-check-4v431g4y/report.json`；同目录 `invalid_ohlc.jsonl` 可与 TradingView 手工比较。

重订阅证据：`/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/longbridge-recovery-80yla527/report.json`。

前一轮 live 曾检查返回窗口内连续性，导致 REPL 的三个分钟周期与 USDE Daily 因旧空档重试；这些周期的最新目标均存在。最终已删除历史连续性检查并重跑以上全名单验收。前一轮产物 `longbridge-check-b8zmpv5b` 仅供差异追溯，不代表最终行为。

本轮未重新完整操作所有既有布局/日联动手势；chart.ts 与 layout.ts 未改动，历史验收范围见下表。长时间运行、物理断网和系统休眠仍需另行观察。

## 历史证据摘要

以下规则属于旧版本，不能作为当前需求：严格 OHLC 拒绝、定点修复、history offset、readiness v2、历史连续性补齐均已删除。

| 日期 | 当时验证 | 范围与限制 |
| --- | --- | --- |
| 2026-09-20 | 52 项离线测试通过 | 旧 OHLC 拒绝/定点修复，不代表当前保留原值方案 |
| 2026-09-20 | 40 项离线测试、TypeScript 通过；45 ticker 完整模拟跨周期/交易日 | 浏览器验证三栏拖动、短历史 spacing、自由十字线、交易日联动；未连券商 |
| 2026-09-20 | 首版 34 项离线测试通过 | 初版双图/HTTP/WS；已被后续布局与状态语义取代 |
| 2026-09-18 19:31 UTC | 17 项测试、45 ticker 真实接口、3,060 次 Quote 推送 | 当时重订阅恢复及 5m closed 更新通过；258,795 根旧规则库审计；部分官方 OHLC 被拒绝，不能表述成全量 Ready |

旧实测产物曾保存于 runtime/full-universe-http.json、full-universe-report.json、recovery-smoke.json、invariant-audit.json；文件若仍存在，仅作历史数据，正式服务不消费这些报告。

移动触控、全天稳定运行和实际系统长时间休眠恢复仍未完整验收。模拟测试、短时 live 和历史记录分别标明，不相互替代。

## 2026-10-06 Alert 实现与 macOS 通知

环境：macOS 26.7 arm64，Python 3.13.1；PyObjC Cocoa/UserNotifications 12.2.2、py2app 0.28.10、setuptools 80.10.2；Lightweight Charts 5.2.0、TypeScript 5.9.3。原生应用固定 `dist/Market Monitor.app`，Bundle ID `local.cyno.MarketMonitor`，本地 ad-hoc designated requirement 固定 identifier；当前为 alias bundle，运行依赖原工程和 .venv。

- TypeScript 构建通过；22 个现有 UI 用例通过。Python 定向运行 Alert、Workspace、List rules、Scan、Holdings integration 与 Quote/DataService，100 个通过（含重连首快照后下一次穿越）；后续 UI 跳转修改后复验 Alert/Scan 44 个通过。最终补充 Focus 已保存但 Alert 写入失败的明确部分成功响应用例，并将 Alert Quote 回调置于图表处理之前，复验 Alert/Quote/DataService 27 个通过，其中 Alert 20 个。localhost 监听与原生 watcher 用例在沙箱外运行，数据仅写临时目录。
- 新增核心用例覆盖上/下到达与跳价、原始精度、同秒 push/旧 snapshot、相同 symbol 多条、扩展时段/闭市/新日/重启/休眠起点、旧事件与新 generation、到期和出范围、未知初始 Holdings、来源 Tag 清理和重新分类、同源 Origin 与独立 WS 快照。既有快照成交量用例继续通过；同秒快照保留 push 的价格，同时接受原有累计量更新。
- 真实服务：停止旧 CLI 后，以原生同进程应用恢复正式 runtime；/health 为 running/CONNECTED，Focus ∪ 已接受 Holdings 为 56 个 symbols，scope_known=true。只额外读取 GPRO 的现有 Quote，不扩大订阅；实际图表验证 Command+Option 创建、Daily/Intraday 共用黑线/右箭头、拖动保存（0.96 → 1.06，generation 1 → 2）与 Backspace 删除，已清除该测试 Alert。
- 原生首次启动暴露 Finder 的 C locale；launcher 设置 UTF-8 后 Holdings 可读取已接受缓存并刷新，未把原失败当空持仓。通知授权 authorized，alert/sound 均开启；系统设置确认 Desktop/Notification Center 开启，并将 Temporary 改为 Persistent。重启应用后权限保持；SIGTERM 进入与菜单 Quit 相同的 Cocoa terminate 路径，确认监听端口、进程和 runtime 锁释放后可重新启动。
- 独立 `--notification-check` 只发送两条 CHECK 原生通知，不读取凭证/数据库或连接行情。UserNotifications 返回 delivered=2，提交 error=null，最终 CHECK 验证结束后清理两条测试通知；up.wav/down.wav 均为 44.1kHz 单声道 PCM 的不同短音资源，最终构建直接复制实际文件进应用包。投递/配置记录不等于人工听辨已经完成。
- UI 卡片验收：使用现有 Scan Mock 的复制品及临时库，localhost:8767 最长300秒、结束删除临时目录。PAYS 两个 Triggered 事件显示上下穿 SVG（蓝/黑）、两位价格与 ET 日期/秒，灰线对齐、左下角 stack；卡片保持不超时。灰线拖动至11.70后为 Active generation=2，关闭旧上穿卡片没有删除新线；另一卡片跳转 Monitor 成功后处理，最终 unhandled=0，Active 新线仍保留。此验收没有读取凭证或投递系统通知。
- 当前额外 live 检查发生于纽约 Regular 之后，没有等待下一交易日或设置自动任务；没有伪造真实穿越。尚未实机覆盖：Regular live 穿越与实际听辨两种声音、系统通知 Open/Close 的完整人工操作、Mac 重启/真实睡眠，以及 macOS 27。对应逻辑由定向用例与正常系统 API 实现，以上未覆盖项不能视为已验收。
- 184 个 Markdown 相对链接/锚点与 git diff --check 核对，codesign 普通校验 valid on disk / satisfies Designated Requirement；未改 vendor、未加入 Atomic 算子、策略、下单、跨存储事务或回放框架。

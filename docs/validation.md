# 验证记录

## 2026-10-30：In 14 Days 财报排除

环境：本机macOS、Python3.13.1、TypeScript5.9.3；使用正式2026-10-29 Massive截面、当前Tag/人工名单及Nasdaq真实财报SQLite/原始响应。定向测试只写临时名单/财报库，不构造Mock行情或财报，不调用供应商接口；没有全量或全链路测试。

- 新增纯日期算子days_to_earnings及36字段目录中的Earnings条件；空日期返回None/JSON null，按当前ET自然日计算。日期原值继续使用独立财报库，无新增表/列、999替代值或历史截面写入。图表和名单共用next_earnings读取，未发布且不早于当前日期的最近日程才为下一次事件。
- AdditionalInfo在缓存成功加载、单日财报提交/内存更新成功后通知Workbench；Workbench原有循环检测ET日期变化，统一通过list_snapshot补入候选与当前名单成员特征并重分类。保留成员没有当日bar时只补symbol、非候选身份及日期特征，不编造行情。继承Hidden/人工保留与Focus淘汰仍用原规则，不重排候选、不重建bar特征，也不执行Refresh的人工清理。
- 5项定向用例通过，最终1.07秒：真实财报日的0/14/15天边界与空值、实际缓存加载后的优先级/多Tag重叠及缺失不排除、真实原始单日响应提交后自动分类/重新加载、原循环跨ET日从15天进入14天且不获取数据、当前保存Tag条件保真。原始snapshot内容、排名和源scan.json保持不变；机器Excluded仍不保存成员身份。日期边界使用受控时钟，不将其记录为真实跨日运行证据。
- npm run build --prefix ui、修改Python语法检查与git diff --check通过。同步维护现有前端用例中的字段数量与section顺序，但没有扩大前端测试；未做浏览器、全部行情周期、真实跨日长跑、交易或Alert验证。
- 正式服务按原Trade参数重启为PID48683，并经现有preferences保存接口新增In 14 Days（role=earnings，min=0、max=14）；原有七个Tag、选择偏好和模式保留。最高机器优先级为earnings → broken → extended → under50，使用现有label图形默认外观，不新增图标系统。实际GET核对8个Tag、36项条件、名单中的可空特征字段，workspace_error为空、Quote CONNECTED、Massive Ready；正式原始Scan截面逐字核对未变。没有发送交易请求或重置人工名单。
- 当前产品/数据/开发/UI文档及根、数据、Additional Info、UI的AGENTS同步；CLI继续只处理行情截面，财报分类由正式Workbench加载成功缓存后应用。

## 2026-10-30：Tag 条件保存与凭证读取简化

环境：本机macOS、现有Python虚拟环境、正式2026-10-29 Scan截面、保存的Tag/人工名单与本机凭证。只验证本轮清理涉及的读取、保存条件保真及名单分类/发布，不构造Mock、不运行全量或全链路测试。

- 核对上次提交没有新增Market专用拒绝函数，原通用Tag校验会因目录删字段而拒绝。现删除整段重复的条件字段、规则结构、数值类型/有限值/上下界及选项枚举校验和FIELDS映射；条件由前端唯一目录生成，后端原样保存。既有Tag数量、命名、用途、外观和当前选择约束保留。
- 删除统一凭证读取中新增的分组类型、字段字符串类型及非空检查，直接读取约定JSON字段。三家真实凭证均可按原值读取；未输出凭证值。Scan配置正常加载，未改候选规则、行情数据校验或交易约束。
- 删除注入未知/已移除字段并断言拒绝的测试。使用现有真实偏好、截面与人工名单的三项定向用例通过（0.70秒），覆盖条件值保留、规则重分类与实际名单发布/特征范围；Python语法与git diff --check通过。没有修改TypeScript，不重复前端构建。
- 正式后台重启为PID46685，恢复原Trade模式及2026-10-29日期；服务running、Quote CONNECTED、Massive Ready、持仓后台运行，workspace_error为空，偏好文件内容未变。未提交Tag修改、Alert或交易操作。

## 2026-10-30：统一 MDV20、Scan 基础筛选与配置入口

环境：本机macOS、Python3.13.1、TypeScript5.9.3；使用正式Massive日库、官方ETF目录、保存的Tag规则与人工workspace。验证只使用真实数据及其临时副本，没有构造Mock行情或发送交易写请求。

- 共用日线指标改为turnover最近最多20根完成记录的中位数，缺金额仍返回空；Scan、日图summary、名单和前端使用同一个mdv20字段。基础规则集中config/scan.json：非ETF、至少50根有效完成日K、MDV20≥15M、ADR20≥4%、Close严格>5，然后在完整合格集合内排名一次，三个RFL周期Top75取OR；Tag分类不重排或补位。35项形态目录不包含Market条件，旧均值计算/字段与独立展示配置加载链路删除。
- 7项真实数据定向用例通过、6项无关用例未运行。独立验证20条成交额排序中间两项均值、共享Daily summary与Scan一致、ADR公式、完整合格Universe和稳定排名、Top75 OR、过滤后不合格行无名次、候选/保留成员feature scope及名单发布/分类。首次4项核心验证也通过；未执行全项目或全链路测试。npm run build --prefix ui通过，Python源码只做语法检查，没有执行无关测试。
- 直接清理21份旧派生截面，保留35份原dated workspace，逐文件内容核对未改写。正常准备一次最新成熟日2026-10-29：原始Daily/split完成，SQLite因输入更新按原策略重建（578份raw、16,521只历史证券，约71.52秒）；新截面12,597只当日证券、649只基础合格、135只候选、149只完整特征，筛选2.463秒、特征1.581秒、总计4.043秒。当前仅保留该最新截面，不提供旧日期兼容字段。
- 三份本机凭证文件合并为config/credentials.json，三分组按需读取，真实字段仅在本地验证结构与非空、未输出值；文件权限0600、Git忽略，不进入UI静态目录。CLI只保留一个凭证路径参数。Schwab Keychain保持原样。根目录旧workspace删除，模拟器改为复制最新dated workspace至临时目录；未运行模拟器。
- 正式服务PID41664按原Trade启动参数恢复，再恢复原先的Scan展示。只读health、名单和单只ACN.US日图：2026-10-29、Massive Ready、Quote CONNECTED、workspace_error为空，SnapTrade后台任务运行；页面Discover52、Focus23、Excluded70（含持仓屏蔽），ACN图表与名单MDV20均为1,460,490,383.3773513。没有为验证提交或修改Schwab订单，也未验收全部行情周期/账户链路。
- 当前规范、操作说明与三处AGENTS同步；旧均值/配置/凭证路径依赖清除，git diff --check与现行文档相对文件链接检查通过。正常数据准备更新了允许版本化的split快照。

未覆盖：浏览器绘制与点击、全部旧离线用例、实盘下单/撤单/止损、报警播放和全量行情Ready。Trade价差仍严格大于0.5%才强调，数值仅维护于ui/src/trade.ts的SPREAD_WARNING_PERCENT，CSS继续只维护外观。

## 2026-10-30：Reset 按钮隔离与 Trade 点击遮挡修复

环境：正式Trade页、已有真实行情、隔离Chrome与Lightweight Charts 5.2.0；仅前端修改和构建，未重启后端、创建Alert或发送交易写请求。

- 复现Daily Reset调用onSelect，进而通过交易日联动移动Intraday视口；同时命中测试发现Intraday按钮中心实际落在trade-ticket空白层。移除Reset的candle选中调用，并只提高Trade Intraday按钮点击层级，不改控件位置或票据布局。
- 真实浏览器把双图移到历史并设置不同间距：点击Daily后Intraday的逻辑范围、间距和滚动位置完全不变；点击Intraday后Daily完全不变。两图各自回到5px及最新位置。R仍同时重置两图，Trade按钮中心命中intraday-latest，浏览器无脚本错误。
- 前端构建、既有Chart定向6项及git diff --check通过。Chart唯一规范与开发职责补清Reset不触发选日联动；未扩展其他功能或全量测试。

## 2026-10-30：成交额显示、等宽图表组与统一 Reset

环境：本机 macOS、Python 3.13、TypeScript 5.9.3、Lightweight Charts 5.2.0、隔离 Chrome，正式 127.0.0.1:8765。Massive 使用现有已完成日2026-10-28，Longbridge 使用已有正式缓存；没有新增模拟行情。为更新计算短暂停止服务，本地CLI重算最新Scan，随后恢复原先的Trade模式及正常后台；没有提交交易、改动止损或创建Alert。

- 正式页面真实样本的Daily/Intraday柱值分别等于其turnover；读数为Dollar Vol $2.52M与$367.67K，tooltip保留股数，5D Avg按金额计算。公开图表API核对金额柱，没有引用close估算。
- Trade双图宽度均为733.03px，拖动图表组/List分隔条后均为693.03px；Monitor仍等宽，Scan只显示单图，旧双图中间把手和键盘焦点已删除。未改变卡片、头部或交易票据样式。
- R同时恢复两图5px间距及最新位置；F预览后R清除预览状态，松开F不会还原旧视图。搜索输入R不触发重置；按钮复用同一方法重置本图。普通探查指针实测crosshair，按钮仍为pointer；可编辑线继续由原生primitive cursor覆盖，没有发起真实拖价。
- 本轮不改变Intraday常规价格比例、独立纵轴缩放或平移。量能报警、等级和排序继续使用原volume；没有迁移实时金额报警。未覆盖Regular实时换桶、全部周期、实际交易操作或所有股票，历史/缓存验证不作为实时金额报警鲁棒性证据。

## 2026-10-29：Daily setup 统一线性比例尺

环境：本机 macOS、TypeScript 5.9.3、Lightweight Charts 5.2.0、隔离 Chrome；真实 `runtime/massive/daily.sqlite3`，截至 2026-10-28。临时 127.0.0.1:18766 服务使用正式 Workbench/HTTP/Scan 读取和正式 UI 模块，workspace/Alert 库为现有文件的临时副本；未启动券商、账户或行情下载后台，未读取凭证、修改正式名单或发送交易请求。没有生成模拟行情。

- `npm run build --prefix ui`、定向 `node --test ui/tests/chart.test.mjs`（6 项）及 `git diff --check` 通过。现有 Chart 事件用例同步固定范围契约和公开 API 替身；本轮新图形验证使用真实数据及真实图表库，没有新增 Mock 行情。
- JBDI / YMAT / BNC / BKYI / DXC 的最近五根已完成收盘中位数分别为 2.36 / 2.12 / 5.34 / 2.85 / 16.09。577px 主图中锚点坐标为距顶部 192px；默认 5px 间距下，相对锚点 1% 的坐标差均为 5px（浮点误差小于 1e-10）。各股按住 F 后一年 OHLC 均处于范围内，松开精确恢复逻辑视口和间距；BKYI 因交易记录稀疏，一年预览的间距允许大于默认值。
- 真实滚轮缩放从 5px 到 5.5px，纵向 1% 同步为 5.5px；水平/垂直拖动、窗口尺寸变化及主图/成交量分区高度变化后比例与锚点保持正确。修正初次创建时 pane DOM 尚未出现导致 ResizeObserver 未绑定的问题；分区调整后成交量文字位置同步更新。
- Reset 恢复 5px 和最新位置；F 期间禁止缩放、删除键和图表编辑起手，松开/失焦/换股正确退出，输入框 F 不触发；消耗 pointerup 的图表手势后仍可进入预览。历史 2026-10-27 的 F/Reset 保持日期和数据截止日，不跳到最新 Scan 日。JBDI 顶部裁切提示有实际像素，已目视检查常规图、全貌及正式 Scan 列表；浏览器无脚本错误。
- 完整需求独立维护于 Chart UI 的 Daily setup scale，相关 UI、行为、职责、快捷键入口同步；旧 Daily 独立纵轴缩放、报价撑大范围及 Go to latest 保留 zoom 的要求已替换。vendor、后端行情/指标/订阅未改。
- 验收后已移除临时验证页、关闭 18766 临时服务，并按常规命令启动正式 Scan（127.0.0.1:8765）供用户试用。只读确认 mode=scan、日期=2026-10-28、真实数据、Massive 准备未运行；正式后台恢复其正常行情/账户刷新。这次启动不作为 SDK 闭合边界或交易验收证据。
- 未覆盖真实 SDK 开收盘边界、券商交易、全部 Intraday 周期、移动端或所有股票。用户后续通过真实 Scan 连刷约 20 只股票评估视觉力度；本轮没有扩大为全量测试。

## 2026-10-29：Schwab 导入目录与集成遗留文件清理

环境：本机 macOS、Python 3.13.1；仅文件迁移、文档与一处测试时钟修正。正式服务没有重启，未读取凭证、调用真实券商或发送任何交易写请求。

- 原独立项目目录不被正式运行链引用。后端设计迁入 docs/schwab-backend.md，25 个章节全部保留；交易函数/固定参数/风控/OTO/Replace/Cancel/响应/写入安全（第 8–15 节）与冻结原则（第 25 节）逐段 SHA-256 比对一致。旧前端展示、交互说明已从参考文档移除；兼容 FastAPI/SSE 协议明确标为网关参考，正式接入仍由 Schwab Trade 唯一文档维护。
- 原网关测试迁入 tests/test_schwab_backend.py，仅修改模块导入；其余测试内容逐字比对一致。现在由根项目默认 tests 路径收集。原集成用例的 Sold Today 日期写死为 10 月 26 日，却读取当前真实时间；独立重跑也失败，现仅固定该用例 monitor.now 与成交日期一致，未改生产逻辑。
- 删除旧独立项目（含其虚拟环境、锁文件、部署示例、包元数据和缓存）、runtime/import-backups 下的旧 Git/前端/交互文档备份、无引用的 build、空 dist 和旧 pytest 缓存；合计约 185 MiB 文件内容。实际账户/行情缓存、根项目虚拟环境和现用 UI 构建产物保留。
- 删除后 `.venv/bin/python -m pytest -q tests/test_schwab_backend.py tests/test_trade.py -p no:cacheprovider` 150 项通过。两个根项目 CLI 的 --help 可正常加载；交易内核 SHA-256 与清理前一致，Keychain service 名保持原值。旧 5678 端口检查无监听者；没有重启或连接另一份 Runtime。
- README、AGENTS、开发与 Trade 入口已指向迁移后的文档和测试；当前文档本地链接检查、遗留引用检查、git diff --check 通过。未运行无关全项目测试或前端构建，未做真实交易验收。

## 2026-10-29：Buy 类型文字的底部留白

本机 CSS 静态检查：仅将 Buy 内 stop/market 的文字 span 相对上移 2px，保留同一基线、按钮尺寸、标题/分界线和点击区域；不修改 padding、字号或行高。git diff --check 通过。纯样式微调，按用户要求不截图或扩大测试，最终视觉由用户查看。

## 2026-10-29：Buy/Sell 与 Send 等高

本机 CSS 静态检查：Buy/Sell 高度从 35px 改为现有 Send 的 30px；Buy 上下区域为 18/12px，Sell 行高同步 30px。保留横向 padding、字体、宽度与平移，35px 按钮所在行和其他模块位置不变。git diff --check 通过。纯 CSS 调整，按用户要求不截图、不扩大测试，未改 TypeScript 或交易逻辑。

## 2026-10-29：交易区水平视觉对齐

本机 CSS 静态检查：Qty、预估和 Buy/Sell 共用 translateX(-15px)，按现有 30px Send 胶囊的半径对齐右侧矩形本体；不改变宽度、行距或垂直位置，Auto/Send、报价不参与平移。保留用户已调整的 row-gap:12px、字号与按钮大小。git diff --check 通过；本轮无 TypeScript/后端改动，按用户要求不做截图或扩大测试，最终视觉由用户手动查看。

## 2026-10-29：交易区间距从固定按钮向上展开

环境：本机 macOS，现有正式服务与真实 GTLB，美东 10 月 28 日约 23:34–23:37。仅修改两条布局 CSS 与相关文档；保留用户手调的字号、按钮大小，未改 TypeScript 或交易逻辑，未重启服务或发送真实交易。

- 原布局四行自顶部排列，row-gap 增大会增加总高度、把按钮推到容器裁切区。现在只有 Qty、预估、按钮三行进入 grid，使用 align-content:end；报价和反馈独立绝对定位。
- 临时分别将同一 CSS 的 row-gap 设为 6/8/12px，通过实际浏览器重载测量。Qty 顶部为 82/78/70px，预估顶部为 122/120/116px；按钮始终为 162–197px，Send 底部始终为 194.5px，报价始终为顶部 20px、右边缘 836px。默认已恢复为原来的 6px。
- 在 12px 间距下实际拖动数量从 344 到 520，预估正常更新；浏览/激活状态切换未移动按钮和报价。截图：`/Users/cyno/.codex/visualizations/2026/10/26/01a17832-a589-7120-8e1f-ffe5c161d0de/trade-bottom-anchor.png`。
- 本轮只做布局浏览器检查及 git diff --check，不重复未改动的 TypeScript 构建或账户/交易用例。未验证任意极大间距、所有窗口尺寸及实体输入硬件。

## 2026-10-29：数量轴恢复原生拖动与交易细节

环境：本机 macOS、TypeScript 5.9.3，现有正式 8765 服务及真实 GTLB 数据，美东 10 月 28 日约 23:08–23:14。只改前端，未重启后端、修改交易网关或发送真实订单/改单/撤单。

- 删除上一轮数量轴的显式指针捕获、全局隐藏光标 CSS 和自定义拖动生命周期，恢复浏览器原生 range；普通指针始终显示，仅借原生 :active 冻结拖动中的数量步长与范围。本机浏览器在改动前能拖动，未复现用户实体触控板的失败，因此不将指针捕获认定为已证实的硬件故障原因；删除这层干预以恢复最直接的原生路径。
- `npm run build --prefix ui` 通过；Trade 与 Schwab 数据定向 UI 用例 24 项通过。原光标状态用例删除，改为验证原生 input 更新数量与预估金额、报价变化期间不改变拖动范围、释放后刷新步长仍保留数量。
- 实际浏览器连续拖动 Market 数量 364→670→150，右端选择 821、键盘左移为 820；Buy Stop 从 344 拖至 520，预估总额同步；Sell 从全部 400 拖到 200，再从右端选回 400。均未点击 Send。本轮没有实体鼠标/触控板硬件验收，不用自动化拖动冒充该覆盖。
- 百分比未发现其他模块覆盖，原嵌套行内文本盒为 29.5px 高、带半像素定位；移除外层 span 后独立块级文本盒为 34px 高，报价起点改为整数 10px。截图及元素命中检查中百分比完整可见，最上层为自身，不声称已复现用户端的裁切原因。
- 实际 GTLB 取消按钮为 16×16px，SVG 为 14×14px，四边间距均为 1px，保留原交叉线粗细。截图：`/Users/cyno/.codex/visualizations/2026/10/26/01a17832-a589-7120-8e1f-ffe5c161d0de/trade-native-qty.png`。相关唯一 UI/Chart/Trade 与开发文档已同步，未运行全项目测试。

## 2026-10-29：价差主视觉、Buy 明细与盘外止损改单

环境：本机 macOS、TypeScript 5.9.3、Python 3.13；正式 8765 服务，真实美东 10 月 28 日约 22:20–22:47，Regular 之外。仅本次定向验证，不运行全项目测试。

- `npm run build --prefix ui` 通过；`node --test ui/tests/trade.test.mjs ui/tests/schwab-data.test.mjs` 24 项通过；网关 Replace 定向用例 39 项通过（测试文件现已迁至 `tests/test_schwab_backend.py`）。覆盖 Buy 明细两项盈亏为空、Sold/Stop 按当前均价估算及缺均价留空、PENDING_ACTIVATION 在 editable 为 true/false 时的单次 PUT、原数量/有效期/NORMAL 保留、其他不支持状态继续拒绝，以及新 ID 仍待激活时结束旧改单预览。
- 正式只读订单显示六张普通 SELL STOP 均为 PENDING_ACTIVATION，其中五张 editable=false，另一张为 true；原前后端状态限制共同阻止拖动/提交。仅放开这一状态的本地门禁，其他校验保留。原服务按原入口重启，账户/订单初始化成功、REST connected、认证有效。
- 实际浏览器显示百分比 25px、蓝 Ask/红 Bid 各 12px 上下排列；Buy 全背景激活、未选 type 隐藏。真实 GTLB 七列盘外表格中，Buy 的 P/L% 与 P/L 完全留空，Stop 显示参考盈亏、数量、价格和红色取消按钮，未增加虚列。
- 对真实 GTLB 止损线只做本地拖动，确认进入 stop 编辑且 Send 可用，再按 Esc 回到 browse；未点击 Send、取消订单或发送任何真实券商写请求。数量轴实际按住时 cursor=none，松手后立即恢复 default；取消/失焦等清理路径由定向 UI 用例覆盖。截图：`/Users/cyno/.codex/visualizations/2026/10/26/01a17832-a589-7120-8e1f-ffe5c161d0de/trade-spread-focus.png`。
- 启动时既有 Massive Daily 准备对 2026-10-28 返回 HTTP 403，页面保留 Refresh failed；本轮未修改或排查该独立数据源问题，Schwab 读取与交易图表正常。

未覆盖：真实 Stop PUT 的券商接受/拒绝、真实成交、撤单、Regular 实时行为及全部浏览器/输入硬件。盘外允许本地提交不代表已验证 Schwab 接受 editable=false 的改单，也不改变止损的 NORMAL 执行时段。

## 2026-10-26：Home / End 未读导航快捷键

- Home / End 在现有 main.ts 键盘入口归一为 Command+U/G，继续调用原 jumpUnread，没有改查找、排序、选图和已读逻辑。非编辑区域拦截单键原生滚动；Scan 的 Home 不跳 Holdings。
- `npm run build --prefix ui` 与 `git diff --check` 通过。Node VM 加载实际生成的 main.js，定向验证单键及原组合键路由、Monitor/Scan范围、阻止滚动、编辑内容／输入法和修饰键保留；脚本 `/tmp/alert-home-end-check-2026-10-26.mjs`。未运行全项目测试、重启后端或创建真实报警；未覆盖浏览器实按键盘，本轮只增加按键别名。

## 2026-10-26：Symbol 模板、未读波浪与统一声音节奏

环境：本机 macOS、Python 3.13.1、TypeScript 5.9.3；现有正式 Monitor、Longbridge 与 Holdings 数据。只验证本次模板、显示阈值和提醒契约，没有运行全项目测试。

- `npm run build --prefix ui` 通过；Alert、Intraday State 与声音模块共 51 项相关后端用例通过，21 项相关 UI 用例通过。HTTP/WS 用例首次受沙箱端口绑定限制，允许本机绑定后单独通过。覆盖最新方向／等级覆盖和恢复、旧无方向 urgent 清理而不改变价格线、播放并行及退出清理、旧播放不能恢复已读提醒、节拍去重，以及 Focus 原始量比阈值与 Holdings 原显示不变。
- 临时页面直接使用正式构建的 Watchlist、HoldingsList、Symbol 模板与 attention 模块，数据使用 Mock。浏览器检查两表 Symbol 对齐、完整 Holdings 价格区域、独立量能胶囊、整行选中、低值留白、强底色文字、同时未读、最新颜色覆盖及点击已读。修正价格区域末端留白，避免半圆裁切 ADR。截图 `/tmp/symbol-row-2026-10-26.png`；临时页面已删除，没有新增正式预览入口。
- 三种完整 WAV 经实际后台 `afplay` 播放成功；上行 4、下行 6、紧急 8 次节拍反馈，无播放错误。最终下行及紧急音色替换后仅重验这两种。播放命令与节拍成功不代表用户已完成主观听辨；音画使用同一节奏，未承诺采样级同步。
- 正式服务按原 Monitor 命令重启，Quote 为 CONNECTED、Massive 为 Ready；浏览器只读确认真实图表、Holdings、Focus 和新选中外观，检查后恢复原 CAI 选择。未创建正式 Alert、改变名单、手动 Refresh 或增加券商连接。既有 TJGC 六周期最新 closed 缺失与重启前一致；启动任务按原规则更新 Massive 缓存及 `splits.json`，未修改数据准备逻辑。
- UI 唯一入口维护 Symbol 模板和颜色名称；Alert、Holdings、Intraday State、behavior/development、README 与各 AGENTS 同步。删除旧虚线／闪烁样式与重复价格区域实现，声音不再循环播放旧短文件，未读不叠加或保存历史。`git diff --check` 通过。

未覆盖：真实 Regular 市场事件触发、多 symbol 实时音画同步及最终音色主观确认。正式页面检查发生在 Regular 之外，动态外观以实际组件的 Mock 状态验证，不作为真实市场触发证据。

## 2026-10-23：Alert Regular 未读生命周期与键盘导航

环境：本机macOS、Python3.13.1、TypeScript/Node。当前09:06 ET检查时8765服务未运行，本轮不启动正式后台或触发任何行情/账户下载；只覆盖本次清理、已读和未读导航。

- 后端定向`tests/test_alerts.py -k 'unread or read_only or scope_removal or reaches_or_crosses or old_card'`15项通过；HTTP/WS定向`-k 'alert_http_origin'`1项通过。覆盖正常/提前收盘准确失效、同Regular重启保留、跨夜/周末/下一Regular清理、scope尚未就绪也清理、state首次输出前清理、灰线/Active线逐字段与期限不变、不补播。HTTP用例首次因沙箱禁止临时端口失败，允许本机临时绑定后通过，未修改用例绕过权限。
- 前端`ui/tests/list-interactions.test.mjs ui/tests/scan.test.mjs`22项通过；新增覆盖完整Focus共用分组顺序、Pinned/In Play/原分组、折叠目标、Tag隐藏但不改筛选、后台更新保留隐藏选图、持仓按当前主行排序与同symbol多批次只跳一次、全部读完无操作。`npm run build --prefix ui`与`git diff --check`通过。
- 实际生成的main.js以Node VM加载，图表/DOM/网络使用轻量替身，直接验证连续选图尚无响应也立即read、持仓及切周期同入口、零bar图表更新仍read、G/U不依赖当前选择来源、输入/修饰键保留及Scan不处理U。证据`/tmp/alert-main-check-2026-10-23.mjs`；这是主界面接线检查，不是浏览器视觉或实际按键验收。
- 09:06 ET只读备份当前真实`runtime/alerts/alerts.sqlite3`到临时目录后运行实际AlertEngine：原16条价格线逐字段不变，3条已过所属Regular的未读变为0；无scope准备依赖、无新表、无播放。正式库未写入，副本已删除，结果`/tmp/alert-session-audit-2026-10-23.json`。
- README、Alert、List交互、Holdings/UI、behavior/development及模块AGENTS同步；没有新增viewed/已读等待状态、遍历游标、期限字段或服务依赖。未跑全项目测试，未覆盖本轮浏览器实按G/U、真实市场收盘瞬间推送或物理睡眠唤醒，也未重测未修改的声音/图表拖动。

## 2026-10-23：List 单只操作与 Refresh 统一清理

环境：macOS、Python 3.13.1、TypeScript 5.9.3；本机已有真实 Massive 截面/名单与 SQLite、现有 8765 服务。仅本次相关验证，不运行全项目测试。

- TypeScript build 及 git diff --check 通过。6 个定向 UI 用例通过：Scan 删除/左右入选、两模式组内移动与 Command 置顶的按键分流、机器释放禁止、重复置顶不跳、保存成功/失败选择、末尾不循环、跨 section 展开与搜索仍选中目标。
- 17 个相关后端用例通过。真实截面测试仅编辑临时 workspace 副本：同日 Refresh 与新日首次分类的 statuses/orders 一致，清除 Pin/人工 Tag/section/Discover/排序，Focus 恢复自动淘汰，Hidden 不延期；同日 carried 不伪装成新日。重复 Refresh 幂等，Ready 数据不重新 build，准备失败保留人工名单。单只入选继续与 Alert 共用重新匹配，Hidden 释放和机器禁止释放沿用既有规则。
- 正式服务页面仅做显示/导航检查：Monitor Page Down 到下一组首只，在末组不循环；Scan 不再显示勾选框/Move to，显示单只 Add to Focus，Page Up 展开折叠 Bounce-20 并选中 PDSB。检查后恢复 Monitor，未提交正式名单移动、置顶、删除或 Refresh，也未更改真实 Alert。
- 原 Monitor 服务按原配置重启加载后端改动，确认 Quote CONNECTED、27 个完整行情 symbol、Massive Ready；不新增测试券商连接或扩大订阅范围。重启前已存在的 TJGC 历史缺失不属于本次改动，不以启动时 errors 为空宣称解决该问题。
- 未覆盖：真实账户上的名单修改/Alert 删除、所有键盘硬件、全天运行及其他模块全流程。真实数据副本验证不冒充正式名单实操；样式仅做当前页面检查。


本文件只记录各次验证事实，不定义 UI 要求；当前规范统一见 [ui.md](ui.md)。

## 2026-10-31：Longbridge 多账号与访问台账

环境：本机macOS、Python3.13.1、Longbridge SDK5.0.0；实际行情为美东2026-10-30 Regular，本机跨10月30/31日。使用当前真实Focus、两套账户展示范围及原Trade模式，无Mock响应、伪造价格或交易写请求。

- 本机凭证改为有序accounts列表，保留原账号并配置第二个独立账号；权限600、Git忽略及改动文件无凭证值检查通过。新增独立longbridge-accounts.md，行情、开发、行为、README与两份AGENTS入口同步；不增加前端组件或修改TypeScript。
- 先仅用当前Focus的CDNA进行有界第二账号检查，原正式报价服务保持运行。实际SDK会员身份与主账号不同；官方ForwardAdjust Daily取得999根closed，最近20根OHLCV/turnover与正式缓存逐值一致。六周期SDK起点各1000根，24.2秒内收到125份真实candle回调，主服务Quote增加1491次。10秒周期保存成功；连续11秒没有K线调用时文件mtime不变，期间SDK实时推送仍继续。最终再次查询后aclose补存了最新访问时间，六周期及底层订阅正常移除。
- `tests/test_longbridge_usage.py`使用正式Longbridge库中本月真实成功batch元数据，在临时目录验证第90只仍归账号1、第91只及六次重复访问归账号2、归纳计数、无变化不重写、保存重读后归属保持；1项通过。没有请求91只股票消耗额度，也没有Mock SDK、时钟或行情。Python编译与git diff --check通过，未运行原有Mock用例。
- 按原参数恢复正式Trade服务，两个context均实际创建。完整行情14个symbol、三名单等报价143个；台账为账号1的13只和账号2的1只，重复初始化、收盘查询及重启没有增加去重数量。同一本机日跨午夜后归属保持。第二账号CDNA的Daily及5m/15m/30m/1h/2h开放根均通过现有链路显示；3秒实际WebSocket收到14份2h图表更新，首份含完整closed，持续包含active。
- 最终代码的短启动SIGINT检查3.92秒内退出，退出码0，早于首次10秒定时保存；CDNA与JBDI的新最后访问时间补存，14只映射与归属保持，日志没有Traceback或ERROR。未到保存周期的数据通过正常关闭流程落盘。随后以原命令恢复Trade并保持运行。
- 实际12:00边界有15个周期短暂缺最新closed，12:05下一轮全部回补成功。12:13:05 ET检查时JBDI的12:05起点5m缺失，最后Regular报价为12:01:24，已有12:00柱仍显示，保留原有缺柱重试/提示。12:20后最新目标回补完成，最终12:21:39 ET只读核对14个symbol、84份官方窗口全部达到当前closed目标，pending=0、errors为空。过程中的缺柱没有被台账逻辑隐藏，报价连接、Holdings与其他窗口继续运行。

未覆盖：供应商完整月度用量、启用前访问、真实跨月、第三/第四实际账户、全部账号100只耗尽、断电及保存失败。台账是启用后的本地访问记录，不等同官方额度。只读统计命令不创建SDK context；独立live_check复用已有runtime锁，避免并发进程写同一台账。


## 2026-10-23：三名单最新报价与 Overnight

环境：本机macOS、Python3.13.1、Longbridge SDK5.0.0、TypeScript5.9.3；真实美东10月23日00点后夜盘。重启原正式Monitor服务加载Overnight配置，复用一条行情context；未创建另一条券商连接、测试报警或模拟行情。验证结束恢复Monitor模式。

- 正式服务收到Overnight推送，推送计数由初始98增长至121；随后30秒Monitor/Scan有界WS观察又增长5。当前有效范围按真实名单与持仓去重为27只完整行情、73只Quote-only；服务CONNECTED，切模式前后started_at一致，日志无连接重建。
- Monitor的MRNA.US共74份view，夜盘价200.70→200.21→200.20；Scan额外成员ASST.US共71份view，夜盘价29.44→29.43。所有latest均等于同份响应中各时段报价的最大timestamp项；两轮观察中candle active和indicator_preview保持不变，Scan没有active candle。
- 真实PAYS.US没有Overnight报价，latest保留Post15.00；原始快照的JBDI.US latest为Overnight2.30。将这两份真实响应送入实际Panel.setQuotePrice，分别得到蓝色#2962ff与黑色#000000，价格正确，candle/volume序列不变。此检查复用既有UI测试的绘图库替身，只验证应用公开API调用，不冒充浏览器像素验收。
- 97项相关后端回归通过，覆盖最新值/缺值/历史Scan、常驻批量订阅、完整与Quote-only范围、前收盘基准、图表、持仓、模拟器、Alert及Intraday State。TypeScript构建与20项相关UI用例通过，覆盖来源颜色、价格轴替换/清理、自动缩放和原生candle标签。未新增Mock数据源、恢复机制或历史下载入口。
- 当前需求统一维护在Longbridge及Chart UI，README、behavior/development、UI总入口、List说明及AGENTS同步契约；移除被替代的时钟/日期报价过滤、前端二次选价、旧SDK字段别名、时段文字及相关旧规则验证段落。报价只在内存；Quote、Trade、candle共用原连接与恢复流程。
- 正式服务重启按既有流程完成下一日Massive准备，更新运行缓存及splits.json；未修改Massive逻辑。

未覆盖：真实Regular/Pre/Post逐跳推送、断网/休眠、周末连续运行及浏览器实际视觉验收。本轮夜盘真实推送与静态快照样本不替代这些场景。

## 2026-10-23：后端目录与模块命名整理

环境：本机macOS、Python3.13.1、Longbridge SDK5.0.0；北京时间10月23日，对应美东10月22日Regular。仅调整代码归属、导入和类名，正式运行目录、SQLite路径、请求额度与调度规则保持原状。

- Longbridge收拢为client/realtime/history三个模块；历史读取检查合入history。Massive准备流程归入massive包，证券目录归入additional_info并保持独立CLI。共用Bar、持久化、序列化和OHLC诊断集中于storage，图表缓存与Monitor编排分别使用chart_cache、monitor。未保留旧模块转发，后端Python文件总数42→42。
- 对照改名前HEAD的174个原有函数/类，归一化四个类名和导入后，语法树函数体全部相同。42个内部模块的82条顶层导入依赖无环，41个后端子模块在新解释器中全部导入成功；Scan单独导入不加载Longbridge SDK。保留既有函数内延迟导入，未为目录调整改写业务依赖。
- 正式CLI、live_check、证券目录获取、附加信息获取、Massive获取、Scan Mock生成器及模拟器共7个help入口通过。新路径成功读取现有真实证券目录13,289只；没有触发目录或历史重新下载。
- 现有311项后端用例中308项通过、3项失败，另11个subtest通过。3项均为Scan旧断言：要求继承机器Excluded身份或将机器Excluded保存到workspace。将改名前HEAD的代码与原用例提取到临时目录，三项出现完全相同失败；本轮保留现有产品规则，仅更新导入与符号，不修改这些断言来制造通过。未新增Mock数据源或测试框架。
- 原服务停止后以原Monitor模式恢复，真实范围仍为28个symbol。短时HTTP核对Quote为CONNECTED，推送计数3秒内1,127→1,151；AMC Daily/15m均含实时active及历史，持仓任务运行，Massive为Ready，附加信息缓存无错误并正常返回。既有TJGC六周期官方最新closed缺失继续独立重试，未因迁移增加其他错误。
- README、开发职责、数据入口及AGENTS同步新结构；脚本、模拟器、测试中的直接导入和字符串patch/sys.modules路径已更新。未改TypeScript，不重复前端构建。

未覆盖：浏览器视觉与声音听辨、真实断网/休眠、拆股日及首次无缓存的全量下载。本轮是目录与依赖迁移，没有再次进行行情算法或启动性能对照。

## 2026-10-23：Longbridge 同日缓存复用与启动分级

环境：本机macOS、Python3.13.1、Longbridge SDK5.0.0、TypeScript5.9.3；北京时间10月23日零点后，对应美东10月22日Regular。停止原服务后，直接使用正式SQLite、当前Focus/Holdings与真实接口做两次35秒/55秒有界启动，分别始于12:42:03、12:43:13 ET；随后恢复普通Monitor服务。测量钩子仅在临时脚本内记录耗时和请求，不进入正式代码，没有额外并行行情context、Mock数据源或测试报警。

- 两轮完整行情均为28个symbol。初始25个Focus共150个周期中，144个同日成功批次直接恢复；Holdings补入的有效缓存也逐周期复用。第一轮仅JBDI缺一根5m，执行一次count2；第二轮同一5m窗口内，有效symbol没有历史查询。两轮均只有TJGC六周期因官方最新closed缺失各尝试4次，返回码2明确表示该缺失，没有以SDK值冒充历史成功。
- 从进入启动脚本计时，两轮全部Quote在4.8–5.4秒可用；25个具备有效状态输入的symbol同时得到ADR，无需等待SDK Daily。第一轮CumVol首次6.1秒、24个可用样本最晚28.0秒，LocalVol为6.4–20.3秒；第二轮25个可用状态的CumVol为5.8–20.5秒、LocalVol为7.0–20.1秒。暂缺某根或历史区间的symbol独立等待，未填零或阻塞其他股票。两轮28只的5m/15m SDK均在约20秒内完成初始化。
- 正式服务恢复后跨过12:45闭合点：只读SQLite确认JBDI/AMC/TEAM的5m、15m批次在12:45:02至12:45:13提交，30m/1h仍为12:30批次，Daily/2h沿用此前有效批次；未重复全量。随后health为CONNECTED、Quote推送计数继续增长、Holdings任务运行；当前盘中状态范围25只，其中24只ADR/CumVol/LocalVol均可用，TJGC三项缺失与官方历史错误一致。
- 161项后端定向回归通过；最后补强零点/周末与EMA首值用例后相关61项再次通过。覆盖同日逐周期恢复、缺一/多闭合边界、1h开盘对齐、SDK不能推进权威水位、连续运行跨零点及周末、9:25不重复刷新、恢复期间在途成功复用、Quote OHL同日保留/跨日清除、ADR不等Daily、价格与量比分开就绪、首个价格/EMA静默及既有Chart/Alert/Scan/Holdings消费契约。TypeScript构建与6项状态UI用例通过。
- 清除盘前刷新标记及其调度，恢复不再无条件重拉六份历史窗口；未增加数据库表、额外水位或操作系统解锁监听。文档以Longbridge与Intraday State唯一规范为准，并同步职责、行为、UI及AGENTS入口。

未覆盖：真实美东零点、系统断网/休眠/解锁、真实拆股日、首次无缓存的全名单启动，以及浏览器视觉与声音听辨。零点、周末、恢复和EMA首值由既有真实SQLite/交易日历定向用例覆盖，不作为上述真实事件的实测证据。量比仍需官方SDK逐symbol/周期初始化，不能承诺整个列表秒级齐备。

## 2026-10-22：Longbridge 当天 SDK 序列与官方历史统一读取

环境：本机macOS、Python3.13.1、Longbridge SDK5.0.0；真实接口范围为当前Focus内AMC/MRNA及正式服务现有Focus/Holdings。先停止旧服务，使用两只股票的临时SQLite做有界初始化/恢复验证，再恢复正式Monitor；全程没有第二条并行券商连接，不创建测试报警，不注入断网或进行录屏。

- 两symbol六周期初始化5.142秒，12个官方历史窗口各1000根，12个SDK周期注册。随后主动执行一次既有recover：原context与Quote callback代次不变，Quote推送计数3→5，无Quote/Trade退订或重订；六周期各重新取得SDK起点及官方历史，全部成功。含3秒后续观察的总用时12.988秒。
- 正式服务09:25盘前全量刷新：MRNA Daily09:25:06、15m09:25:12、30m09:25:18、1h09:25:24、2h09:25:31完成；09:30开盘没有重启这些任务。09:30:07只读chart已同时包含Regular Quote、SDK Daily及5m，Daily volume465,301、5m volume18,470，各自保留官方口径。
- 09:35:02官方5m增量以count2成功提交，缓存从1000自然增加到1001根，其他周期仍为09:25成功窗口，未在每5m重拉未闭合的大周期。
- 153项定向回归通过：统一读取及权威覆盖、迟到SDK不能改回权威值、换桶无需等待REST、超过1000根、新日/开盘/恢复、限流与优先级、同秒历史修正后的量比/ADR失效、既有Manual Alert、SDK/Scan订阅范围、模拟器及持仓/Scan消费契约。只更新既有SDK测试替身的契约与旧周期数量，没有新建Mock数据源。未改TypeScript。
- 最终版09:36:31启动，仍有120个历史任务pending时，Quote已CONNECTED且push_count为68；约09:37:48变为815，仅TJGC的六周期缺目标继续独立报错。MRNA的SDK Daily/分钟数据与列表状态在各自可用后持续显示。
- 只读WS观察MRNA至09:40:15：09:35–09:40桶结束后0.142秒，closed序列已包含SDK根，volume338,866；2.822秒后同根被官方volume339,131覆盖，差265（约0.078%），OHLC均为233.95/237.29/233.035/236.66。557次开放volume数值变化；首次数据出现后Daily active消失、末根时间倒退、盘中状态消失均为0。旧一次观察因页面切Scan而中断，没有将其计作完整边界证据。
- 重写Longbridge唯一说明，清除旧等待/清空/重建逻辑说明，同步README、behavior/development、Chart/UI、Intraday State及三处AGENTS。204个相关本地链接与git diff --check通过。正式Monitor服务已恢复；重启时既有Massive任务正常更新了运行缓存和splits.json，未改Massive处理逻辑。
- 最后health核对：Monitor、Quote CONNECTED、push_count2,911、Holdings后台运行。TJGC六周期与PSIG当根5m的官方最新目标缺失，按既有有界回补独立报错/重试，保留可用SDK及旧历史，不填造权威根。

未覆盖：真实断网/系统休眠、真实拆股日、1h/2h/Daily收盘、全部symbol逐根SDK/历史对照、浏览器视觉与声音听辨。边界连续性证据来自后端WS及只读SQLite，没有录屏或故障注入；SDK暂定误差与官方历史修正的产品前置条件保持不变。

## 2026-10-21：自动排除改为当天派生结果

环境：本机macOS、Python3.13.1、TypeScript5.9.3；使用现有真实Daily SQLite、28份dated workspace、真实Scan截面及preferences。未建立Mock或另建行情连接，测试中的名单编辑只发生在真实数据的临时副本。

- 跨日只继承Focus及有效Hidden，保留Focus每日负面淘汰；淘汰的非候选退出名单。自动Excluded成员身份、section和机器Tag不再写入workspace，读取时从当天截面/规则重建。原Pin与人工Tag仍按当天保存，文件watcher比较同一持久投影；NEW保留，旧恢复标记及其字段/显示链路清除。
- 8项真实数据定向用例通过，覆盖候选范围、跨日继承、真实Focus淘汰、AVAH七个自然日Hidden到期、规则修改、机器成员Pin/人工Tag、Hidden/Release/Focus操作、保存/重读、发布与feature scope，以及搜索Discover仅当日保留。`npm run build --prefix ui`通过；未运行Mock、全项目或全链路测试。
- 停止旧进程后直接清理28份workspace，共799个旧机器身份、87个废弃字段，无备份或兼容恢复分支。仅从本地SQLite重算2026-10-19：12,638只证券、88个candidate，筛选4.731秒、完整特征2.060秒、总计6.791秒，完整feature scope为94只。当前Focus和Hidden的保存状态与清理前一致；落盘所有Excluded成员均为Hidden。
- 正式服务恢复为原先正在使用的Scan模式，PID23703。只读`/v1/scan`和health确认：2026-10-19的页面Excluded由96降至42，其中Under-50为23、Extended为10、Broken为7、Hidden为2；Discover24、Focus23（已屏蔽持仓）保持不变。所有机器成员均为当天candidate，接口无废弃字段，workspace_error为空、Quote为CONNECTED、Holdings后台任务运行。启动时Massive仍按既有规则准备下一个成熟日，本轮不等待或验收其完整网络流程。
- 同步List/Massive/UI唯一规范、behavior/development、README与三处AGENTS入口；194个本地文档链接和`git diff --check`通过。既有splits.json修改未处理。

未覆盖：浏览器实际点击/绘制、全周期行情Ready、实时报警播放与账户交易链路。真实接口核对仅用于确认本次名单契约与服务恢复，未扩展为全链路验收。

## 2026-10-20：报警边框仅作用于 symbol row

环境：本机macOS、TypeScript/Node；仅调整前端边框作用范围，未修改后台或重启服务。

- 删除名单section与Holdings标题的报警聚合调用及section成员缓存；源码和生成JS的边框调用均只剩名单row、持仓row两处，辅助函数简化为单symbol入参。
- `npm run build --prefix ui`通过；`node --test --test-name-pattern='symbol unread' ui/tests/intraday-state.test.mjs`定向1项通过，覆盖多symbol同时闪烁、点击已读清除、播放结束后静态驻留。`git diff --check`通过。
- 同步Alert、UI、Holdings及维护入口。未运行全量测试、浏览器视觉验收或真实报警播放；页面刷新后加载新前端。

## 2026-10-20：In Play 与统一未读边框

环境：本机macOS、Python3.13、TypeScript；北京时间00:46起为美东10月19日Regular。本轮仅覆盖自动聚集、价格列外观、统一报警/已读与独立声音，不跑全项目回归。

- 后端定向 `tests/test_alerts.py tests/test_alert_sound.py tests/test_intraday_state.py` 41项通过。包括原手动穿越/精度/恢复、read不改灰线及重新设置、同symbol最新未读覆盖、恢复不播放、旧events迁移移除、HTTP同源与WS未读推送、自动规则接入同一notify、并行四遍/失败/退出清理。首次HTTP用例因沙箱禁止临时端口失败；允许本机绑定后全组通过，未改测试行为绕过限制。
- 前端定向 `ui/tests/intraday-state.test.mjs ui/tests/holdings.test.mjs ui/tests/scan.test.mjs` 26项通过；`npm run build --prefix ui`通过。覆盖离散稳定排序/Pin、持仓批次尾部及统一边框：多symbol同时ringing、read后剩余播放不恢复该次边框、结束后保持静态未读。没有新增全项目或样式数值测试。
- 当前真实Alert SQLite只读备份到临时目录迁移，5条价格线逐字段一致，旧卡片表移除，未处理记录按symbol合并。本轮正式服务从原Monitor命令平稳重启，PID15882；`/health`为running/CONNECTED。正式库仅alerts/unread两表，5条价格线与重启前完全一致；现场有27个盘中状态、4个未读symbol，仍有原行情初始化待处理项，不据此声称全名单Ready。证据`/tmp/alert-refactor-live-report.json`，日志`runtime/alert-refactor-live.log`。
- Chrome正式页面只读确认：Grouped/Dynamic及卡片DOM不存在，In Play在Pinned下自动生成，真实成员NOWL/OABI/IOVA等跨原分组聚集；NAUT已由用户置顶，保持Pinned且只出现一次，HTFL位于独立Holdings。Monitor价格底色实际覆盖grid第1至4列，Tags仍为正常深色。Safari Charts已刷新加载核心界面并恢复原CMCT选择。没有为验证修改正式Pin/Tags/名单或创建正式价格线。
- 临时UI服务localhost:8767使用本轮正式服务的真实名单/行情/图表快照，提醒库隔离、播放状态替身静音，不读凭证/新建券商连接。临时NAUT手动线与HTFL自动提醒同时显示ringing；当前已经选中NAUT不会自动read。刷新后两者静态虚线恢复；点击NAUT成功选图后仅其边框消失，HTFL保留，灰线实际超过10秒仍存在。重新设置后Active且其他symbol未读不变。把临时排序等级置空后In Play整个消失，22个symbol均只显示一次，原分组恢复；浏览器无JavaScript error。截图`/tmp/alert-in-play-unread.png`为该真实行情快照/隔离提醒验收页；临时页、服务及数据库已清理。
- 实际声音另用独立AlertSound同时播放TEST_UP/TEST_DOWN，各原声四遍，无插入间隔；两者playing状态重叠，afplay均成功退出，最终无遗留播放任务或错误。证据`/tmp/alert-parallel-sound.json`。本轮没有新增人工听辨确认，不把命令成功表述为用户已听到。
- 需求、职责、UI图形及各AGENTS入口同步；Markdown相对链接/锚点和`git diff --check`通过。未覆盖整个Regular日持续运行、真实市场同时触发多symbol的音画同步、macOS27或物理休眠；未对未修改的图表拖动手势重做全量验收。

## 2026-10-19：MRNA 当日日内成交手工归零

环境：本机macOS、Python3.13、原正式Monitor进程PID1587及localhost:8765。用户确认MRNA当天多次买卖均已完成、当前持仓为0，授权合并关联。只修改`runtime/holdings/sequences.txt`与现有`merge_buys.txt`，未重启或另起服务，未修改账户、Python/TypeScript实现及其他股票关联。

- 初始现有服务报MRNA卖出订单`0459A5…6C56`归属歧义，成功快照停在本日21:58:53。依据该已接受快照先关联首轮买入200股与卖出200股后，现有轮询越过第一笔错误并报告后续卖出歧义。失败轮原始数据不提交缓存，因此仅额外读取一次SnapTrade executed orders（沿用现有端点/参数），只核对当日MRNA；没有调用付费连接refresh或另行获取持仓/行情。
- 真实订单共5笔BUY与5笔SELL，双方累计均700股、净数量0。按用户授权，沿用现有人工合并买入机制将5笔BUY归到一个批次，sequences明确关联全部5笔SELL；真实成交标量经原sequences/performance函数核对，余仓0、已实现盈亏-427.99。未伪造成交或改变原始缓存。
- 23:52:33（Asia/Shanghai）只读确认原服务已自动重读规则：最后成功时间23:52:26、error=null、error_kind=null；MRNA为5买/5卖、买卖各700股、余仓0。现有规则保留一条灰色当日清仓复盘记录，次日自动移除，不为此次操作新增临时隐藏ticker机制。成功后结束接口验证并删除临时MRNA订单摘录。

本轮只验证人工关联、真实数量对账及服务恢复；未运行全项目测试、前端构建或浏览器交互，也未验证后续新成交。其他模块现有未提交改动保持原样。

## 2026-10-17：Holdings 中性状态 ADR 方向

环境：本机 macOS、当前正式 Monitor 服务 localhost:8765；北京时间02:31–02:34（美东10月16日Regular）。本轮只修复前端ADR格式化，未重启后台、修改阈值、名单或账户，不使用mock，不跑全量测试。

- 直接读取现有接口中的LIFE.US、MU.US、PBF.US及其Daily缓存。三者role均为holding、state为neutral；首次读取Up/Down分别为0.05994/0.54667、0.06982/0.42837、0.30510/0.59742。用真实last/high/low/ADR20独立复算，两项结果均匹配。原因是Down尚低于预警阈值时，旧格式化只检查state前缀，所有neutral都显示Up。
- 新格式化在holding neutral时显示较大的ADR方向，有预警等级时仍显示主状态方向；只影响数值和箭头。`npm run build --prefix ui`通过。构建后函数直接消费当前真实状态，三只均输出Down，另核对当前五个余仓symbol的格式化一致性；证据`/tmp/adr-direction-live-check.json`。
- Chrome正式页面实际显示LIFE、MU、PBF均为↓，tooltip保留Up/Down两项，中性底色保持；TEAM/CDNA已有回撤等级仍显示↓。截图时三者分别约0.48×、0.41×、0.64×，与之前读取的差别来自实时行情更新。截图`/tmp/adr-direction-live-ui.png`；浏览器无JavaScript error，验证页已关闭。原有用户页面需刷新加载新JS。
- 独立需求、behavior与development同步；`git diff --check`通过。本轮未重新验证声音、排序、账户获取或全交易日规则穿越；这些逻辑没有修改。

## 2026-10-17：Intraday State 盘中状态

环境：本机 macOS、Python 3.13、项目虚拟环境、TypeScript；浏览器验证使用 Chrome 的临时模拟页。唯一需求见 [intraday-state.md](intraday-state.md)。本轮只覆盖新增状态、量比、Dynamic 展示及共用声音的改动，未跑全项目回归。

- 后端定向 `tests/test_intraday_state.py tests/test_alert_sound.py tests/test_alerts.py`：41 项通过。覆盖候选 open 门槛、上下行阈值与再次穿越、持仓回撤优先且降级静默、EMA 重穿、冻结 ADR、首次/恢复静默、范围清理、5m 延后降级与量能边界更新、连续大窗口覆盖、历史尾部插值、缺失/半日/DST、配置校验、真实回调接入及手动 Alert 兼容。HTTP 用例仅使用临时库。
- 前端定向 `ui/tests/intraday-state.test.mjs ui/tests/holdings.test.mjs ui/tests/scan.test.mjs`：25 项通过；`npm run build --prefix ui` 通过。验证离散等级与人工 Pin 稳定顺序、不修改输入名单、持仓批次与清仓尾部、格式化及新增列。Markdown 相对目标检查及 `git diff --check` 通过。
- 隔离 UI：既有 FakeLongbridgeClient、临时 workspace/SQLite、真实状态引擎与模拟有效 Quote/SDK candle，localhost:8767，不读凭证。确认候选蓝色、持仓黄/红色、ADR 与两个圆角量比格，Dynamic 跨组排列、Pin 优先、无重复成员及空 section 隐藏；Grouped 恢复原 Surf/Bounce。NVDA 保持选中，状态从浅蓝升级亮蓝后图表与操作焦点保留；同档相对顺序稳定。截图 `/tmp/intraday-state-ui.png` 为模拟数据，量比缺失用 `—`；最终临时页、服务与数据库已清理。浏览器无 JavaScript error。
- 声音直接使用新后台播放器依次播放上行、下行、紧急，每组原声四遍；afplay 均成功，用户确认“都听到，紧急声音能区分”。优先级用定向用例验证，不额外合成或施加时长上限。
- 本轮只读真实 Longbridge 缓存 ABCL.US、EFOR.US：冻结 ADR20 分别 6.3545%、4.9475%，26 分钟历史累计基准各有五个样本，分别 331721.76、12663.56。没有额外供应商查询或写正式数据；证据 `/tmp/intraday-real-cache-check.json`。
- 正式后台按原 Monitor 展示模式重启，PID 20306；`/health` 为 running / CONNECTED，`/v1/intraday-state` 已启用。现场读取 CAI.US 的真实 Regular 状态、CumVol 与 15m LocalVol，两者都有五个历史样本。重启前后原有七条手动 Alert 内容相同，未处理事件均为零；没有向正式进程注入模拟行情。结束前状态已覆盖30个symbol，待处理窗口从118降至6；服务启动仍按原流程初始化行情窗口，本轮不将这些样本表述为全名单Ready。证据 `/tmp/intraday-live-check.json`，日志 `runtime/intraday-state-live.log`。
- 未覆盖：整个 Regular 交易日运行、真实盘中所有规则穿越、物理断网/休眠、全部名单行情初始化、macOS 27、触屏。离线用例和本轮短时现场读取不替代这些证据。

## 2026-10-16：Holdings 轻量错误详情与统一圆圈感叹号

环境：本机macOS、Python3.13、TypeScript及现有正式Monitor服务。仅验证本轮Holdings错误展示与状态契约，真实接口读取限于现有9条持仓、health及原40个Focus/Holdings行情标识，成功核对即结束；不修改账户、名单或人工交易规则，不做真实网络/账户故障注入。

- Holdings在既有刷新边界统一设置request/accounting/storage阶段，保持原脱敏error字段与30秒重试流程；无消息的超时返回明确文字，成功同时清空错误/阶段。4项相关Python用例通过（23项无关用例未执行），覆盖请求/会计/保存失败分类、脱敏、空超时消息、保留旧结果、成功清除及原周期重试。前端8项Holdings用例、`npm run build --prefix ui`及`git diff --check`通过；未执行全项目测试。
- 以本轮真实快照导入正式Holdings组件/样式的临时离线展示页验证错误样本，不伪造当前服务故障。59秒隐藏错误入口，60秒显示；默认不展开，鼠标/Enter可打开，Esc与外部点击关闭，面板内模拟成功刷新后图标/详情自动隐藏，首次无成功数据的失败直接可见。组件持续秒级刷新时已打开详情仍保留。请求与交易校验建议、可选中复制的原始消息均可见，浏览器无error/warn。
- Chart与Holdings图标实际CSS均为16×16px、1px暖黄边框、50%圆角、600字重，颜色与边框一致；复用一份绘制声明，以独立状态class避免Chart全局quality刷新覆盖Holdings。截图`runtime/holdings-warning-preview.png`明确标注离线错误展示样本，测试控件不属于正式界面；验证后删除临时页面及完整快照输入。
- 按原命令重启原正式服务一次以加载后端分类，PID3914；10:41:33（Asia/Shanghai）只读核对：Monitor、Quote CONNECTED、40个行情标识，9条持仓，成功快照10:41:32，loading=false、error=null、error_kind=null。服务保持运行，没有新增端口、轮询、错误历史、通知或自动恢复框架。

未覆盖新的真实失败事件、全部券商错误类型或移动端；后台实际失败不为本次验收制造。UI/数据唯一需求、Logo/Icon和behavior/development契约已同步。没有重验交易盈亏公式、全周期Ready或全量数据下载。

## 2026-10-15：Holdings 停留旧成功时间与 CDNA 手工关联

环境：本机macOS、Python3.13、现有正式Monitor进程PID9504及其localhost:8765接口。仅只读核对health/holdings、现有账户缓存及人工关联文件；没有另起服务、重启进程、额外直连SnapTrade或改动账户。后台任务active、Quote CONNECTED；23:37与23:38两次读取均返回同一CDNA卖出归属歧义，保留的成功时间是2026-10-14 22:11:55（Asia/Shanghai），而非本日刷新时间。

- 当前错误为CDNA卖出订单`9B6556…F26D`未能唯一匹配买入组，整轮获取完成后会计核对失败，不提交最新缓存/显示批次。既有缓存核对该笔为10/14卖出300股@64，对应此前10/13买入300股@65.35；缓存本身仍可按旧成功批次重建。没有把旧缓存解释为失败轮的完整最新原始数据。
- 用户明确确认旧300股买卖关联、10/14新买400股独立保留后，仅在现有`runtime/holdings/sequences.txt`追加该买入→卖出映射。现有服务正常轮询自动重读；23:39:53读取确认成功时间已前进到23:39:52、error=null，CDNA只剩10/14买入400股、余仓400股、均价66.765、无卖出记录，昨日清仓300股批次不再显示。
- 两项现有Holdings定向用例通过，覆盖启动立即刷新、网络/会计失败保留完整快照、下一周期继续以及规则恢复后成功更新。仅补充唯一Holdings文档的现有重试语义；没有修改Python/TypeScript实现，未构建前端或运行全局测试。未做浏览器/真实网络故障验证，不推断旧成功时间至本轮之间的每次失败均相同；本轮服务的stdout/stderr指向原终端，历史service.log并非当前进程日志。

## 2026-10-09：Scan 导航压缩、列头排序与 Under-50 图案

环境：本机 macOS、Python 3.13、TypeScript、正式 localhost:8765 与 Codex 浏览器，1280×720 视口、680px List。使用 2026-10-08 真实 Massive 截面与现有名单。按原参数重启正式服务，PID 63357；实时行情和持仓后台继续运行。本轮只验证布局、排序、选择、日期控件及 Tag 外观。

- TypeScript build、12 项既有 Scan UI 用例与13项偏好定向 Python 用例通过；没有新增模拟行情。`git diff --check`通过，删除的全选、结果数及旧控件行不再有代码或规范引用。
- 导航、日期与 Refresh 的中心均为 y=150.5px；左侧导航、右侧日期/刷新保持同一行。Chart 与 List 顶部水平线均为 y=130px。Scan 的63行增长数据共用同一组子列位置 x=924 / 973.328 / 1022.664px，包含百分比、倍数和缺失值，无行横向溢出。
- RFL1M、RFL3M、RFL6M、Default order 各自四个 section、63行的显示顺序均与真实排名或原始顺序一致。排序控件在 Monitor 中移出列头，回 Scan 复用同一个控件；模式切换及页面刷新后排序有效，列头没有背景或边框，折号为黑色。
- Discover / Focus / Excluded 导航显示30 / 42 / 63个可见成员。逐行勾选 TWST 后 Focus/Hidden 移动按钮启用，取消后禁用，没有执行名单移动。历史2026-10-06的行勾选禁用；Refresh返回已准备完成的2026-10-08。
- 当前 Under-50 外观保存为 `under50`、`#e53935`，波浪位于两个泳镜镜片上方；行内与编辑预览共用同一 SVG，刷新后保留。偏好与本轮预期完全一致，仅这两个外观字段改变，规则与其他偏好保持原值。21份 dated workspace 哈希全部不变。
- 最终为 Scan / Excluded / RFL1M、无 Tag 筛选；截图折叠 Broken/Extended 以展示 Under-50 行。浏览器无 warn/error，Quote CONNECTED、49个去重行情标识、持仓任务运行、Massive Ready，服务 errors 为空。完成限定核验后保留正式服务运行。

未覆盖其他视口、原生移动端、准备未完成时的下载流程及全部图表/Alert功能；未运行全项目回归。

证据：[布局与图案](/tmp/monitor-scan-ui-2026-10-09/layout-checks.json)、[真实排序核对](/tmp/monitor-scan-ui-2026-10-09/sort-checks.json)、[最终状态](/tmp/monitor-scan-ui-2026-10-09/final-report.json)、[真实页面](/tmp/monitor-scan-ui-2026-10-09/final-scan.png)。

## 2026-10-09：完成日机器排除重评与人工 Hidden

环境：本机 macOS、Python 3.13、TypeScript、正式 localhost:8765 与 Codex 浏览器。主验证使用 2026-10-08 的 12,592 行真实 Massive 截面、152 个现有名单成员与当前保存规则；正式服务按原参数重启，PID 61244。验证限定名单分类、相关接口和页面，不创建真实 Alert 或交易，不新增定时任务。

- 92 项定向 Python 用例、12 项 Scan UI 用例及 TypeScript build 通过。覆盖当日立即恢复、非候选退出、Setup 只分组、负面优先级、未知特征保留原机器排除、已知不成立的 AND 条件、Hidden 七自然日边界与到期成员继承、人工负面 Tag 拒绝、手动与 Alert 共用 Focus 入选，以及现有 HTTP/WS 和文件监听。接口与原生监听用例在授权的本机环境运行，不把沙箱内的权限失败当作业务结果。
- 对真实输入做13项定向核对及临时名单副本操作：分类幂等、Focus/未到期 Hidden 不变、仅 Hidden 有屏蔽日期、Discover 全部属于当天候选、负面优先级、未知特征保留，以及机器排除转 Hidden、Hidden 跳过规则、候选提前释放与 Discover 屏蔽/释放。未构造市场特征或运行 Scan Mock/模拟器。
- 正式启动保存结果与本轮真实输入预期完全一致。23只机器排除确认恢复：13只回 Discover，10只不在当天候选池而退出名单。移除的复核分类6只：5只回 Discover（4只有 Setup），1只退出；没有自动入选 Focus。PSKY 的负面特征不足，保留原 Extended，未用缺失值冒充恢复。最终后端 Focus45、Discover32、Excluded64，其中 Broken8、Extended10、Under-5033、Hidden13。
- 真实接口拒绝机器排除手动移回 Discover和人工负面 Tag，均返回400且不写名单。保存原规则再次重评，名单逐字节不变。页面 Monitor 仅有 Focus 与独立 Holdings；人工 Tag 编辑仅显示现有四个 Setup。Scan 只有四个 Excluded section，机器 section 无 Release，Hidden 保留 Release。
- 页面实际将 P 从机器排除转 Hidden，验证 Hidden 不续做负面判断；提前 Release 后立即按当前条件回 Extended。实际点击 Discover 的 CDNA 垃圾桶进入 Hidden，再 Release 回 Discover。测试结束恢复这两只的完整状态与原始排序，所有其他成员不变，最终 workspace 与正式启动结果逐字节一致；原 Tag/排序/名单偏好完全恢复。
- 一次清理4份已有历史派生名单中的旧复核分类与机器屏蔽日期，共涉及9个旧复核成员；各自使用对应交易日真实截面决定机器排除、候选恢复或退出。没有保留长期兼容分支。页面查看2026-10-06时仅显示当前四类 Excluded、名单编辑禁用；查看历史前后全部 workspace 哈希不变。同步删除过期的名单验证记录，当前需求只在唯一入口维护。
- 最终页面为2026-10-08 Scan / Excluded / RFL1M。当前 Holdings 前端屏蔽后可见 Focus42、Discover30、Excluded63，与后端成员独立。截图显示四个 section，浏览器无 error/warn。服务 Quote CONNECTED，49个去重行情标识，Massive Ready，health errors为空，持仓后台运行；保持正式服务运行，接口核验到此结束。

未覆盖等待下一个真实完成日、长时间跨日运行、全部图表周期/Alert声音及移动端；日期边界由本轮定向用例补足。未运行全项目回归。

证据：[真实输入核对](/tmp/monitor-classification-2026-10-09/real-checks.json)、[分类变化](/tmp/monitor-classification-2026-10-09/classification-preview.json)、[接口检查](/tmp/monitor-classification-2026-10-09/http-checks.json)、[最终状态](/tmp/monitor-classification-2026-10-09/final-report.json)、[真实页面](/tmp/monitor-classification-2026-10-09/final-scan.png)。

## 2026-10-09：Holdings NEW、账户总值与清仓日盈亏

环境：本机macOS、Python3.13、TypeScript及正式localhost:8765 Monitor。纽约市场日期为2026-10-08，本机日期为2026-10-09。仅验证当前8条余仓及3条当日清仓记录；沿用现有Focus/Holdings范围，未改账户、名单、人工买卖关联或Alert。按原参数重启正式服务，PID44917，保持Monitor与48个去重行情标识；不执行额外全流程或全项目测试。

- 18项Holdings定向Python用例通过，28项无关用例未执行；`npm run build --prefix ui`及`git diff --check`通过。覆盖清仓日盈亏加入汇总、P/L及百分比分母仅余仓、昨日卖出不混入今天日盈亏、缺清仓基准时不输出部分日总额、纽约日期NEW/次日移除，以及既有四时段日基准与新旧合并批次。
- 本轮真实HTTP核验成功快照16:27:25 UTC，loading=false、error=null、Quote CONNECTED。PLTR为唯一当日新建仓；ABCL、SMMT、CDNA日盈亏分别为-612、-582、-459.24，清仓合计-1,653.24；余仓日盈亏-655.58，Total P/L Day=-2,308.82。P/L Total=8,146.81，P/L %=6.302670…，均与余仓金额/余仓成本核对一致。接口读取不触发账户刷新或增加行情请求，核对成功后结束接口验证。
- 真实浏览器中的Holdings与常规List NEW均复用相同CSS，实际颜色rgb(41,98,255)、字号8px。右上角显示整数账户总值，正常成功账户刷新后时间隐藏；选中PLTR仍复用原Daily/Intraday。保存`runtime/holdings-refinement-live.png`，浏览器无error/warn。报价后续变化属于正常行情，不用截图金额冒充HTTP核验同一时刻。
- 使用本轮真实快照导入正式Holdings组件/样式的临时离线页面，只切换显示时钟与状态：59秒隐藏，60/61秒显示最后成功时间；失败时保留成功时间并显示失败色/悬停原因，成功刷新后隐藏。复用公开tick入口，没有断开真实连接或注入账户/网络故障。验证后删除临时页面与完整展示输入，保留聚合验证记录。

未覆盖真实纽约跨日长期运行、真实WS断线一分钟及新增同日买入又清仓事件；对应日期与缺值规则由本轮定向用例补足。没有重验所有图表周期或全量行情Ready。正式服务继续运行，NEW、清仓汇总与刷新显示要求已同步唯一数据/UI文档及behavior/development入口。

## 2026-10-08：Vol 与五交易日均量比较

环境：macOS、Python 3.13、Longbridge SDK 5.0.0、TypeScript、真实本机服务与 Codex 浏览器；美东 2026-10-07 Regular。行情 API 验收限定 BMNR / MU，历史规则使用现有 Longbridge 和 Massive 缓存，各来源独立核对；未新增或运行 Mock。

- 历史数据 726 项核对通过：BMNR / MU 的 Daily 与五个 Intraday 周期、Scan Daily、PSIG 的零成交量与零均值、窗口起点无参考历史。真实 MU 2025-12-01 的 13:30 2h 样本自动跳过前五交易日中的 Thanksgiving 提前收盘日，使用4个样本；2025-11-03 的 09:30 时段跨 DST 仍匹配5个样本。
- 13:24:43 ET 完成实时验收：56 个 symbol 的336个 closed 窗口 complete，pending=0；BMNR / MU 的六周期 open 和对应历史参考均正确。MU Daily / 1h 连续观察30秒，144次 WS view、408项独立核对通过，分别出现95 / 96组不同成交量及百分比。比例使用完整历史 candle；无额外券商请求。
- 浏览器确认 Monitor MU 的 Daily、1h、15m 与历史悬停分别显示同一 candle 的 Vol / `5D Avg`；Scan 的 PSIG / JAGX 使用本源历史。最终前端的 JAGX 历史悬停在多次 WS 刷新中保持 `Vol 6.87K · 5D Avg 110%`，离开后恢复最后一根。JAGX 最新 Daily 的原始比例549.300034%，实际显示 `Vol 27.07M · 5D Avg 549%`，验证整数截取。未录屏。
- 后端均值索引复用历史 revision，实时仅计算比例；缓存和数据库的官方 OHLCV 未改变。既有 SECZ Daily 重复时间戳诊断继续保留。
- TypeScript build、Python编译、git diff --check通过；既有 UI 用例的显示预期同步新标签。正式服务已重启，保留当前 Scan 展示，Quote / Holdings 后台持续运行。

证据：[历史规则核对](</var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/monitor-volume-history-_3n791tg/report.json>)、[实时验收](</var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/monitor-volume-live-ji10o50l/report.json>)、[真实页面截图](/tmp/monitor-volume-comparison-2026-10-08.png)。

未覆盖：整日持续运行、移动端、真实开盘/收盘切换；半天与 DST 用真实历史验证，不表示本轮经历了对应 live 时段。未运行全量离线回归。需求唯一入口见 [Turnover comparison](chart-ui.md#turnover-comparison)。

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
- Chrome 使用 Scan Mock 副本、临时库和既有 FakeLongbridgeClient，localhost:8767 限时120秒。两张未处理卡片在刷新前后均存在，原通知按钮为0个，页面无 console error。完整截图保存在 `/tmp/alert-cards-refresh-2026-10-07.png`；临时服务、目录与页面已关闭。
- 正常退出旧原生进程，实际删除 `dist/Market Monitor.app`、macos 构建目录、launcher/setup/build脚本及 PyObjC/py2app 和其专用依赖；原 WAV 移入 Alert 模块。正式 runtime 改用现有 Python CLI 启动，/health 为 running、Quote 为 CONNECTED；Alert sound 为 enabled=true、error=null。切换前后正式库均为3条 Alert、2条历史事件、0条未处理事件。Safari Charts 已刷新，恢复 Monitor 与 PLSE 选择。
- Alert 需求、职责/契约、产品行为、UI 总入口、README 与模块 AGENTS 已同步为后台声音和持久卡片。

未覆盖：真实 Regular 行情穿越、Mac 重启/睡眠与 macOS 27 实机运行。当前听辨只证明本机当前音量和输出设备下的两种声音，不把子进程成功退出当作其他设备的听辨证据。

## 2026-10-07：Additional Info 显示精简与位置微调

环境：本机 macOS、TypeScript、现有正式服务与 Chrome，使用本轮已有 Nasdaq 缓存及真实图表。只修改前端显示和维护文档，不重启服务或安排额外供应商请求。

- `npm run build --prefix ui` 和前端28项用例通过。新增分类精简用例覆盖括号说明、冒号后细节、重复首级/大小写/空白和可空分类；可空显示用例同步 Intraday 市值及无美元符号。未重复运行未改动的 Python 数据/调度用例。
- 实际 Monitor 的 AGEN 显示 `Health Care · Biotechnology`，分类与EMA/SMA均为11px；`Market Cap 394.26M`位于 Intraday 周期按钮下方，11px、黑色且不带美元符号。财报与ET时间均为12px、#293341；两个头部实测均120px，指标行及下边界对齐。浏览器已刷新为本轮生成文件，结束保留Monitor、AGEN与1h。
- 完整原分类及美元金额仍保留在独立数据契约中；显示规则、职责入口和唯一图表规范已同步。`git diff --check`通过。

未覆盖：Regular时段真实bid/ask同时出现的布局、全部行业逐个浏览和移动端；没有把本轮前端显示验证作为刷新调度或上游可用性验证。

## 2026-10-07：独立 Additional Info

环境：本机 macOS、Python 3.13.1、正式 Longbridge SDK 5.0.0、TypeScript 5.9.3、Chrome；真实 Nasdaq 请求使用工程既有代理，不读任何券商或 Massive 凭证。新增模块规则只在 [additional-info.md](additional-info.md) 维护。

- 本轮有界公开接口验收：一份 Screener 整表和四个财报日期（2026-10-01、10-04、10-07、2027-02-04）。新模块真实解析出6,628个可匹配`.US`证券，分别取得5、0、4、0条财报事件，全部成功写入临时独立SQLite。验证AAPL/AAOI分类与市值、ACN已发布报告、未来预估事件及空日期；QCML未覆盖字段为null。当前整表的Common Stock/Ordinary Shares/Class A/B/Preferred Stock/Depositary/Voting后缀均通过Python清理，原行保留。
- Python定向102项通过，覆盖名称清理、零/负EPS、日历请求日期、成功替换某日及取消事件、失败保留旧数据、缓存重读、首次/每日/每周窗口与续做、冻结旧历史、缺失/损坏缓存、Mock不联网、启动不等待附加任务、选择身份、独立WS更新不重发bars及原ETF/Scan流程。旧名称用例迁到新模块；同步一个旧Scan测试的失效断言：指定日重建原本只允许CLI，HTTP仍拒绝。补验独立GET/POST、Origin限制及立即安排刷新后，3项集成用例再次通过；临时CLI同日`--companies-only`成功跳过已有公司表，无新请求。
- `npm run build --prefix ui`通过，前端27项通过；包括最近报告优先、七日后转下次、缺事件、纽约跨日/DST、单数/Today、选择身份及缺失显示。Python编译与`git diff --check`通过。没有升级SDK或新增依赖。
- 正常退出旧原生实例后，把本轮成功Nasdaq缓存作为首次缓存并重启正式Market Monitor。独立首次任务完成2026-06-09至2027-02-04共241个日期，成功跳过已缓存4日，errors全部为空；公司表未重复获取。Monitor Quote为CONNECTED、Holdings持续刷新，附加信息下载中实际图表已显示。没有改名单、账户或Alert；页面结束恢复Monitor、AGEN与1h。
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

- 对照本轮用户修订、longbridge/realtime.py、workspace.py、list_rules.py、workbench.py、现有 List/Chart/UI/开发文档，建立独立 alert.md 和 data_service/alerts/AGENTS.md，并同步总入口及局部维护约束。新需求和新入选规则均明确标为已确认待实现。
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
- 使用 Scan Mock 副本、临时 SQLite 与既有 FakeLongbridgeClient，localhost:8767 最长300秒。PAYS 验证细线段虚线、箭头紧贴价格轴边缘、无 Alert 价格轴标签；悬停价格胶囊包含两位小数与线性垃圾桶，拖动11.40→11.74重新激活，垃圾桶立即删除。Monitor 验证 Command+Option 创建66.45、双图共用横线、悬停胶囊与 Backspace 删除。未修改正式 Alert/名单，也未投递系统通知；临时服务、目录与浏览器页已清理。
- Monitor 实际绘制确认 Daily→Intraday 两侧十字线显示67.33，独立于对应 candle close；超出 peer 价格范围时不吸附到可见 candle。所有图使用内置1px LargeDashed及匹配的Alert primitive线段；两张图的Vol显示正确。
- 正式 Safari Charts 窗口已刷新加载构建，恢复刷新前 BAND 选择，确认 Daily/Intraday 均显示 Vol。没有重启或扩大真实行情订阅。
- 需求分别同步 alert.md（悬停/删除）、chart-ui.md（共用虚线/十字线/Vol）、ui.md（图形），职责与入口同步 development.md、behavior.md。相对链接/锚点及git diff --check通过；vendor未修改。
- 本轮未重新覆盖真实 Regular 触发、macOS 通知、全部六周期/价格轴缩放/pane resize，以及 macOS 27；这些不作为本轮浏览器验收结论。

## 2026-10-06 Alert 定位与横纵独立联动

环境：本机 macOS、Chrome 离线验证页和正式 Safari Charts；Lightweight Charts 5.2.0、TypeScript 5.9.3。本轮只修改 UI 与相应文档。

- `npm run build --prefix ui` 通过，23 项 UI 用例通过。新增定向用例覆盖无对应日期时水平线保留与复用、重新匹配日期时切回原生十字线、价格超出范围时仍传递时间、成交量 pane、离开与清空后的移除；程序更新不回传覆盖鼠标值的既有用例继续通过。
- 浏览器使用 Scan Mock 副本、临时 SQLite 与现有 FakeLongbridgeClient，localhost:8767 限时300秒，不读取凭证或投递系统通知。Scan 验证胶囊位于绘图区约2/3处、无重复上下箭头、右箭头左侧竖边对齐原生价格标签左缘并进入价格轴。
- Monitor 实际验证：Daily 悬停旧日期（Intraday 无该日数据），两图仍显示67.33水平线，Intraday不显示虚构时间线；同一Alert在两图可见。Intraday拖动66.46→66.68，Daily同步；Daily继续拖动66.68→67.12，Intraday同步，悬停胶囊显示相同已保存价格。另用同样临时环境限时60秒保存完整截图 `/tmp/alert-ui-final.png`，显示旧日期的Daily胶囊与Intraday独立水平线。
- 正式 Charts 窗口已刷新加载构建并恢复刷新前BTGO选择；未重启真实服务或修改正式Alert。临时页已关闭，验证服务按时结束并清除临时库。
- 需求和职责同步 alert.md、chart-ui.md、ui.md、development.md、behavior.md；相对链接/锚点及 `git diff --check` 通过。未修改 vendor。未重新覆盖真实Regular触发、macOS通知、全部周期/价格轴缩放/pane resize或macOS27；离线UI证据不替代这些验收。

## 2026-10-27 — Schwab 交易后端接入

环境：本机 macOS、Python 3.13.1。原交易网关 143 项测试通过，相关后端回归共 266 项通过，覆盖 Trade 投影/路由、SnapTrade、Scan/Monitor/Trade 身份、Alert、Intraday State 和模拟器。测试使用假凭证、MockTransport 与临时库，没有真实金融写入。

当日只读确认真实授权、REST/Streaming 正常；当前原生持仓市值、持仓盈亏及日盈亏有值，实际 limits 为 45000 / 2000 / 0.15。Sold Today 的订单树去重、余仓与当天卖出同 symbol 场景由定向用例覆盖。未执行实盘交易、新单成交/拒绝、Replace/Cancel、部分成交、跨日与睡眠恢复验证；该记录不替代后续 live 验收。

## 2026-10-29 — Schwab 明细参考盈亏与交易区间距

环境：本机现有正式 localhost:8765、真实 Regular 账户和行情；未改后端、未重启服务、未发送真实下单/改单/撤单。

- `npm run build --prefix ui`、Schwab原生数据与测宽共7项定向用例、`git diff --check`通过。覆盖Buy沿用券商原值、各Stop独立数量/价格、Sold使用当前券商均价而非历史订单价格、缺成本/完全清仓留空，以及自然测宽不读取已分配宽度；未扩大到全量回归。
- 真实页面数量模块top=82px、预估模块top=122px、按钮top=162px，前两者分别上移4/2px，行距4→6px。撤单SVG描边3px，保持对称路径与居中布局。
- TEAM真实Buy明细+13.4% / +1,564与主行一致；Stop数量60、价格210.91、券商平均成本194.10，显示+8.7% / +1,009，符合本条订单价差估算。两条明细的P/L%和P/L列边界与主行偏差均为0；数量、价格、撤单移至其后。真实HTFL已清仓Sold缺当前均价，两项盈亏留空。Sold有均价的估算路径由定向用例覆盖，未伪造真实成本。
- List宽度680px，console无error/warn。未操作金融写入或拖动图线；未做盘外可见列布局和真实故障验收。最终截图：`/Users/cyno/.codex/visualizations/2026/10/26/01a17832-a589-7120-8e1f-ffe5c161d0de/trade-detail-pnl.png`。已退出验证草稿。

## 2026-10-29 — Trade 顶栏归位、数量与持仓默认列对齐

环境：现有 macOS localhost:8765 正式服务、真实 Regular 行情与账户显示。仅调整前端，不重启服务、不调用金融写接口。

- `npm run build --prefix ui`、持仓自然测宽单项用例与 `git diff --check` 通过，没有扩大为全量回归。Monitor/Scan/Trade 三种模式均核对 List 右上时间模块，其垂直中心与模式按钮完全一致；最终恢复 Trade。
- Intraday归位按钮回到原右上角，报价右端836px、按钮左端844px，间隔8px；三位数报价不会撑宽数量轴。Ask/Bid字号25px、百分比13px，绝对差值保持Bid右侧灰色基线对齐。数量只显示数字，左端与标尺同为598.40625px，位于横线上方；仍保留原行高。Buy上区21px、下区14px，比例60:40。Send按钮与外层均为52.875×30px，外层padding和按钮border均为0。
- 真实TEAM展开行中，金额/数量/价格的右边界分别与主行Net Liq/P/L%/P/L完全一致，撤单所在单元格与Chg%列边界完全一致。白色交叉线改为对称SVG，路径中心相对红色圆形按钮中心的x/y偏差均为0。Entry额外字段保留于后续可见列，没有修改任何原生金额或撤单目标。
- 持仓展开与后续真实刷新下，List保持680px、表格保持664px。Console无error/warn；未点击Send或撤单，未拖动图线。已清理验证草稿；没有验证真实交易、撤单及故障反馈。最终截图：`/Users/cyno/.codex/visualizations/2026/10/26/01a17832-a589-7120-8e1f-ffe5c161d0de/trade-columns-final.png`。

## 2026-10-29 — Trade 顶栏报价与 Buy 四分区微调

环境：本机现有 localhost:8765 正式页面与真实 Regular 报价；本轮只调整 CSS/静态标签，执行构建及局部浏览器核对，不重跑全量用例、不重启服务。

- `npm run build --prefix ui` 与 `git diff --check` 通过。Ask/Bid 和左上价格均为28px，矩形顶部19.5px、行高34px完全一致；中间双行价差为26px高，垂直居中。Qty/预览/按钮的顶部仍分别为86/124/162px。TEAM真实三位数报价220.18/219.68在固定区域完整显示，时钟/归位位于同一顶栏的报价左侧，没有重叠。
- Buy/Sell标题14px加粗，stop/market小写11px正常字重，文字距中界线两侧各6px。分别激活两种买入方式后，另一方式下方区域保留原浅灰，两个全高度点击目标仍生效。
- Auto原SVG容器中心与按钮一致，路径边界中心约偏左0.214px、偏下0.381px；向右上各补偿0.5px后，路径中心相对按钮约为右0.286px、上0.119px。仅作视觉补偿，没有改变图标尺寸或按钮位置。
- Console无error/warn。只切选既有symbol及草稿方式，没有点击Send/撤单，也没有拖动图上横线；不验证真实交易或新故障路径。截图：`/Users/cyno/.codex/visualizations/2026/10/26/01a17832-a589-7120-8e1f-ffe5c161d0de/trade-card-top-aligned.png`。

## 2026-10-29 — Trade 报价与标尺视觉精简

环境：本机现有正式 localhost:8765 页面、真实 Regular 报价；本轮仅改前端外观和刻度节点，不重启服务，不发送真实交易请求。

- `npm run build --prefix ui`、`git diff --check` 通过；未扩大测试范围。页面核对黑蓝 Ask / 黑红 Bid、灰色差值与原百分比颜色；数量标签保持不变，所有小刻度节点已移除，恢复清晰细黑直线。
- Buy 区域选中背景整体变深，当前方式白字、另一方式灰字，Stop/Market 切换正常；Buy/Sell 字重700，Stop/Market仍400。轨道左端598.40625px；胶囊曲线顶点580.90625px，加半径17.5px后的直线起点与轨道相同，Send右端仍870px。
- 真实按住数量滑柄期间，range :active=true，body与range计算出的cursor均为none；释放后恢复default，数量可正常调整。只操作卡片按钮和数量轴，未拖动图上横线、未操作提醒或金融写入；console无error/warn。截图：`/Users/cyno/.codex/visualizations/2026/10/26/01a17832-a589-7120-8e1f-ffe5c161d0de/trade-card-refinement.png`。

## 2026-10-29 — Trade 卡片对齐、点击区域与短暂反馈

环境：本机 macOS、项目 Node/TypeScript 与 Python 3.13，现有正式 localhost:8765 服务及真实 Regular 报价。只核对本轮卡片、草稿交互和反馈，不扩大为后端全量回归。

- `npm run build --prefix ui`、Trade 定向 16 项前端用例与 `git diff --check` 通过。新增覆盖数量两端/不重叠刻度、Sell 末端真实数量、风险金额整数、已知离线不发送、连接中断结果未知、Accepted 两秒后消失且不被账户快照刷新延长、后续错误不被旧计时器清除。写请求全部使用内存 fetch 替身，没有真实下单、改单或撤单。
- 真实页面核对：轨道宽 271.59375px，左端 598.40625px、右端 870px；Ask、总额、Buy/Sell 左端均相同，Send 胶囊右端与轨道相同。浏览/激活四行矩形完全一致；Ask/spread/Bid 两侧间隔均 8px，22px 的价差双行位于 26px 报价高度内。刻度从 0 至实际 maximum，自适应显示不重叠数字。Buy Stop 和 Buy Market 的上半部均可直接点击。卡片内 title 数量为零，console 无 error/warn。
- 浏览器拖价核对误命中了相邻 SKYA Alert；随后依据本机 SQLite WAL 中的原记录，完整恢复为 2.97、triggered、generation=2 及原 updated_at/expires_at。服务按原命令重启，GET /health 与 GET /v1/alerts 已核对恢复后的真实状态。未改 Alert 实现；未继续在真实提醒相邻处拖价，双图/Auto 的规则由上述定向用例验证。
- 最终效果截图：`/Users/cyno/.codex/visualizations/2026/10/26/01a17832-a589-7120-8e1f-ffe5c161d0de/trade-card-polish.png`。Accepted 与故障反馈通过替身和可控时钟验证，未用真实交易验证。

## 2026-10-28 — Trade 原生数据与前端统一收拢

环境：本机 macOS、TypeScript 5.9.3、Lightweight Charts 5.2.0、127.0.0.1:8765 现有正式服务与 in-app browser；当前 Regular，真实 Schwab / Longbridge 连接。不重启后台，不改网关或账户 API。

- `npm run build --prefix ui` 与 `git diff --check` 通过；定向运行 Trade、Schwab 原生数据、共用持仓几何、Monitor Holdings、Chart 共 31 项前端用例通过。覆盖父子单去重及只取消 Entry 母单、多组风险分别配对、唯一原生均价 Buy、缺成本跳过、多笔 Sold/Stop、Entry/Trim 与清仓无标记、市价缺价格留空、价差严格阈值、固定占位、交易写入不重发及双图拖价。请求全部使用内存 fetch 替身，未发真实金融写请求。
- 新增测宽回归：连续 80 次改变已分配宽度不改变内容最小宽度；禁止读取原表 scrollWidth，价格背景排除出自然宽度副本，几何扣除首 td 的 1px 边框。Monitor 与 Schwab 共同调用该纯 DOM 工具，各自原生数据、会计、刷新和渲染保持独立。
- 本轮真实页面 15:22:23 至 15:27:55 UTC（上海 23:22 至 23:27）连续刷新：Trade List 均为 680px、table/scrollWidth 均为 664px，无逐步扩宽。模式切换后 Monitor List 同为 680px、仅显示 SnapTrade；Scan 隐藏 Intraday/Trade/Schwab，恢复 Trade 仍为 680px。
- 两个只读快照入口与前端原生整理核对：auth=valid、REST/Streaming=connected，8个 symbol，1个 Entry、7个余仓 Buy 汇总、7个独立 Stop；Buy 数量/平均成本与 position 完全相同，Entry 取消目标均为母单。数据仅在内存传递，不保存账户/订单快照，不打印凭证或内部订单 ID。
- 真实 ODD 展开只显示一条 Entry 及一个圆形 ×；HTFL 展开为汇总 Buy 与 Stop，各字段单行，Stop 独立一个 ×。未点击任何 × 或 Send；最终 console 无 error/warn。截图：`/Users/cyno/.codex/visualizations/2026/10/26/01a17832-a589-7120-8e1f-ffe5c161d0de/trade-mvp-final.png`。
- 清除被替代的测宽函数、跨列多行订单文字、SOLD/+ENTRY/ORDER 标记及文字 Cancel 样式；原独立前端源码和前端设计/开发文档移出维护源码，导入原文件保留在忽略的本机备份目录。原网关设计与协议测试保留；当前唯一规范同步 Trade、UI、Chart UI、Holdings UI、行为及开发职责。
- 未覆盖：真实新单/改单/撤单、真实成交、全部周期/移动触屏、跨日及非 Regular 长时运行。当前真实快照没有 Sold/Trim 或多 Stop 同 symbol，相关展示使用定向数据用例验证；没有将历史验证作为本轮 live 证据。

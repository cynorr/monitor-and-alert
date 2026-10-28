# Alert 需求

更新：2026-10-26。提醒方式为后台独立播放声音与仅在所属Regular有效的symbol持久未读提醒。具体覆盖和未覆盖见 [validation.md](validation.md)，macOS 27 仍需实机验收。

本文件是 Alert 功能范围、触发、生命周期、图表操作、声音和验收的唯一需求入口。开发遵循 [development-principles.md](development-principles.md)，模块维护入口为 [data_service/alerts/AGENTS.md](../data_service/alerts/AGENTS.md)，职责与接口方案见 [development.md 的 Alert 章节](development.md#alert-实现)。移入 Focus 的完整规则只在 [List / 统一移入 Focus](list-design.md#统一移入-focus) 维护；图形与颜色的具体定义只在 [Logo / Icon](ui.md#alert-图形) 维护。

实时symbol状态、自动规则提醒、量比与In Play是独立的 [Intraday State](intraday-state.md)。手动线的一次触发/灰线生命周期独立；全部报警共用本文件的symbol未读交互与后台声音。

## 目标与范围

- 这是手动价格提醒的工程功能，不包含交易策略、Price Alert 之外的提醒类型、下单或自动交易。
- Alert Engine 独立于浏览器和图表，运行在现有 Python 后台进程中。Safari、Chrome 或其网页在后台或关闭时不停止检测和声音；Scan/Monitor 切换不停止检测。后台服务必须持续运行。
- 仅消费现有行情链路的有效 Regular last price。盘前、盘后、夜盘均不检测、不触发，也不更新 Alert 的比较起点。其余业务继续使用已有行情时段要求。
- 支持 macOS 26、macOS 27；这一版不适配其他操作系统版本，不建设 Android/iOS 原生客户端。
- UI 无价格输入框，创建、选择、删除与改价都直接在图表完成，不弹二次确认。
- 本版只保留后续程序添加 Alert 的函数接口；不接 Atomic feature 自动设置，不添加算子，不为该未来自动调用功能安排测试。

## 身份、价格与图表模式

- 每条 Alert 有独立 `alert_id`，按规范化的 `symbol`（例如 `AAPL.US`）归属和查询。同一 symbol 可以有多个 Alert，包括相同价格；symbol 不是唯一行主键。
- 不以 Scan/Monitor/Trade、图表来源、日期、周期或 Holdings 批次区分 Alert。模式或周期切换不创建副本，Daily 与 Intraday 共用同一组 Alert。
- Scan、Monitor 与 Trade 都允许设置、显示、选中、拖动和删除 Alert。Scan 使用 Daily，Monitor/Trade 使用 Daily/Intraday。Trade 横线的拖动独立处理，不触发 Alert 拖动；Command+Option 创建 Alert 保留优先权；Backspace 不撤交易订单。
- Sold Today 不参与自动余仓风险报警，但不禁用已保存的手动价格线；手动线继续按 symbol 共用。同 symbol 同时持有和当天卖出，不复制检测、声音或未读。
- 创建价格就是按下鼠标左键时，鼠标纵坐标所对应水平线的价格；通过当前图表公开坐标 API 转换，不取 candle close、最高价、最低价或后台最新价，也不吸附 candle。
- 后端把设置价格用 Decimal `ROUND_HALF_UP` 归一到两位小数，持久化为整数 cents；显示始终两位小数。价格必须有限且归一后大于零。
- 直接保存点击得到的价格，不比较、不转换、不校正 Scan 与 Monitor 两种数据的价格口径。跨模式仍显示同一个数值。
- 创建与改价可以在 Regular 之外进行；先持久化，等可用的 Regular 报价建立比较起点。
- 历史 Scan 图表上的 Alert 操作也作用于当前有效 workspace 与当前 Alert 集合，不改写历史 workspace。历史名单本身的只读限制保留。

## 创建时的名单处理

- 当前 Focus 或 Holdings（含当天清仓保留的 symbols）上创建 Alert，无需新增名单归属。Monitor 的 Holdings-only 选择保持独立，不强制加入 Focus。
- 在 Scan 的 Discover 或任一 Excluded section（包括 Hidden、Extended、Broken、Under-50）图表上创建 Alert，立即将该 symbol 移入当前 Focus，然后保存 Alert；即使它同时属于 Holdings，这次 Scan 操作也执行入选 Focus。
- 入选不弹确认、不等待下一次扫描，不依靠触发报警才移动。创建完成仍保持 Scan 展示及当前 symbol 选择，新归属及时同步。
- Alert 入选与手动 Add/Move to Focus 共用 [统一移入 Focus](list-design.md#统一移入-focus) 的清理、重新匹配与 section 首位插入规则，Alert 不维护另一套 Tag 分类算法。
- 已经属于 Focus 的 symbol 再创建 Alert，不清空其 Tag、人工 section 或现有排序。
- 后端校验价格和操作对象后再执行入选；Focus 保存失败不创建 Alert。Focus 已成功保存而 Alert 保存失败时，明确提示 `Added to Focus; alert was not saved`，不显示成功横线，不建立跨 JSON/SQLite 的通用事务或回滚框架。

## 有效范围

允许集合为当前有效 workspace 的 Focus ∪ 当前已接受 Holdings ∪ 当天保留的清仓 Holdings symbols。日期采用现有纽约日期和交易日规则，不由正在查看的 Scan 日期决定。

- 包含临时新加的 Focus；同 symbol 多个持仓批次只决定一次允许归属。
- 只有同时离开 Focus 和 Holdings 才删除它的全部 Alert 及横线。仅删除 Focus，但 Holdings 仍包含该 symbol 时继续有效。
- 当天清仓仍被 Holdings 保留时继续有效；次日不再保留且不在 Focus 时撤下 Alert。具体 Holdings 范围仍以 [holdings-data.md](holdings-data.md) 为准，不维护第二份持仓规则。
- Filter、搜索、排序、折叠、选图与展示模式不改变允许范围；Discover/Excluded 的创建操作必须先完成入选 Focus，不能直接给它们订阅行情。
- 启动重读 workspace，并按当前日期取得有效 Holdings 范围。首次 Holdings 尚未确认时，holdings-only Alert 等待范围确认；请求失败不能被解释为持仓已空，沿用上次已接受范围。
- 出范围立即停止后续触发并持久化删除，不等 UI 连接；重新加入不会恢复已删除 Alert。
- 未读提示按symbol持久化，离开已确认的Focus/Holdings联合范围时清理；归属从Focus转入Holdings不清理。到期删除相应价格线，symbol仍在范围时未读提示保留到主动查看。

## 触发语义

设阈值为 `P`，连续收到的有效 Regular 价格为 `previous`、`current`：

| 方向 | 条件 |
| --- | --- |
| 上穿 | `previous < P <= current` |
| 下穿 | `previous > P >= current` |

- 到达阈值算触发；跳价跨过阈值也触发。默认双向检测，第一次任一方向触发后停止。
- 行情保持原始精度参与比较，不先将 last price 四舍五入。两位小数用于 Alert 阈值和显示。
- 创建/重新设置时，若有本交易日可用的 Regular 最新价，取它作为起点，不因创建动作立即触发；否则等待第一份有效价建立起点。
- 起点恰等于阈值时不立即报警；之后离开再到达或穿过阈值时可触发。
- 使用现有交易日历判定当前 Regular 窗口及报价所属窗口，包含 DST、提前收盘。Regular 之外到达的旧 Regular 报价不触发；不能用昨日收盘快照在今日开市时报警。
- 每个新 Regular 交易日的第一份有效价重新建立起点，不与上一交易日或扩展时段价格比较。
- 应用重启、Mac 重启、已知断线重连与休眠恢复后，第一份有效 Regular 价仅建立起点。没有补报机制，不与停机前价格比较，不查询历史 K 线、历史高低点或图表数据推断遗漏穿越。
- 正常运行中的有效 Regular push 和现有周期 snapshot 共用检测入口。snapshot 只消费归一后的最终 Regular 最新值，不逐个回放快照字段；重复或倒序数据不构造新穿越。
- 现有时间戳精度为秒，同秒不同价格的有效 push 按接收顺序处理；同时间戳旧 snapshot 不能覆盖已接受的更新 push。不新增行情回放或通用事件框架。

## 生命周期与持久化

| 状态/操作 | 结果 |
| --- | --- |
| 创建成功 | Active，黑色横线 |
| Active 首次穿越 | Triggered，立即变灰，覆盖该symbol的最新未读提示 |
| Triggered 继续收到行情 | 不再次触发 |
| 成功拖动/重新设置 | 新 generation，Active，黑色横线 |
| 选图或更新当前图表 | 只标记该symbol已读，灰线保持，不区分操作来源或等待加载 |
| Monitor Backspace 删除 | 删除选中 Alert 及横线；Scan 只用横线垃圾桶 |
| 到期或出范围 | 删除 Alert 及横线，停止后续触发 |
| 服务/Mac 重启 | 恢复尚未到期且仍在范围中的原状态 |

- 默认有效期为创建或成功重新设置后 `7 × 24` 小时；重启不延长。灰线也遵守该期限；symbol未读提示不因价格线到期自动清除。没有点击后倒计时或自动删除。
- 在独立 `runtime/alerts/alerts.sqlite3` 中保存 Alert 与最新未读提示，不使用可重建的 Longbridge/Massive 行情库，不把 Alert 写进每日 workspace。
- 创建、修改、删除、触发与已读都立即提交 SQLite。成功响应前持久化完成；写失败显示错误，不假装已保存或已触发。
- Triggered状态与symbol未读提示在同一事务提交，成功后才播放声音和发送WebSocket更新。每份报价只检查该symbol的Active Alert，不逐份报价写库。
- 同symbol允许多条独立价格线；未读记录只有一条，保存symbol、方向、等级及触发时间，新提醒直接覆盖旧值，不保存历史或逐版本确认。
- 重新设置增加generation，沿用改价请求的身份校验；已读只清理未读记录，不改变任何价格线或generation。
- 页面刷新、重连、后台重启恢复原期限内的灰线与所属Regular仍有效的未读提示；恢复选图仍按统一已读规则清除对应symbol，不重播声音。播放命令成功不等于用户实际听到，听辨证据另记。

## 图表交互

- 创建：按住 `Command + Option (Alt)`，左键按压主价格绘图区，直接创建；不弹确认，不新增价格输入框。图表标题、成交量区域、时间轴与价格轴不创建 Alert。
- Alert 显示为细水平线段虚线和紧贴右侧价格刻度边缘的向右箭头，视觉对照 TradingView macOS 客户端；触发后改为灰色。不在右侧价格轴显示 Alert 方块、数字或 tick；虚线样式统一遵循 [Chart UI](chart-ui.md#colors-margins-and-reference-lines)，图形定义见 [Alert 图形](ui.md#alert-图形)。
- 平时只显示虚线与右箭头。鼠标悬停横线时，在绘图区宽度约 2/3 处显示两位小数价格胶囊，以鼠标上下调整光标提示拖动，不另画重复的上下箭头；离开横线/胶囊即隐藏，单纯选中不常驻显示价格。胶囊右端的垃圾桶左键立即删除该条 Alert，无二次确认，不启动拖动或交易日联动。拖动期间胶囊跟随线条并显示当前预览价格。
- 普通点击横线选中；Monitor 选中后 Backspace 立即删除，无二次确认；Scan 停用 Alert 的键盘删除，保留横线垃圾桶，Delete/Backspace 用于 [List 单只操作](list-interactions.md)。macOS 键帽上的 Delete 退格键按浏览器 `Backspace` 处理。
- 点击空白或 Esc 取消选中；输入框、搜索和可编辑内容获得焦点时，Backspace 保持原来的文本编辑含义。
- 上下拖动时跟随鼠标预览两位小数价格，松手才提交一次。成功提交恢复 Active 并重新计算期限；明确拖动后提交相同的归一价格也可以重新激活灰线，普通点击不重设。
- 拖动取消或提交失败恢复服务端已保存状态，并显示简短错误；不把未保存的预览当成 Active。
- 创建、选中和拖动 Alert 的手势不同时触发交易日联动或图表平移；其余图表手势继续使用原生行为。
- Daily 与 Intraday 同时显示同一 symbol 的 Alert，各自只按价格是否位于可见主图范围判断，不依赖悬停日期或另一张图的时间/价格范围；超出本图价格范围时不强制缩放。任一图都能选中、拖动和删除，拖动预览与提交价格同步到两图。缩放、价格轴缩放、pane resize 和周期切换后仍对准对应价格。重叠 Alert 必须可以逐条选中和删除。
- 使用 Lightweight Charts 的内置参数和公开 primitive/坐标/命中检测 API；保持 vendor 文件原样，不使用私有接口或内部 DOM。

## 统一未读提醒

- 手动价格、ADR与EMA等全部报警使用同一symbol未读入口，不产生弹出卡片或通知历史。每个symbol只保留最后一条方向、等级及触发时间；直接覆盖，不叠加、不保存通知历史或做逐版本确认。
- 名单行/持仓主行触发后立即进入白色中心、边缘波浪的未读状态；对应声音每声触发一次短脉冲，声音结束或失败后继续波浪等待。多只symbol可以同时显示；外观只在[Symbol模板](ui.md#symbol-row-template)维护，独立于整行选中和图表价格线。
- chart选择或展示哪个symbol，就标记哪个symbol已读。鼠标、键盘、自动候补、页面恢复、切周期及当前图表更新使用同一入口；不判断主动/自动、停留时间、加载成功或是否实际渲染，不等待图表响应才处理选图已读。正在看的symbol再次报警，后续图表更新也会清除其未读。已读只清除该symbol未读，不做事件ID或版本确认，不修改灰线。
- 多持仓批次共享symbol未读状态；Focus转入Holdings后提示跟随。未读与播放提示仅作用于symbol row，不作用于任何section或Holdings标题；折叠后不在标题汇总提示，展开本身不标记已读。
- 未读状态立即持久化，仅在触发所属的Regular内有效，达到实际收盘时间即失效，包含提前收盘；不跨夜、周末或休市日保留。睡眠跨过收盘则唤醒后清理，后台关闭则下次启动清理；首次输出状态前清除已失效记录。同一Regular内刷新、重连、后台/Mac重启恢复未读，选中的symbol仍按上述统一已读规则处理。播放状态仅存在于内存，不补报或补播。
- 清理独立使用后台时钟、现有纽约交易日历与fired_at；复用Alert维护和状态输出入口，不绑定Massive、Refresh、workspace日期或Holdings准备完成，不新增定时服务、数据表或期限字段。收盘清理不改变手动价格线、generation、原七天期限或触发状态。
- Command+G与Command+U的范围、顺序及折叠/筛选行为只在 [List未读导航](list-interactions.md#未读-alert-导航) 维护。
- 灰线触发后立即保留，拖动成功重新激活为黑线；普通row点击、声音结束或未读处理均不自动删除价格线。有效期、出范围与主动删除仍按原规则执行。
- 图形与配色只在 [Logo / Icon](ui.md#alert-图形) 维护；错误提示沿用现有简短错误入口。

## 后台声音与运行

- 不使用 macOS 系统通知，不构建原生通知应用。正式入口为现有 Python 后台服务，Safari/Chrome网页显示价格线、未读提醒并处理已读。
- 后台直接播放本地上行、下行、紧急三份短音频，不依赖网页音频、浏览器后台定时器、通知权限或 Focus 的通知允许名单。
- 每次新报警保存后独立播放两段短声：普通上行每段2声、普通下行每段3声、两种方向的紧急报警每段4声。每声140ms、起点相隔280ms，段间650ms；完整节奏预先写入本地WAV，运行时一次afplay播放。上行为合成短嘟声，下行与紧急来源和许可见[声音资源](../data_service/alerts/sounds/SOURCES.md)。不同报警可同时播放；不使用声音队列、优先级、抢占或同symbol替换播放逻辑。播放不阻塞行情和已读处理。
- 播放失败保留Triggered状态与symbol未读提示，并通过现有错误提示及日志报告。该事件不自动重试播放；之后新事件仍尝试播放，成功后清除声音错误。
- 标记已读不播放或中断声音；已读后剩余播放不恢复该次未读提示。刷新、重连、后台重启与恢复未读均不重播。
- Mock/模拟器默认静音；只有明确的声音验收使用临时库和模拟报价启用实际播放，不读取凭证、不连接真实行情。
- 使用 README 的 Python 命令启动后台。关闭网页不停止服务；退出后台才停止检测。退出时停止所有正在播放的声音。
- 声音使用当前系统音量与输出设备。系统静音、输出接到其他设备时可能听不到；不修改用户音量或设备设置。
- Mac 真正休眠、关机或后台退出时无实时检测；恢复后仍按首价建立起点，无补报。macOS 26/27 均需实机听辨，不能用播放命令返回成功代替。

## 实施与必要验收

1. 验证后台独立播放三种声音，不依赖页面或通知；使用临时库模拟触发，并进行实际听辨。
2. 完成后端 Engine、SQLite、Regular 最新价入口、范围与生命周期。统一手动/Alert 移入 Focus 的公共流程，不另建分类策略。
3. 完成同源 mutation 与独立 Alert WebSocket 快照，再接图表手势和持久未读提醒。函数接口复用该核心能力，为后续调用留入口。
4. 只执行有关的定向验证与有界真实数据验证，记录日期、环境、覆盖和未覆盖范围。

必要验收包括：

- Regular 两方向、到达、跳价、同秒不同价格、重复/旧 snapshot；扩展时段不触发、不更新起点，新 Regular 日和重启/恢复首价不补报。
- 鼠标水平线价格、两位小数、同 symbol 多 Alert、Scan/Monitor 共用、不同周期同步、选择/退格/拖动与原生图表手势。
- Discover/全部 Excluded 创建立即入 Focus；丢弃旧自动/人工 Tag 与人工 section，按当前 Focus 规则重新分类；无匹配入 Unclassified，新入组首位；手动移入得到相同结果。
- 持久化、Triggered 不重复、拖动重新激活、已读不修改价格线/generation、到期及 Focus/Holdings 联合范围、当天清仓保留和次日移除。
- 未读提醒、所有选图/图表更新统一已读、Regular收盘/提前收盘失效、睡眠/重启恢复、灰线期限独立；浏览器后台或退出时仍有声音；声音只随新触发播放、失败提示和退出清理，以及两版 macOS 的实际听辨。
- TypeScript 变更后执行 `npm run build --prefix ui`；Python 只跑涉及本次行为的定向用例。真实行情限定当前允许范围中的少量 symbols 并规定结束条件，不建立故障注入、回放或压力测试框架。

后续 Atomic feature 自动设置、真实订单与自动交易均不在本版范围。实现验证与未覆盖范围只在 validation.md 记录，不把离线用例或平台兼容目标当作 Regular live 穿越或 macOS 27 的证据。

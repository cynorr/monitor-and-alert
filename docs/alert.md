# Alert 需求

更新：2026-10-06。状态：功能已实现；macOS 26.7 已构建和验证通知授权、投递及部分实际交互，macOS 27 仍需实机验收。具体覆盖和未覆盖见 [validation.md](validation.md)。

本文件是 Alert 功能范围、触发、生命周期、图表操作、通知和验收的唯一需求入口。开发遵循 [development-principles.md](development-principles.md)，模块维护入口为 [data_service/alerts/AGENTS.md](../data_service/alerts/AGENTS.md)，职责与接口方案见 [development.md 的 Alert 章节](development.md#alert-实现)。移入 Focus 的完整规则只在 [List / 统一移入 Focus](list-design.md#统一移入-focus) 维护；图形与颜色的具体定义只在 [Logo / Icon](ui.md#alert-图形) 维护。

## 目标与范围

- 这是手动价格提醒的工程功能，不包含交易策略、Price Alert 之外的提醒类型、下单或自动交易。
- Alert Engine 独立于浏览器和图表，运行在现有 Python 后台进程中。关闭或后台运行 Chrome 不停止检测、声音与 macOS 通知；Scan/Monitor 切换不停止检测。
- 仅消费现有行情链路的有效 Regular last price。盘前、盘后、夜盘均不检测、不触发，也不更新 Alert 的比较起点。其余业务继续使用已有行情时段要求。
- 支持 macOS 26、macOS 27；这一版不适配其他操作系统版本，不建设 Android/iOS 原生客户端。
- UI 无价格输入框，创建、选择、删除与改价都直接在图表完成，不弹二次确认。
- 本版只保留后续程序添加 Alert 的函数接口；不接 Atomic feature 自动设置，不添加算子，不为该未来自动调用功能安排测试。

## 身份、价格与图表模式

- 每条 Alert 有独立 `alert_id`，按规范化的 `symbol`（例如 `AAPL.US`）归属和查询。同一 symbol 可以有多个 Alert，包括相同价格；symbol 不是唯一行主键。
- 不以 Scan/Monitor、图表来源、日期、周期或 Holdings 批次区分 Alert。模式或周期切换不创建副本，Daily 与 Intraday 共用同一组 Alert。
- Scan 与 Monitor 都允许设置、显示、选中、拖动和删除 Alert。Scan 使用 Daily，Monitor 使用 Daily/Intraday。
- 创建价格就是按下鼠标左键时，鼠标纵坐标所对应水平线的价格；通过当前图表公开坐标 API 转换，不取 candle close、最高价、最低价或后台最新价，也不吸附 candle。
- 后端把设置价格用 Decimal `ROUND_HALF_UP` 归一到两位小数，持久化为整数 cents；显示始终两位小数。价格必须有限且归一后大于零。
- 直接保存点击得到的价格，不比较、不转换、不校正 Scan 与 Monitor 两种数据的价格口径。跨模式仍显示同一个数值。
- 创建与改价可以在 Regular 之外进行；先持久化，等可用的 Regular 报价建立比较起点。
- 历史 Scan 图表上的 Alert 操作也作用于当前有效 workspace 与当前 Alert 集合，不改写历史 workspace。历史名单本身的只读限制保留。

## 创建时的名单处理

- 当前 Focus 或 Holdings（含当天清仓保留的 symbols）上创建 Alert，无需新增名单归属。Monitor 的 Holdings-only 选择保持独立，不强制加入 Focus。
- 在 Scan 的 Discover 或任一 Excluded section（包括 Review、Hidden、Extended、Broken）图表上创建 Alert，立即将该 symbol 移入当前 Focus，然后保存 Alert；即使它同时属于 Holdings，这次 Scan 操作也执行入选 Focus。
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
- 已发生的未处理卡片独立保存，仍须手动处理；出范围或到期只自动删除 Alert/横线并阻止后续通知。出范围卡片保留关闭操作，跳转不能重新扩大订阅范围。

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
| Active 首次穿越 | Triggered，灰色横线，生成一个未处理事件 |
| Triggered 继续收到行情 | 不再次触发 |
| 成功拖动/重新设置 | 新 generation，Active，黑色横线 |
| 处理当前 Triggered 事件 | 删除对应 Alert 及灰色横线 |
| Backspace 删除 | 删除选中 Alert 及横线 |
| 到期或出范围 | 删除 Alert 及横线，停止后续触发 |
| 服务/Mac 重启 | 恢复尚未到期且仍在范围中的原状态 |

- 默认有效期为创建或成功重新设置后 `7 × 24` 小时；重启不延长。灰线也遵守该期限；已经发生的未处理事件不因期限自动清除。
- 在独立 `runtime/alerts/alerts.sqlite3` 中保存 Alert 与触发记录，不使用可重建的 Longbridge/Massive 行情库，不把 Alert 写进每日 workspace。
- 创建、修改、删除、触发与处理都立即提交 SQLite。成功响应前持久化完成；写失败显示错误，不假装已保存或已触发。
- Triggered 状态与对应事件在同一个事务中保存，提交成功后才发送 macOS 通知和 WebSocket 更新。每份报价只检查该 symbol 的 Active Alert，不逐份报价写库。
- 触发记录包含事件 ID、Alert ID/generation、symbol、方向、阈值、实际触发价、报价时间、触发时间和处理状态。存储时间为 UTC，显示时间为 ET。
- 重新设置增加 generation；旧卡片关闭只能处理旧事件，不能删除或改变已重新设置的 Alert，也不能删除它的新一轮 Triggered 状态。
- 恢复未处理事件时不重新播放声音；系统通知提交成功不等同于用户已经看到/听到，网页卡片以持久化事件为准。

## 图表交互

- 创建：按住 `Command + Option (Alt)`，左键按压主价格绘图区，直接创建；不弹确认，不新增价格输入框。图表标题、成交量区域、时间轴与价格轴不创建 Alert。
- Alert 显示为细水平线段虚线和紧贴右侧价格刻度边缘的向右箭头，视觉对照 TradingView macOS 客户端；触发后改为灰色。不在右侧价格轴显示 Alert 方块、数字或 tick；虚线样式统一遵循 [Chart UI](chart-ui.md#colors-margins-and-reference-lines)，图形定义见 [Alert 图形](ui.md#alert-图形)。
- 平时只显示虚线与右箭头。鼠标悬停横线时，在绘图区宽度约 2/3 处显示两位小数价格胶囊，以鼠标上下调整光标提示拖动，不另画重复的上下箭头；离开横线/胶囊即隐藏，单纯选中不常驻显示价格。胶囊右端的垃圾桶左键立即删除该条 Alert，无二次确认，不启动拖动或交易日联动。拖动期间胶囊跟随线条并显示当前预览价格。
- 普通点击横线选中；选中后 Backspace 立即删除，无二次确认。macOS 键帽上的 Delete 退格键按浏览器 `Backspace` 处理。
- 点击空白或 Esc 取消选中；输入框、搜索和可编辑内容获得焦点时，Backspace 保持原来的文本编辑含义。
- 上下拖动时跟随鼠标预览两位小数价格，松手才提交一次。成功提交恢复 Active 并重新计算期限；明确拖动后提交相同的归一价格也可以重新激活灰线，普通点击不重设。
- 拖动取消或提交失败恢复服务端已保存状态，并显示简短错误；不把未保存的预览当成 Active。
- 创建、选中和拖动 Alert 的手势不同时触发交易日联动或图表平移；其余图表手势继续使用原生行为。
- Daily 与 Intraday 同时显示同一 symbol 的 Alert，各自只按价格是否位于可见主图范围判断，不依赖悬停日期或另一张图的时间/价格范围；超出本图价格范围时不强制缩放。任一图都能选中、拖动和删除，拖动预览与提交价格同步到两图。缩放、价格轴缩放、pane resize 和周期切换后仍对准对应价格。重叠 Alert 必须可以逐条选中和删除。
- 使用 Lightweight Charts 的内置参数和公开 primitive/坐标/命中检测 API；保持 vendor 文件原样，不使用私有接口或内部 DOM。

## 卡片与系统通知

- 待处理 stack 默认位于 Market Monitor 网页左下角，Scan/Monitor 共用。浏览器关闭后仍记录事件并发系统通知，重新打开网页恢复 stack；本版不建设独立桌面浮窗。
- 新事件置前，超出可用高度时内部滚动，不设置自动消失计时器。刷新、重连或应用重启不清空未处理卡片。
- 卡片和系统通知保持简洁：symbol、方向符号、阈值价格、日期和精确到秒的 ET 时间；不显示额外策略解释。实际触发价可在 tooltip 查看。
- 上穿用箭头向上穿过横线的亮蓝色图形，下穿用箭头向下穿过横线的黑色图形；详细配色/图形只维护在 [Logo / Icon](ui.md#alert-图形)。
- 卡片 `×` 关闭并处理；跳转按钮成功打开相应 Monitor 图表后处理。跳转失败保留卡片，处理失败保留服务端未处理状态并显示错误。
- 当前 Triggered generation 被处理后删除灰线；若 Alert 已重新设置，只移除旧卡片。手动删除 Alert 后，已有未处理卡片仍可关闭，不再重新触发。
- 系统通知的 Open/Close 回调进入同一处理函数。注册关闭回调；不能仅凭系统通知不再可见推断事件已被处理。
- 使用 macOS UserNotifications 本地通知；不依赖 Chrome Notification、网页音频或浏览器后台定时器。上穿、下穿分别使用两份短声音，网页不重复播放。
- 原生通知的位置、文字颜色和排版由 macOS 控制。应用内完整实现指定图形；系统通知保留方向符号，可附方向图片，但不承诺任意彩色文字布局。
- 通知权限或声音关闭时，Engine 和持久化卡片继续工作，并明确显示通知状态；不绕过系统设置、不偷偷回退 Chrome。系统提交失败保留事件并报告错误，不反复播放旧报警。

## macOS 权限与运行

- 为工程建立稳定身份的 `Market Monitor.app`，固定 Bundle ID、安装路径及签名方式。权限属于应用，不属于工程目录、localhost 页面或 Python 源文件。
- `.app` 承载同一 Python 进程，最小原生层只负责事件循环、通知、声音和用户操作；检测仍在后台 Engine，不拆出第二个服务。具体职责见 [development.md](development.md#alert-实现)。
- 首次设置通知时由应用请求 alert/sound 权限，用户在系统提示中选择 Allow；之后读取实际权限和声音设置。拒绝后到系统设置开启，不重复弹创建确认。
- `System Settings → Notifications → Market Monitor`：打开 Allow notifications、Desktop、Notification Center、Play sound for notification，选择 Persistent。
- 使用 Focus / Do Not Disturb 时，在对应 Focus 的允许应用中加入 Market Monitor。锁屏、显示器休眠及屏幕共享时是否显示通知按本人需要设置。
- 如需登录后自动恢复监控，将应用加入登录项；持久化恢复本身不依赖登录项。浏览器退出不停止应用，明确退出应用才停止后台。
- Mac 真正休眠、关机或程序退出时无实时检测；显示器熄灭与系统休眠不是同一状态，通知显示权限不会补造期间的行情。
- macOS 26 与 27 均需验收权限请求、前后台通知、两种声音、Open/Close 和升级后的权限保留；不能用其中一版结果代替另一版。

官方依据：[通知授权](https://developer.apple.com/documentation/usernotifications/asking-permission-to-use-notifications)、[本地通知](https://developer.apple.com/documentation/usernotifications/scheduling-a-notification-locally-from-your-app)、[自定义声音](https://developer.apple.com/documentation/usernotifications/unnotificationsound)、[关闭回调](https://developer.apple.com/documentation/usernotifications/unnotificationcategoryoptions/customdismissaction)、[macOS 26 通知设置](https://support.apple.com/guide/mac-help/notifications-settings-mh40583/26/mac/26)、[macOS 27 通知设置](https://support.apple.com/en-nz/guide/mac-help/mh40583/27/mac/27)。

## 实施与必要验收

1. 先验证最小 `.app` 通知链路：权限、两份声音、前后台和操作回调；确认平台路径后再接入正式 Engine。
2. 完成后端 Engine、SQLite、Regular 最新价入口、范围与生命周期。统一手动/Alert 移入 Focus 的公共流程，不另建分类策略。
3. 完成同源 mutation 与独立 Alert WebSocket 快照，再接图表手势和持久 stack。函数接口复用该核心能力，为后续调用留入口。
4. 只执行有关的定向验证与有界真实数据验证，记录日期、环境、覆盖和未覆盖范围。

必要验收包括：

- Regular 两方向、到达、跳价、同秒不同价格、重复/旧 snapshot；扩展时段不触发、不更新起点，新 Regular 日和重启/恢复首价不补报。
- 鼠标水平线价格、两位小数、同 symbol 多 Alert、Scan/Monitor 共用、不同周期同步、选择/退格/拖动与原生图表手势。
- Discover/全部 Excluded 创建立即入 Focus；丢弃旧自动/人工 Tag 与人工 section，按当前 Focus 规则重新分类；无匹配入 Unclassified，新入组首位；手动移入得到相同结果。
- 持久化、Triggered 不重复、拖动重新激活、旧卡片不误删新 generation、到期及 Focus/Holdings 联合范围、当天清仓保留和次日移除。
- stack 不自动消失、关闭与成功跳转、重连/重启恢复；浏览器后台或退出时仍有系统通知，两版 macOS 的权限、声音和回调。
- TypeScript 变更后执行 `npm run build --prefix ui`；Python 只跑涉及本次行为的定向用例。真实行情限定当前允许范围中的少量 symbols 并规定结束条件，不建立故障注入、回放或压力测试框架。

后续 Atomic feature 自动设置、真实订单与自动交易均不在本版范围。实现验证与未覆盖范围只在 validation.md 记录，不把离线用例或平台兼容目标当作 Regular live 穿越或 macOS 27 的证据。

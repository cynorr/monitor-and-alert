# UI layout and interactions

Updated: 2026-10-08. This file is the UI entry point and the only current specification for shared layout, List UI and Logo / Icon. General Chart and Holdings details are maintained only in [chart-ui.md](chart-ui.md) and [holdings-ui.md](holdings-ui.md). Alert interactions and lifecycle are maintained only in [alert.md](alert.md). The product UI is English only. List lifecycle and classification rules are maintained in [list-design.md](list-design.md); backend behavior is maintained in [behavior.md](behavior.md), with Holdings data requirements in [holdings-data.md](holdings-data.md).

## Layout

- Monitor has Daily, Intraday and List panels; Scan has Daily and List. Panel width rules are defined once in **List UI / 宽度与视觉** below.
- No application header, brand, global instrument banner or footer. Chart-owned headers follow [Chart UI](chart-ui.md#headers-and-information).
- White floating cards with generous corners on a neutral background. Black header/column rules and divider handles; internal chart panes follow [Chart UI](chart-ui.md#colors-margins-and-reference-lines).
- Search, period selector, price-session labels and resize handles use pills.

## Chart UI

Chart layout, colors, margins, headers, [volume and five-day comparison](chart-ui.md#volume-comparison), scale defaults, mouse/zoom, linked trading day and status are maintained in [chart-ui.md](chart-ui.md). Longbridge cache freshness is defined only in [longbridge-data.md](longbridge-data.md); refresh uses a weak chart status hint. Optional company names, concise category labels, market cap and earnings are governed by [Additional Info](additional-info.md), independently of chart data and Ready. All charts use the same manually adjustable default spacing; visible history depends on that spacing and panel width.

## Alert UI

Scan/Monitor 图表设置、横线操作、待处理 stack 与后台声音的唯一详细要求见 [alert.md](alert.md)。图形及其颜色只在本文件下方 [Alert 图形](#alert-图形) 维护；加入 Focus 的分类规则见 [List 入选规则](list-design.md#统一移入-focus)。当前实现为公开 series primitive、图表鼠标手势与持久事件 stack。

## Logo / Icon

本章统一维护 Tag 图案、操作/状态图标和未来主站/应用 Logo 的当前要求。Android 原生 App 是后续确定目标，iOS 也可能接入；图形含义、配色和操作语义应可复用，平台绘制与交互方式分别实现。这里不维护废弃方案，也不定义 Tag 的判定条件；规则见 [list-design.md](list-design.md)。

### 通用原则

- 区分度优先，图案应让人迅速联想到形态或操作；使用有代表性的轮廓，避免装饰细节。Tag 是辅助信息，不能用大面积亮色背景干扰 Symbol、价格和 Growth。
- Tag、操作图标、品牌 Logo 属于不同用途，不强制共用尺寸或背景。小图形的可视尺寸与按钮的可操作区域分开管理。
- 每种图案保留明确含义；完整名称、操作说明和状态不能只靠图形或颜色表达。Web 使用提示与可访问名称，原生端需提供可触摸的查看方式，不能照搬 hover。

### Tag 图案与配色

Tag 使用自定义纯线条轮廓，不含字母，不使用具象插画或外部图标库。同一形态可以绑定多个 Tag，通过线条颜色区分所关联的 MA。

| 稳定 Icon ID | 图形要求 |
| --- | --- |
| `surf` | 上方价格折线沿下方 MA 曲线运行；不是多条水波纹，MA 不必水平 |
| `bounce` | V 形价格反弹，与 MA 线形成清晰关系 |
| `prior-run` | 上升阶梯 steps |
| `orderly-pullback` | 下降阶梯 steps，不使用下降箭头 |
| `extended` | 单条加速增长曲线：起点低，前段平缓并向右延长，末段接近竖直上冲 |
| `broken` | 价格向下跌破 MA 线 |
| `label` | 中性标签轮廓，作为未绑定专用图案的默认值 |

- 主景线条颜色和背景颜色可调。MA10 默认蓝 **#2962ff**，MA20 默认黄 **#e4b400**，MA50 默认红 **#e53935**，无 MA 关联默认中性 **#64748b**。例如 Surf-10 / Bounce-10 同为蓝线，Surf-20 为黄线；用户保存的颜色优先。颜色不表示人工/自动来源，也不决定分类。
- 背景可选全透明或极浅毛玻璃；默认极浅灰 **#e5e7eb** 毛玻璃胶囊，无 border。保持低 opacity，主景线条承担识别作用；平台不支持模糊时可呈现极浅灰。
- List 中图形容器高度为行字体的 **0.9 倍**，宽高比 **1.5**。当前 Web 字体 12px，对应高 **10.8px**、宽 **16.2px**。行内数量与列宽见 [List UI / 行与格式](#行与格式)。
- 每个新 Tag 都绑定图案与外观；可先用 `label`，以后更换。外观独立于名称、用途和条件，改名不重新推断已保存图案。新增专用图案时更新本表与实现，保持已有 Icon ID 的含义。
- Tag 编辑草稿提供 **Icon / Line color / Background style / Background color** 和实时 preview。与名称、用途、条件一起 Save / Cancel，不增加单独的保存流程。旧 Tag 仅在前端初始化缺失外观，下次偏好保存持久化，不因打开页面重写偏好。

### 操作与状态图标

以下为当前图形及对应含义；更换绘制方式不能改变行为。名单生命周期见 [list-design.md](list-design.md)，图表错误含义见 [Chart status](chart-ui.md#chart-status)。

| 场景 | 当前图形 | 含义 |
| --- | --- | --- |
| 各 List 置顶 | 向上箭头推至顶线，置顶后蓝色、改为向下取消箭头 | Pin / Unpin：仅改变当日显示位置，保留 section |
| Discover / Focus 行操作 | 轮廓垃圾桶 | Exclude：移到 Hidden 七天，**不是永久删除股票或数据** |
| Excluded 的 Hidden / Extended / Broken / Under-50 行操作 | `↩` | Release：解除排除，随后按当前规则重新分类 |
| Review 行操作 | `+` | Add to Focus，开始实时监控 |
| Section 新增股票 / 新建 Tag | `+` | 按所在控件明确新增目标 |
| Section / Holdings / 交易明细 | `▸` / `▾` | 已折叠 / 已展开，点击切换，不改变名单归属 |
| Holdings 列排序 | 列名下的小三角 | 当前降序列，排序只改变显示 |
| Daily / Intraday | `↦` | Go to latest，回到最新可用交易日 |
| 图表 / 名单错误 | `!` | 提供当前错误详情，不扩展错误判断范围 |

- 垃圾桶保持简单线性轮廓；当前 Web 行按钮为 **24×24px**，图形 **16×16px**，默认灰色，hover 时使用浅红背景与红色线条。键盘 focus 也可显示行操作。原生端需单独适配触摸操作区域与可见性。
- 置顶箭头位于原有行操作左侧，按钮之间留 **10px** 空隙；Web 置顶/垃圾桶按钮为 **24×24px**，图形 **16×16px**；Review 的加号复用共用新增按钮。未置顶时 hover/键盘 focus 可见，置顶后持续显示蓝色，并提供 Unpin 名称和 pressed 状态。
- 操作使用完整的英文说明和可访问名称，不能仅靠垃圾桶或 `+` 猜测结果。Tag 定义的 Delete 当前是文字按钮，与名单行的垃圾桶操作不同。

### Alert 图形

| 场景 / 稳定 Icon ID | 图形与颜色 | 含义 |
| --- | --- | --- |
| Chart Alert | 黑色 **#000000** 细水平线段虚线，右端小箭头进入价格轴：三角形左侧竖边与价格刻度标签左边缘对齐，向右延伸 **6px**；Triggered 时线条/右箭头灰色 **#9ca3af**；虚线统一见 [Chart UI](chart-ui.md#colors-margins-and-reference-lines) | Active / 已触发，生命周期以 alert.md 为准 |
| Alert 悬停控件 | 白底价格胶囊中心位于绘图区宽度约 **2/3** 处，**1px** 细边框、**11px / 400** 两位小数文字，圆角端部；Active 黑色、Triggered 灰色。鼠标为上下调整光标，不另画上下箭头；胶囊右端为黑色线性垃圾桶，不在价格轴绘制 Alert 数字标签 | 预览价格、拖动改价、删除该条 Alert |
| `alert-cross-up` | 箭头从下方向上穿过一条水平线，亮蓝 **#2962ff** | 价格上穿或向上到达阈值 |
| `alert-cross-down` | 箭头从上方向下穿过一条水平线，黑色 **#000000** | 价格下穿或向下到达阈值 |
| Alert 卡片关闭 | `×` | 手动处理该事件 |
| Alert 卡片跳转 | `↗` | 打开对应 Monitor 图表并处理事件 |

Chart 标记与方向图形使用简单的应用层绘制/SVG，悬停胶囊使用少量应用层 DOM，视觉对照 TradingView macOS 客户端，不引入图标库、不修改 chart vendor。Alert 垃圾桶复用既有线性轮廓，但其含义是删除 Alert；名单垃圾桶仍按名单生命周期排除 symbol。网页准确使用上述图形；声音由后台播放，状态和错误遵循 Alert 需求。各操作提供英文可访问名称，具体处理语义只在 [alert.md](alert.md) 维护。

### 品牌与平台实现

- 当前没有主站/应用品牌 Logo，不新增页头、页脚或品牌占位。未来主站 Logo、Android/iOS 应用图标的设计统一补充本章，正式需求确定后再制作。
- 关闭图表供应商的画布 Logo；第三方 LICENSE/NOTICE 和 attribution 保留在独立静态 `/licenses.html` 页面。
- 当前 Web 的 Tag 图案与默认外观集中在 `ui/src/tag-appearance.ts`，列表和编辑 preview 共用；样式在 `ui/public/style.css`，行操作在 `ui/src/list.ts`，持仓图标在 `ui/src/holdings.ts`，图表按钮在 `ui/public/index.html`。保存字段契约见 [development.md](development.md)。
- SVG path、viewBox、CSS、blur 和 `title` 属于当前 Web 实现。迁移到原生端时复用图案含义、轮廓和已保存外观，按平台适配密度与触摸交互；不把 Web px、DOM 或 hover 当成原生端实现契约。

## List UI

本章是唯一当前 List UI 规范，覆盖 Scan、Monitor 的观察名单；独立持仓表只在 [Holdings UI](holdings-ui.md) 维护。名单分类与生命周期见 [list-design.md](list-design.md)；显示、筛选和格式化不改变名单归属或行情订阅。

### 宽度与视觉

- 扣除工作区内边距和面板分隔条后，两模式 List 默认占可用面板宽度 **32%**，最小 **680px**；每个图表最小 **320px**，Monitor 双图均分剩余空间。数值统一放在 `layout.ts`，方便单点调整比例。
- 面板分隔条和 List 数据列间距均为 **12px**。拖动只调整相邻面板并保留最小宽度；打开页面、切换模式或双击分隔条恢复默认。小窗口保持最小宽度，允许工作区整体溢出。
- Monitor 的最小宽度也接受独立持仓内容需求，具体测量和固定顶部布局见 [Holdings UI](holdings-ui.md#位置折叠与宽度)。
- List 与图表头部保持等高对齐，高度只在 [Chart UI](chart-ui.md#headers-and-information) 维护。模式、总数、数据标记、Search 和一行 Filter/Tags 位于固定头部的水平分割线上方；与两图保持同一固定高度。Scan 准备状态在分割线下，仅需要时显示。名单列头在 Holdings 下方，文字位于其底部分割线上方；没有额外的 Filters/Holdings 或 section 分割线。
- 计数使用独立 `span.count-badge`：**10px、黑色、不加粗**，与标题留小间距。适用于列表按钮、section、symbol 总数、Holdings、Filter 与结果数。数字本身不统一加背景；选中 pill 中的数字仍为黑色，所在 pill 使用浅背景保证可读。

### 展示范围与控件

| 模式 | 名单 | 数据与控件 |
| --- | --- | --- |
| Scan | Discover / Focus / Excluded 三个入口 | 本地 Massive Daily；日期、Refresh Scan、RFL 排序、批量选择/移动，以及共用 Tag/Filter |
| Monitor | Focus setup sections、折叠 Review、上方独立 Holdings | Focus/Holdings 实时图；Review 本地 Daily 预览；共用 Tag/Filter |

- Discover 和 Excluded 的 Hidden / Extended / Broken / Under-50 仅 Scan 展示。Review 不订阅 Longbridge：选择后显示 Daily 日期，禁用 Intraday 周期按钮，提示 `Add to Focus for live data`；加入 Focus 后才开始实时监控。
- 所有常规 List（Scan 与 Monitor）在前端屏蔽当前 Holdings 已有 symbol，含仅保留当天的清仓批次；可见计数、筛选、搜索、导航和批量操作使用同一屏蔽结果。后端名单、归属、Tag、订阅与原有顺序不变。
- 同 ticker 的 Holdings 仍为独立实时选择。WS 选择携带 `source=holdings` 或 `source=watchlist`；名单刷新、折叠和筛选不得抢走已选持仓的图表。
- 切换模式同步已打开客户端的展示，后台 Focus 行情和账户刷新持续运行。合成 Scan 标记 MOCK，独立模拟器标记 SIM。
- 历史 Scan 与有界 `--symbols` 会话禁用名单编辑；模拟器只修改临时 workspace。

### 行与格式

| 模式 | 列 |
| --- | --- |
| Scan | Symbol / Price / ADR20 / ADV20 / Growth / Tags / 行操作 |
| Monitor | Symbol / Last / Chg% / Ext（仅非 regular）/ Tags / 行操作 |

- 同 ticker 只有一行，固定行高 **28px**，主体数据列保持同一水平行；Scan Growth、Tags 与行操作不换行、不增加副标题。
- **仅 Scan** 的 Growth 依次显示 **1m / 3m / 6m** 三个值，不显示周期 key，以浅色 `|` 分隔。原始 `rfl=(close/low-1)×100`：小于 100 显示最多一位小数的百分比、去掉 `.0`；大于等于 100 显示 `(1+rfl/100)`，保留一位小数和小写 `x`。例如 `65%`、`12.3%`、100% 显示 `2.0x`、130% 显示 `2.3x`。空值和非有限值显示 `—`；只改变显示，不改变原始数据、排序和筛选。
- Tags 列显示轮廓 glyph，图案、尺寸与配色统一见 [Logo / Icon](#logo--icon)。保持 **110px** 列宽下限并为编辑按钮留空隙；最多显示三个 glyph，其余用小号 `+N`，悬停列出完整剩余标签。glyph 悬停显示完整名称与人工 `today` 状态，人工补充仅当日有效，不额外使用蓝色 badge。Tags 与 `+N` 均不换行、不增加行高，不增加测宽或 ResizeObserver。
- Tags 编辑按钮不额外占数据行，hover/键盘 focus 时可见；行内编辑仅修改当日人工补充，Hidden 不提供人工 Tag 编辑。图形外观在保存的 Tag 定义中统一编辑。
- NEW / RETURNED 使用 Symbol 旁的小标记；NEW 使用与 EMA10 一致的蓝色 **#2962ff**，RETURNED 保持灰色。ticker 不显示 `.US`。Scan 的成员勾选与图表选中互相独立。
- Scan Price 是完成日收盘价，ADR20/ADV20 用共用日线定义。Monitor Last 是 regular 价格，Chg% 使用前一完成交易日 regular 收盘价；Ext 使用更新的 extended 报价相对 regular 收盘价，regular 时段隐藏整列（含标题和行单元），离开后恢复；非 regular 缺数据时留空。时段与 Holdings 共用服务端交易日历状态，不依赖某只股票是否已有 Quote。Review 显示本地 Daily close，实时涨幅列留空。
- 选中行保留圆角黑色内边框，不改变背景；仅未选中 hover 行使用灰背景。操作与 Tag 编辑按钮 hover/键盘 focus 时可见；报价更新保留行结构，仅刷新值。

### Section、顺序与选择

- Discover/Focus 按保存的 **Setup** Tag 顺序分组，最后是 Unclassified；Excluded 固定 **Review / Broken / Extended / Under-50 / Hidden**。一只股票可有多个 Tag、一个主 section。
- 置顶是独立显示状态，不是 Tag 定义或 section：每个 List 的 Pinned 区域位于该 List 所有 section 之前，支持多个 ticker；原 section 内不重复显示。取消置顶回到仍属的 section 与其原有顺序。置顶遵循 Filter 和持仓屏蔽。Scan/Monitor 共用保存顺序，置顶区可拖动及 Shift+上下重排，不受 RFL 排序影响。Monitor 的 Focus 与 Excluded/Review 各有自己的置顶区。
- Section 之间不画水平线，以标题行和间距区分。
- Scan 与 Monitor 的折叠状态独立。Review 在 Monitor 默认折叠、Scan 默认展开。非搜索状态 setup 空组也显示；搜索只显示有结果的组。
- 新进入 section 的成员放**队首**，留在同组的成员保留人工顺序。人工主 section 仅当天有效，名单归属和保存顺序按 List 设计执行。
- Default order 下，允许在 Discover/Focus setup 组内及组间拖动。落点显示行前/行后线；落在组头或空组插入队首。筛选/搜索可见行作为完整组顺序的锚点，松手立即保存。
- RFL1M/3M/6M 排序仅改变显示，禁用 Scan 普通 section 人工重排；Excluded 普通分组由规则决定，不提供人工排序。置顶区顺序独立。
- 新置顶保存成功后，当前 List 的黑框选择与图表按操作前可见顺序移到下一个 ticker，跳过刚置顶的成员；到尾部循环至首个其他可见成员，只有一个成员则保留选择。取消置顶保留当前选择；持仓选择不受影响。
- 点击或上下方向键按显示顺序选图，跳过折叠组。非搜索状态 Shift+上下在同一 setup 组内交换相邻成员并保留选择，到边界不移动。Holdings 使用独立导航、不参与 Shift 重排。

### Tag 与 Filter 编辑

- 固定头部最后一行依次为 **Filters + 数字**、保存的 Tags 和新增按钮；Tag 加号固定在右侧，位于 Tag 横向滚动区之外，与 section 加号同一横坐标；不显示 `active`。Tags 单行水平排列，放不开时横向滚动。Setup Tags（Surf/Bounce 等）在前，Label 居中，Extended/Broken/Under-50 在后；仅改变按钮显示，不重写保存顺序或分类优先级。Tag/Filter 标签与 List 列名到下方水平线的间距使用与 Chart legend 相同的共用变量，数值在 [Chart Headers](chart-ui.md#headers-and-information) 维护。Filter 按钮展开线下编辑区，不改变顶部水平线高度；取消原 Filters/Holdings 分割线。
- 两模式使用同一套保存的 Tag/Filter。38 字段目录包含 Market、MA arrangement 和 atomic feature 各组。使用 **CSS 两列 columns** 布局，每组保持完整；不使用横向对齐的 grid，避免短组下面出现空白。
- 数值条件支持 Any / ≥ / ≤ / range；不同条件 AND，分类多选 OR。缺失值匹配 Any 或显式 Missing。Filter 不移动名单、不改变订阅，被筛掉的成员保留底层归属。
- Tag 用途固定为 Setup / Extended / Broken / Under-50 / Label，与名称独立；Setup 提供潜力 section，其余按 List 设计处理。Tag 名称唯一，可保存零到十个；选择按钮点击一次选中，再点击取消。没有选择时不应用保存 Tag 筛选。
- 新建克隆当前草稿条件，用途默认 Setup；未选 Tag 时从空条件编辑，可保存为新命名 Tag。条件编辑即时预览；Save 保存并折叠，Cancel 恢复。未保存时切 Tag 需明确丢弃，保存失败保留草稿；名单/排序偏好写入不得覆盖未保存的 Filter 草稿。
- Tag 外观编辑遵循 [Logo / Icon](#logo--icon)，与本章同一份 Tag 草稿一起保存或恢复；外观编辑保留已保存条件下的人工匹配成员，不切换到纯条件预览。
- 已保存 Tag 的筛选包含人工补 Tag 成员；未保存条件预览只按草稿条件判断。保存规则由后端重评已有本地数据，UI 筛选不触发下载。

### 名单操作与批量移动

- `Add to Focus` 清除排除状态并开始实时监控。行 Exclude 将 Discover/Focus 移到 Hidden 七天；Hidden / Extended / Broken / Under-50 提供 `Release`，当前规则仍可立即重新排除。Review 只有 Add to Focus，可留待处理或规则重分类，没有 Dismiss/Delete。
- 批量 `Move to Discover` 明确结束 Focus 归属，`Move to Excluded` 表示 Hidden。Select all 勾选当前筛选结果，移动时整块插入队首。日期/名单/Filter 改变清空勾选；Space 切换选中 Scan 行的勾选。
- 操作即时写入，保存失败保留原名单并显示简短行内错误。workspace/新日变更自动刷新，不增加 Refresh Workspace 按钮。名单选择消失时改选首个可用成员，空名单清图但保留 Search 和新增入口。
- 手动/Alert 入选：从 Discover/Excluded 移入 Focus 时，统一按 [List 入选规则](list-design.md#统一移入-focus) 重新匹配并插入对应 section 首位。UI 只提交动作并使用后端结果，不继承来源的 Tag/section。

### Search 与 Add

- List 模块的 Tag 新增、section 新增和 Review Add to Focus 只使用一套加号按钮样式：26×26px、21px 字号、圆形 hover 背景；Tag 与 section 加号距面板右边同为8px。
- Search 与可编辑 Focus setup 组的 `+` 共用唯一行内输入，placeholder 始终为 `Search`，不使用新增弹窗。`/` 随时清空并开始 Focus 搜索；Focus 组内 `+` 指定该 section 为新增目标。Esc 退出并恢复全名单。
- 即时筛选本地 ticker，仅显示匹配组，无空组或 No matches；没有本地结果时隐藏报价列头。搜索临时展示折叠组，选中结果只展开当前模式的对应组。
- 没有精确本地 ticker 时，停输一秒发起精确查询：Scan 读本地 Daily，Monitor 经后端官方 static_info。查询不保存、不订阅；输入变化或退出后丢弃旧响应。
- 有效新候选位于本地匹配前，显示蓝色 ticker、公司名和 Add。Enter 优先选择精确已有 ticker；已展示的新候选优先于局部匹配，否则选择首个本地匹配或发起/等待查询。确认新候选后插入目标队首、选图并退出；已有 ticker 只选择、不移动。
- 未找到 ticker 保持空结果，查询/保存失败保留行内错误。只支持美股正股，不新增模糊查询和其他市场入口。
- 上述指定 section 新增针对全新 symbol。已有 Discover/Excluded symbol 明确加入 Focus 时，分类以 [统一入选](list-design.md#统一移入-focus) 为准，不由 Search/section `+` 保留来源结果或强制目标组。

### 独立 Holdings 入口

Monitor 顶部固定的持仓表、整体折叠、水平 overflow、列与格式、买卖明细、排序、选择和状态的唯一要求见 [Holdings UI](holdings-ui.md)。

### Scan 日期与准备状态

- Scan 使用截至所选日的完成 Daily，Focus 也用同一来源，无活跃 candle 或 Intraday。图表显示所选日期；正常时隐藏独立准备状态，不重复显示 Ready 日期或完成时间。
- 日期下拉仅列已生成日。Refresh Scan 补齐并打开最新可用日，与正在查看的历史日期无关；已完成的步骤跳过，全部完成仍切回最新日。自动完成保留历史选择和展示模式，新日按 List 生命周期继承。配置变更/指定日重算仅由CLI处理。
- 未完成、处理中或失败时才显示目标日期与当前阶段，例如 Downloading daily / Updating splits / Building daily bars / Building features，失败详情放悬停；旧日期和结果继续可查看。准备中禁用重复 Refresh，但允许切换模式。GET、选图、Filter 和切页不触发下载。

## Data and simulator boundaries

- One same-origin WebSocket carries initial/selection/reconnect snapshots and subsequent updates. HTTP serves assets, universe and read-only diagnostics; POST /v1/list performs edits. POST /v1/mode, /v1/scan and /v1/preferences handle mode, generation/date and saved Tags. Independent list messages refresh membership even without chart selection. A chart GET must not change selection priority.
- Chart context checks, local/derived history and status boundaries follow [Chart UI](chart-ui.md#data-boundaries).
- Monitor closed-bar refresh continuity and Vol readout semantics follow [Chart UI](chart-ui.md#headers-and-information) and [Mouse, zoom and periods](chart-ui.md#mouse-zoom-and-periods).
- Simulator uses the same UI, scheduler and validation against temporary data with an instance exchange clock. It never reads credentials or falls back to a broker. SIM and MOCK are offline fixtures, not live evidence.

## Checks

Run `npm run build --prefix ui` after TypeScript edits and only the related offline checks. Validate affected layout, List interactions or chart gestures; do not broaden to a live/full workflow without authorization. Record coverage and limitations in [validation.md](validation.md).

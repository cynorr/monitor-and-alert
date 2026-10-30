# UI layout and interactions

Updated: 2026-10-30. This file is the UI entry point and the only current specification for shared layout, List UI and Logo / Icon. General Chart and Holdings details are maintained only in [chart-ui.md](chart-ui.md) and [holdings-ui.md](holdings-ui.md). Alert interactions and lifecycle are maintained only in [alert.md](alert.md). The product UI is English only. List lifecycle and classification rules are maintained in [list-design.md](list-design.md); backend behavior is maintained in [behavior.md](behavior.md), with Holdings data requirements in [holdings-data.md](holdings-data.md).

## Layout

- Monitor has Daily, Intraday and List panels; Scan has Daily and List. Panel width rules are defined once in **List UI / 宽度与视觉** below.
- No application header, brand, global instrument banner or footer. Chart-owned headers follow [Chart UI](chart-ui.md#headers-and-information).
- White floating cards with generous corners on a neutral background. Black header/column rules and divider handles; internal chart panes follow [Chart UI](chart-ui.md#colors-margins-and-reference-lines).
- Search, period selector, price-session labels and resize handles use pills.

## Chart UI

Chart layout, colors, margins, headers, [turnover and five-day comparison](chart-ui.md#turnover-comparison), [Daily setup scale, coupled zoom, Reset and F overview](chart-ui.md#daily-setup-scale), linked trading day and status are maintained in [chart-ui.md](chart-ui.md). Longbridge cache freshness is defined only in [longbridge-data.md](longbridge-data.md); refresh uses a weak status hint while existing charts and valid values remain visible. Optional company names, concise category labels, market cap and earnings are governed by [Additional Info](additional-info.md), independently of chart data and Ready. All charts use the same manually adjustable default spacing; normal visible history depends on that spacing and panel width.

## Alert UI

Scan/Monitor 图表设置、横线操作、统一未读提醒与后台声音的唯一详细要求见 [alert.md](alert.md)。图形及其颜色只在本文件下方 [Alert 图形](#alert-图形) 维护；加入 Focus 的分类规则见 [List 入选规则](list-design.md#统一移入-focus)。当前实现为公开series primitive、图表手势与Regular内持久未读状态；所有选图/当前chart更新统一已读，收盘清理。未读跳转与保留Tag筛选的规则见[List交互](list-interactions.md#未读-alert-导航)。

## Intraday State UI

独立需求、ADR字段、CumVol/LocalVol Badge和In Play自动聚集只在 [intraday-state.md](intraday-state.md#展示与-in-play) 维护。复用现有section，无展示模式选择；空section整个隐藏，全表空时只显示一份空状态。Holdings列与批次见 [holdings-ui.md](holdings-ui.md)。

ADR与两种分钟量比按各自数据就绪显示；单项缺失显示`—`，不等待整行初始化。Focus有效倍数≤0.5留空，量能同时隐藏对应Badge但保留列宽；按原值判断，只影响显示，不改排序、报警或Scan ADR20。Holdings维持自身数值显示范围。

## Color palette

共享颜色速查，2026-10-29 对照当前 CSS、Chart 与 Tag 默认值整理。英文名用于需求沟通；代码的唯一默认色值来源为 `ui/src/palette.ts`，Chart、Tag 默认值与 Symbol 模板直接复用，`installPalette()` 将同一份值安装为 `--color-*` CSS 变量。颜色对应的业务条件仍由各模块唯一需求文档维护。

| 名称 | 色值 | 当前用途 |
| --- | --- | --- |
| Blue / 主蓝 | `#2962ff` | EMA10、MA10 Tag、NEW、上行增强底色 |
| Blue Soft / 浅蓝 | `#e8f1ff` | 上行关注底色 |
| Yellow / 主黄 | `#e4b400` | EMA20、MA20 Tag、Pre 价格标签 |
| Yellow Text / 黄文字 | `#b89100` | Chart EMA20 图例文字；比主黄深 |
| Yellow Soft / 浅黄 | `#fff3c4` | 回撤预警底色 |
| Red / 主红 | `#e53935` | SMA50 / SMA65、MA50 Tag |
| Red Strong / 深红 | `#b42318` | 回撤紧急底色、Alert 错误文字 |
| Positive / 上涨文字 | `#008f83` | Holdings 正向涨跌及盈亏数字 |
| Negative / 下跌文字 | `#df4543` | Holdings 负向涨跌及盈亏数字 |
| Candle Up / 上涨柱 | `#26a69a` | 上涨 K 线与成交量柱；现有 CSS 变量 `--up` |
| Candle Down / 下跌柱 | `#ef5350` | 下跌 K 线与成交量柱；现有 CSS 变量 `--down` |
| Tag Neutral / 中性线条 | `#64748b` | 无 MA 关联的默认 Tag 线条 |
| Volume Base / 量能普通 | `#f4f5f7` | 普通量能 Badge 底色 |
| Volume Low / 量能一级 | `#e5e7eb` | 一级量能底色，也用于默认 Tag 毛玻璃底色 |
| Volume Medium / 量能二级 | `#cbd2db` | 二级量能底色 |
| Volume High / 量能三级 | `#374151` | 三级量能底色、普通至二级量能文字 |
| Ink / 黑 | `#000000` | 选中轮廓、Active Alert 线、Overnight 价格标签 |
| White / 白 | `#ffffff` | 卡片底色、强状态底色上的文字 |
| Muted / 已触发灰 | `#9ca3af` | Triggered Alert 线与操作控件 |

“亮蓝”目前就是 Blue，没有独立的第二个高饱和蓝。主红、回撤深红、下跌文字红和下跌柱红是不同用途；讨论改色时使用上表的完整名字。涨跌文字在强蓝/深红状态底色上沿用白字，不能强行保留红绿而降低可读性。用户保存的 Tag 自定义颜色优先于默认值。

## Symbol row template

背景与设计哲学：在有限行高中突出 Symbol、价格和有效提醒，减少无效数字与装饰。Chart 采用大圆角容器，名单采用胶囊；共用颜色与轻阴影语言，按信息密度调整阴影强度。行的选择、实时价格状态、最新未读报警分别表达，不增加新的选中模式或点击区域。

- Focus、Holdings、Discover、Excluded 共用 Symbol 起始缩进，给半圆端部和 Holdings 展开三角留白。选中始终作用于整行，使用黑色细胶囊轮廓和轻微外阴影，不改背景；未选中 hover 为浅灰，不能覆盖价格状态。普通行与量能胶囊不额外加阴影。
- 价格区域为连续胶囊。Monitor Focus 覆盖 Symbol、Last、Chg%、ADR；非 Regular 的 Ext 也属于价格区域。Tags、量能与操作独立。Scan 保持自身数据列，使用相同模板，不为两种量能重排列。Holdings 的区域边界只在 [Holdings UI](holdings-ui.md#列与格式) 维护。
- 已读时底色表达当前实时状态：Blue Soft / Blue 对应上行关注／增强，Yellow Soft / Red Strong 对应回撤预警／紧急；强蓝、深红价格区域使用白字。Candidate Chg% 使用 Positive / Negative，强底色时继承白字；白色未读区域恢复通常文字配色。其他字段保持本色。
- 未读时价格区域中间为稳定白底，文字不运动；边缘叠加横向流动的渐变波浪。颜色只取最后一次未读报警的方向与等级，直接覆盖，不叠加或保存历史；当前价格状态仍持续更新，已读后立即恢复当时最新底色。上行关注边缘使用 Blue 与 White 的 68% 混色以保证可见，上行增强使用 Blue；下行预警使用 Yellow，紧急使用 Red Strong。手动穿越及 EMA 上穿为相应方向的普通等级。
- 整条只用一份长边渐变遮罩，取消端部单独拼接、实色色带和虚线。当前 Web 波浪每 2.8s 平移一个周期；遮罩可见峰值 0.48，向内 6px 淡至透明，中央保持白色。波浪没有实色停留段；外层胶囊自然裁切，不另做内圈 border。音频每声通过同一入口触发一次短亮度脉冲，不缩放数字或整行；播放结束后只保留流动波浪。
- 仅 symbol 主行承载提醒，section、Holdings 标题、Buy/Sold 明细及 Total 不聚合提醒。已读、期限与声音行为只在 [Alert](alert.md#统一未读提醒) 维护。
- Web 复用 `symbol-row.ts` 创建 `.price-surface` / `.price-wave`，`attention.ts` 应用最后一条提醒及本次节拍；Grid 与 Holdings Table 使用同一套 CSS。Chart 与行阴影分别由 `--panel-shadow` / `--row-shadow` 集中定义。不为未来功能复制绘制或增加动画框架；平台实现可以调整绘制方式，保留上述语义。

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
| `under50` | 上方波浪水面、下方泳镜，表示价格仍在 SMA50 下方；默认使用 SMA50 红色 |
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
| Discover / Focus 行操作 | 轮廓垃圾桶 | Move to Hidden：人工屏蔽七个自然日 |
| Excluded / Hidden 行操作 | `↩` | Release：提前结束屏蔽，仅当天候选回 Discover，再按当前规则分类 |
| Section 新增股票 / 新建 Tag | `+` | 按所在控件明确新增目标 |
| Section / Holdings / 交易明细 | `▸` / `▾` | 已折叠 / 已展开，点击切换，不改变名单归属 |
| Holdings 列排序 | 列名下的小三角 | 当前降序列，排序只改变显示 |
| Schwab 活动订单 | 红底圆形按钮内白色 `×` | 取消指定订单；Entry/Stop 的目标规则见 Schwab Trade |
| Trade Auto | 浅灰圆形按钮内线性 `↺` | 恢复两条参考线的自动标价；自动时灰色禁用，手动拖价后蓝色可点，无悬停说明 |
| Daily / Intraday | `↦` | Reset view & go to latest，重置本图；R 重置全部可见图，见 [Chart 交互](chart-ui.md#mouse-zoom-and-periods) |
| 图表 / 名单 / Holdings 错误 | 轮廓圆圈内的 `!`，暖黄色 | 提供当前错误详情，不扩展错误判断范围；Holdings 点击详情见独立 UI 规范 |

- 垃圾桶保持简单线性轮廓；当前 Web 行按钮为 **24×24px**，图形 **16×16px**，默认灰色，hover 时使用浅红背景与红色线条。键盘 focus 也可显示行操作。原生端需单独适配触摸操作区域与可见性。
- Schwab 订单取消复用 icon-button 圆形按钮，Red 背景、White 符号，hover 加深为 Red Strong；Web 圆底14px，内部为14px SVG中的对称交叉线，使用3px SVG描边，两条对角线的中心与圆心重合；使用flex居中和单元格垂直居中，不依赖文字字形基线。不增加文字按钮或图标库。
- Trade Auto 复用 26px icon-button 圆形按钮，16px 线性回转箭头 SVG，不引入图标库；容器保持水平/垂直居中，箭头本身向右0.5px、向上0.5px补偿原路径偏左下的视觉重心。保留英文可访问名称，不设置 title。
- 错误感叹号复用当前Chart警告的极简圆形轮廓：Web图形16×16px、1px边框，边框#b58722、文字#a47614，圆角50%；Chart与Holdings共用一份CSS绘制声明。交互按各模块要求，状态独立，Chart刷新不得改变Holdings错误入口。
- 置顶箭头位于原有行操作左侧，按钮之间留 **10px** 空隙；Web 置顶/垃圾桶按钮为 **24×24px**，图形 **16×16px**。未置顶时 hover/键盘 focus 可见，置顶后持续显示蓝色，并提供 Unpin 名称和 pressed 状态。
- 操作使用完整的英文说明和可访问名称，不能仅靠垃圾桶或 `+` 猜测结果。Tag 定义的 Delete 当前是文字按钮，与名单行的垃圾桶操作不同。

### Alert 图形

| 场景 / 稳定 Icon ID | 图形与颜色 | 含义 |
| --- | --- | --- |
| Chart Alert | 黑色 **#000000** 细水平线段虚线，右端小箭头进入价格轴：三角形左侧竖边与价格刻度标签左边缘对齐，向右延伸 **6px**；Triggered 时线条/右箭头灰色 **#9ca3af**；虚线统一见 [Chart UI](chart-ui.md#colors-margins-and-reference-lines) | Active / 已触发，生命周期以 alert.md 为准 |
| Alert 悬停控件 | 白底价格胶囊中心位于绘图区宽度约 **2/3** 处，**1px** 细边框、**11px / 400** 两位小数文字，圆角端部；Active 黑色、Triggered 灰色。鼠标为上下调整光标，不另画上下箭头；胶囊右端为黑色线性垃圾桶，不在价格轴绘制 Alert 数字标签 | 预览价格、拖动改价、删除该条 Alert |

Chart标记使用简单的应用层绘制，悬停胶囊使用少量应用层 DOM，视觉对照 TradingView macOS 客户端，不引入图标库、不修改 chart vendor。Alert 垃圾桶复用既有线性轮廓，但其含义是删除 Alert；名单垃圾桶表示移入 Hidden，Release 回转箭头表示释放归属，方向箭头表示加入 Focus；动作在 [List 交互](list-interactions.md) 维护。网页准确使用上述图形；声音由后台播放，状态和错误遵循 Alert 需求。各操作提供英文可访问名称，具体处理语义只在 [alert.md](alert.md) 维护。

Symbol 未读图形统一使用 [Symbol row template](#symbol-row-template)，与 Chart Alert 水平虚线是不同用途。

### 品牌与平台实现

- 当前没有主站/应用品牌 Logo，不新增页头、页脚或品牌占位。未来主站 Logo、Android/iOS 应用图标的设计统一补充本章，正式需求确定后再制作。
- 关闭图表供应商的画布 Logo；第三方 LICENSE/NOTICE 和 attribution 保留在独立静态 `/licenses.html` 页面。
- 当前 Web 的 Tag 图案与默认外观集中在 `ui/src/tag-appearance.ts`，列表和编辑 preview 共用；样式在 `ui/public/style.css`，行操作在 `ui/src/list.ts`，持仓图标在 `ui/src/holdings.ts`，图表按钮在 `ui/public/index.html`。保存字段契约见 [development.md](development.md)。
- SVG path、viewBox、CSS、blur 和 `title` 属于当前 Web 实现。迁移到原生端时复用图案含义、轮廓和已保存外观，按平台适配密度与触摸交互；不把 Web px、DOM 或 hover 当成原生端实现契约。

## List UI

本章是唯一当前 List UI 规范，覆盖 Scan、Monitor 的观察名单；独立持仓表只在 [Holdings UI](holdings-ui.md) 维护。名单分类与生命周期见 [list-design.md](list-design.md)，导航、移动、搜索和操作反馈只在 [List 交互](list-interactions.md) 维护；显示、筛选和格式化不改变名单归属或行情订阅。

### 宽度与视觉

- 扣除工作区内边距和间距后，List 默认占可用面板宽度 **32%**，最小 **680px**；其余空间由当前可见图表等分，一个图占满、多个图始终等宽。每个图至少 **320px**；Trade 的 Intraday 票据需要 540px，因此双图均至少 540px。分配函数按图表数量和各组件最小宽度计算，不为模式维护不同分配算法。数值统一维护在 `layout.ts`。
- 图表之间保留 **12px** 静态间距，删除中间拖动把手、键盘焦点及调整行为。只保留图表组与 List 的 **12px** 分隔条，拖动均匀增减各图宽度；List 数据列间距不变。打开页面、切换模式或双击该分隔条恢复默认比例。持仓自然测宽仍约束 List 最小宽度；小窗口允许整体溢出，Trade 在 List 最小值下工作区至少1804px。圆角、阴影、头部、内边距、票据和内部成交量分界不变。
- Monitor 的最小宽度也接受独立持仓内容需求，具体测量和固定顶部布局见 [Holdings UI](holdings-ui.md#位置折叠与宽度)。
- List 与图表头部保持等高对齐，高度只在 [Chart UI](chart-ui.md#headers-and-information) 维护。模式、总数、数据标记、Search 和一行 Filter/Tags 位于固定头部的水平分割线上方；与两图保持同一固定高度。Scan 准备状态在分割线下，仅需要时显示。名单列头在 Holdings 下方，文字位于其底部分割线上方；没有额外的 Filters/Holdings 或 section 分割线。
- 原 Intraday 时间模块统一移到 List 右上角，与 Monitor / Scan / Trade 模式按钮垂直居中、同排显示；使用12px、#293341、26px行高和右侧12px内距。继续读取现有 view.server_time 并显示纽约时间及 ET，不新增时钟请求或定时器。
- 计数使用独立 `span.count-badge`：**10px、黑色、不加粗**，与标题留小间距。适用于列表按钮、section、symbol 总数、Holdings 与 Filter。数字本身不统一加背景；选中 pill 中的数字仍为黑色，所在 pill 使用浅背景保证可读。

### 展示范围与控件

| 模式 | 名单 | 数据与控件 |
| --- | --- | --- |
| Scan | Discover / Focus / Excluded 三个入口 | 本地 Massive Daily；日期、Refresh Scan、RFL 排序、单只名单操作，以及共用 Tag/Filter |
| Monitor | Focus setup sections、上方独立 Holdings | 实时 Daily/Intraday；共用 Tag/Filter |

- Scan 固定顶部水平线下的第一行：左侧为 Discover / Focus / Excluded，最右侧为日期下拉与 Refresh Scan，全部垂直居中、同一行显示。计数随名单按钮显示，不另设结果数。
- Discover 与全部 Excluded 仅 Scan 展示本地 Massive Daily；明确加入 Focus 后开始实时监控。
- 所有常规 List（Scan 与 Monitor）在前端屏蔽当前 Holdings 已有 symbol，含仅保留当天的清仓批次；可见计数、筛选、搜索、导航和单只操作使用同一屏蔽结果。后端名单、归属、Tag、订阅与原有顺序不变。
- 同 ticker 的 Holdings 仍为独立实时选择。WS 选择携带 `source=holdings` 或 `source=watchlist`；名单刷新、折叠和筛选不得抢走已选持仓的图表。
- 切换模式同步已打开客户端的展示，后台 Focus 行情和账户刷新持续运行。合成 Scan 标记 MOCK，独立模拟器标记 SIM。
- 历史 Scan 与有界 `--symbols` 会话禁用名单编辑；模拟器只修改临时 workspace。

### 行与格式

| 模式 | 列 |
| --- | --- |
| Scan | Symbol / Price / ADR20 / MDV20 / RFL 排序 / Tags / 行操作 |
| Monitor | Symbol / Last / Chg% / Ext（仅非 regular）/ Tags / 行操作 |

- 同 ticker 只有一行，固定行高 **28px**，主体数据列保持同一水平行；Scan Growth、Tags 与行操作不换行、不增加副标题。
- **仅 Scan** 的 Growth 数据列以排序下拉作为列头，显示当前 **RFL 1M / RFL 3M / RFL 6M / Default order**。控件沿用列名的字体与颜色，无背景或边框，右侧使用黑色向下折号。没有独立排序工具行。
- 该列始终依次显示 **1m / 3m / 6m** 三个值，不随所选排序改变顺序，不显示周期 key。三个等宽子列右对齐，以浅色竖线分隔，所有数据行的竖线位置一致。原始 `rfl=(close/low-1)×100`：小于 100 显示最多一位小数的百分比、去掉 `.0`；大于等于 100 显示 `(1+rfl/100)`，保留一位小数和小写 `x`。例如 `65%`、`12.3%`、100% 显示 `2.0x`、130% 显示 `2.3x`。空值和非有限值显示 `—`；只改变显示，不改变原始数据、排序和筛选。
- Tags 列显示轮廓 glyph，图案、尺寸与配色统一见 [Logo / Icon](#logo--icon)。保持 **110px** 列宽下限并为编辑按钮留空隙；最多显示三个 glyph，其余用小号 `+N`，悬停列出完整剩余标签。glyph 悬停显示完整名称与人工 `today` 状态，人工补充仅当日有效，不额外使用蓝色 badge。Tags 与 `+N` 均不换行、不增加行高，不增加测宽或 ResizeObserver。
- Tags 编辑按钮不额外占数据行，hover/键盘 focus 时可见；行内编辑只提供 Setup/Label，修改当日人工补充；Hidden 不提供人工 Tag 编辑。图形外观在保存的 Tag 定义中统一编辑。
- NEW 使用 Symbol 旁的小标记，颜色与 EMA10 一致为蓝色 **#2962ff**。ticker 不显示 `.US`。不显示成员勾选框。
- Scan Price 是完成日收盘价，ADR20/MDV20 用共用日线定义。Monitor Last 是 regular 价格，Chg% 使用前一完成交易日 regular 收盘价；Ext 使用更新的 extended 报价相对 regular 收盘价，regular 时段隐藏整列（含标题和行单元），离开后恢复；非 regular 缺数据时留空。时段与 Holdings 共用服务端交易日历状态，不依赖某只股票是否已有 Quote。
- 选中、hover 与价格区域外观共用 [Symbol row template](#symbol-row-template)。操作与 Tag 编辑按钮 hover/键盘 focus 时可见；报价更新保留行结构，仅刷新值。

### Section、顺序与选择

- Discover/Focus 按保存的 **Setup** Tag 顺序分组，最后是 Unclassified；Excluded 固定 **Broken / Extended / Under-50 / Hidden**；前三类为当天候选的计算结果，仅 Hidden 保存人工屏蔽。一只股票可有多个 Tag、一个主 section。
- 置顶是独立显示状态，不是 Tag 定义或 section：每个 List 的 Pinned 区域位于该 List 所有 section 之前，支持多个 ticker；原 section 内不重复显示。取消置顶回到仍属的 section 与其原有顺序。置顶遵循 Filter 和持仓屏蔽。Scan/Monitor 共用保存顺序，置顶区可拖动及 Shift+上下重排，不受 RFL 排序影响。Monitor 只展示 Focus 的置顶区。
- Section 之间不画水平线，以标题行和间距区分。
- Scan 与 Monitor 的折叠状态独立。非搜索状态 setup 空组也显示；搜索只显示有结果的组。
- 新进入 section 的成员放**队首**，留在同组的成员保留人工顺序。人工主 section 仅当天有效，名单归属和保存顺序按 List 设计执行。
- Default order 下，允许在 Discover/Focus setup 组内及组间拖动。落点显示行前/行后线；落在组头或空组插入队首。筛选/搜索可见行作为完整组顺序的锚点，松手立即保存。
- RFL1M/3M/6M 排序仅改变显示，禁用 Scan 普通 section 人工重排；Excluded 普通分组由规则决定，不提供人工排序。置顶区顺序独立。
- 点击、键盘导航、置顶/移动后的选择处理见 [List 交互](list-interactions.md)，不在本文件重复维护。

### Tag 与 Filter 编辑

- 固定头部最后一行依次为 **Filters + 数字**、保存的 Tags 和新增按钮；Tag 加号固定在右侧，位于 Tag 横向滚动区之外，与 section 加号同一横坐标；不显示 `active`。Tags 单行水平排列，放不开时横向滚动。Setup Tags（Surf/Bounce 等）在前，Label 居中，Extended/Broken/Under-50 在后；仅改变按钮显示，不重写保存顺序或分类优先级。Tag/Filter 标签与 List 列名到下方水平线的间距使用与 Chart legend 相同的共用变量，数值在 [Chart Headers](chart-ui.md#headers-and-information) 维护。Filter 按钮展开线下编辑区，不改变顶部水平线高度；取消原 Filters/Holdings 分割线。
- 两模式使用同一套保存的 Tag/Filter。35字段目录仅包含MA arrangement和atomic feature；Price、ADR20、MDV20基础门槛只在config/scan.json配置，Tag编辑器没有Market分组。使用 **CSS 两列 columns** 布局，每组保持完整；不使用横向对齐的 grid，避免短组下面出现空白。
- 数值条件支持 Any / ≥ / ≤ / range；不同条件 AND，分类多选 OR。缺失值匹配 Any 或显式 Missing。Filter 不移动名单、不改变订阅，被筛掉的成员保留底层归属。
- Tag 用途固定为 Setup / Extended / Broken / Under-50 / Label，与名称独立；Setup 提供潜力 section，其余按 List 设计处理。Tag 名称唯一，可保存零到十个；选择按钮点击一次选中，再点击取消。没有选择时不应用保存 Tag 筛选。
- 新建克隆当前草稿条件，用途默认 Setup；未选 Tag 时从空条件编辑，可保存为新命名 Tag。条件编辑即时预览；Save 保存并折叠，Cancel 恢复。未保存时切 Tag 需明确丢弃，保存失败保留草稿；名单/排序偏好写入不得覆盖未保存的 Filter 草稿。
- Tag 外观编辑遵循 [Logo / Icon](#logo--icon)，与本章同一份 Tag 草稿一起保存或恢复；外观编辑保留已保存条件下的人工匹配成员，不切换到纯条件预览。
- 已保存 Tag 的筛选包含人工补 Tag 成员；未保存条件预览只按草稿条件判断。保存规则由后端重评已有本地数据，UI 筛选不触发下载。

### 名单行操作

- 行操作直接针对该行，Scan 提供 Pin/Unpin、Add to Focus 与按归属显示的 Hide/Release；Monitor 保持既有 Pin/Unpin、Hide。布局预留 Scan 三个、Monitor 两个圆形操作按钮。图形见 Logo / Icon，语义与反馈见 [List 交互](list-interactions.md)。
- 保存失败显示简短行内错误；未列入自动下一只白名单的外部更新、Filter、拖动等保持既有选择规则。

### Search 与 Add

见 [List 交互 / Search 与 Add](list-interactions.md#search-与-add)。加号沿用本文件 Logo / Icon 的共用样式。

### 独立 Holdings 入口

Monitor 顶部固定的持仓表、整体折叠、水平 overflow、列与格式、买卖明细、排序、选择和状态的唯一要求见 [Holdings UI](holdings-ui.md)。当日新仓复用List的NEW标记；账户总值与延迟时间显示也只在该入口维护。

### Scan 日期与准备状态

- Scan 使用截至所选日的完成 Daily，Focus 也用同一来源，无活跃 candle 或 Intraday，最新日仅叠加Longbridge最新报价的一个价格轴标签（含Overnight），历史日隐藏。图表显示所选日期；正常时隐藏独立准备状态，不重复显示 Ready 日期或完成时间。

- Monitor双图在最新报价来自扩展时段时显示价格轴标签，Intraday最新值保留原生candle价格；缺少新报价保留最后值，不增加时段提示，仅显示price，外观及刷新规则见Chart UI，数据范围见Longbridge说明。
- 日期下拉仅列已生成日。Refresh Scan 补齐并打开最新可用日，与正在查看的历史日期无关；已完成的步骤跳过，全部完成仍切回最新日。自动完成保留历史选择和展示模式，新日按 List 生命周期继承；手动 Refresh 即使跳过数据准备，也按 [List 每日规则](list-design.md#每日规则) 清理人工状态并重新分类。配置变更/指定日重算仅由CLI处理。
- 未完成、处理中或失败时才显示目标日期与当前阶段，例如 Downloading daily / Updating splits / Building daily bars / Building features，失败详情放悬停；旧日期和结果继续可查看。准备中禁用重复 Refresh，但允许切换模式。GET、选图、Filter 和切页不触发下载。
- 实时报价失败或连接中断复用图表现有质量图标与悬停原因，不改变 Scan 完成状态、不阻止本地日 K 展示；有效价格轴标签的外观只在 [Chart UI](chart-ui.md#colors-margins-and-reference-lines) 维护。

## Data and simulator boundaries

- One same-origin WebSocket carries initial/selection/reconnect snapshots and subsequent updates. HTTP serves assets, universe and read-only diagnostics; POST /v1/list performs edits. POST /v1/mode, /v1/scan and /v1/preferences handle mode, generation/date and saved Tags. Independent list messages refresh membership even without chart selection. A chart GET must not change selection priority.
- Chart context checks, local/derived history and status boundaries follow [Chart UI](chart-ui.md#data-boundaries).
- Monitor closed-bar refresh continuity and Vol readout semantics follow [Chart UI](chart-ui.md#headers-and-information) and [Mouse, zoom and periods](chart-ui.md#mouse-zoom-and-periods).
- Simulator uses the same UI, scheduler and validation against temporary data with an instance exchange clock. It never reads credentials or falls back to a broker. SIM and MOCK are offline fixtures, not live evidence.

## Checks

Run `npm run build --prefix ui` after TypeScript edits and only the related offline checks. Validate affected layout, List interactions or chart gestures; do not broaden to a live/full workflow without authorization. Record coverage and limitations in [validation.md](validation.md).

### Intraday State 图形与颜色

价格、量能与未读的共同外观只在 [Symbol row template](#symbol-row-template) 与 [Color palette](#color-palette) 维护；业务阈值见 [Intraday State](intraday-state.md)。ADR以↑/↓加倍数表达方向，tooltip保留两项数值。量能以 Volume Base / Low / Medium / High 表示等级，普通至二级文字用 Volume High，三级用 White，不与价格方向混色。

## Trade UI

第三模式与独立持仓/交易交互唯一规范见 [Schwab Trade MVP](schwab-trade.md)。保留当前布局、共用 Symbol row template、palette 和表格风格；Scan/Monitor 原有显示不变。Trade 的 Net Liq 沿券商字段，Avg Price 仅展开详情显示。

### Trade 图形

Buy 使用 Blue、Stop 使用 Red，Daily/Intraday 均在 K 线和指标下方绘制细实线；使用公开 primitive 的 bottom 层，实线宽度为一个物理像素（Retina 也不增粗），右轴原生标签只显示价格。横线上不常驻 Buy/Stop、数量、Auto/Draft/Awaiting 或把手。直接命中横线后显示上下调整光标；重合线可再次点击轮换。手动 Alert 保留原虚线与悬停胶囊，双方共用坐标换算、命中范围和横线 renderer，编辑/提交规则独立。多个真实订单分别绘制；未激活或不可编辑订单不可拖动。绘制与命中使用公开 API，不修改 vendor。

交易区报价突出价差百分比，右侧同一列上方为蓝色 Ask、下方为红色 Bid，绝对差值在 Bid 右侧底部对齐，不重复文字标签；绝对差值使用 Muted 灰色，百分比平时黑色，宽价差时仍按 Schwab Trade 配置使用主红粗体。其他报价正常字重，图上 Buy/Stop 线继续使用主蓝/主红。Buy/Sell 为与Send等高的整体胶囊，保留原宽度和水平位置：Buy 共享标题下显示小写 stop / market，左右垂直切分为两个全高度点击区域；标题仅为装饰、不截获点击。Buy 的上下区域按60:40分配，标题在上区水平和垂直居中。选择任意买入方式后，整个 Buy 使用统一深色背景和白字，只显示所选 stop/market，未选类型文字隐藏；隐藏文字保留原点击区域与宽度，可以直接切换模式，hover不改变统一背景。不恢复下方文字小胶囊；浏览时内部白色分隔线从标题下方开始，两侧小字朝中线对称靠拢，文字共同略向上做视觉对齐，为下伸字形保留底部空间，不改变按钮布局或点击区域；Buy激活后隐藏内部线。Buy 和 Sell 标题放大加粗，stop/market 保持正常字重。Sell 位于右侧，以全高度白线分隔。Auto 沿用 Logo / Icon 的圆形回转箭头；Send 保持模式胶囊的尺寸，去掉外圈留白，深色背景填满整个胶囊，与新单/真实止损改价共用同一个入口，和 Buy/Sell 拉开距离。卡片所有操作均无悬停说明。数量为细黑直线、仅保留带数值的大刻度和简洁滑柄，数值在L端上方、无输入框，不显示Qty文字；滑动完全使用浏览器原生 range 行为，始终保留普通鼠标指针，不增加指针捕获、隐藏或左右调整箭头。浏览时隐藏内容但固定位置不变。下方数量、预估和按钮自底向上排布，按钮贴住固定底边；增大行距只让数量和预估向上移动，顶部报价独立定位。数量、预估与Buy/Sell保持原宽度整体左移，使右端按Send的矩形本体视觉对齐；Auto/Send及报价不动。Schwab 明细沿用 Holdings 行高与字体，每条 Buy/Sold/Entry/Stop 单行排列；金额、P/L%和P/L对齐主行，数量、价格及撤单顺序右移，具体列与字段口径只在 Schwab Trade 维护。Entry/Trim 使用现有小号 symbol-flag 文字风格，不增加色块。订单取消沿用 Logo / Icon 的红底白色 ×。字号、对齐、间距与头部位置只在 [Chart UI](chart-ui.md#trade-mode) 维护。

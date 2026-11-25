# UI layout and interactions

Updated: 2026-11-25. This file is the UI entry point and the only current specification for shared layout, List UI and Logo / Icon. General Chart and Holdings details are maintained only in [chart-ui.md](chart-ui.md) and [schwab.md](schwab.md). Alert interactions and lifecycle are maintained only in [alert.md](alert.md). The product UI is English only. List lifecycle and classification rules are maintained in [list-design.md](list-design.md); backend behavior is maintained in [behavior.md](behavior.md), with Holdings data requirements in [schwab.md](schwab.md).

## Layout

- Monitor has Daily, Intraday and List panels; Scan has Daily and List. Panel width rules are defined once in **List UI / 宽度与视觉** below.
- No application header, brand, global instrument banner or footer. Chart-owned headers follow [Chart UI](chart-ui.md#headers-and-information).
- White floating cards with generous corners on a neutral background. Black header/column rules and divider handles; internal chart panes follow [Chart UI](chart-ui.md#colors-margins-and-reference-lines).
- Search, period selector, price-session labels and resize handles use pills.

## 金额格式

- 前端美元金额统一省略 `$`，包括名单、交易和持仓界面、图表坐标轴、十字线标签及 tooltip。
- MDV20 在 Scan 列表和 Daily 图表使用 `K/M/B` 等紧凑单位，四舍五入至整数。Dollar Vol 使用相同单位，固定一位小数。精度只作用于显示。

## Chart UI

Chart layout, colors, margins, [headers and metric typography](chart-ui.md#headers-and-information), [turnover readout and five-day comparison](chart-ui.md#turnover-comparison), [Daily setup scale, coupled zoom, Reset and F overview](chart-ui.md#daily-setup-scale), linked trading day and status are maintained in [chart-ui.md](chart-ui.md). Longbridge cache freshness is defined only in [longbridge-data.md](longbridge-data.md); refresh uses a weak status hint while existing charts and valid values remain visible. Optional company names, concise category labels, market cap and earnings are governed by [Additional Info](additional-info.md), independently of chart data and Ready. All charts use the same manually adjustable default spacing; normal visible history depends on that spacing and panel width.

## Alert UI

Scan/Monitor 图表设置、横线操作、统一未读提醒与后台声音的唯一详细要求见 [alert.md](alert.md)。图形及其颜色只在本文件下方 [Alert 图形](#alert-图形) 维护；加入 Focus 的分类规则见 [List 入选规则](list-design.md#统一移入-focus)。当前实现为公开series primitive、图表手势与Regular内持久未读状态；所有选图/当前chart更新统一已读，收盘清理。未读跳转与保留Tag筛选的规则见[List交互](list-interactions.md#未读-alert-导航)。

## Intraday State UI

独立需求、ADR字段、CumVol/LocalVol Badge和In Play自动聚集只在 [intraday-state.md](intraday-state.md#展示与-in-play) 维护。复用现有section，无展示模式选择；空section整个隐藏，全表空时只显示一份空状态。Holdings列与批次见 [schwab.md](schwab.md)。

Focus、活动 Entry 和真实余仓共用 ADR、CumVol 与 LocalVol 显示规则。各字段独立显示，缺失或原始倍数 ≤0.5 时留空，量比徽标同时隐藏。该阈值仅用于盘中字段显示。

## Color palette

共享颜色速查，2026-10-29 对照当前 CSS、Chart 与 Tag 默认值整理。英文名用于需求沟通；代码的唯一默认色值来源为 `ui/src/palette.ts`，Chart、Tag 默认值与 Symbol 模板直接复用，`installPalette()` 将同一份值安装为 `--color-*` CSS 变量。颜色对应的业务条件仍由各模块唯一需求文档维护。

| 名称 | 色值 | 当前用途 |
| --- | --- | --- |
| Blue / 主蓝 | `#2962ff` | EMA10、5D Avg 超均值强调、MA10 Tag、NEW、上行增强底色 |
| Blue Soft / 浅蓝 | `#e8f1ff` | 上行关注底色 |
| Yellow / 主黄 | `#e4b400` | EMA20、MA20 Tag、Pre 价格标签 |
| Yellow Text / 黄文字 | `#b89100` | Chart EMA20 图例文字；比主黄深 |
| Yellow Soft / 浅黄 | `#fff3c4` | 回撤预警底色 |
| Red / 主红 | `#e53935` | SMA50 / SMA65、MA50 Tag、近期待发布财报 |
| Red Strong / 深红 | `#b42318` | 回撤紧急底色、Alert 错误文字 |
| Positive / 上涨文字 | `#008f83` | Holdings 正向涨跌及盈亏数字 |
| Negative / 下跌文字 | `#df4543` | Holdings 负向涨跌及盈亏数字 |
| Candle Up / 上涨柱 | `#26a69a` | 上涨 K 线与成交量柱；现有 CSS 变量 `--up` |
| Candle Down / 下跌柱 | `#ef5350` | 下跌 K 线与成交量柱；现有 CSS 变量 `--down` |
| Tag Neutral / 中性线条 | `#64748b` | 无 MA 关联的默认 Tag 线条、近期已发布财报、纯 Entry 的常态 ticker |
| Volume Base / 量能普通 | `#f4f5f7` | 普通量能 Badge 底色 |
| Volume Low / 量能一级 | `#e5e7eb` | 一级量能底色，也用于默认 Tag 毛玻璃底色 |
| Volume Medium / 量能二级 | `#cbd2db` | 二级量能底色 |
| Volume High / 量能三级 | `#374151` | 三级量能底色、普通至二级量能文字 |
| Ink / 黑 | `#000000` | 选中轮廓、Active Alert 线、Overnight 价格标签 |
| White / 白 | `#ffffff` | 卡片底色、强状态底色上的文字 |
| Muted / 已触发灰 | `#9ca3af` | Triggered Alert 线与操作控件 |
| Pane Divider / 分隔线灰 | `#c6cbd1` | Chart pane 分界线和 Holdings Total 上沿 |

“亮蓝”目前就是 Blue，没有独立的第二个高饱和蓝。主红、回撤深红、下跌文字红和下跌柱红是不同用途；讨论改色时使用上表的完整名字。涨跌文字在强蓝/深红状态底色上沿用白字，不能强行保留红绿而降低可读性。用户保存的 Tag 自定义颜色优先于默认值。

## Symbol row template

背景与设计哲学：在有限行高中突出 Symbol、价格和有效提醒，减少无效数字与装饰。Chart 采用大圆角容器，名单采用胶囊；共用颜色与轻阴影语言，按信息密度调整阴影强度。行的选择、实时价格状态、最新未读报警分别表达，不增加新的选中模式或点击区域。

- Focus、Holdings、Discover、Excluded 共用左右留白、Symbol 文字起点和整行边界。灰色悬停底与黑色选中轮廓使用同一行壳，文字起点独立于胶囊边界。方向键选股由整行接收键盘焦点，选中轮廓同时表示行焦点。Tab 聚焦操作按钮时使用按钮焦点提示。键盘选股时暂停鼠标悬停外观，鼠标移动或按下后恢复。
- Web 行高 28 px。价格胶囊左端、上、下内缩 3 px，右端由列定义划定。末位铃铛为 24 px 点击区和 22 px 可见圆面。价格胶囊的左端和铃铛圆面分别与外框对应端同心。1 px 选中描边内侧各留约 2 px。行位置和尺寸由 Grid 布局确定，状态和波浪随价格胶囊一起裁切。
- 价格区域为连续胶囊。Monitor Focus 覆盖 Symbol、Last、Chg%、ADR；非 Regular 的 Ext 也属于价格区域。Tags、量能与操作独立。Scan 保持自身数据列，使用相同模板，不为两种量能重排列。Holdings 的区域边界只在 [Schwab 持仓 UI](schwab.md#列与格式) 维护。
- 底色及文字始终表达当前实时状态。Blue Soft / Blue 对应上行关注／增强，Yellow Soft / Red Strong 对应回撤预警／紧急。强蓝、深红价格区域使用白字。Candidate Chg% 使用 Positive / Negative，强底色时继承白字。其他字段保持本色。
- 最新未读用价格胶囊两侧横向流动的渐变波浪表达。浅底上的上行关注用 Blue 与 White 的 68% 混色，上行增强用 Blue，回撤预警用 Yellow，回撤紧急用 Red Strong。深底使用对应方向的浅色波浪以保留对比。同方向的紧急未读与强底色同时存在时，波浪用 White。
- 整条使用一份长边渐变遮罩。当前 Web 波浪每 2.8s 平移一个周期。持续流动时，白色波浪的遮罩峰值与波浪层自身的不透明度均为 100%。其余波浪的遮罩峰值为 48%，波浪层自身的不透明度为 85%。遮罩均向内 6px 淡至透明，中央保留实时底色。外层胶囊自然裁切。音频每声通过同一入口触发一次短亮度脉冲，播放结束后保留流动波浪。
- 仅 symbol 主行承载提醒，section、Holdings 标题、Buy/Sold 明细及 Total 不聚合提醒。已读、期限与声音行为只在 [Alert](alert.md#统一未读提醒) 维护。
- Web 共用 `symbol-row.ts` 的 Grid 表头与主行，列配置指定字段、宽度和价格区边界。悬停、选中与提醒是独立绘制层，行及各字段坐标保持稳定。`attention.ts` 应用最新提醒及节拍。Chart 与行阴影分别由 `--panel-shadow` 和 `--row-shadow` 定义。原生端按平台适配绘制，保留上述语义。

## Logo / Icon

本章统一维护 Tag 图案、操作/状态图标和未来主站/应用 Logo 的当前要求。Android 原生 App 是后续确定目标，iOS 也可能接入；图形含义、配色和操作语义应可复用，平台绘制与交互方式分别实现。这里不维护废弃方案，也不定义 Tag 的判定条件；规则见 [list-design.md](list-design.md)。

### 通用原则

- 区分度优先，图案应让人迅速联想到形态或操作；使用有代表性的轮廓，避免装饰细节。Tag 是辅助信息，不能用大面积亮色背景干扰 Symbol、价格和 Growth。
- Tag、操作图标、品牌 Logo 属于不同用途，不强制共用尺寸或背景。小图形的可视尺寸与按钮的可操作区域分开管理。
- 每种图案保留明确含义；完整名称、操作说明和状态不能只靠图形或颜色表达。Web 为图标提供可访问名称，原生端按平台提供可触摸的查看方式。

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

- 主景线条颜色和背景颜色可调。MA10 默认蓝 **#2962ff**，MA20 默认黄 **#e4b400**，MA50 默认红 **#e53935**，无 MA 关联默认中性 **#64748b**。例如 Surf-10 / Bounce-10 同为蓝线，Surf-20 为黄线；用户保存的颜色优先。颜色只用于展示。
- 背景可选全透明或极浅毛玻璃；默认极浅灰 **#e5e7eb** 毛玻璃胶囊，无 border。保持低 opacity，主景线条承担识别作用；平台不支持模糊时可呈现极浅灰。
- List 中图形容器高度为行字体的 **0.9 倍**，宽高比 **1.5**。当前 Web 字体 12px，对应高 **10.8px**、宽 **16.2px**。行内数量与列宽见 [List UI / 行与格式](#行与格式)。
- 每个新 Tag 都绑定图案与外观；可先用 `label`，以后更换。外观独立于名称、用途和条件，改名不重新推断已保存图案。新增专用图案时更新本表与实现，保持已有 Icon ID 的含义。
- Tag 编辑草稿提供 **Icon / Line color / Background style / Background color** 和实时 preview。与名称、用途、条件一起 Save / Cancel，不增加单独的保存流程。旧 Tag 仅在前端初始化缺失外观，下次偏好保存持久化，不因打开页面重写偏好。

### 操作与状态图标

以下为当前图形及对应含义；更换绘制方式不能改变行为。名单生命周期见 [list-design.md](list-design.md)，图表错误含义见 [Chart status](chart-ui.md#chart-status)。

| 场景 | 当前图形 | 含义 |
| --- | --- | --- |
| 各 List 置顶 | 向上箭头推至顶线，置顶后蓝色、改为向下取消箭头 | Pin / Unpin：仅改变当日显示位置，保留 section |
| Discover 行操作 | 轮廓垃圾桶 | Hide：人工屏蔽七个自然日 |
| Focus / Hidden 行操作 | 列表轮廓和向外箭头 | Release：移出 Focus 或结束人工屏蔽 |
| Focus / Holdings 自动报警 | 圆形按钮，启用时为铃铛，暂停时为红色斜杠铃铛，铃身轮廓在斜杠两侧留出细缝 | 仅在行选中、悬停或获得焦点时显示启用图案。暂停图案持续显示。两种状态共用一个位置 |
| Section 新增股票 / 新建 Tag | `+` | 按所在控件明确新增目标 |
| Section / Holdings / 交易明细 | `▸` / `▾` | 已折叠 / 已展开，点击切换，不改变名单归属 |
| Holdings 列排序 | 列名下的小三角 | 当前降序列，排序只改变显示 |
| Schwab 展开明细 | 灰色空心圆 / 实心圆 | 空心表示买入侧 Buy / Entry，实心表示卖出侧 Sold / Stop |
| Schwab 活动订单 | 红底圆形按钮内白色 `×` | 取消指定订单；Entry/Stop 的目标规则见 Schwab 账户与交易 |
| Trade Auto | 浅灰圆形按钮内线性 `↺` | 恢复两条参考线的自动标价；自动时灰色禁用，手动拖价后蓝色可点，无悬停说明 |
| Daily / Intraday | `↦` | Reset view & go to latest，重置本图；R 重置全部可见图，见 [Chart 交互](chart-ui.md#mouse-zoom-and-periods) |
| 图表 / 名单 / Holdings 错误 | 轮廓圆圈内的 `!`，暖黄色 | 提供当前错误详情，不扩展错误判断范围；Holdings 点击详情见独立 UI 规范 |

- 垃圾桶保持简单线性轮廓；当前 Web 行按钮为 **24×24px**，图形 **16×16px**，默认灰色，hover 时使用浅红背景与红色线条。键盘 focus 也可显示行操作。原生端需单独适配触摸操作区域与可见性。
- Schwab 展开明细圆点为 5px，使用 Muted 灰色。空心圆为 1px 轮廓和白色中心，实心圆使用 Muted 填充。圆点从可访问树隐藏。树线与缩进只维护在Schwab 账户与交易，不加入图标库或节点坐标计算。
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

Chart标记使用简单的应用层绘制，悬停胶囊使用少量应用层 DOM，视觉对照 TradingView macOS 客户端，不引入图标库、不修改 chart vendor。Alert 垃圾桶复用既有线性轮廓，但其含义是删除 Alert；名单垃圾桶表示移入 Hidden，Release 向外箭头表示释放归属，方向箭头表示加入 Focus；动作在 [List 交互](list-interactions.md) 维护。网页准确使用上述图形；声音由后台播放，状态和错误遵循 Alert 需求。各操作提供英文可访问名称，具体处理语义只在 [alert.md](alert.md) 维护。

Symbol 未读图形统一使用 [Symbol row template](#symbol-row-template)，与 Chart Alert 水平虚线是不同用途。

### 品牌与平台实现

- 当前没有主站/应用品牌 Logo，不新增页头、页脚或品牌占位。未来主站 Logo、Android/iOS 应用图标的设计统一补充本章，正式需求确定后再制作。
- 关闭图表供应商的画布 Logo；第三方 LICENSE/NOTICE 和 attribution 保留在独立静态 `/licenses.html` 页面。
- 当前 Web 的 Tag 图案与默认外观集中在 `ui/src/tag-appearance.ts`，列表和编辑 preview 共用；样式在 `ui/public/style.css`，行操作在 `ui/src/list.ts`，持仓图标在 `ui/src/schwab-holdings.ts`，图表按钮在 `ui/public/index.html`。保存字段契约见 [development.md](development.md)。
- SVG path、viewBox、CSS、blur 和 `title` 属于当前 Web 实现。迁移到原生端时复用图案含义、轮廓和已保存外观，按平台适配密度与触摸交互；不把 Web px、DOM 或 hover 当成原生端实现契约。

## List UI

本章是唯一当前 List UI 规范，覆盖 Scan、Monitor 的观察名单；独立持仓表只在 [Schwab 持仓 UI](schwab.md) 维护。名单分类与生命周期见 [list-design.md](list-design.md)，导航、移动、搜索和操作反馈只在 [List 交互](list-interactions.md) 维护；显示、筛选和格式化不改变名单归属或行情订阅。

### 宽度与视觉

- 扣除工作区内边距和间距后，List 默认占可用面板宽度 **32%**，最小 **680px**；其余空间由当前可见图表等分，一个图占满、多个图始终等宽。每个图至少 **320px**；Monitor 的 Intraday 票据需要 540px，因此双图均至少 540px。分配函数按图表数量和各组件最小宽度计算，不为模式维护不同分配算法。数值统一维护在 `layout.ts`。
- 图表之间保留 12px 间距，图表组与 List 之间共用一个 12px 分隔条。拖动时各图等宽，名单弹性列压缩到列定义允许的最小宽度。打开页面、切模式或双击分隔条恢复默认比例。当前可见列及 Holdings 的自然内容共同约束最小宽度。低于整体工作区的最小宽度时工作区维持其最小尺寸，名单数据区域平铺。
- Scan 头部与左图分界等高，高度见 [Chart UI](chart-ui.md#headers-and-information)。Monitor 的头部按内容高度排布。Scan／Monitor 按钮等宽，与 ET 同行，Search 保持整行。观察名单列头固定在自身纵向滚动区顶部。
- 原 Intraday 时间模块统一移到 List 右上角，与 Monitor / Scan 模式按钮垂直居中、同排显示；使用12px、#293341、26px行高和右侧12px内距。继续读取现有 view.server_time 并显示纽约时间及 ET，不新增时钟请求或定时器。
- 名单按钮、section、Holdings 和结果数使用独立的 10 px 黑色常规字计数。Scan 结果数在模式按钮旁，Monitor Focus 结果数紧跟 Symbol 列头。Filter 条件数继承 Filter 按钮的字号和颜色。

### 展示范围与控件

| 模式 | 名单 | 数据与控件 |
| --- | --- | --- |
| Scan | Discover / Focus / Excluded 三个入口 | 本地 Massive Daily、日期、Refresh、RFL 排序、名单操作、Tag/Filter |
| Monitor | 上卡为模式工具栏和 Holdings，下卡为 Focus | 实时 Daily/Intraday、Search、名单行操作 |

- Scan 顶部分界线上方的末行左侧为 Discover / Focus / Excluded，右侧为透明背景的日期下拉与 Refresh。日期文本用与 Tag 一致的小号中性灰，日期和 RFL 下拉共用小 V 指示。准备阶段在中部显示。分界线下方依次为 Filter/Tag 工具栏、可展开的编辑区及列头。
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
- Scan 与 Monitor 共用 Tags 弹性列宽，最小 **80px**，伸展权重 **0.45fr**。列头留空。按规则结果顺序靠左平铺前四个只读图标，图标间隔 **3px**，距列左缘 **4px**。每行首个图标对齐，Ext 与首个图标之间留 **16px**。无 Tag 时留空。图标提供可访问名称，行内仅显示图标。图案、尺寸与配色见 [Logo / Icon](#logo--icon)。
- NEW 使用 Symbol 旁的小标记，颜色与 EMA10 一致为蓝色 **#2962ff**。ticker 不显示 `.US`。不显示成员勾选框。
- Scan Price 是完成日收盘价，ADR20/MDV20 用共用日线定义。Monitor Last 是 regular 价格，Chg% 使用前一完成交易日 regular 收盘价；Ext 使用更新的 extended 报价相对 regular 收盘价，regular 时段隐藏整列（含标题和行单元），离开后恢复；非 regular 缺数据时留空。时段与 Holdings 共用服务端交易日历状态，不依赖某只股票是否已有 Quote。
- 选中、hover 与价格区域外观共用 [Symbol row template](#symbol-row-template)。行操作在选中、悬停或获得焦点时可见，已置顶和已暂停自动报警的按钮持续显示。报价更新保留行结构，仅刷新值。

### Section、顺序与选择

- Discover/Focus 按保存的 **Setup** Tag 顺序分组，最后是 Unclassified；Excluded 固定 **In 14 Days / Broken / Extended / Under-50 / Hidden**；前四类为当天候选的计算结果，仅 Hidden 保存人工屏蔽。一只股票可有多个 Tag、一个主 section。
- 置顶是独立显示状态，不是 Tag 定义或 section：每个 List 的 Pinned 区域位于该 List 所有 section 之前，支持多个 ticker；原 section 内不重复显示。取消置顶回到仍属的 section 与其原有顺序。置顶遵循 Filter 和持仓屏蔽。Scan/Monitor 共用保存顺序，置顶区可拖动及 Shift+上下重排，不受 RFL 排序影响。Monitor 只展示 Focus 的置顶区。
- Section 之间不画水平线，以标题行和间距区分。
- Scan 与 Monitor 的折叠状态独立。非搜索状态 setup 空组也显示；搜索只显示有结果的组。
- 新进入 section 的成员放**队首**，留在同组的成员保留人工顺序。人工主 section 仅当天有效，名单归属和保存顺序按 List 设计执行。
- Default order 下，允许在 Discover/Focus setup 组内及组间拖动。落点显示行前/行后线；落在组头或空组插入队首。筛选/搜索可见行作为完整组顺序的锚点，松手立即保存。
- RFL1M/3M/6M 排序仅改变显示，禁用 Scan 普通 section 人工重排；Excluded 普通分组由规则决定，不提供人工排序。置顶区顺序独立。
- 点击、键盘导航、置顶/移动后的选择处理见 [List 交互](list-interactions.md)，不在本文件重复维护。

### Tag 与 Filter 编辑

- Scan 工具栏依次为 Filters 及条件数、保存的 Tags 和新增按钮。Filters 和 Tags 使用小号字，默认 Tag Neutral，Filters 展开或 Tag 选中时使用 Ink。Tag 单行排列，加号固定在右侧。Setup Tags 在前，Label 居中，Earnings/Extended/Broken/Under-50 在后。工具栏下方留 6 px，Filter 按钮展开编辑区。
- Tag 筛选和草稿只属于当前 Scan 会话，切出 Scan 即清空。保存的 Tag 定义继续用于名单分类。36 字段目录包含 MA arrangement、atomic feature 和 Earnings。Price、ADR20、MDV20 基础门槛只在 config/scan.json 配置。编辑器用 CSS 两列 columns，保持每组完整。
- 数值条件支持 Any / ≥ / ≤ / range；不同条件 AND，分类多选 OR。缺失值匹配 Any 或显式 Missing。Filter 不移动名单、不改变订阅，被筛掉的成员保留底层归属。
- Tag 用途固定为 Setup / Earnings（显示In 14 Days）/ Extended / Broken / Under-50 / Label，与名称独立；Setup 提供潜力 section，其余按 List 设计处理。Tag 名称唯一，可保存零到十个；选择按钮点击一次选中，再点击取消。没有选择时不应用保存 Tag 筛选。
- 新建克隆当前草稿条件，用途默认 Setup；未选 Tag 时从空条件编辑，可保存为新命名 Tag。条件编辑即时预览；Save 保存并折叠，Cancel 恢复。未保存时切 Tag 需明确丢弃，保存失败保留草稿；名单/排序偏好写入不得覆盖未保存的 Filter 草稿。
- Tag 外观编辑遵循 [Logo / Icon](#logo--icon)，与本章同一份 Tag 草稿一起保存或恢复；外观编辑继续使用已保存条件下的匹配结果。
- 已保存 Tag 的筛选使用规则结果和保存的条件。条件有改动时，预览按草稿条件判断。保存规则由后端重评已有本地数据，UI 筛选不触发下载。

### 名单行操作

- 行操作直接针对该行。Focus 在 Scan 和 Monitor 都预留 Pin/Unpin、Release 及暂停自动报警三个圆形按钮。Discover 与 Excluded 按归属提供 Add to Focus、Hide 或 Release。图形见 [Logo / Icon](#logo--icon)，语义见 [List 交互](list-interactions.md)。
- 保存失败显示简短行内错误；未列入自动下一只白名单的外部更新、Filter、拖动等保持既有选择规则。

### Search 与 Add

见 [List 交互 / Search 与 Add](list-interactions.md#search-与-add)。加号沿用本文件 Logo / Icon 的共用样式。

### 独立 Holdings 入口

Monitor 上卡包含模式按钮、ET、Search 和可折叠 Holdings，下卡在 Focus 表头上方留 12 px。上卡按内容排布。Holdings 字段、订单明细、Total 和折叠见 [Schwab 持仓 UI](schwab.md#持仓布局选择与自然宽度)。

### Scan 日期与准备状态

- Scan 使用截至所选日的完成 Daily，Focus 也用同一来源，无活跃 candle 或 Intraday，最新日仅叠加Longbridge最新报价的一个价格轴标签（含Overnight），历史日隐藏。图表显示所选日期；正常时隐藏独立准备状态，不重复显示 Ready 日期或完成时间。

- Monitor双图在最新报价来自扩展时段时显示价格轴标签，Intraday最新值保留原生candle价格；缺少新报价保留最后值，不增加时段提示，仅显示price，外观及刷新规则见Chart UI，数据范围见Longbridge说明。
- 日期下拉仅列已生成日。Refresh 补齐并打开最新可用日。自动完成保留历史选择和展示模式，手动 Refresh 按 [List 每日规则](list-design.md#每日规则) 清理人工状态并重新分类。配置变更和指定日重算由 CLI 处理。
- 未就绪、处理中或失败时，在名单切换与日期之间显示目标日期和阶段，例如 Downloading daily / Updating splits / Building daily bars / Building features。进行中将与左图等高的 1 px 黑色分界线呈现为无底色的不定进度线，结束后恢复实线。失败详情以悬停查看。准备中可看旧日期和切换模式，Refresh 禁用重复操作。
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

## Monitor UI

Monitor 整合 Longbridge 双图与 Schwab 持仓、提醒和交易。Holdings 复用 Symbol row template、palette 和右侧自动提醒控件。账户字段、主行标记、展开树及交易交互只在 [Schwab 账户与交易](schwab.md) 维护。

### Trade 图形

Buy 使用 Blue、Stop 使用 Red，Daily/Intraday 均在 K 线和指标下方绘制细实线；使用公开 primitive 的 bottom 层，实线宽度为一个物理像素（Retina 也不增粗），右轴原生标签只显示价格。横线上不常驻 Buy/Stop、数量、Auto/Draft/Awaiting 或把手。直接命中横线后显示上下调整光标；重合线可再次点击轮换。手动 Alert 保留原虚线与悬停胶囊，双方共用坐标换算、命中范围和横线 renderer，编辑/提交规则独立。多个真实订单分别绘制；未激活或不可编辑订单不可拖动。绘制与命中使用公开 API，不修改 vendor。

交易区报价突出价差百分比，右侧同列蓝色 Ask / 红色 Bid，绝对差灰色；百分比宽价差时主红粗体。底部蓝色 Market/Stop 与红色 Market/ATR/EMA 为两个独立单行胶囊，未选分段使用对应主色与白色混合后的浅色背景和白字，所选分段使用主色背景；悬停只加深同色背景。字体使用 semibold；所有策略名保持可见，每个分段全高度可点，不加 Buy/Sell 大标题、二层类型或悬停说明。Auto 沿用圆形回转箭头，Send 沿用现有实心模式胶囊，字体与策略按钮共用同一样式并与策略组拉开距离，统一提交新单或真实 Stop 修改。买卖共用细黑数量轴和等距档位，原生滑动使用普通指针；百分比/EMA 参数复用轴上方空间。浏览时保留布局，报价独立固定；策略组决定票据自然宽度，滑杆/预估同步向左扩展并按胶囊直线边缘对齐。首尾标签通过非对称内边距向内部直线侧做光学校正，中间分段保持居中，不增加 JS 测宽。Schwab 增加 Days/Sold 主列，Sold百分比在Symbol与Net Liq之间使用小号灰字、不显示列名；逐笔明细使用平级树线，树干对齐symbol首字母中心，数量与Sold百分比对齐，灰色日期与P/L Day列右对齐，沿用 Holdings 单行行高和财务列对齐；NEW取当天实际买入，Entry/NEW 使用小号 symbol-flag；取消按钮沿用红底白色 ×。具体几何只在 [Chart UI](chart-ui.md#trade-ticket) 维护，策略、字段和 Send 语义只在 [Schwab 账户与交易](schwab.md) 维护。

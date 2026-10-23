# UI 维护入口

先读 UI 总入口 [docs/ui.md](../../docs/ui.md)，名单改动读 [List UI](../../docs/ui.md#list-ui)，图表改动读 [Chart UI](../../docs/chart-ui.md)，持仓表改动读 [Holdings UI](../../docs/holdings-ui.md)，Alert 交互读 [docs/alert.md](../../docs/alert.md)，Tag 图案、操作/状态图标及品牌 Logo 读 [Logo / Icon](../../docs/ui.md#logo--icon)；产品分类与生命周期读 [docs/list-design.md](../../docs/list-design.md)。不要在这里复制产品数值或建立第二份 UI 规范。当前用户要求优先。

- 盘中状态另读 [Intraday State](../../docs/intraday-state.md)，`intraday-state.ts`仅负责格式化、Badge及服务端离散rank比较；In Play复用section，不改真实归属，重排保留节点/选择/焦点/滚动。Holdings当前余仓同步状态，清仓尾部保持灰色。
- `list.ts`：名单行、section、选择、拖拽、人工 Tag；`scan.ts`：两模式共用 Tag/Filter 与 Scan 批量操作及草稿编辑；`board.ts`：分组、角标和显示格式；`tags.ts`：Tag 保存与草稿比较；`tag-appearance.ts`：外观默认值、图案与共用 SVG 渲染入口。
- `layout.ts`：两模式统一的默认名单宽度比例与最小宽度；`holdings.ts`：独立持仓表；`main.ts`：模式和图表选择来源。样式在 `../public/style.css`，静态结构在 `../public/index.html`。
- Holdings数据语义只在 [Holdings 数据需求](../../docs/holdings-data.md) 维护。前端使用后端金额/基准/批次状态，按`closed_today`将当日清仓固定在灰色尾部，排序仅影响余仓；不从市值0猜测清仓，不重算会计或改变名单归属。
- `additional-info.ts`：独立信息身份校验、分类显示精简、可空格式化及纽约自然日倒计时；原始分类保留在数据契约中，数据与显示规则只读 [Additional Info](../../docs/additional-info.md)，不改变bar revision或Ready。
- `chart.ts`：共用图表、十字线与成交量显示、交易日联动；`chart-settings.ts`：统一初始 bar spacing 与成交量区比例的集中人工参数。修改参数后构建并刷新页面，不增加设置界面。
- 图表调整首先遵守 [Chart 首要开发准则](../../docs/chart-ui.md#implementation-principle)，优先内置参数和公开 API，保持 vendor 源码原样。
- 名单归属、自动标签、Hidden 期限由后端计算；自动 Excluded 仅当天候选可见，成员新出现只显示 NEW 标记。Filter、格式化和拖拽显示不能扩大行情订阅，也不能改变底层增长数值或计算口径。
- Tags 使用纯 SVG 轮廓；图形与外观只维护在 Logo / Icon，行高、列宽与折叠数量只维护在 List UI。新增图案保持已有 Icon ID 的含义，列表与编辑 preview 复用 `tag-appearance.ts`。不恢复文字堆叠或人工蓝色 badge，不引入图标库、测宽监听或另一套外观保存流程；前端初始化旧 Tag 缺失的外观，下次偏好保存才持久化。外观草稿不切换到纯条件预览，不改后端分类默认逻辑。
- 图标不能改变操作语义：名单垃圾桶是移入 Hidden 七天；Release 仅用于 Hidden，Add to Focus 遵循统一入选规则。后续 Android/iOS 按 Logo / Icon 复用图形与外观契约，按平台实现触摸与可访问说明；Web 的 DOM、hover、CSS 与 px 不是原生实现要求。不提前建设移动端原生工程；Alert 声音由后台播放，前端显示持久未读边框及实际错误。
- Monitor 的 Focus 与 Holdings 保留独立 selection source；Scan 日 K 统一使用本地 Massive Daily，最新报价仅作为一个独立价格轴标签。全局 Search 新股进入当日 Discover 置顶，复用 add/Pin，不建立临时预览系统。维持 request_id、mode、source 和 socket 身份检查。
- Scan Daily及Monitor双图统一使用后端`quote.latest`，颜色直接读取trade_session，不据时钟推断来源或另选报价；无新报价保留最后值，无时段/陈旧提示。扩展报价不更新volume或candle；Intraday最新值保留Monitor原生candle标签。
- TS 源码是维护入口；在项目根目录用 `npm run build --prefix ui` 生成对应 public JS，不直接修改生成 JS。保留图表 vendor 文件与许可。
- Alert 创建价格取鼠标水平线，Scan/Monitor 共用 symbol 归属；UI 不计算名单分类或直接请求券商，入选 Focus 交由同一后端操作完成，详细规则不在这里重复。
- `alerts.ts`：公开图表primitive、手势、mutation和错误；`attention.ts`：仅symbol row的统一未读/播放边框，不聚合标题；`main.ts`：主动row点击成功选图后read，自动选择不read。API持久化结果才更新横线，row已读不改变灰线或generation，不建倒计时删除。
- 只验证本次改动相关的离线场景；live 必须有明确范围与时限。同步唯一 UI 文档和必要产品文档，不新增交易入口、Atomic feature 自动 Alert 或通用框架。

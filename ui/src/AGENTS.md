# UI 维护入口

先读 UI 总入口 [docs/ui.md](../../docs/ui.md)，名单改动读 [List UI](../../docs/ui.md#list-ui)，图表改动读 [Chart UI](../../docs/chart-ui.md)，持仓表改动读 [Holdings UI](../../docs/holdings-ui.md)，Tag 图案、操作/状态图标及品牌 Logo 读 [Logo / Icon](../../docs/ui.md#logo--icon)；产品分类与生命周期读 [docs/list-design.md](../../docs/list-design.md)。不要在这里复制产品数值或建立第二份 UI 规范。当前用户要求优先。

- `list.ts`：名单行、section、选择、拖拽、人工 Tag；`scan.ts`：两模式共用 Tag/Filter 与 Scan 批量操作及草稿编辑；`board.ts`：分组、角标和显示格式；`tags.ts`：Tag 保存与草稿比较；`tag-appearance.ts`：外观默认值、图案与共用 SVG 渲染入口。
- `layout.ts`：两模式统一的默认名单宽度比例与最小宽度；`holdings.ts`：独立持仓表；`main.ts`：模式和图表选择来源。样式在 `../public/style.css`，静态结构在 `../public/index.html`。
- Holdings数据语义只在 [Holdings 数据需求](../../docs/holdings-data.md) 维护。前端使用后端金额/基准/批次状态，按`closed_today`将当日清仓固定在灰色尾部，排序仅影响余仓；不从市值0猜测清仓，不重算会计或改变名单归属。
- `chart.ts`：共用图表、十字线与成交量显示、交易日联动；`chart-settings.ts`：统一初始 bar spacing 与成交量区比例的集中人工参数。修改参数后构建并刷新页面，不增加设置界面。
- 图表调整首先遵守 [Chart 首要开发准则](../../docs/chart-ui.md#implementation-principle)，优先内置参数和公开 API，保持 vendor 源码原样。
- 名单归属、自动标签、排除期限由后端计算。Filter、格式化和拖拽显示不能扩大行情订阅，也不能改变底层增长数值或计算口径。
- Tags 使用纯 SVG 轮廓；图形与外观只维护在 Logo / Icon，行高、列宽与折叠数量只维护在 List UI。新增图案保持已有 Icon ID 的含义，列表与编辑 preview 复用 `tag-appearance.ts`。不恢复文字堆叠或人工蓝色 badge，不引入图标库、测宽监听或另一套外观保存流程；前端初始化旧 Tag 缺失的外观，下次偏好保存才持久化。外观草稿不切换到纯条件预览，不改后端分类默认逻辑。
- 图标不能改变操作语义：名单垃圾桶是七天排除，Release 和 Add to Focus 遵循名单生命周期。后续 Android/iOS 按 Logo / Icon 复用图形与外观契约，按平台实现触摸与可访问说明；Web 的 DOM、hover、CSS 与 px 不是原生实现要求。本版本不新增原生工程。
- Review 只预览本地 Massive Daily；同 ticker 的 Holdings 通过独立 selection source 使用实时图。维持 request_id、mode、source 和 socket 身份检查。
- TS 源码是维护入口；在项目根目录用 `npm run build --prefix ui` 生成对应 public JS，不直接修改生成 JS。保留图表 vendor 文件与许可。
- 只验证本次改动相关的离线场景；live 必须有明确范围与时限。同步唯一 UI 文档和必要产品文档，不新增 Alert、交易入口或通用框架。

# UI 维护入口

先读 [docs/ui.md](../../docs/ui.md)，名单改动重点读其中唯一的 **List UI** 章；产品分类与生命周期读 [docs/list-design.md](../../docs/list-design.md)。不要在这里复制产品数值或建立第二份 UI 规范。当前用户要求优先。

- `list.ts`：名单行、section、选择、拖拽、人工 Tag；`scan.ts`：两模式共用 Tag/Filter 与 Scan 批量操作；`board.ts`：分组、角标和显示格式。
- `layout.ts`：两模式统一的默认名单宽度比例与最小宽度；`holdings.ts`：独立持仓表；`main.ts`：模式和图表选择来源。样式在 `../public/style.css`，静态结构在 `../public/index.html`。
- 名单归属、自动标签、排除期限由后端计算。Filter、格式化和拖拽显示不能扩大行情订阅，也不能改变底层增长数值或计算口径。
- Review 只预览本地 Massive Daily；同 ticker 的 Holdings 通过独立 selection source 使用实时图。维持 request_id、mode、source 和 socket 身份检查。
- TS 源码是维护入口；在项目根目录用 `npm run build --prefix ui` 生成对应 public JS，不直接修改生成 JS。保留图表 vendor 文件与许可。
- 只验证本次改动相关的离线场景；live 必须有明确范围与时限。同步唯一 UI 文档和必要产品文档，不新增 Alert、交易入口或通用框架。

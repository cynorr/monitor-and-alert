# List UI

先读 `../../docs/list-design.md` 与 `../../docs/ui.md`。产品规则以最新用户要求为准。

- `list.ts` 管行、section、选择、拖拽与人工 Tag；`scan.ts` 管共用 Tag/Filter 编辑和 Scan 批量操作；`board.ts` 只提供分组辅助。
- 列表归属、自动标签、排除期限由后端计算；Filter 只改变显示，不能触发行情订阅。
- Monitor 仅展示 Focus、独立 Holdings 与默认折叠的 Review；Review 是本地 Massive Daily 预览，不发券商查询。
- 同 ticker 一个名单行、多标签、一个主 section；新进入 section 的成员由后端放队首。
- 修改后运行 `npm run build --prefix ui`，只验证相关离线场景。不要新增 Alert 或交易入口。

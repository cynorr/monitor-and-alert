# List 后端维护入口

先读项目根入口；List 需求以 [docs/list-design.md](../docs/list-design.md) 为准，Massive 特征范围以 [docs/massive-data.md](../docs/massive-data.md#名单完整特征范围) 为准。

- `workspace.py` 管三名单归属、顺序、迁移与同步保存；`list_rules.py` 只做纯条件匹配和分类，不请求行情。
- `preferences.py` 与前端共用 `filter-catalog.json`；Tag 的 `role` 决定用途，名称可以改。
- 实时名单只含 Focus；Holdings 由独立模块补入。Review 使用本地 Daily，不授权券商请求。
- Focus 和全部 Excluded（含 Hidden）均计算完整特征；Hidden 七天内仅跳过名单规则判断。Review 不要求每日清空；新进入 section 的成员在队首。
- 日分类改动优先跑 `tests/test_list_rules.py` 和相关 Workspace 离线用例，不为此连接真实券商。

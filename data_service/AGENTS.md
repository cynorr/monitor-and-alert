# 数据模块维护入口

先读项目根入口与 [开发准则](../docs/development-principles.md)；Longbridge需求只在 [docs/longbridge-data.md](../docs/longbridge-data.md) 维护；List需求以 [docs/list-design.md](../docs/list-design.md) 为准，Massive特征范围以 [docs/massive-data.md](../docs/massive-data.md#名单完整特征范围) 为准，Holdings数据需求只在 [docs/holdings-data.md](../docs/holdings-data.md) 维护。Alert 需求见 [docs/alert.md](../docs/alert.md)，模块维护另读 [alerts/AGENTS.md](alerts/AGENTS.md)。

Additional Info 的唯一需求见 [docs/additional-info.md](../docs/additional-info.md)，维护模块前另读 [additional_info/AGENTS.md](additional_info/AGENTS.md)。

- `workspace.py` 管三名单归属、顺序、迁移与同步保存；`list_rules.py` 只做纯条件匹配和分类，不请求行情。
- 手动与 Alert 移入 Focus 共用 [统一入选规则](../docs/list-design.md#统一移入-focus)；不继承来源 Tag/人工 section，不由 Alert 另写分类逻辑。
- `preferences.py` 与前端共用 `filter-catalog.json`；Tag 的 `role` 决定用途，名称可以改。
- 实时名单只含 Focus；Holdings 由独立模块补入。Review 使用本地 Daily，不授权券商请求。
- Focus 和全部 Excluded（含 Hidden）均计算完整特征；Hidden 七天内仅跳过名单规则判断。Review 不要求每日清空；新进入 section 的成员在队首。
- 日分类改动优先跑 `tests/test_list_rules.py` 和相关 Workspace 离线用例，不为此连接真实券商。
- `snaptrade.py`只获取原始账户数据；`holdings.py`统一买卖归属、余仓估值、当日清仓与日期规则；`workbench.py`复用共用Quote基准和时钟。HTTP/UI不另算会计，不通过其他历史ticker扩大范围。
- Holdings修改优先核对现有真实快照/服务，仅补充相关`test_holdings.py`和`test_holdings_integration.py`；失败保持已接受快照，不增加轮询任务或恢复框架。

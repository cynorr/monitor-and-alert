# 数据模块维护入口

先读项目根入口与 [开发准则](../docs/development-principles.md)；Longbridge需求只在 [docs/longbridge-data.md](../docs/longbridge-data.md) 维护；List需求以 [docs/list-design.md](../docs/list-design.md) 为准，交互见 [docs/list-interactions.md](../docs/list-interactions.md)，Massive特征范围以 [docs/massive-data.md](../docs/massive-data.md#名单完整特征范围) 为准，Holdings数据需求只在 [docs/holdings-data.md](../docs/holdings-data.md) 维护。Alert 需求见 [docs/alert.md](../docs/alert.md)，模块维护另读 [alerts/AGENTS.md](alerts/AGENTS.md)。

Additional Info 的唯一需求见 [docs/additional-info.md](../docs/additional-info.md)，维护模块前另读 [additional_info/AGENTS.md](additional_info/AGENTS.md)。

- `longbridge/`仅含官方SDK入口、实时订阅与历史获取/检查；`monitor.py`组合行情、名单及盘中状态；`massive/pipeline.py`管理Massive准备任务。共享Bar、持久化和OHLC诊断集中在`storage.py`，图表序列与指标缓存集中在`chart_cache.py`，来源包不作为共用工具入口。

- 显式 Refresh 与跨日首次分类共用人工状态清理，不重复准备 Ready 数据；清理后 Focus 接受自动淘汰。普通重分类与用户 Refresh 分开，详细边界见 List 设计。
- `workspace.py` 管三名单归属、顺序、迁移与同步保存；`list_rules.py` 只做纯条件匹配和分类，不请求行情。
- 手动与 Alert 移入 Focus 共用 [统一入选规则](../docs/list-design.md#统一移入-focus)；不继承来源 Tag/人工 section，不由 Alert 另写分类逻辑。
- `preferences.py` 与前端共用 `filter-catalog.json`；Tag 的 `role` 决定用途，名称可以改。
- 完整实时行情只含Focus与独立Holdings；Scan/Monitor始终为完整Discover/Excluded保留Quote-only订阅，切模式不退订。Daily 仍读 Massive，不授权其 Trade/candle 或 Alert。Quote开启Overnight，统一latest按timestamp选价，来源直接保留trade_session，无新价保留最后值；范围只在 Longbridge 数据要求维护。
- Longbridge SDK 保留当天完整周期序列，ChartCache统一叠加官方closed；图表、指标与盘中状态共用该读取结果。同日恢复只用SQLite成功批次/最新closed判断缺口，不能用SDK暂定行跳过官方修正；全量窗口就绪后替换旧值，刷新/恢复期间保留有效显示。接口与生命周期只在Longbridge数据要求维护。
- 候选、当日人工 Discover、Focus 和有效 Hidden 计算完整特征。只继承 Focus 和有效 Hidden；机器 Excluded 为当天候选的派生结果，不保存成员身份。Focus 仍每日自动淘汰；已非候选的淘汰成员直接退出。Hidden 七个自然日内跳过分类；到期非候选退出。新进入 section 的成员在队首。
- 日分类改动使用 `tests/test_list_rules.py` 的现有真实截面/名单及真实 SQLite 做定向验证；不为此连接真实券商或建立 Mock。
- `snaptrade.py`只获取原始账户数据；`holdings.py`统一买卖归属、余仓估值、当日清仓与日期规则；`workbench.py`复用共用Quote基准和时钟。HTTP/UI不另算会计，不通过其他历史ticker扩大范围。
- Holdings修改优先核对现有真实快照/服务，仅补充相关`test_holdings.py`和`test_holdings_integration.py`；失败保持已接受快照，不增加轮询任务或恢复框架。

- Schwab Trade 的唯一规范为 [docs/schwab-trade.md](../docs/schwab-trade.md)。schwab_backend.py 维护原交易内核；trade.py 只投影独立账户/订单并复用严格模型，不读取 SnapTrade 账本、不增加写重试。Workbench 管理第三模式、生命周期与当前账户风险角色；旧项目后端设计保留。

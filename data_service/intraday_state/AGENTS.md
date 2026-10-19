# Intraday State 模块入口

先读项目[README](../../README.md)、[开发准则](../../docs/development-principles.md)、[独立需求](../../docs/intraday-state.md)与[实现契约](../../docs/development.md#intraday-state-实现)。用户当前要求优先；本文件不复制阈值、颜色或UI数值。

- engine.py管理Regular symbol状态、独立规则穿越及稳定排序等级；volume.py管理同源分钟量区间覆盖和历史插值。函数直接互调，不建策略/adapter/repository框架。
- 只消费DataService已有Quote、SDK candle与closed缓存；不引入broker、下载、第二个context或服务。订阅范围只在Longbridge需求维护，不把Scan Quote-only成员提升为完整行情。
- ADR复用现有百分数公式、截至昨日并当日固定；EMA复用图表当前preview。上下行各自判断触发，显示回撤优先不能制造新的上穿。
- 新增、恢复或角色改变首状态静默；降级无声音。状态缺失不能当作正常或零；原始OHLC仍遵守项目数据校验，不自行修正。
- volume区间核心来自旧ChartCache.closed_volume，只生成标量，不恢复旧活跃K线合成或落盘。历史每个日期完整覆盖后再均值，不混Quote/Daily量与分钟量。
- 同symbol共用状态；当前余仓角色由Workbench提供，当日清仓只复盘。Workspace/List持久归属仍由原模块管理，排序只是展示投影。
- 不逐份Quote写库，不做补报、故障注入、回放或下单。手动线生命周期独立；自动转换调用AlertEngine.notify，共用持久未读与独立声音，不直接调用播放器。
- 配置在config/intraday-state.json，启动直接读取；前端intraday-state.ts负责格式化与离散rank比较，list.ts用In Play复用section，holdings.ts维持独立排序；两者保留节点、选择与焦点，不重新计算业务规则。
- 只跑本次必要定向验证，真实范围/时限明确。同步独立需求、development、对应UI入口与validation，不把离线结果当作实盘或macOS27证据。

# Intraday State 模块入口

先读项目[README](../../README.md)、[开发准则](../../docs/development-principles.md)、[独立需求](../../docs/intraday-state.md)与[实现契约](../../docs/development.md#intraday-state-实现)。用户当前要求优先；本文件不复制阈值、颜色或UI数值。

- engine.py管理Regular symbol状态、独立规则穿越及稳定排序等级；volume.py管理同源分钟量区间覆盖和历史插值。函数直接互调，不建策略/adapter/repository框架。
- 只消费DataService已有Quote与ChartCache统一序列，不区分SDK/历史来源；相关revision变化立即失效重算，不引入broker、下载、第二个context或服务。订阅范围只在Longbridge需求维护，不把Scan Quote-only成员提升为完整行情。
- ADR复用现有百分数公式，样本截至昨日，相关历史修正后重算；当日开高低/最新价用Regular Quote，不等待SDK Daily，EMA仍复用图表preview。价格与量比独立就绪，缺失字段为null；首个有效价格/EMA只建立比较起点。上下行各自判断触发，显示回撤优先不能制造新的上穿。
- 新增、恢复或角色改变首状态静默；降级无声音。状态缺失不能当作正常或零；原始OHLC仍遵守项目数据校验，不自行修正。
- volume区间覆盖只生成标量，不生成或落盘K线；按统一closed revision缓存分钟量索引，历史每个日期完整覆盖后再均值，不混Quote/Daily量与分钟量。短暂等待新根时保留有效显示，恢复只清报警比较起点。
- 同symbol共用状态；当前余仓角色由Workbench提供，当日清仓只复盘。Workspace/List持久归属仍由原模块管理，排序只是展示投影。
- 不逐份Quote写库，不做补报、故障注入、回放或下单。手动线生命周期独立；自动转换调用AlertEngine.notify，共用持久未读与独立声音，不直接调用播放器。
- 配置在config/intraday-state.json，启动直接读取；前端intraday-state.ts负责格式化与离散rank比较，list.ts用In Play复用section，holdings.ts维持独立排序；两者保留节点、选择与焦点，不重新计算业务规则。
- 只跑本次必要定向验证，真实范围/时限明确。同步独立需求、development、对应UI入口与validation，不把离线结果当作实盘或macOS27证据。

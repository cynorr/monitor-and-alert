# Longbridge 数据要求

本文件是 Longbridge 数据定位、获取、缓存与刷新规则的唯一维护入口。实现职责见 [development.md](development.md)，图表显示见 [chart-ui.md](chart-ui.md)，持仓与 Alert 的业务要求分别见 [holdings-data.md](holdings-data.md)、[alert.md](alert.md)。

## 定位与范围

Longbridge 只服务 Monitor 看盘、实时报价、持仓行情与 Alert。磁盘 K 线是可重建的近期行情缓存，不承担长期历史研究、归档、回溯或 Intraday 研究需求。

只请求和订阅当前 Focus 与当前 Holdings 的并集；同 ticker 共用底层行情。Discover、Excluded（含 Review）使用本地 Massive Daily，不扩大 Longbridge 范围。Scan/Monitor 切换仅改变展示，正式服务的 Monitor 行情、Alert 与账户刷新持续后台运行；关闭网页也不停止服务。

Scan 使用 Massive，Monitor 使用 Longbridge。两个来源分别写入自己的数据库，不拼接、不交叉校验、不互相补缺、不共用复权因子。仅共用 Bar 格式、读取、指标公式与图表。

## 官方数据与时段

- SDK 唯一入口为 `broker.py`；只订阅 Quote，K 线通过最近 K 线接口获取。
- 持久化官方 `1d / 5m / 15m / 30m / 1h`，统一显式请求 `AdjustType.ForwardAdjust` 和 `TradeSessions.Intraday`。复权完全由 Longbridge 提供，读取、指标及显示不再复权。
- Intraday 仅限 Regular：官方分钟 K、Quote 临时 K 和合成周期均遵循实际交易日历的 Regular 开闭市边界；盘前、盘后、夜盘 Quote 只用于报价与持仓估值。
- 只存 closed 官方柱，过滤 forming 柱；接受不足 1000 根的短历史。官方成交量保留非负整数，turnover 可为空。
- `2h / 4h` 从官方 5m 在内存合成。`15m / 30m / 1h` 的官方缺柱可用同一内存合成补充显示，官方值优先；合成与临时柱不落盘，不扩展缓存的时间跨度。

供应商参数见 [官方最近 K 线接口](https://open.longbridge.com/docs/quote/pull/candlestick)。共用字段及原值校验见 [Bar 契约](upstream-daily-data.md)。

## 缓存与提交

`runtime/longbridge/bars.sqlite3` 保留逐根 `bars` 表，主键为 `(symbol, timeframe, ts)`。每个 symbol、官方周期是一份独立的当前窗口；`batches` 仅保存其最新成功请求信息。

全量刷新请求 `count=1000`。先获取、解析和校验响应，确认最新应闭合目标存在，再用一次普通 SQLite 提交删除该 symbol、该周期的旧行并写入本次有效 closed 柱。没有成功的新窗口就不删除旧窗口；失败保留已有图表并重试。各周期独立完成，不等待全部周期一起提交。

增量只接受与当前交易日、刷新阶段相同的成功窗口；尚未初始化或阶段不匹配时直接安排全量。正常收盘更新使用 `count=2`，覆盖并追加有效 closed 柱。1000 是全量请求数量，不是缓存或图表读取上限；盘中允许自然增长，下次成功全量刷新直接替换。无需计数裁剪、历史拼接、分页、offset 或历史连续性检查。

同时退出 Focus 与 Holdings 的 symbol 停止任务与订阅，不主动追删磁盘缓存；重新加入时全量初始化，成功前已有缓存仍为待刷新数据。

## 全量刷新时机

| 时机 | 处理 |
| --- | --- |
| 启动、重启 | 当前所有 symbol、官方周期立即全量初始化 |
| 新加入或重新加入实时范围 | 该 symbol 的全部官方周期全量初始化 |
| 连续运行进入新的美东交易日 | 立即刷新完整窗口；不按机器本地日期判断 |
| 当日初始化在 Regular 开盘前完成 | 实际 Regular 开始时再全量刷新一次，不等待第一根 5m 收盘 |
| 当日首次初始化已在盘中或盘后 | 不额外安排开盘刷新 |
| 重连、休眠恢复、错过多个闭合边界、请求或数据失败 | 使用同一近期窗口回补任务 |

盘前开机立即初始化，不设置开盘前一小时的额外任务。休市日沿用上一个交易日的刷新阶段，不安排每日定时重建；开机初始化仍正常执行。交易日、DST、提前收盘均由现有 XNYS 日历决定。

请求开始与结束跨越交易日或 Regular 开始边界时，该响应不提交，立即按新阶段重拉。业务假定 Regular 开始后的官方复权基准在当日稳定，因此成功初始化后可正常使用 `count=2`；不增加公司行动服务或自行计算复权。

## 调度、失败与状态

订阅恢复和到期 closed 更新优先，其次选中 symbol 的 5m、Daily 与所选官方分钟周期，其余按 5m、Daily、15m、30m、1h 推进。每根闭合后 2 秒开始正常更新。全局每秒最多 10 次请求、5 个在途；后台全量最多每秒 8 次、3 个在途，同一 symbol、周期不重复下载。

首次失败后最多再重试三次，间隔 2 / 5 / 10 秒；本轮耗尽则显示原因，下一实际 5m 收盘后 2 秒开启最多三次的新一轮。每个失败周期独立处理，其他行情任务继续运行。成功清除错误；只检查最新应闭合目标，不追查历史断档。SDK 负责底层连接恢复，应用保留现有重新订阅、30 秒 snapshot 与开市 Quote watchdog。

刷新优先立即回补，不中断最新 Quote、Alert 或持仓刷新。旧缓存可继续展示，并以弱提示 `Refreshing` 表示尚未完成；Daily + 5m 成功后为基本 Ready，五个官方周期成功后为完整 Ready。正常增量的等待不重置 Ready。

未完成当前阶段刷新时，不把旧历史与当前 Quote 临时柱或其他已刷新周期合并，也不用旧 Daily 修正当天涨跌幅及持仓日基准。最新 Quote 自带的有效前收价可继续使用。图表读取、选择和诊断接口只读，不触发下载。

# Longbridge 数据说明

本文件是 Longbridge 数据定位、获取、实时处理、缓存与刷新规则的唯一维护入口。实现职责见 [development.md](development.md)，图表显示见 [chart-ui.md](chart-ui.md)，持仓与 Alert 的业务要求分别见 [holdings-data.md](holdings-data.md)、[alert.md](alert.md)。

## 定位与范围

Longbridge 服务 Monitor 的 Daily / Intraday 图表、实时报价、持仓行情与 Alert。SQLite 是可重建的近期 closed 行情缓存。当前窗口可用于相同周期、相同 Regular 时段的盘中成交量比较；不扩展为长期历史归档或下载研究系统。

只请求和订阅当前 Focus 与当前 Holdings 的并集，含仅保留当天的已清仓批次；同 ticker 共用底层行情。Discover、Excluded使用本地 Massive Daily。Scan/Monitor 切换只改变展示，正式服务的行情、Alert 与账户刷新持续后台运行，关闭网页也不停止服务。

Scan 使用 Massive，Monitor 使用 Longbridge；两源分别存库，仅共用 Bar、读取、指标和图表。

## 官方数据与时段

| 数据 | 来源及用途 |
| --- | --- |
| Quote | 最新价、日累计量、Regular / extended 报价；服务名单、持仓估值和 Alert |
| 当前 open candle | 官方 SDK `subscribe_candlesticks`，显式 `PushCandlestickMode.Realtime`；六周期独立原始 OHLCV，仅在内存 |
| closed candle | 官方 `candlesticks`，显式 `ForwardAdjust` + `Intraday`；六周期独立保存到 SQLite |

六周期为 `1d / 5m / 15m / 30m / 1h / 2h`。图表的当前 1h 成交量直接取 SDK 1h candle，可与历史官方 1h 的同一开盘时段比较。成交量是该 candle 起点至当前收到行情的累计值；它不是最后一个 5m 的量。盘中值始终是 provisional，最终 closed 以官方历史接口为准。

`broker.py` 是唯一 SDK 入口，所有行情共用一个 `AsyncQuoteContext` 和一条行情长连接。应用订阅 Quote + Trade，SDK 在同一底层推送上更新各周期 candle。美股普通股票的分钟 candle 由 SDK 合并 Trade；Daily 由 SDK 的 QuoteDay 逻辑更新。应用直接接受 candle，不另算 OHLCV。每周期初始化会请求近期 candle 作为 SDK 起点，之后由推送连续更新；没有周期性 open candle 轮询。按当前白名单 symbol 去重，各周期共用一条连接；初始化请求受现有额度控制。

周期的网络开销主要在历史请求：每个 symbol、周期初始化包含一次 closed `count=1000` 和一次 SDK 起点 `count=1000`；恢复时重新请求。Quote / Trade 已订阅后，增加分钟周期只增加 SDK 本地计算与 callback，不增加持续行情推送流量。正常 closed 请求仅在本周期实际闭合后发送 `count=2`，不会每 5 分钟刷新全部大周期。N 个 symbol、六周期对应 12N 次周期历史初始化请求，不含共享的报价、证券信息及连接请求。

SDK 5.0.0 订阅返回的历史采用 `NoAdjust`，只接收最后一根、且属于当前 Regular 时间桶的 open candle；这些历史不能写入前复权 closed 库。当前交易日的原始 candle 与官方前复权历史连接显示，应用不二次复权。SDK 的 `is_confirmed` 也不触发落盘，仍等待正式 closed 请求。

Regular 边界由 XNYS 日历决定，包含 DST、提前收盘及尾根。盘前、盘后和夜盘 Quote 只用于报价与持仓估值。OHLC 须为正数有限值，volume 须为非负整数，turnover 可为空；时间戳须符合官方周期的 Regular 网格。仅 OHLC 上下界矛盾保留官方原值，追加 `invalid_ohlc.jsonl`，不改价、不告警、不重试。共用字段见 [Bar 契约](upstream-daily-data.md)。

### 已确认的数据特性

Daily / Quote 日累计量与分钟 candle 的统计口径不同，不能要求同一开盘时长总量相等。2026-10-07 Regular 的原始响应中，BMNR 当天 Daily / Quote 为 8,787,839，首根尚未闭合的 1h 为 3,333,474，且该 1h 等于同一响应中当天 5m 的总量。差额的供应商内部成交分类尚未确认；Daily 与 Intraday 各自按官方口径比较。

SDK 初始化位于时间桶中途时，与最终 closed 可有小差异。2026-10-07 11:30–11:35 ET 的 5m 对照：

| Symbol | SDK volume | 官方 closed volume | 差额 | 占 closed |
| --- | ---: | ---: | ---: | ---: |
| BMNR | 125,255 | 125,324 | 69 | 0.055% |
| MU | 196,359 | 197,163 | 804 | 0.408% |

两者 OHLC 相同。重构代码连续完整接收的 12:10–12:15 ET 桶，BMNR 为 99,281 / 99,281，MU 为 259,532 / 259,532，OHLC 也相同。这些样本说明 SDK open 值适合实时监控，不能据此保证所有 open 值与最终 closed 完全一致；不增加应用补偿。

拒绝非法时间戳行；重复时间戳的全部行也拒绝，不从冲突记录中任选一根。保留有效官方数据；当前成功 batch 明确保存 `rejected`，同窗口增量继续保留这些诊断，图表状态显示原因。最新应 closed 目标必须有效且存在，否则整个请求失败并回补。不会移动时间戳、制造替代 bar 或用别的周期填入。最近 1000 的响应允许短历史及历史缺口。

依据：[官方最近 K 线接口](https://open.longbridge.com/docs/quote/pull/candlestick)、[SDK 5.0.0 candle 初始化、推送与恢复实现](https://github.com/longbridge/openapi/blob/v5.0.0/rust/src/quote/core.rs)。

## 缓存与提交

`runtime/longbridge/bars.sqlite3` 的 `bars` 主键为 `(symbol, timeframe, ts)`，只保存官方 closed；每个 symbol、周期维护独立窗口。`batches` 保存最新成功请求的阶段、时间、数量及拒绝行诊断。

全量 `count=1000`：先获取并校验，确认最新 closed 目标存在，再用一次 SQLite 提交替换该 symbol、周期的旧窗口。失败保留旧数据。正常 closed 更新在闭合后 2 秒请求 `count=2`，覆盖并追加有效 closed 行；只对当前交易日、刷新阶段的成功窗口使用增量。1000 是请求数量，盘中缓存可自然增长，下次成功全量直接替换。

## 初始化与恢复

| 时机 | closed 窗口 | SDK 实时 candle |
| --- | --- | --- |
| 启动、重启 | 当前全部 symbol、六周期全量初始化 | 订阅六周期，接收当前 open 起点及持续推送 |
| 新加入或重新加入范围 | 该 symbol 六周期全量初始化 | 增加该 symbol 的 Quote / Trade 与六周期订阅 |
| 新美东交易日、盘前初始化后的实际开盘 | 全量刷新 | 重新初始化订阅起点 |
| 应用重连、休眠恢复或调度时间跳跃超过 30 秒 | 全量回补 | 清掉 active，退订再订阅 candle，取得新起点 |
| 请求失败、缺少最新 closed、错过多个 closed 边界 | 相应周期近期窗口回补 | 保持已有实时订阅 |

重复调用已订阅周期会得到 SDK 内存历史，因此恢复必须先退订 candle，再订阅；同一 context 中完成，不创建第二条行情连接。只清掉内存 active，图表保留上一份完整显示直到新数据就绪。SDK 自动恢复底层短暂断线；应用保留开市 90 秒 Quote watchdog 与 30 秒 Quote snapshot。SDK 没有公开连接恢复回调，短暂内部重连不等于重新初始化 candle，期间丢失的成交可能影响 provisional 值，闭合后仍由官方 closed 替换。

移出 Focus 与 Holdings 的 symbol 停止任务与全部订阅，清掉内存显示，不主动追删磁盘缓存。请求跨交易日或 Regular 开始阶段时不提交，按新阶段重拉。Regular 开始后的官方复权基准假定当日稳定。

## 调度、失败与状态

closed 更新优先，其次选中 symbol 的 5m、Daily 与所选周期，其余按 5m、Daily、15m、30m、1h、2h 推进。全局每秒最多 10 次请求、5 个在途；后台全量最多每秒 8 次、3 个在途，同一任务不重复下载。

closed 首次失败后最多再试三次，间隔 2 / 5 / 10 秒；耗尽显示原因，下一实际 5m 收盘后 2 秒开启最多三次的新一轮。实时订阅失败按 symbol / 周期显示原因，现有行情循环每 30 秒重试未成功的订阅；成功清除对应错误。

Daily + 5m closed 窗口成功后为基本 Ready，六个官方周期成功后为完整 Ready。历史拒绝行和实时订阅错误另行显示，Ready 不表示数据供应商全部历史无异常。正常增量等待不重置 Ready；全量期间旧图继续显示 `Refreshing`。每个图表只依赖本周期的 closed 窗口及 SDK open，5m 回补不阻塞 Daily。

跨周期边界，先等本周期官方 closed 替换与下一根可用 open，再一次发布完整图表；最终 Regular candle 也等官方替换后退出 active。只更新尾部，不先清空最后一根。未完成当前阶段的旧 Daily 不修正当天涨跌幅或持仓基准。图表选择、读取和诊断均只读，不触发下载。

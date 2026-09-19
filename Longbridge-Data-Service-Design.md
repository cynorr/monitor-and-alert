# Longbridge Data Service 开发规格

## 1. 目的

建立一个个人使用的行情数据服务，用于：

- 实时看盘
- Volume Alert
- Lightweight Charts 数据源
- 为后续策略提供稳定、可靠的历史行情

规模：

- 通常监控 20–30 个 ticker
- 当前上限约 100 个 ticker
- 单用户
- 运行于个人 macOS / Linux 机器
- 稳定性和数据可靠性优先于初始化速度

---

# 2. 核心原则

## 2.1 实时行情

实时行情只使用 Longbridge `Quote`。

使用：

```text
last_done
volume
timestamp
trade_session
```

其中：

```text
last_done = 当前价格
volume    = regular session 当日累计成交量
```

Volume Alert 的核心数据直接使用：

```text
quote.volume
```

禁止本地累加 Trade 或 push delta 来生成累计成交量。

不使用：

```text
Trade subscription
Depth
Broker
current_volume
sequence
```

断线后重新连接 Quote，并重新获取当前 snapshot/state。

---

## 2.2 持久化行情

SQLite 只保存 Longbridge 官方 API 返回的 authoritative closed bars。

保存：

```text
5m
15m
30m
1h
1d
```

不保存：

```text
1s
1m
2h
4h
tick
trade
provisional candle
```

2h / 4h 等由消费层按需计算，不落盘。

所有落盘数据：

```text
NoAdjust
Regular Session only
Closed Bar only
```

数据库中禁止存在正在形成中的 candle。

---

# 3. 数据可靠性状态

每个 ticker 独立维护两个状态：

```text
READY
FULL_READY
```

状态文件只是派生状态，不是数据 source of truth。

---

## 3.1 READY

`READY` 用于决定依赖历史数据的核心 Alert 是否可以启动。

必须同时满足：

### Daily

验证最近：

```text
300 个已完成交易日
```

要求这些交易日的 Daily bar 完整。

### 5m

验证最近：

```text
12 个已完成交易日
```

要求这些交易日内所有预期的 regular-session 5m bar 完整。

验证成功：

```text
ready = true
ready_through = 最近一个已完成交易日
```

只有达到 `READY` 后，该 ticker 的历史对比 Alert 才可以运行。

---

## 3.2 FULL_READY

`FULL_READY` 表示本次初始化拉取的数据已经完成全面验证。

覆盖：

```text
1d
5m
15m
30m
1h
```

每个 timeframe 冷启动时都会请求：

```text
count = 1000
```

Validator 必须验证本次返回的所有 closed bars。

即：

```text
1d  → 最多 1000 根全部验证
5m  → 最多 1000 根全部验证
15m → 最多 1000 根全部验证
30m → 最多 1000 根全部验证
1h  → 最多 1000 根全部验证
```

如果证券本身历史不足 1000 根，则验证 API 实际返回的全部 available closed bars。

验证内容：

- timestamp 合法
- timeframe 正确
- regular session
- bar 已关闭
- OHLCV 字段合法
- 按交易日历检查应有 bar 是否存在
- 不允许出现无法解释的时间缺口

全部通过：

```text
full_ready = true
full_ready_through = 最近一个已完成交易日
```

---

# 4. SQLite

使用：

```text
SQLite
WAL mode
synchronous = NORMAL
```

核心表：

```sql
CREATE TABLE bars (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,

    PRIMARY KEY (symbol, timeframe, ts)
);
```

时间：

```text
UTC Unix timestamp
```

所有写入使用 UPSERT：

```sql
INSERT ...
ON CONFLICT(symbol, timeframe, ts)
DO UPDATE ...
```

原则：

> Longbridge 本次重新下载的数据直接覆盖本地旧数据。

不需要比较新旧 candle 是否相同。

---

# 5. 每日冷启动

每次服务冷启动都执行一次 reconciliation。

正常情况下不根据 ready 日期计算复杂的增量范围。

直接重新获取最近最多 1000 根，然后 UPSERT。

这样同时完成：

- 新数据补充
- 旧数据修复
- 缺失数据修复
- Longbridge 后续修订覆盖

---

## Phase 1 — Daily

先处理所有 ticker：

```text
Daily
count = 1000
```

顺序：

```text
AAPL daily
NVDA daily
SPY daily
...
```

所有 ticker Daily 完成后进入 Phase 2。

这样前端可以最早获得长期历史数据。

---

## Phase 2 — 5m

再处理所有 ticker：

```text
5m
count = 1000
```

完成后立即执行 READY Validator：

```text
Daily 最近 300 个交易日
+
5m 最近 12 个交易日
```

通过后：

```text
READY
```

此时核心 Alert 可以启动。

---

## Phase 3 — 15m / 30m / 1h

READY 之后继续下载：

```text
15m count = 1000
30m count = 1000
1h  count = 1000
```

全部完成后运行 FULL_READY Validator。

验证：

```text
1d / 5m / 15m / 30m / 1h
本次拉取的全部 closed bars
```

验证通过：

```text
FULL_READY
```

---

# 6. 为什么冷启动重新拉 1000 根

明确采用：

```text
recent full refresh + UPSERT
```

不实现复杂增量同步。

原因：

1. 每个 ticker/timeframe 无论缺一天还是缺多天，通常都需要至少一次 API 请求。
2. 同一个 symbol 重复查询不会额外增加 unique historical symbol 数量。
3. 能自动覆盖 Longbridge 后续可能修订的数据。
4. 能自动修复数据库历史残缺。
5. 实现最简单。
6. 更容易验证。
7. 更容易从 crash、sleep、断网后恢复。

`ready_through` 主要用于：

```text
证明数据已经验证到哪里
```

而不是用于实现复杂的数据下载优化。

当前规模不需要为减少少量网络流量增加同步复杂度。

---

# 7. 初始化请求规模

一个 ticker：

```text
Daily  = 1
5m     = 1
15m    = 1
30m    = 1
1h     = 1

总计 = 5 requests
```

100 ticker：

```text
500 requests
```

默认限速：

```text
2 request / second
single worker
```
这里可以考虑适度增加并行数量，但是优先保证运行稳定。


因此理论时间：

```text
READY:
100 Daily
+
100 × 5m
=
约 200 秒

FULL_READY:
总共约 500 秒
```

初始化速度不是核心指标。

优先级：

```text
数据可靠
>
系统稳定
>
实现简单
>
初始化速度
```

---

# 8. 盘中 Closed Bar 更新

盘中 Quote 始终独立运行。

Closed bar 到达对应 timeframe boundary 后进入 BarScheduler。

例如：

```text
10:35 → 5m

10:45 → 5m + 15m

11:00 → 5m + 15m + 30m + 1h
```

盘中更新不需要重新拉 1000 根。

使用：

```text
count = 2
```

检查预期 timestamp 的 closed bar 是否已经出现。

如果 Longbridge server 尚未生成：

```text
retry
```

建议：

```text
+2s
+5s
+10s
+30s
```

成功后 UPSERT。

如果暂时失败：

```text
记录错误
继续系统运行
等待 retry 或下一次冷启动自动修复
```

Quote 和核心 Alert 不允许因为 Bar API 暂时失败而停止。

---

# 9. Closed Bar 判断

任何写入 SQLite 的 bar 必须已经关闭。

必须过滤：

```text
当前正在形成的 5m
当前正在形成的 15m
当前正在形成的 30m
当前正在形成的 1h
当前正在形成的 Daily
```

系统必须知道：

```text
bar start
bar end
market session
trading calendar
```

只有：

```text
bar_end <= 当前时间
```

并确认属于 Regular Session 后才能落盘。

---

# 10. Validator

Validator 与 Downloader 必须完全分离。

## Downloader

只负责：

```text
fetch
parse
filter closed bars
UPSERT
```

Downloader 不修改 ready 状态。

---

## Validator

只负责：

```text
读取 SQLite
检查完整性
更新 readiness
```

Validator 不负责下载数据。

---

## READY Validator

检查：

```text
Daily:
最近 300 个 completed trading days

5m:
最近 12 个 completed trading days
```

使用 trading calendar 判断：

- 正常交易日
- holiday
- early close

不能硬编码每天固定 78 根。

失败：

```text
ready 不推进
记录具体缺失
进入 repair/retry
```

---

## FULL_READY Validator

检查当前初始化过程中拉回的全部：

```text
1d
5m
15m
30m
1h
```

每种 timeframe 最多 1000 根。

验证全部 returned closed bars 的时间连续性和交易日完整性。

失败：

```text
full_ready 不推进
记录具体 timeframe / trading day / timestamp
进入 repair/retry
```

---

# 11. Readiness 文件

独立保存：

```text
runtime/data_ready.json
```

示例：

```json
{
  "AAPL.US": {
    "ready": true,
    "ready_through": "2026-09-18",
    "full_ready": true,
    "full_ready_through": "2026-09-18",
    "validated_at": "2026-09-19T12:01:32Z"
  }
}
```

这是 derived state。

如果：

```text
文件不存在
文件被删除
文件损坏
```

直接重新运行 Validator，根据 SQLite 重建。

禁止让该文件成为系统单点故障。

---

# 12. Historical Symbol Quota

独立保存：

```text
runtime/history_symbol_usage.json
```

示例：

```json
{
  "2026-09": [
    "AAPL.US",
    "NVDA.US",
    "SPY.US"
  ]
}
```

只负责记录：

```text
本自然月已经使用过历史 K-line 的 unique symbols
```

与：

```text
SQLite
Downloader
Validator
Alert
```

全部解耦。

该文件允许直接删除。

删除不会影响行情数据正确性。

---

# 13. Quote Service

Regular session 使用：

```text
Longbridge WebSocket
Quote subscription only
```

内存只维护：

```text
last_price
cumulative_volume
timestamp
trade_session
connection_health
```

核心 Volume Alert：

```text
current_day_volume = quote.volume
```

不做本地累计。

---

## 断线恢复

流程：

```text
disconnect detected

→ reconnect

→ subscribe Quote

→ 获取当前 Quote state / snapshot

→ 恢复 current price + cumulative volume

→ LIVE
```

不进行：

```text
Trade replay
sequence replay
秒级缺口恢复
```

因为业务只关心当前 Quote state。

---

# 14. Watchdog

不能只依赖 socket connected 状态。

维护：

```text
last_quote_received_at
```

市场正常交易期间，如果超过合理时间未收到任何 universe Quote：

```text
认为连接可能 stale
```

执行 reconnect。

Watchdog 保持简单。

禁止实现复杂分布式 heartbeat 系统。

---

# 15. Pre / Post / Overnight

SQLite：

```text
不保存
```

如果 UI 不需要：

```text
无需为了 extended session 单独运行历史下载逻辑
```

如果 UI 打开：

```text
Quote only
```

可以显示：

```text
price
volume（如果 Quote 已直接提供）
```

但：

```text
不落盘
不进入 READY
不进入历史 Alert
```

---

# 16. Consumer 边界

Data Service 只提供 authoritative data。

例如：

```text
5m 已下载
15m 尚未下载
```

消费层可以临时：

```text
3 × 5m → 15m
```

用于 UI 提前显示。

但该计算结果：

```text
不得写入 authoritative bars
```

官方 15m 到达以后，消费层切换到官方数据。

这属于 Consumer/UI 逻辑，不属于 Data Service。

---

# 17. 推荐模块

保持模块数量少。

```text
TickerLoader
QuoteService
BarScheduler
BarDownloader
BarStore
DataValidator
ReadinessStore
HistoryQuotaTracker
```

职责必须清晰，但不要为了“架构漂亮”继续拆更多层。

---

# 18. 代码风格

## 18.1 总原则

代码目标：

```text
简单
鲁棒
容易理解
容易维护
容易排错
```

这是个人使用项目。

禁止为了未来假想规模提前设计复杂架构。

---

## 18.2 禁止过度开发

除非出现明确业务需求，否则禁止引入：

```text
Redis
Kafka
RabbitMQ
TimescaleDB
ClickHouse
Kubernetes
Docker Swarm
负载均衡
多节点
分布式锁
微服务
event sourcing
复杂 CQRS
复杂 repository abstraction
复杂 dependency injection
```

默认：

```text
单进程
SQLite
内存状态
Longbridge SDK
简单文件配置
```

已经足够。

---

## 18.3 优先直接代码

如果一个普通函数可以完成工作：

```text
使用函数
```

不要为了抽象而创建：

```text
interface
factory
manager factory
provider factory
abstract base class
多层 wrapper
```

只有存在真实的多个实现时才增加抽象。

---

## 18.4 函数要求

函数应该：

- 名称明确
- 单一职责
- 尽可能短
- 输入输出明确
- 错误明确抛出或记录

例如：

```python
fetch_bars(...)
upsert_bars(...)
validate_ready(...)
validate_full_ready(...)
reconnect_quote(...)
```

优于模糊名称：

```python
handle_data(...)
process(...)
manager(...)
do_work(...)
```

---

## 18.5 Comment 风格

Comment 尽可能少。

代码本身可以明确表达含义时，不写 comment。

禁止：

```python
# Fetch bars
bars = fetch_bars()

# Save bars
save_bars(bars)
```

只在以下情况写 comment：

- Longbridge API 的非直观行为
- 特殊交易日处理
- retry 原因
- 容易被未来开发者错误修改的重要 invariant
- 某段代码看起来可以简化，但实际上不能简化的原因

Comment 应解释：

```text
为什么
```

而不是解释：

```text
代码正在做什么
```

---

## 18.6 Error Handling

关键外部操作必须处理失败：

```text
WebSocket connect
subscribe
Quote snapshot
Candlestick request
SQLite transaction
JSON state write
```

原则：

```text
单个 ticker 失败
≠
整个服务退出
```

失败任务记录并 retry。

数据库错误、无法启动 SQLite 等基础设施错误可以直接 fail fast。

---

## 18.7 日志

日志只保留真正有价值的信息。

建议：

```text
INFO
service start
quote connected
quote disconnected
READY reached
FULL_READY reached
cold start phase changed

WARNING
bar retry
validation gap
stale quote connection

ERROR
API repeated failure
SQLite failure
unexpected data
```

禁止每条 Quote / 每根 bar 打 INFO log。

---

# 19. 明确不实现

V1 不实现：

```text
Trade subscription
bars_1s
bars_1m
tick persistence
provisional DB bars
current_volume aggregation
sequence replay
复杂增量同步
Massive 数据拼接
分布式架构
高并发优化
负载均衡
多数据库
```

---

# 20. 最终目标

Data Service 只需要保证两件事：

## Realtime

```text
Quote 稳定
实时 price 正确
累计 volume 正确
断线后快速恢复当前状态
```

## Historical

```text
SQLite 只保存 Longbridge official closed bars
每天冷启动重新获取最近 1000 根
UPSERT 覆盖旧数据
READY / FULL_READY 通过独立 Validator 验证
任何局部缺失都可以通过重新下载恢复
```

系统设计必须始终遵守：

```text
可靠 > 简单 > 性能优化 > 架构美观
```
---

# 21. 实现审阅与已确认补充（2026-09-19）

本节修正前文存在冲突的边界；其余原则继续适用。

1. **Universe**：每次进程启动重新读取 `workspace.json`。只以 `statuses` 中 `focus` / `wait` 为准，`orders` 只排序；不订阅其他 ticker，不监控文件变化。当前为 45 个。
2. **交付范围**：本轮实现 Data Service、可验证的只读 HTTP 数据接口；看盘 UI 和具体 Alert 公式、阈值、通知另行确定。
3. **短历史降级**：用户确认，历史不足 300 日的 ticker 可按可用历史降级。保留严格 `ready`，新增 `degraded_ready`、`alert_eligible`、可用样本数。额外查询确认历史边界后才能降级，数据缺失不能作为“新股”放行。边界证明表示 Longbridge 可用历史，不等同于独立核实上市日期。
4. **盘中 5m 补拉**：正常交易日 78 根；12 日为 936 根，当日加入后最多需要 1014 根。最近 1000 根不足时，按缺失前缀补拉；补拉也进入验证。因此初始化请求量可能超过每 ticker 5 次。
5. **交易日历**：官方 trading_days 文档只保证最近一年（单次跨度不超过一月），不足以覆盖 300 交易日和 1000 根 Daily。使用支持多年历史、假期、提前收盘和 DST 的本地交易所日历。
6. **1h 边界**：实测从美东 09:30、10:30 等开始，常规收盘前最后一根为 15:30–16:00。前文 11:00 同时触发 1h 的例子不适用于本次美股数据。Daily ts 为美东零点，bar_end 为实际收盘时间。
7. **FULL_READY 范围**：允许第一根从某交易日中段开始；验证从该时间戳至拉取时应已关闭的最后一根，不误报窗口之前的正常截断。SQLite 附加保存批次边界和拒绝项，以便 JSON 丢失时重建同等语义。
8. **断线/休眠**：`count=2` 仅用于正常周期更新。跨多个周期时重新拉最近 1000 根并检查缺口；超出覆盖范围的缺口显式报告。历史错误不阻断 Quote。
9. **上游质量异常**：实测发现部分 official bars 的 open 不在 high/low 内。按原规格严格检查 OHLCV，异常不落盘、不伪造、不合成，并明确阻止受影响范围的验证通过。若以后希望放宽该规则，应单独确定业务口径。
10. **配额记录**：本地按月保存“曾尝试历史查询”的 symbol，作为保守使用记录；无法替代券商实际余额，也不因删除文件而恢复券商额度。

核对来源：
- [Longbridge Candlesticks](https://open.longbridge.com/docs/quote/pull/candlestick)
- [Longbridge Historical Candlesticks](https://open.longbridge.com/docs/quote/pull/history-candlestick)
- [Longbridge Market Trading Days](https://open.longbridge.com/docs/quote/pull/trade-day)
- [Longbridge 官方接入点](https://open.longbridge.com/docs/getting-started)
- [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars)

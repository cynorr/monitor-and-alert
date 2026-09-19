# Longbridge Data Service 开发规格

更新：2026-09-20。当前范围为图表显示所需的数据服务；完整产品要求见 [图表规格](Tradingview-Lightweight-Chart-Visualization-and-Alert-Development-Specification.md)。实现地图见 [维护手册](docs/data/README.md)。

## 1. 范围与不变量

个人使用，通常 20–30 个、约 100 个 ticker，单用户、单 Python 进程、SQLite。只负责官方行情、数据质量、内存展示数据及指标。没有下单、Price Alert 或通知。

- 启动重读 workspace.json，仅 statuses 为 focus / wait 的 ticker 可请求和订阅；orders 只排序。运行中不编辑名单。
- 唯一正式 SDK 入口为 broker.py；不在 UI 中调用券商。
- 实时仅 SubType.Quote；last_done 为最新价，volume 为官方 session 累计量，不累加 Trade/delta。
- 正式存储仅官方 NoAdjust、regular、closed 1d/5m/15m/30m/1h。
- 不保存 tick、正在形成的 candle、本地聚合 candle；不补零、不把缺口视为新股证据。
- 合法行情与派生显示数据分离；不因 UI 需求放宽 OHLCV 校验。
- 凭证不输出到日志、文档、fixture。离线测试不读 token，不自动回退真实接口。

## 2. 官方接口、连接和请求预算

复用一个 AsyncQuoteContext 承载订阅、snapshot 和历史请求。请求共享每秒最多 10 次、最多 5 个在途请求；SDK 内部仍可能延迟调用。单次请求超时 15 秒。

请求任务使用有界并发与动态优先级：

1. Quote 订阅与连接恢复及时执行；与历史请求共享全局额度。
2. 当前 ticker 的到期 closed-bar 更新。
3. 其他 ticker 的到期更新。
4. 当前 ticker 的 5m、Daily 与所选周期初始化。
5. 其他 ticker 的 5m、Daily，然后 15m、30m、1h。

已在途请求不强制中止。禁止以新建多个 context 绕过账户限额。SQLite 写入仍在单事件循环中按事务顺序执行，不让并发网络请求变成多线程数据库写入。

参考：[官方限流](https://open.longbridge.com/docs#rate-limit) · [最近 K 线](https://open.longbridge.com/docs/quote/pull/candlestick) · [历史 K 线](https://open.longbridge.com/docs/quote/pull/history-candlestick)

## 3. 初始化与持续更新

- 后端冷启动，对每个 ticker / timeframe 拉最近最多 1000 根，过滤未收盘数据后 UPSERT。
- 当前显示对象优先，不等待全 universe 的 Daily 才开始当前 5m。
- UI 后开或重开时复用运行中的后端缓存，提升当前选择的未完成任务优先级。
- Quote 与 BarScheduler 从启动就运行，历史初始化不阻断到期更新。
- 正常 closed-bar 更新用 candlesticks(count=2)，bar_end+2 秒开始请求。
- 未取得有效目标 bar 时按 2/5/10/30 秒间隔重试；耗尽后记录错误并释放任务。持续服务等待 30 秒继续补齐，无本轮同步证据时重新执行初始同步，不依赖下一边界；一次性 reconcile 在有界重试后结束。
- 跨多个周期/休眠恢复使用最近 1000 根；必要时按缺失前缀调用 history offset。无进展、上游非法或持续缺口明确失败，不伪造数据。
- 每次官方更新覆盖相同 timestamp 的旧合法记录，并使派生指标缓存失效。
- 单 ticker 请求错误隔离；SQLite 基础设施错误使服务失败退出。

## 4. 存储

SQLite WAL、synchronous=NORMAL。

bars 的主键为 (symbol,timeframe,ts)，字段：open/high/low/close、整数非负 volume、nullable turnover。

- ts 为 UTC Unix 秒。
- turnover 优先官方值；缺失/非法成交额存 null，由派生层估算并提示。
- OHLC 必须为正数、有限值，low≤open/close≤high；非法 OHLCV 不落盘并保存拒绝证据。
- 旧数据库自动增加 turnover 列，不删除、清空或重建旧行情。
- batches 保存本轮返回范围、run_id、as_of、拒绝项；后续合法修订可清除对应拒绝项。
- metadata 保存供应商可用历史边界，不宣称已独立核实 IPO 日期。
- 已移出白名单的数据库数据保留，但本轮不对外暴露，不继续请求。

## 5. 时间与交易日历

使用 exchange_calendars 多年 XNYS 日历处理假期、提前收盘与 DST。

- Daily ts 为美东零点，闭合时间为实际收市时间。
- 分钟周期从 09:30 开始；1h 尾段 15:30–16:00，提前收盘按实际边界截短。
- 不硬编码每天 78 根；1000 根窗口首日允许从中间开始。
- SDK naive 时间按机器本地时区转换为绝对时间，不直接贴 UTC。
- 只有 bar_end≤now 的官方 regular bar 才能落盘。
- UI 标签格式化使用 America/New_York，浏览器不自行判断交易时段。

## 6. 图表 readiness v2

旧的 300 日 / 12 日样本门槛、degraded_ready、alert_eligible 不再用于本版。

每个 ticker、每个 timeframe 检查：

- synced：本轮历史同步证据存在。
- target：此刻应有的最后一根 closed bar。
- latest：当前合法历史最新时间。
- loaded：完成同步并取得有效 target；可伴随更早的缺口 warning。
- ok：loaded 且验证窗口无缺口、非法或异常 timestamp。
- missing / invalid / warnings：具体质量证据。

ready 为 Daily+5m 的 ok；full_ready 为全部五周期的 ok。through 为各周期具体时间戳。目标随时间前进，不固定为进程启动时刻。

短历史允许显示与计算；不足 1000 根显示样本 warning。中间缺 K 允许降级显示现有合法数据，但 ok/ready 不伪造为 true。最新目标缺失继续显示加载。

检查缓存按数据 revision、最新闭合目标和 run_id 失效；HTTP 请求不重复全量扫描不变数据。verify 从 SQLite 和批次证据重建，不能混合初始化 run。data_ready.json 是可删的派生文件。

正常提示 5 秒后消失；后台仍检查。已进入正常运行的周期，bar_end 超过 15 秒尚未获得有效 bar 时显示 warning，恢复后清除。初始旧历史补齐只显示加载。

## 7. Quote 与连接恢复

- regular/extended 独立内存分桶；输出时间戳、接收时间、来源与连接健康。
- 拒绝倒序 timestamp、非法价格/volume 和明显未来时间。
- 订阅后获取 snapshot，解析 regular、pre/post 及可用 overnight 字段。
- 每 30 秒 snapshot 补足 SDK 内部自动重连后的状态。
- regular 开市时持续没有 universe 推送，由 watchdog 触发重新订阅与 snapshot，SDK 负责底层连接恢复。
- 少量股票不成交不能单独判为整个连接断线；休市无推送不显示休市状态或误报断线。
- 不存 tick、不录制/回放、不还原断线期间每笔交易。

## 8. 内存图表数据与指标

charts.py 管理当前 5m 以及较大周期活跃 candle，indicators.py 提供唯一指标实现。

- 首条区间内 last_done 初始化 OHLC；缺失 open 可用当前首价，不回补未收盘 5m 内部行情。
- 较大周期由官方已收盘 5m + 当前临时 5m 合并，只在内存展示。
- 官方闭合数据到达后替换该位置、重算活跃较大周期及指标。
- volume 用官方累计量减当前区间之前完整的当日官方 5m 总量。前缀缺失/已知拒绝时不显示差值，负数不伪造为零。
- EMA10/20、SMA50 使用对应周期 close，包含当前预览；每条 Quote 从上一根 closed 基准计算，不累加 EMA 状态。
- ADR20 = mean((high-low)/low)×100%；ADV$20 优先官方 turnover，退化为 volume×(open+close)/2。
- ADR/ADV 只用最近 20 个已完成交易日窗口内有效数据；不足/缺失提示 ticker warning。
- 数据持久化只有一份 SQLite，不建指标数据库。价格不复权，不实现公司行动调整。

## 9. HTTP 与 WebSocket

API 与前端静态文件由本机 aiohttp 服务提供，默认 127.0.0.1:8765。同源部署，WebSocket 校验 Origin。

保留 health/universe/quotes/bars；readiness 为 v2。新增 chart 完整快照与 stream 长连接。详细请求契约见 README。

- 初始化、切换、重连获取完整图表快照。
- 常规事件发送当前 candle、指标预览和状态；历史 revision 改变才重发历史序列。
- request_id 防止快速切换时旧响应覆盖当前图，断开后重新取得快照，不维护复杂事件日志。
- UI 停止不影响后端数据流程；慢浏览器发送任务不阻塞行情回调。

## 10. 配额、模拟与验收

history_symbol_usage.json 保守记录每自然月已尝试历史请求的 symbol，不是券商额度余额，删除不能重置券商限额。

独立 simulator 继续只提供 Quote JSON，删除该目录不影响正式 data。生产服务不导入模拟器、不使用模拟分支绕过校验。

默认测试离线，不连接券商。浏览器测试夹具仅位于 tests/，数据与数据库为临时合成样本，不是正式行情或新增模拟器能力。真实接口测试需独立明确范围与时限；历史实测报告不代表本轮已 live 验证。

# 开发维护手册

更新：2026-09-23。此文件供 Codex/Claude Code 和维护者使用；产品行为以 [behavior.md](behavior.md) 为准，UI 以 [ui.md](ui.md) 为准。历史证据见 [validation.md](validation.md)。

## 文件与依赖

| 文件 | 唯一职责 |
| --- | --- |
| data_service/__main__.py | CLI、单实例锁、生命周期、有限运行报告 |
| config.py | 启动白名单、凭证读取、错误脱敏 |
| broker.py | 单 SDK context、最近 K 线、Quote 请求、全局/后台请求预算 |
| calendar.py | UTC/ET、XNYS、实际闭合边界、5m 到 4h 时间网格 |
| downloader.py | 每次一页 fetch/parse/validate/写入，追加 OHLC 比较日志 |
| store.py | 官方 bars、最近窗口批次、事务及 revision |
| validator.py | 最近窗口完整性检查与缓存；不联网、不写状态文件 |
| service.py | 每个 ticker/官方周期一份 SyncState，排序、执行、重试、恢复；API 组合 |
| quotes.py | 共用 Quote 标准化入口、时段最新值、snapshot/watchdog、恢复通知 |
| resample.py | 所有内存周期合成的唯一算法 |
| charts.py / indicators.py | 活跃 candle、官方/合成显示、图表缓存；唯一指标公式 |
| http_api.py | aiohttp 静态页面、只读 HTTP、WebSocket/Origin 校验 |
| ui/src/main.ts / types.ts | WS 选择与重连、列表、显示状态、契约 |
| ui/src/chart.ts / layout.ts | Lightweight Charts、日联动、列宽和原生交互 |
| simulator/market.py / server.py | 隔离历史/Quote/时钟，复用正式流程，单一网站入口 |
| scripts/live_check.py | 明确执行的有界 live 验收；临时库、单连接 |

依赖方向：UI → Data API → service/charts → store/quotes；正式 data 不 import simulator。不增加 services 层、指标数据库或事件日志协议。

## 同步与状态

`service.sync[(symbol, timeframe)]` 是唯一任务记录。首次 pending+refresh；执行时 refresh 为 count=1000，其余 count=2。请求返回后使用同一窗口验证。正常完成记录 target，调度器发现新闭合目标时入队；跨多个闭合边界、Quote 恢复或循环暂停超过 30 秒重新请求最近 1000。

失败原地重试，首次最多 4 次请求，耗尽后下一个实际 5m 收盘+2 秒开启最多 3 次的新一轮。状态查询不改变任务。重连到达在途请求期间不能被该请求完成覆盖。reconcile 共用调度器，所有任务完成或本轮耗尽即退出。

全局滑动窗口 10 次/秒、5 在途；后台历史 8 次/秒、3 在途。等待后台额度不持有 limiter 锁；后台信号量在全局信号量之前取得。调度器也不提前发起超过 3 个后台历史任务，保留两个可插队槽。Quote 请求和正常到期更新走全局预算。

UI 契约仅 `status: {stage: loading|basic|full, errors: string[]}`。stage 根据五份任务最近的成功状态派生；每根正常新 bar 的 2 秒等待不会重置 Ready。未完成/恢复失败不宣称已验证。详细 `complete/target/latest/count/missing/errors` 只在诊断接口提供，不再暴露旧六组 readiness 标记。

## 存储与数据校验

SQLite WAL/NORMAL，bars 主键 (symbol,timeframe,ts)，只允许 1d/5m/15m/30m/1h。OHLC 必须正数有限；volume 必须非负整数；必须 regular 且已经闭合。唯一 range 检测是 `Bar.invalid_range`，仅用于 downloader 的 JSONL 追加。不得 clamp 原值。

旧库保留，turnover 缺列时仅 ALTER ADD COLUMN。batches 继续使用旧表结构，run_id 列留空字符串以兼容旧表；payload 仅保存最近窗口起点、请求/返回数量、as_of 和无法使用的返回项。旧 metadata 表不再读取/维护，也不破坏已有表。旧 data_ready.json / history_symbol_usage.json 均不再读取或更新。

count=1000 返回确定新的 window_start；count=2 延续窗口。实际读取最多最近 1000 根并过滤起点之前的旧记录。历史空档不检查；缺失仅检查最新应闭合目标。重复/无法绘制的修订撤下旧值，合法新值可恢复；仅 range 矛盾永不撤下。

官方数据值实际改变才增加 bars revision；批次/质量变化增加质量 revision。图表比较最终显示序列，内容未变不重发。validator 按质量 revision 和当前目标缓存结果，HTTP 不重复扫描不变数据。返回数据逐根合法性检查在数据变化后执行；不建立持久化完整性水位。

## 合成和时段

resample 接受统一 5m 行结构，按 calendar 网格分组，O首/H最大/L最小/C末，量与额相加。闭合组必须有齐全的 5m 槽；活跃组可展示当前近似值。按交易日分组，处理 DST、提前收盘、常规尾根。2h/4h 从不读取官方 1h 作为基础，也不发额外历史请求。

15m/30m/1h 显示按 timestamp 合并“5m 合成 + 官方优先”，官方到达即通过现有 revision 消息替换。5m 临时 candle 从本进程收到的第一条 Quote 起算；更大活跃 candle 也复用 resample。合成和临时 candle 绝不写入官方 bars。

Quote 接收不按 UI 选择筛选；regular/pre/post/overnight 共用 apply，按时段保留最新值。snapshot 归一化后走同一入口。倒序拒绝、旧 callback 代次保护继续保留。扩展时段只改价格展示，不改 regular candle。

## 传输

同源 HTTP 静态资源与 `/v1/universe`；`/health`、`/v1/quotes`、`/v1/bars`、`/v1/readiness`、`/v1/chart` 为只读诊断。`/v1/chart` 不改变优先级。

UI 图表只通过 `/v1/stream`：select 消息含 symbol/timeframe/request_id。初次、选择、重连为完整 bars+指标；常规只传 active/indicator_preview/status，历史改变才重发。约 5Hz 图表预览、1Hz 列表。run_id 标识后端实例，request_id 与 socket identity 防止串图。保留 heartbeat、慢客户端独立发送任务和 Origin 校验；不新增差量重放协议。

## 检查与真实测试

```bash
.venv/bin/python -m pytest -q
npm run check --prefix ui
npm run build --prefix ui
```

默认测试全部离线，只绑定本机 HTTP/WS，覆盖白名单、日历、OHLC 原值/日志、无法绘制的输入、最近窗口、次数/5m 重试、恢复、限流、合成、指标和模拟器跨边界/交易日。测试数量会随删除旧需求测试而变化，不与历史通过数量直接比较。

live 需确认没有另一正式实例占用账户连接，再明确当前 focus/wait 子集与时限：

```bash
.venv/bin/python scripts/live_check.py --symbols PAYS --duration 60
```

脚本使用当前白名单、一个 context、独立临时 SQLite 和 JSONL，输出 report.json 路径；只读行情，不交易。默认不会自动执行。不要把模拟通过描述成 live 通过，不把历史记录当本轮证据。

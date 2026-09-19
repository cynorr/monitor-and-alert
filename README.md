# Longbridge Data Service

个人使用、单进程、SQLite 的美股行情服务。当前交付数据层和只读 HTTP 接口，尚未实现看盘网页、Alert 策略或通知渠道。

## 启动

Python 3.11+，macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m data_service universe
.venv/bin/python -m data_service serve
```

在项目目录执行。每次进程启动重新读取 `workspace.json`，只接受 `statuses[ticker].status` 为 `focus` / `wait` 的 ticker；`orders` 只决定顺序。`hidden`、`carried`、仅出现在排序列表中的 ticker 不会加入订阅。运行中不监控文件变化，更新后重启生效。默认绑定 `127.0.0.1:8765`。

默认使用官方 `.cn` 接入点。需要全球接入点（包括 Longbridge 美国账户）时加 `--region global`。凭证由现有 `longbridge-token.txt` 读取，格式为 `App Key`、`App Secret`、`App Token` 各占一行，下一行对应值；代码和日志不输出这些值。

```bash
# 只测试当前白名单的子集，不能添加白名单之外的 ticker
.venv/bin/python -m data_service serve --symbols PAYS BLSH --duration 60

# 一次冷启动同步及有界重试后退出
.venv/bin/python -m data_service reconcile

# 完全离线：从 SQLite 重新验证并重建 data_ready.json
.venv/bin/python -m data_service verify

.venv/bin/python -m pytest -q
```

`--workspace`、`--credentials`、`--runtime` 可指定路径；`--port` 可改端口；前端跨域访问时可设 `--cors-origin http://localhost:3000`。同一 runtime 只允许一个实例，避免重复订阅。退出码 0 表示本次所有 ticker 均有完整或降级历史可用，且 FULL_READY；2 表示同步完成或测试结束但存在未通过验证的数据；1 表示启动错误。

## 数据接口

以下 API 都只接受启动时的 focus/wait symbol；无 Longbridge 查询透传入口。

| 接口 | 返回内容 |
| --- | --- |
| `GET /health` | 初始化阶段、Quote 健康状态、推送计数、历史错误 |
| `GET /v1/universe` | 本次加载的 ticker 和 status |
| `GET /v1/quotes?symbol=PAYS.US` | 各 session 的最新价、官方累计量、UTC Unix 时间戳；省略 symbol 返回全部 |
| `GET /v1/readiness?symbol=PAYS.US` | 从 SQLite 重算的验证结果、缺失时间戳、样本量；省略 symbol 返回全部 |
| `GET /v1/bars?symbol=PAYS.US&timeframe=5m&limit=1000` | 按时间升序的官方已收盘 OHLCV |

`timeframe` 支持 `1d/5m/15m/30m/1h`。`from`、`to` 为可选 UTC Unix 秒，包含边界；`limit` 为 1–10000，返回范围内最近的 N 根。`bars` 中的 `time/open/high/low/close` 可直接用于 Lightweight Charts 蜡烛序列，volume 可供成交量序列使用。所有 bars 均为 NoAdjust、regular session、closed only。

```bash
curl 'http://127.0.0.1:8765/health'
curl 'http://127.0.0.1:8765/v1/quotes?symbol=PAYS.US'
curl 'http://127.0.0.1:8765/v1/readiness?symbol=PAYS.US'
curl 'http://127.0.0.1:8765/v1/bars?symbol=PAYS.US&timeframe=5m&limit=100'
```

接口只读。`/v1/readiness` 会进行历史验证，建议消费端适度轮询，不要按每条 Quote 触发。

## 已确认的规则

- Quote 只订阅 `SubType.Quote`，直接使用 `volume`；不累加 Trade 或推送 delta，不保存 tick。
- regular 与 extended quote 分开存储，扩展时段不会覆盖常规时段累计量。`alert_eligible` 仅表示历史基线可用，消费端还需检查 Quote 健康状态、时间戳和交易时段。
- 断线/无推送 watchdog 重建订阅并获取 snapshot；每 30 秒也获取 snapshot，覆盖 SDK 内部自动重连后的状态恢复。
- 历史下载与 Quote 任务独立；请求共享单一限速器，每次间隔至少 0.55 秒，留出 2 req/s 限额余量。请求有 15 秒超时；单 ticker 失败不终止其他 ticker。SQLite 基础设施错误会终止服务。
- 冷启动顺序：所有 Daily → 所有 5m → 15m → 30m → 1h，各请求最近 1000 根。只将已收盘且合法的 bars UPSERT 到 SQLite。
- 5m 的 1000 根窗口在盘中不足以覆盖前 12 个完整交易日时，按缺少的前缀定向补拉，补拉结果也进入 FULL_READY 验证。
- 使用 `exchange_calendars` 的多年 XNYS 日历，处理假期、提前收盘、DST。美股 1h 按 09:30 起始，最后一根在收盘时截短；Daily 时间戳为美东零点，但收盘边界为该交易日实际收市时间。
- 常规更新拉 2 根，在闭合后 +2 秒进入队列，失败按 2/5/10/30 秒间隔重试。单 worker 队列会带来额外延迟。跨多个周期或休眠恢复时改拉 1000 根，并检查缺口。超过这段覆盖范围的长中断会明确报告缺口，重启重新进行最近窗口 reconciliation。
- `ready=true`：最近 300 个已完成交易日 Daily 和 12 个已完成交易日 5m 均完整。
- `degraded_ready=true`：历史不足 300 日，但已通过额外向前查询确认 API 可用历史边界，且边界内所需 Daily / 5m 完整。接口明确提供样本数，`ready` 仍为 false，`alert_eligible` 为 true。它表示“供应商可用历史”，不凭空声明已核实 IPO 日期。
- 若连 12 日 5m 也不足，按有日线的可用交易日验证；未解释缺口（含 IPO 首日非正常开盘、停牌或无成交导致的缺 K）仍保持不可用，不合成本地 candle，不自动把缺失当作 0 成交量。
- `full_ready` 验证本次所有周期的拉取范围；1000 根窗口首日允许从中间开始，但范围内不允许缺口。批次元数据保存在 SQLite，JSON 被删后仍可重建。FULL_READY 与 READY 独立，FULL_READY 不代表满足 300 日样本要求。
- 非法 OHLCV 不落盘并记录原始异常字段；相同 timestamp 的旧合法数据也不能掩盖本次已知异常。初始化失败最多追加 3 轮修复，避免无限重试。

## 本地文件

- `runtime/bars.sqlite3`：官方 closed bars、下载批次及可用历史边界。
- `runtime/data_ready.json`：可删、可重建的派生状态；写失败不会阻断内存接口。
- `runtime/history_symbol_usage.json`：按月保守记录已尝试请求历史的 symbol。它不是券商配额余额，删除不影响数据正确性，也不会重置券商额度。
- `runtime/last_run_report.json`：有时限实测结束后的状态快照。
- `runtime/service.lock`：本地单实例锁。

原始凭证、runtime、虚拟环境均已加入 `.gitignore`。保留历史数据库中旧 ticker 的数据，但不会重新请求、订阅或通过本轮 API 暴露被移出 focus/wait 的 ticker。

## 当前实测记录

见 `runtime/design_probe.json` 和 `runtime/http_smoke.json`。真实测试确认了 Quote 推送、各周期 K 线、盘中 1000 根 5m 窗口截断、BLSH 历史不足 300 日，以及上游存在 open 超出 high/low 的个别 K 线。遇到这些异常，服务如实报告验证失败，不将状态伪装成 READY。

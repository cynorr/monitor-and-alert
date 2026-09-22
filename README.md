# Market Monitor

个人美股看盘工作台：Python 行情服务、SQLite 官方历史、Daily / Intraday 双图与实时指标。Price Alert 和运行中编辑股票名单不在本版范围。

入口：[图表交互维护](docs/ui/chart-interactions.md) · [图表规格](Tradingview-Lightweight-Chart-Visualization-and-Alert-Development-Specification.md) · [数据规格](Longbridge-Data-Service-Design.md) · [维护地图](docs/data/README.md) · [测试记录](docs/testing/chart-validation.md)

## 启动

**模拟和真实行情使用不同启动命令。每个命令都同时启动数据服务和网站，只需选择一个，再打开对应地址。没有自动切换或回退，也不需要额外模式开关。**

| 模式 | 启动命令 | 浏览器地址 | 数据位置 |
| --- | --- | --- | --- |
| 模拟盘中 | `./simulator/start.command --speed 30` | http://127.0.0.1:18765/（SIM 标签） | 独立临时 SQLite，退出删除 |
| 真实行情 | `.venv/bin/python -m data_service serve` | http://127.0.0.1:8765/ | runtime/bars.sqlite3 |

模拟时不要为了打开网页而另跑 `data_service serve`：该命令会使用真实凭证请求 Longbridge。两者可以独立同时运行，浏览器所在地址决定其数据源；停止模拟器不会使模拟页面自动转为真实行情。`/health` 的 `mode` 为 `simulation` 或 `live`，真实服务启动会打印 `LIVE` 和地址。

Python 3.11+，macOS / Linux，在仓库目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m data_service serve
```

打开 **http://127.0.0.1:8765/**。前端构建产物与 Lightweight Charts 5.2.0 已随仓库提供，正常启动无需 npm 或 CDN。

每次后端启动重新读取 workspace.json，只加载 statuses 中的 focus / wait；orders 只决定顺序。运行中不监控文件变化。默认使用 longbridge-token.txt 的既有 App Key / App Secret / App Token 格式，凭证不输出到日志。

默认官方 .cn 接入点；全球接入点加 `--region global`。可用 `--workspace`、`--credentials`、`--runtime`、`--port` 指定路径或端口；同一 runtime 仅允许一个实例。

```bash
# 当前白名单的子集；正式接口运行，有明确时限
.venv/bin/python -m data_service serve --symbols PAYS BLSH --duration 60

# 一次历史同步及有界重试
.venv/bin/python -m data_service reconcile

# 不联网，从 SQLite 重建质量状态
.venv/bin/python -m data_service verify

# 离线回归（包括本机 HTTP/WebSocket 回环测试，不连接券商）
.venv/bin/python -m pytest -q
```

退出码：0 为所有 ticker 均 FULL_READY；2 为同步结束但存在缺口、未追上或质量异常；1 为启动失败。关闭浏览器不停止后端。停止后端使用 Ctrl+C。

## 图表

- 左 Daily、中 Intraday、右紧凑列表；拖动两条分界线调整宽度。右图默认 5m，可切换 15m / 30m / 1h。
- 两图均有成交量、EMA10/EMA20、Daily SMA50 / Intraday SMA65；无网格、自由十字线、交易日联动。Daily 初始约九个月，短历史保持 candle 宽度、靠右显示。
- 观察列表支持搜索、上下键选股；图表支持十字线、缩放、拖动、回到最新。
- 当前 ticker 优先加载，其余白名单后台并发加载。
- 官方 closed bars 存 SQLite，活跃 candle 和指标仅存后端内存。
- 最新 5m 由 Quote last_done 更新；较大周期活跃 candle 合并官方 5m 和临时 5m。官方到达后修正。
- 活跃成交量只有在当日前缀完整时显示差值，Daily 使用官方累计量。
- ADR20 为最近 20 个完成交易日平均振幅百分比；20 日均额优先官方 turnover。
- 界面仅英文，正常时无状态通知；加载/断线使用小标签，数据问题用 ticker 警告图标及悬停详情。
- 列表四列 Symbol / Last / Chg% / Ext；OHLC、ADR20、ADV20 与可用 Bid/Ask 位于图表顶部。
- 所有图表采用不复权 regular 数据；pre/post 仅显示价格，不修改 regular candle。

## API

| 接口 | 内容 |
| --- | --- |
| GET /health | 数据模式 mode、连接、初始化、错误和推送计数 |
| GET /v1/universe | 启动白名单 |
| GET /v1/quotes?symbol=PAYS.US | regular / extended 最新状态；省略 symbol 返回全部 |
| GET /v1/bars?symbol=PAYS.US&timeframe=5m&limit=1000 | 官方 closed OHLCV + turnover，升序 |
| GET /v1/readiness?symbol=PAYS.US | schema_version=2 的周期追齐/质量状态 |
| GET /v1/chart?symbol=PAYS.US&timeframe=5m | Daily + 所选周期完整图表、活跃 candle、指标和状态；提高加载优先级 |
| WS /v1/stream | 图表长连接，默认当前关注对象 |

bars 的 timeframe 支持 1d/5m/15m/30m/1h，limit 1–10000，from/to 为包含边界的 UTC Unix 秒。

WebSocket 选择消息：

```json
{"type":"select","symbol":"PAYS.US","timeframe":"15m","request_id":1}
```

服务端 view 回传 request_id、symbol、timeframe、run_id、server_time。首次/选择/重连包含完整 bars 和指标序列；其后只在对应历史 revision 改变时重发历史，持续发送 active 和 indicator_preview。列表 Quote 和 warning 每秒更新。客户端忽略旧 request_id；慢客户端不阻塞券商行情任务。

接口只接受启动白名单。默认同源访问；必要时可设 `--cors-origin` 为具体前端 origin。WebSocket 校验 Origin。浏览器不连接券商、不写数据库。

**readiness v2 为语义变更**：ready=Daily+5m 当前闭合范围验证通过；full_ready=五周期全部通过；loaded 表示已完成同步并取得最新目标，可伴随旧历史缺口 warning。旧 300 日/12 日、alert_eligible、degraded_ready 不再属于此接口。

官方 OHLC 区间异常时，小范围重取同源历史；仍不合法则隔离并显示 ticker warning。旧历史异常不会使初始化反复下载整个窗口，最新目标缺失仍重试。`Quarantined invalid bars` 表示供应商数据未通过校验，不是模拟/真实数据混用；原始异常字段保留在 SQLite batches，不通过修改价格来消除警告。

## 前端开发

```bash
cd ui
npm ci
npm run build
```

TypeScript 源码在 ui/src/，main.ts 管传输/列表、chart.ts 管图表联动、layout.ts 管列宽、types.ts 管契约；构建至 ui/public/。使用本地 IIFE 图表文件，npm 中 lightweight-charts 仅提供编译期类型，不重复打包运行时。

浏览器离线验收夹具（只写临时目录，不读真实凭证）：

```bash
.venv/bin/python tests/preview_fixture.py
```

打开 http://127.0.0.1:18765/，页面用 SIM 标签标识合成数据。该兼容入口直接启动完整模拟器，不再使用静态历史夹具。

## 独立图表模拟器

双击 simulator/start.command，或执行 `./simulator/start.command`。打开 http://127.0.0.1:18765/；同时保留 ws://127.0.0.1:18766 Quote 推送。

模拟器提供一致的 Quote 与五周期历史，复用实际 BarScheduler 持续生成 closed bars，独立临时数据库、无需凭证。`./simulator/start.command --speed 30` 可加速收盘测试（5m 约 10 秒）；`--start` 指定美东盘中时刻。不修改系统时间、不连接真实券商。保持终端运行，使用 18765 页面并确认 SIM 标签；8765 是正式行情，不会自动进入模拟。修改 Python 后重启模拟器。见 [模拟器说明](simulator/README.md)。

## 本地文件与证据

- runtime/bars.sqlite3：官方 closed bars、turnover、批次与元数据。旧表自动增加 nullable turnover 列，不清空历史。
- runtime/data_ready.json：可重建派生状态；删除不会丢失行情。
- runtime/history_symbol_usage.json：本地按月已尝试 symbol 记录，不是券商额度余额。
- runtime/service.lock：单实例锁；last_run_report.json 为有时限运行的结果。
- [VALIDATION-REPORT.md](VALIDATION-REPORT.md) 是旧版本真实接口证据，不能代表本版已完成 live 验收。
- 本版验证范围见 [chart-validation.md](docs/testing/chart-validation.md)。

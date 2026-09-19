# Market Monitor

个人美股看盘工作台：Python 行情服务、SQLite 官方历史、Daily / Intraday 双图与实时指标。Price Alert 和运行中编辑股票名单不在本版范围。

入口：[图表规格](Tradingview-Lightweight-Chart-Visualization-and-Alert-Development-Specification.md) · [数据规格](Longbridge-Data-Service-Design.md) · [维护地图](docs/data/README.md) · [测试记录](docs/testing/chart-validation.md)

## 启动

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

- 左图 Daily，右图默认 5m，可切换 15m / 30m / 1h；两图均有成交量、EMA10、EMA20、SMA50。
- 观察列表支持搜索、上下键选股；图表支持十字线、缩放、拖动、回到最新。
- 当前 ticker 优先加载，其余白名单后台并发加载。
- 官方 closed bars 存 SQLite，活跃 candle 和指标仅存后端内存。
- 最新 5m 由 Quote last_done 更新；较大周期活跃 candle 合并官方 5m 和临时 5m。官方到达后修正。
- 活跃成交量只有在当日前缀完整时显示差值，Daily 使用官方累计量。
- ADR20 为最近 20 个完成交易日平均振幅百分比；20 日均额优先官方 turnover。
- READY / FULL_READY 提示 5 秒消失；历史不足、缺 K、估算及闭合后超过 15 秒的更新延迟显示 ticker warning。
- 所有图表采用不复权 regular 数据；pre/post 仅显示价格，不修改 regular candle。

## API

| 接口 | 内容 |
| --- | --- |
| GET /health | 连接、初始化、错误和推送计数 |
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

## 前端开发

```bash
cd ui
npm ci
npm run build
```

TypeScript 源码在 ui/src/main.ts，生成 ui/public/main.js。使用本地 IIFE 图表文件，npm 中 lightweight-charts 仅提供编译期类型，不重复打包运行时。

浏览器离线验收夹具（只写临时目录，不读真实凭证）：

```bash
.venv/bin/python tests/preview_fixture.py
```

打开 http://127.0.0.1:18765/，页面明确标注“离线测试 · 合成数据”。该入口仅用于开发验收，不是生产数据源。

## 独立 Quote 模拟器

双击 simulator/start.command，或执行 `./simulator/start.command`，监听 ws://127.0.0.1:18766。范围保持不变：仅盘中随机 Quote，无历史、时钟或验证框架。本版生产图表不自动切换到模拟来源。见 [模拟器说明](simulator/README.md)。

## 本地文件与证据

- runtime/bars.sqlite3：官方 closed bars、turnover、批次与元数据。旧表自动增加 nullable turnover 列，不清空历史。
- runtime/data_ready.json：可重建派生状态；删除不会丢失行情。
- runtime/history_symbol_usage.json：本地按月已尝试 symbol 记录，不是券商额度余额。
- runtime/service.lock：单实例锁；last_run_report.json 为有时限运行的结果。
- [VALIDATION-REPORT.md](VALIDATION-REPORT.md) 是旧版本真实接口证据，不能代表本版已完成 live 验收。
- 本版验证范围见 [chart-validation.md](docs/testing/chart-validation.md)。

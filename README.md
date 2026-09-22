# Market Monitor

个人美股看盘工作台：Daily + Intraday 双图、实时行情与指标。单进程 Python、SQLite、同源 WebSocket。Price Alert 和下单不在范围。

[运行逻辑](docs/behavior.md) · [开发维护](docs/development.md) · [布局/样式/交互](docs/ui.md) · [验证记录](docs/validation.md)

## 启动

| 模式 | 命令 | 地址 | 数据 |
| --- | --- | --- | --- |
| 真实行情 | `.venv/bin/python -m data_service serve` | http://127.0.0.1:8765/ | runtime/bars.sqlite3 |
| 模拟 | `./simulator/start.command --speed 30` | http://127.0.0.1:18765/ | 临时库，退出删除 |

每条命令都同时启动数据服务和网页，不需要再启动前端。模拟页面带 SIM 标签，不读凭证、不自动切换真实行情。首次安装需 Python 3.11+：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
```

启动重读 workspace.json，仅 statuses 为 focus/wait 的 ticker 可请求/订阅；orders 只排序。真实凭证从 longbridge-token.txt 读取，使用既有 App Key / App Secret / App Token 格式，不输出到日志。默认官方 .cn；`--region global` 切换接入点。可指定 `--workspace`、`--credentials`、`--runtime`、`--port`。同一 runtime 只允许一个实例；账户只使用一个正式行情连接。

## 看盘

- 三栏、双图、拖动列宽、搜索与键盘选股、自由十字线和交易日联动。
- Intraday：5m/15m/30m/1h/2h/4h。2h/4h 永远由 5m 合成，官方 15m/30m/1h 未到时也可由 5m 临时显示。
- Daily 约九个月初始范围；短历史靠右、保持 candle 宽度。5m 合成的大周期仅覆盖已有 5m 的时间范围。
- EMA10/20、Daily SMA50、Intraday SMA65、ADR20/ADV20；计算在 Python。
- Loading → 黄色 Ready（Daily+5m）→ 蓝色 Ready（五周期，3 秒后隐藏）。缺失/请求失败重试耗尽显示原因；正常不反复提示。
- 官方 OHLC 上下界矛盾保留原值，不报警、不补数据，仅追加 runtime/invalid_ohlc.jsonl 供人工对照。
- 官方 closed bars 落库，Quote、活跃 candle 和合成数据只在内存。extended 只显示价格。

所有历史请求均使用最近 K 线：启动/恢复/补缺 count=1000，正常 closed 更新 count=2。过滤未收盘后可能不足 1000 根；没有翻页或历史查缺口。全局 10 请求/秒、5 并发；后台历史最多 8 请求/秒、3 并发，为点选保留两个请求与并发位置。

## 命令与接口

```bash
.venv/bin/python -m data_service universe
.venv/bin/python -m data_service reconcile  # 本轮有界历史同步
.venv/bin/python -m data_service verify     # 不联网的当前窗口诊断
.venv/bin/python -m data_service serve --symbols PAYS --duration 60
.venv/bin/python -m pytest -q
npm run build --prefix ui
```

示例 ticker 必须仍属于当前 focus/wait。有限命令退出码：0 为五个官方周期窗口检查通过，2 为存在缺失/不可用数据，1 为启动失败。停止后端使用 Ctrl+C；关闭网页不停止后端。

| 接口 | 内容 |
| --- | --- |
| GET /health | mode、Quote 连接、推送数、待处理任务、耗尽错误 |
| GET /v1/universe | 启动白名单 |
| GET /v1/quotes?symbol=PAYS.US | 最新 regular/extended |
| GET /v1/bars?symbol=PAYS.US&timeframe=5m&limit=1000 | 官方 closed 数据，只支持五个官方周期 |
| GET /v1/readiness?symbol=PAYS.US | 简单 status + 详细周期诊断 |
| GET /v1/chart?symbol=PAYS.US&timeframe=4h | 只读完整图表快照 |
| WS /v1/stream | UI 唯一图表数据通道 |

WS 选择：`{"type":"select","symbol":"PAYS.US","timeframe":"4h","request_id":1}`。切换、重连完整快照；常规发实时预览与状态，历史改变再发历史。status 为 `{stage: "loading" | "basic" | "full", errors: []}`，替代旧 readiness v2 多布尔字段。HTTP 图表查询不改变选择优先级。

UI 构建产物与本地 Lightweight Charts 已随仓库提供，正常启动不需 npm/CDN；开发时 `cd ui && npm ci && npm run build`。模拟器详见 [simulator/README.md](simulator/README.md)。显式 live 检查使用 `scripts/live_check.py`，范围与证据规则见开发文档。

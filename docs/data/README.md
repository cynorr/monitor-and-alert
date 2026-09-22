# Data 与图表模块维护手册

核对：2026-09-20。需求见 [数据规格](../../Longbridge-Data-Service-Design.md) 、[图表交互维护](../ui/chart-interactions.md) 与 [图表规格](../../Tradingview-Lightweight-Chart-Visualization-and-Alert-Development-Specification.md)，运行方式见 [根 README](../../README.md)。

## 已实现范围

本地单进程 Python + SQLite，HTTP 初始查询与 WebSocket 图表更新；Daily / Intraday 双图、观察列表、EMA10/20、Daily SMA50 / Intraday SMA65、ADR20、20 日均额。Price Alert 与运行中编辑名单不在本版范围。

启动只读取 focus/wait；官方历史只保存 NoAdjust、regular、closed bars。临时 candle、派生指标只在内存；模拟器独立且不被生产模块导入。

## 文件地图

| 文件 | 职责 |
| --- | --- |
| data_service/__main__.py | CLI、参数、单实例锁、HTTP 生命周期与退出码 |
| data_service/config.py | workspace 白名单、凭证读取与脱敏 |
| data_service/broker.py | 唯一 SDK 入口，共享 context、10 req/s、5 在途、超时、配额 |
| data_service/calendar.py | UTC/ET、XNYS、闭合目标和活跃区间 |
| data_service/quotes.py | Quote 分桶、倒序拒绝、snapshot、watchdog、推送回调 |
| data_service/downloader.py | 获取/过滤/校验/写入、官方 turnover、异常 OHLC 有界同源重取、拒绝记录修订 |
| data_service/store.py | bars/batches/metadata、turnover 迁移、事务、内存 revision |
| data_service/validator.py | readiness v2，按 revision/目标/run 缓存完整性检查 |
| data_service/charts.py | 临时 candle、较大周期组合、成交量前缀、图表缓存 |
| data_service/indicators.py | 唯一 EMA/SMA/ADR/日均额公式与实时预览 |
| data_service/service.py | 动态优先级、5 并发下载、到期更新、错误隔离、API 组合 |
| data_service/http_api.py | aiohttp、静态页面、HTTP、WebSocket、Origin 校验 |
| ui/src/main.ts / types.ts | 请求取消、选择代次、长连接、英文列表及数据契约 |
| ui/src/chart.ts / layout.ts | 图表配置、交易日联动、固定 candle 间距、三栏拖动 |
| ui/public/ | 可直接运行的构建结果、样式、页面、本地 5.2.0 图表库 |
| tests/test_data_service.py | 白名单、日历、存储、下载、Quote、readiness、恢复 |
| tests/test_charts.py | 活跃 candle、成交量、指标、并发、HTTP/WS 回环集成 |
| tests/preview_fixture.py | 完整模拟器的兼容启动入口 |
| scripts/ | 明确执行的旧真实接口诊断；不被业务代码 import |
| simulator/ | 隔离 Quote + closed bar 数据源、交易时钟与完整图表模拟 |

依赖：UI → Data API；图表派生层 → 官方存储/行情；正式 data 不依赖 simulator 或 UI 源码。HTTP 静态入口从仓库 ui/public 提供资源。没有 alerts/ 空框架。

## 运行与状态

- Quote 与调度同时启动，当前 ticker 5m/Daily/所选周期优先，其余 5m、Daily、15m、30m、1h 后台推进。
- 网络请求最多 5 并发，统一滚动窗口 10 req/s；SQLite 仍单线程事务写入。
- 正常 closed 更新 count=2；跨多个周期 count=1000，必要时补缺失前缀。初始化及更新失败有界重试；serve 耗尽后等待 30 秒继续恢复，reconcile 有界结束。
- READY=当前 Daily+5m 完整追齐；FULL_READY=五周期完整追齐。目标是具体 bar timestamp，随当前时间变化。
- loaded 允许更早历史缺口伴随 warning；最新目标缺失则不可宣称追齐。
- OHLC range 异常逐 timestamp history offset(count=2) 重取一次，每批最多 10 个，仍受 Broker 共享限流约束；不递归修复、不改 OHLC。仍异常保留原字段，重取成功保存 recovered 证据。
- 已知非法新修订会事务性撤下旧 bar，防止旧合法值进入图表/指标；合法重取可恢复并清除拒绝证据。首条异常也参与范围验证。
- 初始化 latest 已有效时，旧历史质量缺陷不触发整窗重试；loaded 可用、ready/full_ready 保持 false，ticker warning 保留。最新目标缺失或非法继续重试。
- 启动命令决定数据来源，无自动切换；模拟器自身提供 18765 网站，serve 启动真实 Longbridge 并打印 LIVE。/health 返回 mode=live/simulation。
- 正常时 UI 静默，历史不足/缺口/异常/估算/超过 15 秒的 bar 延迟以图标和英文悬停详情提示。
- HTTP readiness 使用缓存检查，不每次重复扫描不变数据。
- bars 新增 turnover。迁移保留旧记录，null 使日均额使用估算值并提示。
- WebSocket 初次、切换和重连发送完整快照；常规只发送实时预览与已改变的历史序列。图表显示合并频率约 5Hz，Quote 内存处理不按 UI 频率丢弃。

## 缓存与时间边界

- 官方 bars UPSERT 更新 revision，指标按 revision 失效；原始行情只一份。
- 当前 5m 仅 Quote last_done 采样；较大活跃周期合并官方 5m。该区间闭合后必须等待其官方 bar。
- 成交量只在当日完整前缀可用时相减。前缀拒绝/缺失时隐藏活跃量，价格照常。
- service/downloader 接受实例级 clock，生产默认真实时间；模拟器注入自己的交易时间，不全局修改时钟。
- 列表 Chg% 以前一完成交易日 close 为基准；Quote 的可用 bid_price/ask_price 原样保留，不扩展 Depth 订阅。
- UTC 存储；美东规则、标签；1h 从 09:30，处理 DST 和提前收盘。
- UI 重开复用后端缓存；Python 进程退出会丢失活跃 candle 和指标缓存，启动重建。

## 已知边界

- 不复权；没有公司行动调整、证券级停牌/无成交例外日历。缺 K 不自动补零。
- 接收的 Quote 不保证覆盖每笔成交；当前 5m O/H/L 可近似，官方到达后修正。
- 数据源持续失败不能保证 15 秒内完成；15 秒是警报阈值。
- SDK 实际响应速度、限流及券商全天恢复能力尚需本版独立 live 验收。
- 模拟器内部价格与历史一致，但不与真实历史混合；生产 UI 不自动切换来源。
- 默认运行方式是在仓库中 editable install；UI 资源由仓库目录提供。

## 开发检查

```bash
.venv/bin/python -m pytest -q
cd ui
npm ci
npm run build
```

HTTP/WebSocket 回环测试需要允许绑定 localhost；不读取凭证、不连接券商。UI 需在修改 TypeScript 后重新构建。测试记录见 [图表验收](../testing/chart-validation.md)，旧 [VALIDATION-REPORT.md](../../VALIDATION-REPORT.md) 仅是旧版本证据。

修改 API、启动方式、状态语义和文件职责时同步维护规格、README 和本手册。不得将离线夹具或历史报告称为本轮 live 测试。

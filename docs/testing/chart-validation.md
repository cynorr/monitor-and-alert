# 图表开发验收记录

## 2026-09-20：数据模式与异常官方 OHLC 处理

macOS / Python 3.13.1，`.venv/bin/python -m pytest -q`：**52 passed，2.37 秒**。本机 HTTP/WebSocket 回环已放行执行；没有读取真实凭证或连接券商。

- 用户日志中的五组非法 OHLC 原值全部作为回归输入；重取仍异常时不入 bars，并撤下旧合法修订。
- 精确 timestamp 的合法官方替身可修复；错误 timestamp、重复响应、重取超时不能消除拒绝证据。
- 每批定点重取最多 10 次；首条坏 bar 不缩短验证范围；旧历史质量缺陷不使初始化重试整窗，最新目标非法仍继续重试。
- /health 明确 live/simulation；既有模拟历史、BarScheduler 跨周期/交易日、HTTP/WebSocket 测试通过。
- 未重新做浏览器视觉验收，未核实 Longbridge 是否已修正这些原始记录。

此前微调：Daily/Intraday 信息去重、固定对齐的顶部边界、边界下方 OHLC/Range、volume 位置调整、Intraday SMA65 和 Ext 百分比。当时仅重新构建前端，按用户要求未运行测试或浏览器验收。

## 2026-09-20：三栏交互与完整模拟器

本轮离线回归 **40 passed，2.45 秒**；TypeScript check/build 通过。没有读取凭证或调用券商。

- 三栏布局与两条分界线拖动已在浏览器验证，刷新后保持列宽；两张图初始等宽，列表更窄。
- 全英文紧凑列表、Symbol/Last/Chg%/Ext 四列、胶囊控制、无网格和指定颜色显示正常。顶部品牌、底栏、bar 数量和 TradingView 图内标志均已移除；版权说明移到静态 licenses.html。
- Daily 初始约九个月；一次性 20 根 Daily 验收夹具确认 candles 靠右、左侧留白，没有铺满或变宽。
- 自由十字线与美东交易日联动验证通过；修正程序联动反向吸附鼠标十字线的问题。切换 1h → 5m 后仍能显示选中交易日。
- 模拟器以 10 倍交易时间运行当前 45 个 focus/wait，跨过多个 5m/15m/30m/1h 边界；状态抽查为 45/45 FULL_READY、0 warning、0 history error。浏览器观察到收盘后自动进入下一交易日。
- 自动化新增：五周期各 1000 根 closed 历史、跨周期 OHLCV/turnover 一致、累计量前缀一致、真实 scheduler 跨周期及交易日、提前收盘/周末时钟推进、Quote WebSocket 生命周期，以及当日 Daily 存入后 Chg% 仍使用前日 close。
- 浏览器未记录 JavaScript 运行错误。移动端触控、长时间性能与真实券商全天恢复未验收。

下方保留前一版记录作为历史证据；旧布局和静态浏览器夹具已由本轮实现取代。

## 2026-09-20：首版双图

日期：2026-09-20。范围：本版代码的离线回归与本机浏览器交互。未调用真实券商接口，未读取真实凭证。

## 环境与结果

macOS，Python 3.13.1，aiohttp 3.14.3，TypeScript 5.9.3，Lightweight Charts 5.2.0。

| 验证 | 结果 |
| --- | --- |
| `.venv/bin/python -m pytest -q` | 34 passed，1.87 秒 |
| `cd ui && npm run check` | 通过 |
| `cd ui && npm run build` | 通过，已生成本地 main.js |
| verify CLI + 空临时数据库 + 不存在的凭证路径 | 不联网完成，输出 schema_version=2，正确返回未就绪退出码 2 |
| 本机 HTTP / WebSocket | 快照、增量、切换、重连及 Origin 拒绝验证通过 |

## 自动化覆盖

- 白名单、交易日历、DST / 提前收盘、官方 closed bar 校验、SQLite 覆盖及旧表 turnover 迁移。
- 活跃 5m 缺失 open、跨桶、官方替换；较大周期使用官方 5m 修正；扩展时段隔离。
- 累计成交量差值、缺失或被拒绝的历史前缀、负差值、交易日切换。
- EMA 以 closed bar 为基准预览、不随重复 Quote 漂移；SMA 样本不足；ADR 窗口与成交额降级。
- readiness v2 当前闭合目标、同步批次隔离、非法历史、延迟超过 15 秒及跨边界持续警告。
- 当前 ticker 优先、失败隔离、五请求并发、全局滑动请求限额、多边界恢复与历史前缀补齐。
- 初始请求耗尽后，在原闭合目标不变时恢复同步；一次性 reconcile 保持有界。
- HTTP / WebSocket 完整快照与历史 revision 增量、选择标识、重连全量恢复、非白名单和跨源请求拒绝。

## 浏览器验收

使用 `tests/preview_fixture.py` 和应用内浏览器，访问 `http://127.0.0.1:18765/`。夹具只写临时目录，页面明确标注“离线测试 · 合成数据”，与生产数据及独立 Quote 模拟器隔离。

- Daily / Intraday 双图、成交量 pane、三条均线、价格与 ADR / ADV 显示正常，活跃 candle 持续更新。
- 切换 15m、1h、30m，快速切股与切周期后，最终 ticker 和周期正确，无旧响应串图。
- 搜索筛选与上下键选股正常。
- 日线拖动历史、滚轮缩放、十字线 OHLCV 和回到最新正常；实时价格更新期间历史视口保持位置。窄窗口下图表自动纵向排列。
- FULL READY 提示在五秒后消失；夹具不补官方历史时，缺 K warning 与不可用活跃成交量如实显示。
- 停止测试服务后显示“连接中断”并保留已显示历史；重启后自动恢复当前 ticker / 周期、完整快照和实时价格，无需刷新页面。
- 检查浏览器错误日志，未出现 JavaScript 运行错误。

## 未覆盖范围

本轮结果不代表券商 live 验收。真实账户限流、官方生成延迟、长时间休眠后的券商连接恢复及完整交易日运行仍需独立实测；默认离线回归不执行这些请求。

移动端触控及长时间性能未进行完整交互验收。Price Alert、名单运行中编辑、生产 UI 与独立 Quote 模拟器切换不在本版范围。旧 VALIDATION-REPORT.md 保留为历史证据。

# 模拟器范围与维护

更新：2026-09-20。当前已实现 Quote + 历史 closed bars + 连续收盘调度。用户本轮明确扩展了之前仅 Quote 的范围，本文件取代旧限制。

## 目标与边界

一键启动独立的看盘开发环境，打开 http://127.0.0.1:18765/ 即可使用与生产相同的 UI。仍提供 ws://127.0.0.1:18766 原始 Quote 消息。

模拟器按 workspace focus/wait 生成数据，不读取凭证、不调用券商。数据只写临时目录中的 SQLite；不能混入正式 runtime。生产代码不 import simulator、不回退到模拟来源。

## 已实现

- Daily / 5m / 15m / 30m / 1h 最近 1000 根有效 closed bars。
- 统一交易日价格路径，跨周期 OHLCV / turnover 一致，Quote 累计成交量与 closed bar 前缀一致。
- 模拟历史接口支持 count=2、完整加载与 offset 前缀。
- 复用正式 downloader、validator、BarScheduler；初始化、边界更新、跨多个区间补齐都走实际数据流程，不强制 READY。
- 注入实例级交易时钟：默认最近交易日盘中，支持 --start / --speed；跳过休市并按提前收盘规则推进，不全局替换 time.time。
- UI 用小型 SIM 标签区分来源。正常无警告；错误保留实际验证证据。
- 原 Quote JSON WebSocket 继续可用。生成器与所有客户端共享市场状态。

原 tests/preview_fixture.py 的静态历史夹具已被替换为模拟器入口，避免只有 Quote 更新、跨边界不断出现缺 K 的问题。

## 不扩展的范围

不开发故障注入框架、回放、交易执行、Price Alert 或真实券商切换。模拟器不是 Longbridge 二进制协议服务器。

## 文件与验证

具体启动、参数和文件地图见 [simulator/README.md](../../simulator/README.md)。核心回归是 tests/test_simulator.py：周期一致、1000 根完整性、实际 scheduler 跨 5m/15m/30m/1h 与交易日、成交量校验、原始 WebSocket。

本轮证据见 [chart-validation.md](chart-validation.md)。2026-09-19 的 Quote-only 验收属于旧版历史证据，不代表本版新增流程已进行券商 live 测试。

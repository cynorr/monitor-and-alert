# 独立图表模拟器

双击 start.command 或在仓库运行 `./simulator/start.command --speed 30`，打开 http://127.0.0.1:18765/ 并确认 SIM 标签。一个命令同时启动行情与网页；不需启动正式服务。

模拟器按 workspace focus/wait 生成 Quote 和五周期 closed bars，复用实际调度、校验、指标、2h/4h 合成与同一 UI。使用实例级交易时钟，不修改系统时钟。数据只在临时 SQLite，退出删除；不读取凭证、不连 Longbridge。原额外 18766 Quote 监听已删除。

参数：`--workspace`、`--symbols`（当前白名单子集）、`--port`、`--speed`、`--start`（ET 盘中，例如 2026-09-18T13:44:45）。30 倍时 5m 约 10 秒；休市自动跳到下一交易日。

不扩展故障注入、录制回放或真实数据回退。文件职责和检查见 [开发维护](../docs/development.md)。

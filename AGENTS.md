# 项目入口：Market Monitor

先读 [README.md](README.md)；开发读 [docs/development.md](docs/development.md)，产品逻辑读 [docs/behavior.md](docs/behavior.md)，UI 改动另读 [docs/ui.md](docs/ui.md)。这些是唯一维护入口，用户当前要求优先于文档。

- 单进程 Python + SQLite + 本机 WebSocket + TypeScript；不新增服务、消息中间件或通用适配框架。
- 每次启动重读 workspace，只请求/订阅 focus、wait；不以历史报告中的 ticker 作为白名单。
- 唯一正式 SDK 入口是 broker.py。只订阅 Quote；UI 不调用券商。
- SQLite bars 只存官方 NoAdjust、regular、closed 的五个周期。2h/4h 及其他合成数据只在内存。
- OHLC 正数有限值与基本结构必须验证；仅上下界矛盾保留官方原值，追加 invalid_ohlc.jsonl，不修正、不告警、不重试。
- 初始化、恢复、补缺只请求最近 1000 根，过滤未收盘；接受少于 1000 根。禁止 offset、翻页、连接旧历史和历史查缺口。
- 缺失和请求失败用同一回补任务重试；次数与节点见开发文档。不要把 UI 查询变成下载触发器。
- 模拟器只写临时库，不读凭证、不自动回退真实 API。默认测试不连券商；live 验收必须明确 ticker 范围与时限。
- 不输出凭证；不新增 Price Alert、下单、故障注入或回放框架。
- 变更行为同步 behavior；变更职责/契约同步 development；UI 同步 ui。验证记录写日期、环境、覆盖和未覆盖范围。
- TypeScript 改动后 npm run build --prefix ui；数据/调度改动运行离线测试及相关错误路径。历史记录不能当成本轮 live 证据。

# 项目入口：Market Monitor

先读 [README.md](README.md)；开发遵循 [docs/development-principles.md](docs/development-principles.md)，实现维护读 [docs/development.md](docs/development.md)，产品逻辑读 [docs/behavior.md](docs/behavior.md)，Longbridge 规则只在 [docs/longbridge-data.md](docs/longbridge-data.md) 维护，Massive 规则读 [docs/massive-data.md](docs/massive-data.md)，List/Tag/Filter 另读 [docs/list-design.md](docs/list-design.md)，持仓数据需求只在 [docs/holdings-data.md](docs/holdings-data.md) 维护。Manual Alert 需求只在 [docs/alert.md](docs/alert.md) 维护，模块另读 [data_service/alerts/AGENTS.md](data_service/alerts/AGENTS.md)。Intraday State 的实时状态、量比、自动提醒和 In Play 需求只在 [docs/intraday-state.md](docs/intraday-state.md) 维护，模块另读 [data_service/intraday_state/AGENTS.md](data_service/intraday_state/AGENTS.md)。Additional Info 需求、数据源与处理只在 [docs/additional-info.md](docs/additional-info.md) 维护，模块另读 [data_service/additional_info/AGENTS.md](data_service/additional_info/AGENTS.md)。UI 总入口为 [docs/ui.md](docs/ui.md)，通用图表需求只在 [docs/chart-ui.md](docs/chart-ui.md)、持仓 UI 只在 [docs/holdings-ui.md](docs/holdings-ui.md)、图案与图标只在 [Logo / Icon](docs/ui.md#logo--icon) 维护。这些是唯一维护入口，用户当前要求优先于文档。

- 单进程 Python + SQLite + 本机 WebSocket + TypeScript；不新增服务、消息中间件或通用适配框架。
- 每次启动重读 workspace；完整 Longbridge 行情仅覆盖 Focus 与 SnapTrade 当前 Holdings（含仅保留当天的已清仓批次）；Scan/Monitor均订阅完整Discover/Excluded的Quote，日K仍用Massive。订阅范围只在 Longbridge 数据要求维护。Holdings 归属独立，同 ticker 底层行情去重；不以其他历史成交或报告中的 ticker 作为白名单。
- Massive 完整特征覆盖候选、当日人工 Discover、Focus 和有效 Hidden；跨日只继承 Focus/Hidden，机器 Excluded 由当天候选生成、不保存成员身份。保留 Focus 每日自动淘汰，非候选淘汰后退出名单；继承成员不另行排名。详细范围只在 [Massive 数据要求](docs/massive-data.md#名单完整特征范围) 维护。
- 唯一正式 SDK 入口是 [data_service/longbridge/client.py](data_service/longbridge/client.py)。Quote / Trade 与六周期 SDK candle 共用一个行情 context；UI 不调用券商。
- Longbridge 当天 SDK 序列与官方 closed 缓存统一读取，同时间戳由官方历史覆盖；下游只消费最新合并值，修正必须使相关计算缓存失效。开盘保持连接与显示，已知恢复重新取得 candle 起点；具体生命周期只维护在 Longbridge 数据要求。
- Longbridge 服务 Monitor 核心行情、Alert 与 Scan 最新报价（含Overnight），按 [Longbridge 数据要求](docs/longbridge-data.md) 维护可重建缓存；按 symbol/周期复用同日成功历史批次，只按实际闭合边界补缺。Massive 单独存库；两源共用 Bar、指标和显示，不拼接、交叉验证或互相补缺。
- OHLC 正数有限值与基本结构必须验证；仅上下界矛盾保留官方原值，追加 invalid_ohlc.jsonl，不修正、不告警、不重试。
- Longbridge 获取、刷新、失败与状态遵循唯一数据要求文档，不新增历史研究功能。Massive 独立按交易日获取原始文件；split API 保留完整分页及两年窗口覆盖。
- Longbridge 缺失和请求失败用同一回补任务重试；次数与节点见 Longbridge 数据要求。正式服务启动一次 Massive 准备任务，Ready 跳过；网络失败有界重试，本地派生构建失败直接报错，下次从 raw 重建。切模式复用三名单Quote订阅，Monitor/Alert/SnapTrade持续后台运行。不要把 UI 查询变成历史下载触发器。
- 验证优先使用真实数据，可直接使用现有服务，必要时可停止并重启，无需重复确认。真实接口验证明确范围与结束条件；只做本次必要验证。模拟器仍只写临时库、不读凭证、不自动回退真实 API。
- 不输出凭证；Alert 仅按已确认的工程需求开发，不新增 Atomic feature 自动设置、下单、故障注入或回放框架。
- 变更行为同步 behavior；变更职责/契约同步 development；UI 同步 ui 总入口及对应的唯一详细规范，不复制完整规则。验证记录写日期、环境、覆盖和未覆盖范围。
- Android 原生 App 是后续确定目标，iOS 可能接入。维护跨平台的产品语义、图形含义与数据契约，平台绘制和交互细节另行适配；Logo/Icon 只维护一份当前规范，不在 AGENTS.md 复制数值，不提前引入移动端原生框架。Alert 后台声音按其独立需求实现，不依赖原生通知应用。
- TypeScript 改动后 npm run build --prefix ui；数据/调度改动只做相关的必要真实数据验证与定向用例。历史记录不能当成本轮 live 证据。

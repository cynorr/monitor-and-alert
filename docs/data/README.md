# Data 模块维护手册

最后核对：2026-09-19。此文件记录**当前实现**，用于在没有聊天上下文时继续开发。

## 文档分工

| 文件 | 用途 |
| --- | --- |
| [根 AGENTS.md](../../AGENTS.md) | 项目入口、模块边界、维护约定 |
| [data_service/AGENTS.md](../../data_service/AGENTS.md) | 修改数据层时的局部约束 |
| [开发规格](../../Longbridge-Data-Service-Design.md) | 已确认的业务需求与数据不变量 |
| 本文件 | 代码位置、调用关系、开发方法、现状及限制 |
| [README](../../README.md) | 安装、运行与 HTTP 使用方法 |
| [实测报告](../../VALIDATION-REPORT.md) | 带日期的测试证据，不代表现在仍在运行或现在仍 READY |
| [模拟器范围说明](../testing/simulation-plan.md) | 独立盘中 Quote 数据源，取代原复杂提案 |

需求与代码不一致时应明确记录差异；不要靠旧报告或旧聊天推断现在的运行状态。用户最新明确要求优先，需求变更同步修改开发规格和本手册。

## 已确认的业务范围

个人使用的美股 Data Service，负责官方行情、历史数据和数据质量。数据层不包含买卖建议、Alert 公式、通知或 UI。

- 每次启动加载 `workspace.json`，以 `statuses[*].status` 的 `focus` / `wait` 为唯一白名单；`orders` 只排序。不监控文件变化。`--symbols` 只能缩小白名单。
- 实时仅订阅 Quote；价格来自 `last_done`，累计量直接来自官方 `volume`。不同 session 独立存储，不本地累计 Trade/delta。
- 生产数据库只接受官方 NoAdjust、regular session、已收盘的 `1d/5m/15m/30m/1h`。不保存正在形成的 candle、tick、1m、2h、4h；不靠补零或本地聚合伪造官方数据。
- 每次冷启动重新拉取最近 1000 根，各 ticker 按周期分阶段处理；UPSERT 允许官方修订覆盖旧数据。
- 单进程、SQLite WAL、内存行情；可靠和简单优先，不引入分布式组件。

## 文件归属与修改入口

| 当前路径 | 职责 | 应放在这里的变更 |
| --- | --- | --- |
| `data_service/__main__.py` | CLI、依赖装配、单实例锁、启动/关闭 | 启动参数、运行模式 |
| `data_service/config.py` | 白名单与凭证读取、敏感信息脱敏 | workspace 结构兼容、ticker 选择 |
| `data_service/broker.py` | 唯一正式 Longbridge SDK 适配器、限速、配额调用记录 | SDK、端点、请求参数、超时 |
| `data_service/quotes.py` | Quote 内存状态、订阅、snapshot、watchdog、重连 | 实时状态与连接恢复 |
| `data_service/calendar.py` | XNYS 交易日历、session 与 candle 边界 | 假期、DST、提前收盘、时间对齐 |
| `data_service/downloader.py` | 获取/解析/过滤/写入、短历史边界查询、5m 前缀补拉 | 下载与恢复覆盖范围 |
| `data_service/store.py` | `Bar` 校验、SQLite、原子 JSON、配额记录 | 表结构、事务、持久化 |
| `data_service/validator.py` | 从 SQLite 与批次元数据推导 readiness | 完整性验证、降级与状态解释 |
| `data_service/service.py` | 冷启动、单 worker 调度、重试、数据 API 结果 | 数据工作流；不要继续塞 UI 或 Alert 策略 |
| `data_service/http_api.py` | 本地只读 HTTP 传输、状态码、可选 CORS | HTTP 层；业务数据生成在 service.py |
| `data_service/__init__.py` | 无连接副作用的包入口 | 不在 import 时创建券商连接 |
| `tests/test_data_service.py` | 当前离线回归测试 | 数据正确性与失败隔离的测试 |
| `scripts/probe_longbridge.py` | 两个白名单 ticker 的真实接口核对 | 诊断脚本，不能被业务代码 import |
| `scripts/smoke_recovery.py` | PAYS 的真实重连和 closed-bar 更新测试 | 实测脚本，不能被业务代码 import |
| `simulator/` | 独立随机 Quote WebSocket；不依赖或进入 data 流程 | 仅数据生成和推送，见独立 README |
| `runtime/` | 本地数据库、锁、派生状态、日志、实测产物 | 不放业务代码，不提交凭证或实测私有数据 |

后续目录预留（**目前未实现，不因列出而提前创建**）：

| 目录 | 边界 |
| --- | --- |
| `ui/` | 看盘展示，消费 Data API，不直接连接 Longbridge 或写 bars |
| `alerts/` | Alert 基线、规则、去重、通知；消费数据质量状态，不修改官方 bars |

依赖方向：`ui / alerts → Data API`；`data_service → 官方 SDK / SQLite`。模拟器完全独立，不依赖 data_service；模拟 UI/Alert 直接接其 WebSocket。不允许 `data_service → simulator / ui / alerts`。禁止为了展示需求在数据层加入合成 K 线落盘或交易策略。

## 当前执行流程

1. CLI 启动重读 workspace，锁定本次白名单与 runtime。
2. 创建券商适配器、日历、SQLite、Validator；启动 localhost HTTP。
3. Quote 与历史任务分别运行。SDK 请求共享至少 0.55 秒间隔的限速器，单次 15 秒超时。
4. 历史顺序：全部 Daily → 全部 5m → 全部 15m → 全部 30m → 全部 1h。
5. 5m 阶段后验证 READY/降级；最后验证 FULL_READY。报价无需等待历史初始化。
6. 盘中单 worker 优先处理到期 closed-bar 更新，然后处理有界初始化修复；生产存储异常 fail fast，单 ticker API/质量失败隔离。
7. Quote 无推送 watchdog 触发重连；订阅后获取 snapshot，另每 30 秒获取 snapshot 以补足 SDK 自动重连后的状态。

Downloader 不修改 readiness；Validator 不下载。`service.py` 串联二者。

## 时间与覆盖范围

存储和 HTTP bar/quote 时间使用 UTC Unix 秒，交易规则按 `America/New_York`。SDK 5 的 naive 时间由 `sdk_timestamp()` 按机器本地时区解释，再转为绝对时间；不要直接给 naive 值贴 UTC 标签。

- Daily 时间戳是美东零点，关闭时间是交易日实际收市时间。
- 1h 从 09:30 开始，常规尾段为 15:30–16:00；提前收盘同样截短。
- 使用多年 XNYS 日历；正常 78 根 5m 只是普通交易日示例，不能硬编码为完整性判断。
- 最近 1000 根 5m 在盘中可能不足以覆盖此前 12 个完整交易日；按缺失前缀补拉，并把补拉纳入初始化批次验证。
- 正常更新用 count=2；跨多个周期用最近 1000 根并检查缺口。超出该窗口的长中断不承诺自动恢复全部旧缺口。
- 当前 `service.py/quotes.py/downloader.py` 直接读取实际时间；虚拟时钟没有实现，也不再属于模拟器需求。独立模拟器用实际时间戳和 Intraday 标记直接服务下游，跳过本模块整个验证/日历流程。

## readiness 的含义

| 字段 | 含义 |
| --- | --- |
| `ready` | 300 个完整交易日 Daily + 12 个完整交易日 5m 全部合法完整 |
| `degraded_ready` | 不足 300 日，经额外历史查询确认可用历史边界后，较短基线仍完整 |
| `alert_eligible` | `ready or degraded_ready`；仅表示历史基线可用 |
| `full_ready` | 同一初始化批次的五个周期返回范围全部验证通过，允许首日被 1000 根窗口正常截断 |
| `*_through` | 验证覆盖到的已完成交易日；不是下载增量游标 |
| `available_daily_days / available_5m_days` | 当前实现的样本统计，需结合 checks、reasons 与状态解释 |

不足 12 日的新股按有日线的可用日验证；未知缺口不会因新股标签放行。供应商历史边界并非独立核实的 IPO 日期。`available_5m_days` 目前按一天记录数是否完整统计；不能单独替代 OHLCV 校验结论。

FULL_READY 与 READY 独立。Alert 消费端还必须检查 Quote 时效、连接健康及 regular session；`alert_eligible` 不是“此刻允许触发所有策略”的总开关。

## 存储与消费接口

SQLite 包含 `bars`、`batches`、`metadata`。后两张表保存初始化证据和可用历史边界，因此离线恢复 FULL_READY 不会把不同启动批次混在一起。

`data_ready.json` 是可重建的派生输出。`history_symbol_usage.json` 是按月保守记录的请求 symbol 集合，不是券商真实额度余额。删除它不会恢复额度。

当前数据 API 是 **HTTP 轮询**，没有向 UI 提供 WebSocket/SSE 推流。正式模式使用 `/health`、`/v1/universe`、`/v1/quotes`、`/v1/readiness`、`/v1/bars`；模拟模式另接 `ws://127.0.0.1:18766` 的 Quote JSON，尚未实现消费者切换逻辑；具体字段和请求参数见根 README。

## 当前证据与已知限制

2026-09-19 的一次实测：45 个白名单 ticker；26 READY、7 degraded_ready、2 FULL_READY；17 项离线测试通过。详见带日期的实测报告。这些数字不是常量，也不是未来运行的通过保证。

- 部分官方 K 线 open 超出 high/low；已严格拒绝。尚未确认是供应商口径还是源数据错误，不擅自放宽规则。
- 未解释的停牌、无成交、IPO 首日非正常开盘缺口会阻止验证；没有完整证券级例外日历。
- 当前有独立盘中 Quote 网络模拟器；没有业务时钟注入、录制回放、UI、Alert 或自动通知。旧的复杂模拟提案已取消，禁止作为待办恢复。
- 短时 live 测试验证了接入、推送、重连与一次闭合更新，未覆盖全天运行、所有网络故障或所有修复轮次。
- 当前测试主要在一个文件；以后按职责拆分时更新上面的文件地图，避免同时维护两套实现。

## 日后开发与维护

1. 先读规格对应章节、本文件与涉及模块；从已有入口修改，不复制新数据管线。
2. 修改规则时把需求、实现状态、接口影响写清楚；拟议功能标注“待讨论/未实现”。
3. 运行相关离线测试；完整命令为 `.venv/bin/python -m pytest -q`。真实 API 测试单独选择白名单子集和时限，不将其混入默认单测。
4. API 或表结构变更说明兼容性；文件移动同步更新此地图及根/局部 AGENTS 导航。
5. 实测证据注明时间、环境、范围和未覆盖项。更新报告时不要把模拟成功表述为券商 live 成功。
6. 凭证不写入文档、测试 fixture 或日志。不要把历史报告里的 ticker 当作下次可请求的固定白名单。

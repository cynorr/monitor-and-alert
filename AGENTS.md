# 项目工作入口

这是个人美股看盘与 Alert 项目的仓库。当前已实现 Data Service、双图 UI、指标及独立盘中 Quote 模拟器；Price Alert 不在本版范围。不要依赖聊天记忆判断文件归属或功能状态。

## 开始工作时

1. 先读 [README.md](README.md) 确认运行方式。
2. 修改 data 或其消费者之前，读 [Data 模块维护手册](docs/data/README.md) 和 [数据开发规格](Longbridge-Data-Service-Design.md) 的相关章节。
3. 修改 `data_service/` 时遵循其 [局部 AGENTS.md](data_service/AGENTS.md)。
4. 涉及模拟测试时读 [模拟器范围说明](docs/testing/simulation-plan.md)，保持用户已确认的极简范围。用户当前要求优先于旧文档；不要把未确认提案当作已完成需求。
5. [VALIDATION-REPORT.md](VALIDATION-REPORT.md) 是历史实测证据，不是持续运行状态。

## 目录边界

- `data_service/`：正式行情、历史持久化、验证、调度、Data API。
- `tests/`：data/图表离线测试、本机 HTTP/WS 集成及显式浏览器夹具。
- `scripts/`：明确执行才运行的真实接口诊断，不是业务库。
- `docs/data/`：数据层实现地图与维护状态；根设计文档定义需求。
- `docs/testing/`：测试方案与覆盖边界。
- `runtime/`：本地运行产物，不能作为代码或需求来源。
- `simulator/`：独立盘中随机 Quote WebSocket 数据源，不接入 data 的校验/历史流程。
- `ui/`：TypeScript 图表界面与本地 Lightweight Charts，消费 HTTP/WebSocket。
- `alerts/` 不在本版范围，不创建空框架。

后续 UI/Alert 正式模式消费 Data API，模拟模式可直接消费独立模拟器 WebSocket；不得直接调用 Longbridge 或写 authoritative bars。正式 data 不依赖 UI、Alert 或 simulator。具体文件地图在维护手册，移动/新增职责时同步更新。

## 跨模块不变量

- 启动重读 workspace；只有 `statuses` 为 focus/wait 的 ticker 可请求/订阅。不要把历史报告或示例 ticker 当成固定白名单。
- 生产 bars 仅来自官方已收盘 regular-session NoAdjust K 线；模拟、聚合和回放数据必须隔离。
- 正式 data 保留严格数据校验和显式降级，不伪造 READY。独立模拟器按用户要求不走验证，不生成 readiness 状态。
- 模拟器只提供盘中长连接 Quote，不新增异常场景、历史生成、虚拟时钟、适配器框架。
- 不将凭证输出到日志、文档或 fixtures。模拟测试不读真实凭证、不自动回退真实 API。
- 默认离线测试不连券商。真实接口测试独立选择范围和时限，遵守用户当次任务范围。
- 维持单进程、SQLite 和直接可读的实现；不为假想规模引入多层框架。

## 文档维护

变更需求更新设计规格；变更文件归属、已实现能力或已知限制更新维护手册；变更启动/API 更新 README；测试证据写明日期、环境及未覆盖项。提案始终标注状态，实施后再改成已实现。

不能把模拟测试通过表述成券商 live 测试通过，也不能把历史通过记录表述为本轮重新验证。若代码与文档冲突，定位并说明真实差异。

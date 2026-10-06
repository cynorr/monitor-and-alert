# Alert 模块维护入口

先读项目 [README.md](../../README.md)、[开发准则](../../docs/development-principles.md)、[Alert 需求](../../docs/alert.md) 和 [开发维护 / Alert](../../docs/development.md#alert-实现)。engine.py 管业务 SQLite、状态和检测；macos.py 管原生通知，macos/launcher.py 管应用主线程。验证事实以 docs/validation.md 为准。

- `docs/alert.md` 是 Alert 的唯一需求入口，不在本文件复制价格精度、期限、快捷键或 UI 数值。当前用户要求优先。
- Engine 是现有 Python 进程中的独立模块，由 Workbench 管生命周期；不依赖 Chrome、图表选择、网页连接或 Scan/Monitor 展示模式，不新增服务、消息中间件或通用适配框架。
- 只消费共用行情校验入口接受的 Regular 最新价；不引入 SDK context 或直接请求券商。起点、跨日和恢复规则严格遵循 Alert 需求，不使用扩展时段或历史数据补报。
- Alert 按 symbol 归属，每条有独立 ID；不按模式、日期、周期、来源或持仓批次拆分。创建价来自鼠标水平线，不转换 Scan/Monitor 价格口径。
- 允许范围由当前 Focus 与有效 Holdings 决定。Scan Discover/Excluded 创建先入 Focus；与手动移入共用 [List 入选规则](../../docs/list-design.md#统一移入-focus)，不复制 Tag 匹配算法，不继承来源 Tag/人工 section。
- Workspace 归属与同步保存仍由 `workspace.py` 管理，Tag 匹配仍由 `list_rules.py` 管理；Alert 模块不直接改 workspace JSON，也不改变 Holdings 的归属/清仓语义。
- 独立 SQLite 保存 Alert 和未处理事件；写入成功后才返回成功或发送通知。触发状态与事件一起提交，事件处理按 generation 判断，不误删重新设置的 Alert。
- macOS 通知层只承担权限、投递、声音与操作回调；平台回调返回同一业务入口。报告实际错误，不伪造投递成功，不自动回退 Chrome 或重播旧声音。
- 图表使用公开 API，遵循 [Chart 首要准则](../../docs/chart-ui.md#implementation-principle)；图案只维护在 [Logo / Icon](../../docs/ui.md#logo--icon)。UI 全英文；TypeScript 在 `ui/src` 维护并按要求构建。
- 只提供后续函数入口，不新增 Atomic feature 自动设置、算子、下单或该未来功能的测试。
- 验证优先使用现有真实数据/服务，明确 symbols、时限与结束条件；定向用例只补本次必要边界。模拟器只写临时库、不读凭证、不自动回退真实 API。不建立故障注入、回放、压力或恢复框架。
- 变更需求同步 `docs/alert.md`，职责/接口同步 `docs/development.md`，名单入选同步 `docs/list-design.md`，相关总入口保留链接；验证事实写 `docs/validation.md` 的日期、环境、覆盖与未覆盖范围。

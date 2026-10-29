# Schwab Trade MVP

更新：2026-10-29。本文件是 Schwab Trade 产品范围、账户数据、交易交互及接入契约的唯一入口。开发遵循 [development-principles.md](development-principles.md)。[原交易后端设计](../schwab-minimum-trader/backend-design.md) 保留为交易网关协议与安全规则参考，不删除；当前集成方式以本文件为准。

## 范围与模式

现有模式入口为 Monitor / Scan / Trade，三者互斥、所有客户端共享选择。Monitor 使用原 SnapTrade Holdings；Scan 保持扫描功能；Trade 复用 Monitor 的 Daily、Intraday、Focus，显示独立 Schwab Holdings 与交易区。SnapTrade 和 Schwab 各自刷新、各自保存当前成功状态，不拼接账户数据或成本。Scan 切换不停止后台账户和行情任务；自动盘中状态在 Scan 延续上次 Monitor/Trade 账户角色。

正式服务启动即运行一份 Schwab Runtime，与 Longbridge、SnapTrade 同属现有 Python 进程。没有独立前端或 5678 服务。Mock、模拟器及 --symbols 会话不读取 Schwab 凭证、不开放 Trade。正常入口：

```sh
.venv/bin/python -m data_service serve --mode trade
```

凭证继续使用原 macOS Keychain service，首次授权或失效后运行：

```sh
.venv/bin/python -m data_service.schwab_backend auth
```

配置维护在 data_service/schwab_backend.py。旧项目 schwab_backend.py 只转入同一实现，避免维护两份网关。旧 5678 进程必须停用，不能与集成 Runtime 同时刷新同一份 OAuth 凭证。认证失效不影响网页和 Longbridge，重新授权后沿用原后台恢复机制。

## 账户字段与持仓表

一个 symbol 一行，默认顺序为 Entries、实际 Holdings、其他活动订单、仅 Sold Today 的灰色尾行，不显示 section 标题。持仓同时挂买单或当天卖出仍为同一行；分别保留真实订单，操作不按 symbol 合并委托。位置、折叠、选择及表面效果复用现有 Holdings / Symbol row template。

| 显示 | 来源与口径 |
| --- | --- |
| Net Liq | Holding 使用 Schwab positions.marketValue；纯 Entry 使用父单数量 × 买入触发价，不计入持仓 Total |
| P/L | longOpenProfitLoss |
| P/L % | 沿原 Schwab 前端：P/L / (averagePrice × quantity) × 100，缺值为空 |
| P/L Day | currentDayProfitLoss，保持券商口径 |
| 顶部账户总值 | currentBalances.liquidationValue，不以 cashBalance 加本地市值替代 |
| Quantity / Avg Price | 券商当前数量及 averagePrice，在展开后的汇总 Buy 行显示 |
| Chg% / Ext | 现有 Longbridge Quote 与完成 Daily 修正基准；沿用现有时段显示 |
| ADR / CumVol / LocalVol | 复用现有 Intraday State 计算、格式和 Regular 显隐 |

主行顺序为 Symbol、Net Liq、P/L %、P/L、Chg%、Ext、P/L Day、ADR、CumVol、LocalVol。金额取整数、百分比一位小数、详情价格两位小数；缺值显示 —。Regular 隐藏 Ext，ADR/量比按已有时段规则。列排序降序/取消，Entries 固定前部、仅 Sold Today 固定尾部；余仓复用既有风险 rank。

Total Net Liq / P/L / P/L Day 仅汇总当前 Schwab 余仓，日盈亏不包含 Sold Today 的已实现结果，不声称是完整账户日收益。已知缺值不计算部分金额总计。账户与订单保留各自成功更新时间；snapshot 的生成时间不代表账户刚刷新。失败保留成功快照，并在交易区显示认证/REST 状态。

两源原生数据、取数、刷新及会计各自独立。前端共用 palette、Symbol row、折叠/圆形按钮风格和 holdings-layout.ts 的自然内容测宽，不强制共用字段模型或表格 renderer。内容宽度只由必要时的隐藏自然宽度副本决定，价格背景宽度另按实际单元格边框原点计算；禁止用当前已分配的 scrollWidth 反推侧栏最小宽度。报价更新只改已有节点，顺序或展开结构变化才重排。

展开内容一条记录一行。标签位于 Symbol 列并缩进；金额、P/L %、P/L 分别与原表的同名列右对齐，数量、价格、撤单按钮依次移到后续可见列。Entry 额外的止损价、风险比例和风险金额位于其后；缺失额外字段不留空槽，跨列数按当前可见表头计算。可见列较少时，末尾操作与额外字段合并在末列内保持单行，不增加虚列。

- Buy：唯一汇总行，金额仍为 quantity × averagePrice，表示当前余仓成本；P/L%与P/L均留空，后接数量与均价。缺成本直接跳过，不回溯历史买入、不提示缺失。
- Sold：从 sold_today.executions 按真实 order ID 分组，显示成交金额、参考盈亏、实际数量和加权成交价；不建立成本归属或卖出比例。
- Entry：每张买入母单一行，显示名义金额、数量、买入触发价、对应子单止损价、风险比例与金额。risk% = (buy − stop) / buy × 100，risk = quantity × (buy − stop)。多组 Entry 分别配对，不使用其他 Stop；市价单缺少的价格/风险留空。
- Stop：未归入活动 Entry 的每张真实 SELL STOP 单独一行，显示 quantity × Stop、数量、Stop。不堆叠常态状态文字；原生状态、editable/cancelable 仍控制交互。

明细盈亏口径：Buy 不表示卖出或止损收益，P/L与P/L%为空，不显示横杠；主行仍保留券商当前持仓盈亏。Sold 与 Stop 以当前券商持仓 averagePrice 为参考，本条价格分别取成交均价或止损价；P/L = 本条数量 ×（本条价格 − averagePrice），P/L % =（本条价格 / averagePrice − 1）× 100。Sold 是按当前均价估算的参考盈亏，不追溯卖出批次成本；完全清仓后通常没有当前持仓均价，缺正均价或本条价格时两项留空，不显示提示。Entry 尚未成交，P/L 两项为空，保留独立的风险预估。明细盈亏显示整数金额、一位百分比，正负沿用已有配色；不参与 Total，不改变券商主行盈亏。

Entry 每组仅母单保留一个圆形 ×，向该 order ID 发送一次 DELETE，父子联动由 Schwab 处理；独立活动 Stop 按自己的 cancelable 显示 ×。Buy/Sold 成交行无取消按钮。界面不显示 @、解释性分隔符、内部 ID 或 Pending activation 等常态文字；缺失历史直接跳过，无补齐提示或 warning。

主行只用两个小号标记：Entry 表示仍有活动买单；Trim 表示当天有卖出记录且当前仍有余仓。两者可并列。完全清仓行仅为灰色，不显示 Sold/Order 或其他状态标签。

MVP 隐藏 Days、NEW、Sold%、历史买入批次、人工买卖归属及按批次归属的已实现盈亏。不调用 transactions，不使用 SnapTrade 缓存或 sequences/merge_buys，不建立执行账本。

## Sold Today

沿原 trader 范围：从现有最近 59 天创建的订单快照递归查找股票 SELL / FILLED，按最后一笔 execution 的纽约日期判断当天，按 order ID 去除订单树重复出现的订单。累计数量取 filled_quantity，金额为逐笔 quantity × price，均价为金额 / 数量。数量、实际均价及未扣费用的总额保持原生值；明细参考盈亏沿用上方明细口径，不建立历史成本归属。

部分卖出余仓或卖出后买回均保留当日记录；同 symbol 仍一行，卖出信息位于展开详情。没有余仓且无活动买单的当天卖出记录才作为灰色尾行；仍有余仓的卖出只在该 Holding 下展开，并标记 Trim。纽约跨日移除，不依赖页面收到成交声音事件。

保持原支持边界：只统计完全成交订单，不处理跨日分批成交或部分成交后撤单；59 天以前创建的有效订单/止损不承诺完整覆盖。不给这些边界增加历史补取或账本。

## 行情与报警

Schwab 一条 Streaming 连接，继续订阅 ACCT_ACTIVITY 与 LEVELONE_EQUITIES 的 symbol / bid / ask。启动即覆盖完整 Focus，再追加当前 Schwab 持仓、活动 Entries、当天卖出记录和当前选择；差集使用原 SUBS/ADD，重连恢复，MVP 不另加自动退订。不为订阅 Focus 逐股发 REST Quote；选股时只对选中股票初始化交易报价，提交前仍使用原 REST 校验。

Longbridge 完整范围只在 [longbridge-data.md](longbridge-data.md) 维护。Trade 复用现有图表、Quote、指标和订阅连接，不改变原行情数据含义。

自动 Intraday State 仅把当前账户源的真实余仓视为 holding；Entries 与 Sold Today 保留图表，不充当持仓风险身份，也不因仍在 Focus 而重复作为候选。相同 symbol 同时有持仓、卖出记录只计算一次。切回 Monitor 使用 SnapTrade 角色，切入 Trade 使用 Schwab 角色；Scan 延续上次账户角色，改变角色首状态静默。

手动 Alert 仍按 symbol 共享，既有保存线可按原规则触发。Sold Today 不触发自动持仓风险声音，不代表禁用已有手动价格线。未读与声音继续通过同一 AlertEngine，不按列表复制提醒。

## 交易区与图上操作

Trade 在 Intraday header 右侧使用固定行列显示交易区，报价与左上价格同一行、紧邻右上归位按钮的左侧，顶部报价独立固定；下方仅数量、预览和按钮参与底部对齐布局，按钮底边固定，增大三组间距只让预览和数量向上移动。浏览状态隐藏 Qty/预览内容但保留空间，不显示占位横杠；时钟移动到共用 List 顶部模式行右端，归位恢复顶栏右上角，周期按钮位置保留。头部几何、字号与最小宽度只在 [Chart UI](chart-ui.md#trade-mode) 维护，颜色、胶囊与横线只在 [UI / Trade 图形](ui.md#trade-图形) 维护。账户数据、行情与后台行为不变。

- 默认浏览模式，只保留 Schwab 报价、交易方式入口及已有真实订单线，不初始化新单草稿。Buy Stop、Buy Market、Sell 各自直接点击进入对应新单；Buy 的两半均为全高度点击区域，共享 Buy 标题不截获点击。再次点击当前方式回到浏览。切 symbol/账户模式清理草稿，切周期保留草稿。卡片不设置悬停说明，保留可访问名称。
- 数量使用浏览器原生标尺选择正整股，始终保留普通鼠标指针、不接管拖动，仅在轨道左端上方显示数字，不显示 Qty 文字。刻度对应实际数量，始终标注两端，在当前宽度内尽量显示不重叠的数值。买入初始名义金额约 $20,000；步长随股价取约 $500 名义金额，拖动中不变刻度。Sell 初始取当前整股余仓，标尺最右端可准确选择全部整股，不向上超出余仓。
- 三种交易方式都显示相同的参考线。Auto Buy = max(Longbridge 当天 Regular High, Schwab Ask + 0.01)，Auto Stop = 当天 Regular Low；自动状态持续跟随两者。不得用前一天或扩展时段 High/Low 冒充当天 Regular。手动拖动任意参考线即关闭 Auto，点击 Auto 同时恢复两条线；已自动时 Auto 灰色不可点。调整价格不改变已选数量。
- Daily 与 Intraday 的 candle pane 同时显示同一组交易线，任意一图可直接拖动，另一图同步。不设置常驻价格把手、线旁文字或价格输入框；价格只在右轴显示。市价买卖的参考线不传入订单，也不附加止损；名义金额按 Ask/Bid 估算，只有 Buy Stop 显示止损价差风险。
- 当前 symbol 的活动 Stop 常驻，多单分别画真实价格，不合成平均止损。AWAITING_PARENT_ORDER 子单及其他不支持的状态只读。标准 SELL STOP 的 PENDING_ACTIVATION 状态允许盘前、盘后及夜盘拖动并 Send 申请改单，包括 Schwab 将其 editable 标为 false 的情况；其他可编辑状态仍要求 editable=true。不增加已提交 BUY 改单。
- 新单持续预览，点击 Send 一次提交当前 symbol/数量和该接口所需价格，期间冻结草稿及操作，Send 保持原文字和位置、禁用并设置 busy 状态。前端只要求所需字段为正有效值、数量为正整股；不重复执行后端价格关系和风控判断。成功回到浏览，不自动重填数量。
- 拖动真实 Stop 只改本地预览，同时退出新单状态；右下角同一个 Send 改为提交这一张止损的 PUT，每次只编辑一张真实 Stop；再次拖另一张或点击新单方式会放弃上次尚未提交的改价。等待券商新 ID/快照期间不重复发送该改单。Esc 撤销尚未提交的真实改价。撤单保留明确的独立按钮，不绑定 Backspace。
- 预估金额和价差风险是估算，不称最大损失；STOP 不承诺执行价格。后端提交前的新 Bid/Ask 可导致拒绝，不自动改用户价格或重发。错误、认证与 unknown 保留必要反馈，正常就绪不堆叠提示。

交易报价突出 (Ask − Bid) / Bid × 100%，其右侧 Ask 在上、Bid 在下，绝对差值位于 Bid 右侧并与其底部对齐。百分比严格大于 config/trade-ui.json 的 spread_warning_percent 时，百分比使用红色粗体；默认 0.5（单位为百分比数值）。该文件随 npm build 复制为静态 trade-ui.json，修改后重新构建并刷新页面；不新增后端配置或交易路由。

## 风控与写入契约

统一买入名义金额上限 $45,000、突破单估算价差风险 $2,000、止损比例 15%；前端读取实际配置。保留固定 NORMAL、DAY / GTC 和原五个交易函数。NORMAL 决定常规时段执行，不将本机当前时段作为下单或改单门禁；盘外止损改单仍保留 NORMAL，不转为扩展时段执行。市价卖出不隐式取消止损，Replace 不执行 Cancel+Place。止损执行时段参考 [Schwab 官方说明](https://www.schwab.com/learn/story/stop-orders-mastering-order-types)。

网关仍使用 Decimal、严格正整数数量、十进制字符串价格和拒绝未知字段的请求模型。只监听本机；交易入口检查 Host、同源 Origin 与 JSON，不使用普通名单 mutation 的错误/重试提示替代交易契约。

每个交易操作最多一次券商写请求。收到现有接口的 accepted 响应后，仅显示 Accepted，约两秒后独立消失，不等待或耦合 Holdings、订单刷新及其他接口，也不被这些刷新延长计时；表示请求被接受，不表示成交。已知浏览器离线时不发请求，显示 Not sent · offline。已尝试的写操作超时或连接丢失分别显示 Request timed out · result unknown / Connection lost · result unknown；未知响应仍为 unknown，不自动重发，也不冒充确定未发送。unknown 常驻提示提供只读 Refresh orders 与人工核对后的清除操作；读取订单不代表原写入已经确认。后来的错误不受 Accepted 旧计时器影响。

## 实现入口

- data_service/schwab_backend.py：原交易核心，Keychain、认证、REST、Streaming、Runtime、TradingGateway；旧独立 API 保留兼容，不随主服务另起端口。
- data_service/trade.py：独立账户投影、Sold Today、订阅入口、严格请求模型到原网关的调用，不操作 SnapTrade。
- workbench.py / http_api.py：三模式、生命周期、范围、独立状态、固定交易 HTTP 路由及原 WS 的 trade_quote 推送。
- ui/src/schwab-data.ts：完整原生响应类型、订单树去重、Entry/Stop 读取、汇总 Buy 与当天 Sold 明细、原生余仓及止损/卖出参考盈亏；不引用 SnapTrade。
- ui/src/schwab-holdings.ts：Schwab 表格、排序、选择与稳定节点更新；与 Monitor 共用 holdings-layout.ts 的纯 DOM 测宽及 Symbol row/attention/palette。
- ui/src/trade.ts：交易草稿、预览、Send 分派、请求与 unknown；trade-lines.ts 负责双图交易线；price-lines.ts 与 Alert 共用坐标、命中及绘制；ui/src/main.ts 复用 symbol/request_id/mode/source/socket 身份检查。

本地入口为 GET /v1/trade、GET /v1/trade/quote?symbol=…、GET /v1/trade/orders，以及 POST /v1/trade/orders/{market-buy|market-sell|breakout-buy}、PUT /v1/trade/orders/{id}/stop、DELETE /v1/trade/orders/{id}。读取 chart/list/trade 状态不触发账户历史下载。交易写入只在正式 Trade 模式接受，Mock / 模拟器不可启用。

原项目导入时携带的 Git 元数据已完整备份到本机 `runtime/import-backups/schwab-minimum-trader-2026-10-27.git`；网关兼容入口、测试和 backend-design 保留为主仓库普通文件。已被替代的独立前端源码及其设计/开发文档移出维护源码，原导入文件保存在忽略的 runtime/import-backups/schwab-original-ui-2026-10-28，不由应用读取。

# Schwab Trade MVP

本文件是 Schwab Trade 产品范围、账户数据、交易交互及接入契约的唯一入口。开发遵循 [development-principles.md](development-principles.md)。[后端网关设计](schwab-backend.md) 维护认证、内存、恢复、协议及安全规则；当前集成方式以本文件为准。

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

配置和唯一网关实现维护在 data_service/schwab_backend.py。Keychain service 名沿用既有值，不随源码目录清理而修改。正式服务只运行一份集成 Runtime，不另起 5678 服务刷新同一份 OAuth 凭证。认证失效不影响网页和 Longbridge，重新授权后沿用原后台恢复机制。

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

Trade 复用 Daily/Intraday 图表，顶部报价固定在归位按钮左侧，时钟位于共用 List 顶部。底部数量、预估、策略与 Send 的几何只在 [Chart UI](chart-ui.md#trade-mode) 维护，颜色与图形只在 [UI / Trade 图形](ui.md#trade-图形) 维护。浏览时隐藏数量/预估但保留空间；选择策略不会移动报价或 Send。

- 底部两个独立单行胶囊：蓝色买入 `Market / Stop`，红色卖出 `Market / ATR / EMA`。每项直接选择，再点 Send；无大号 Buy/Sell 标题、二层标签、隐藏类型或 Review。再次点击当前项回到浏览。卡片无悬停说明，保留可访问名称。
- 买入初始约 $20,000，数量步长约 $500 名义金额。市价卖出默认当前余仓的 30% 向下取整，显示实际股数及占余仓百分比，提供 25/30/40/50% 快捷选择，最右端可准确选全仓。卖出与真实 Stop 编辑步长为一股。ATR/EMA 固定全仓，数量标尺只读。
- 数量轴保持浏览器原生 range 与普通鼠标指针，不接管拖动；拖动期间冻结刻度。Auto 已开启时灰色禁用；拖动草稿线后解除自动跟随，Auto 可恢复所选策略公式，不改变手选数量。
- Buy Stop 及市价参考线：Buy = max(Longbridge 当天 Regular High, Schwab Ask + 0.01)，Stop = 当天 Regular Low；市价订单不提交参考价格、不附加止损。缺当天 Regular 数据不使用前一天或扩展时段替代。Buy Stop 的父子结构不变。
- ATR/EMA 只画一条红色目标 Stop；Daily/Intraday 显示和拖动同一份草稿。自动模式在 Send 时取最新参考并冻结为两位小数，手动模式提交可见目标价，不偷偷恢复公式。
- 已有活动 Stop 常驻，多单分开显示。点击可编辑线即载入该单数量；可只改数量、只拖价格或同时修改，统一点 Send 提交一张 PUT。选另一张 Stop/新策略放弃未提交编辑，Esc 清除编辑。PENDING_ACTIVATION、AWAITING_RELEASE_TIME 均可申请修改，包括 editable=false；AWAITING_PARENT_ORDER 不可编辑。延迟 Stop 的手动修改保留原 DAY/releaseTime。
- Stop 目标价必须为正且低于当前 Bid，否则 Send 禁用。后端在撤任何旧单之前使用新 Schwab Bid 再校验；失败不撤旧单、不切为市价。新单与真实改单发送期间冻结操作；成功回浏览，真实替换等待新 ID 出现在快照前禁用重复提交。

报价突出 (Ask − Bid) / Bid × 100%，其右侧上方 Ask、下方 Bid，绝对差值在 Bid 右侧底部对齐。百分比严格大于 ui/src/trade.ts 的 SPREAD_WARNING_PERCENT 时使用红色粗体；默认 0.5，单位为百分比数值。显示金额为整数，Risk 保留两位百分比和整数金额；它是价差估算。

## 卖出策略

### Market

Send 时刷新 Schwab 持仓及活动订单。若未被 Stop 占用的仓位足够覆盖本次数量，直接市价卖出；不足则取消该 symbol 的全部当前持仓 Stop，确认 CANCELED 后立即发送本次数量的市价单。不缩减 Stop、不重建剩余保护、不回滚。未成交买单的保护子单不占用当前余仓。取消尚未确认、失败或结果未知时停止，明确显示实际进度，禁止自动重发。

### ATR

目标价 = 提交时当天 Regular High − 1.1 × 上一完整交易日的 Wilder ATR20。ATR20 复用现有 true_range/wilder_atr 算法及 Longbridge 合并后的 closed Daily，排除当天；按图表 revision 缓存，不使用 ADR 百分比换算、不触发额外行情请求。

提交普通 NORMAL/GTC 全仓 Sell Stop：无旧 Stop 时新建，一张时修改价格和数量，多张时全部撤销并确认后新建一张。已有延迟 Stop 改为 ATR 时清除 releaseTime 并改用 GTC。

### EMA

只有 10/20 两项。进入 EMA 时默认选当前 Daily EMA 较高的一项；相等时选 10。用户可直接切换，之后不会自动更换周期。参考价来自与图表相同的 closed Daily 序列及当前 indicator_preview，不使用鼠标悬停的历史值。

Send 将选定 EMA 冻结为静态两位小数价格，覆盖全部当前持仓，NORMAL/DAY，releaseTime 为当天实际收盘前 30 分钟（交易日历处理半日市和夏令时，以 UTC ISO 发送）。已到激活时刻且未收盘则发送即时 DAY Stop、不带过去的 releaseTime；收盘后或休市日不可发送当天 EMA 单。

EMA 直接替换旧 Stop，旧保护不持续到延迟激活。单张优先 PUT 改为 DAY/releaseTime；明确不支持替换或券商明确拒绝时撤旧并确认后新建。超时或结果未知禁止转为撤旧重建。多张旧 Stop 全撤确认后新建一张；无旧单直接新建。当天未触发则随 DAY 到期，不恢复旧 GTC。无本地定时器、夜间策略服务或动态 EMA 追踪。

releaseTime 的券商实际支持、激活时已低于 Stop 的触发方式、DAY 失效及数量替换由本人使用小仓实测；已发送到 Schwab 的有效订单由券商管理，不要求本机整晚在线。

## 风控与写入契约

买入名义金额上限 $45,000、Buy Stop 估算价差风险 $2,000、止损比例 15%；前端读取实际配置。普通订单使用 NORMAL，市价及 Buy Stop 母单 DAY、保护子单 GTC；时段决定执行规则，不将本机当前时段设为止损改单门禁。EMA 使用上面的固定 DAY/releaseTime 契约，不暴露通用订单参数。

网关保留 Decimal、严格正整股数量、十进制字符串价格、拒绝未知字段的请求模型以及本机 Host/同源 Origin/JSON 校验。每个底层交易函数最多一次券商写请求；trade.py 只组合上述已明确选择的卖出流程，同一时间接受一个工作流。取消最多等待五秒确认；未确认不发送后续订单。没有交易写重试、通用编排框架或交易账本。

Accepted 独立显示约两秒后消失，不等待 Holdings/订单刷新，也不代表成交。已知离线不发请求，显示 Not sent · offline；写入超时或连接丢失按 result unknown 处理，不自动重发。unknown 提供只读 Refresh orders 及人工核对后的清除操作。中途撤单后的失败/未知保留已请求撤销的订单 ID 和必要提示，不伪装成全部成功。

## 实现入口与接口

- data_service/schwab_backend.py：认证、Keychain、REST、单条 Streaming、Runtime、固定网关函数。买入核心不变；Stop 支持可选数量、保留/显式更新有效期及 releaseTime，新增固定 place_stop。旧兼容 API 不另起服务。
- data_service/trade.py：原生账户投影、Sold Today、订阅及显式卖出流程；不读取 SnapTrade、不增加落盘。
- workbench.py / chart_cache.py：从现有 Longbridge Daily/Quote/交易日历提供 trade_reference；读取不下载历史。http_api.py 使用原交易专用访问、校验及 unknown 契约。
- ui/src/schwab-data.ts / schwab-holdings.ts：原生订单/成交字段、展示和节点更新；仅复用通用表面与测宽。
- ui/src/trade.ts / trade-lines.ts：所选策略、数量/比例、统一 Send 和双图线；price-lines.ts 与 Alert 共用绘制/命中。main.ts 保持既有选择身份检查。

| 本机接口 | 参数 |
| --- | --- |
| GET /v1/trade | 只读账户与订单状态 |
| GET /v1/trade/quote?symbol=… | 当前 Schwab Bid/Ask |
| GET /v1/trade/orders | 刷新活动及近期订单 |
| POST /v1/trade/orders/market-buy、market-sell | symbol、qty |
| POST /v1/trade/orders/breakout-buy | symbol、qty、buy_stop、sell_stop |
| POST /v1/trade/orders/atr-stop | symbol；手动目标可传 price |
| POST /v1/trade/orders/ema-stop | symbol、ema（10/20）；手动目标可传 price |
| PUT /v1/trade/orders/{id}/stop | new_stop；可选 qty，省略则保留原数量 |
| DELETE /v1/trade/orders/{id} | 只取消指定订单 |

ATR/EMA 不接受客户端数量，后端刷新后取全仓，当前全仓 Stop 要求持仓为整股。price 为正十进制字符串，省略表示在 Send 时计算固定公式；EMA 周期不接受 Max。view 的 trade_reference 含 atr20、ema10/ema20、当天 high/low、server_time、session_close、release_at。订单 release_time 原样映射 Schwab releaseTime。

交易入口只在正式 Trade 模式开放。网关、接入、策略定向测试分别在 tests/test_schwab_backend.py、tests/test_trade.py、tests/test_trade_strategies.py；金融协议用假凭证/MockTransport，绝不提交真实订单。行情验证优先读取当前正式服务的真实数据。

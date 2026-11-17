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

一个 symbol 一行，默认顺序为 Entries、真实 Holdings、其他活动订单、仅 Sold Today 的灰色尾行，不显示 section 标题。持仓、活动买单和当天卖出共用同一行。主行当前估值不使用 FIFO 成本重算，来源保持独立：

| 显示 | 来源与口径 |
| --- | --- |
| Net Liq | Schwab positions.marketValue；纯 Entry 使用母单股数 × 买入触发价，不计入持仓 Total |
| P/L | Schwab longOpenProfitLoss |
| P/L % | longOpenProfitLoss / (averagePrice × quantity) × 100；仅依赖当前 Positions |
| P/L Day | Schwab currentDayProfitLoss |
| 顶部账户总值 | Schwab currentBalances.liquidationValue |
| Days | 当前 FIFO 最老未清批次的买入日期；旧批卖完后转下一批 |
| Sold | 本轮累计卖出数量 / 本轮累计买入数量 × 100 |
| Chg% / Ext | 共用 Longbridge Quote 与完成 Daily 修正基准 |
| ADR / CumVol / LocalVol | 共用 Intraday State，沿用 Regular 显隐 |

主行顺序为 Symbol、Sold、Net Liq、Days、P/L %、P/L、Chg%、Ext、P/L Day、ADR、CumVol、LocalVol。Sold 不显示列名，使用与历史日期一致的11px Muted灰色，保留列头区域的排序操作。金额取整数，P/L%与Chg%一位小数，Ext与成交价两位小数。Sold 为整数百分比，零留空，非零但四舍五入为零显示 <1%。缺值显示 —，明细缺值留空。Regular 隐藏 Ext；ADR/量比按现有规则。排序只影响余仓，Entries 固定前部，纯 Sold Today 固定灰色尾部。

Total Net Liq / P/L / P/L Day 仅汇总当前券商余仓；P/L Day Total 不合并已清仓交易，保持券商当前持仓口径。主行盈亏、账户净值和行情不等待历史整理成功；FIFO、Days、Sold 或明细成本不可用时只影响相应派生字段。账户、订单和历史分别保留自己的成功时间，不把视图生成时间当刷新时间。

表面复用 Holdings / Symbol row template、palette、attention 和 holdings-layout.ts 的纯 DOM 自然测宽，账户和会计不引用 SnapTrade。内容宽度由隐藏自然宽度副本决定，不使用已分配 scrollWidth 反推最小宽度。普通报价更新复用节点，顺序或明细结构变化才重排。

## 历史范围与成交链

只接受正常多头股票/ETF买卖：assetType=EQUITY、有 orderId，Transactions 为 TRADE/VALID，正数 OPENING 为买入、负数 CLOSING 为卖出。期权腿、卖空/回补、无 orderId 的记录直接跳过，不用 activityId 补造订单，不猜配、不引入对账或特殊操作恢复框架。有 orderId 的重复 Transactions 记录仍用其原生 activityId 去重。

Transactions 主动读取最近365天，启动和纽约跨日各读一次，复用原认证及 GET；记录仅在内存，重启从券商重建，不落盘。达到接口3000条上限时不把截断响应当完整历史。读取失败保留成功历史；历史读取错误不污染交易 REST 健康或阻塞当前持仓。

成交日期使用交易发生时间转纽约日期，不用订单创建、改单或结算日。每个日期只有一个来源：

- 今天之前的成交只使用 Transactions，同一 orderId 的股票成交汇总数量、金额与实际成交时间。
- 今天的成交只使用现有 Orders 中完全成交且带 executions 的 BUY/SELL；当前只支持原59天创建订单的查询范围，不增加部分成交或跨日分批成交处理。
- 同一订单不叠加两份数量；当天 Transactions 不参与，纽约跨日后该日期交给 Transactions。历史尚未补齐时派生缺值，不用昨天的 Orders 猜补。Entry、未触发 Stop 和撤单不充当实际成交。

历史涉及的其他 ticker 不扩大正式行情订阅。普通行情范围只按 Longbridge 数据要求维护。

## FIFO、Days、Sold 与 NEW

从当前真实 Positions 股数倒序处理成交：遇到买入减去股数，遇到卖出加回股数；第一次回到零即找到本轮起点。更早轮次不参与当前轮次。负数不是清仓边界，无法建立可靠顺序或数量不符时派生缺值，不把负数清零猜测。

本轮再按时间正序执行 FIFO：买入追加批次，卖出扣除最老余仓批次，扣完转下一批。只使用成交价与 Decimal 数量计算税费前价差。主行仍只有一个 symbol，多批次在展开明细中显示。

- Days 取 FIFO 队首剩余批次日期。买入当天为0；自然日差不超过7时只计周一至周五，不处理休市日；超过7直接取自然日差。纯清仓行冻结最后清仓前余仓的 Days。
- Sold 统计从零建仓到再次归零的整轮累计卖出/买入。加仓扩大分母；完全清仓为100%，当天重新买入开启新轮并清零进度。
- NEW 使用最新实际买入成交日期，纽约当天买入或加仓均显示；与 Days 起点独立。未成交买单不算买入，周末 Days=0 不等于 NEW。
- 未在窗口内找到本轮起点时，窗口前余额作为未知旧批次参与 FIFO，不编造其成本或买入日期。旧批次仍剩余且已成功读取完整窗口时 Days 显示 >1y；旧批次已卖完，只剩窗口内批次时 Days 正常计算。整轮分母缺失则 Sold 留空；无法确定的成本及盈亏留空。

主行标记仅保留 Entry 和 NEW，复用 symbol-flag。完全清仓仍为灰色行，不增加额外状态标签。

## 展开明细与 Sold Today

下拉每条记录单行，显示当前轮次的逐笔 Buy/Sold、当天更早结束轮次的 Buy/Sold，以及真实 Entry/Stop。不把历史已结束旧轮次铺入当前持仓，不再生成一条虚构的平均成本 Buy。

- Buy：按真实买入订单分别显示日期、原买入金额、数量、成交均价；Days/P/L两项留空。
- Sold：按真实卖出订单显示日期、金额、FIFO买入成本对应的税费前价差与比例、卖出时 Days、数量及成交均价。一笔卖出跨多个批次时内部累加成本，界面仍只显示一条 Sold；缺对应成本时盈亏留空。
- Entry：每组母子买单保留原名义金额、数量、买入价、保护 Stop、风险比例及金额；只有母单保留一个圆形 ×，取消联动交给券商。
- Stop：每张真实活动 SELL STOP 独立显示数量×Stop、数量和价格；预估盈亏继续使用当前券商 averagePrice，不混入 FIFO 历史已实现盈亏。只按 cancelable 显示圆形 ×。

历史 Buy/Sold 保持同级、按成交时间排列，以浅灰树线表达同一 symbol 归属，不绘制买卖配对或嵌套批次。历史行移除常驻及悬停背景；树干对齐主行symbol首字母中心，当前Web距单元格左边21px，由CSS的 --history-tree-x 统一控制。文字在树干右侧20px，分支连向5px圆点，末条历史行在圆点中心收尾。圆点含义只维护在 [Logo / Icon](ui.md#操作与状态图标)。Entry/Stop 保留原订单行和取消交互，不加入历史树线。

Buy/Sold 类型12px，位于 Symbol 单元格；明细数量移至 Symbol 和 Net Liq 之间，与主行 Sold 百分比右对齐，保留原11px字号与正常明细颜色。金额、Days、P/L%、P/L 对齐主行同名列，价格位于Chg%列。历史日期与主行P/L Day列右对齐，使用11px Muted灰色；取消操作保留原位置。文本使用正常表格布局参与自然测宽，不绝对定位覆盖其他字段；Entry额外字段合并在末尾可见区域。不显示内部 ID 或常态订单状态，不增加缺失历史提示。

Sold Today 的显示范围沿用当前订单中完全成交股票 SELL 的最后 execution 纽约日期；有余仓时卖出位于同一 Holding 下拉，无余仓且无活动买单时灰色尾行。当天清仓再买回仍只显示一条当前 symbol 主行，其旧轮次明细保留在下拉，Sold 统计新轮次。纽约跨日移除昨日纯清仓行。

## 可逆持仓预览

正式命令默认使用真实 Positions。本人观察显示时可启动：

```sh
.venv/bin/python -m data_service serve --mode trade --schwab-holdings-preview
```

开关只在内存展示副本忽略纽约最近30个自然日的 Sell，以真实余仓加被忽略卖出股数推导预览股数。剩余成本由同一 FIFO 得到，Net Liq/浮盈亏按真实 Longbridge 最新价估算，P/L Day 留空；官方账户净值继续保持真实值。原始 Transactions、Orders、Positions 不被删除或改写。

表头显示 Preview，交易卡片显示 Holdings preview · trading disabled。前端禁用 Send/撤单，后端 Trade 接入层拒绝所有金融写操作；原交易网关函数不变。预览标的不获得真实持仓自动风险身份，当前预览展示范围可取得行情。该临时显示保持到本人明确要求关闭；重启时去掉 --schwab-holdings-preview 即恢复真实持仓，无须恢复文件或重新导入记录。

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
- data_service/trade.py：原生账户投影、低频历史生命周期、可逆预览、Sold Today、订阅及显式卖出流程；trade_history.py 只做正股/ETF 成交归一、轮次截取、FIFO 和展示派生，不读取 SnapTrade、不落盘。
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

交易入口只在正式 Trade 模式开放。网关、接入、策略及历史定向测试分别在 tests/test_schwab_backend.py、tests/test_trade.py、tests/test_trade_strategies.py、tests/test_trade_history.py；金融协议用假凭证/MockTransport，绝不提交真实订单。行情验证优先读取当前正式服务的真实数据。

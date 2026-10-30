# Longbridge 数据说明

本文件是 Longbridge 数据需求、官方接口、处理与缓存的唯一维护入口。多账号配置、选号与访问台账只在 [longbridge-accounts.md](longbridge-accounts.md) 维护。模块职责见 [development.md](development.md#longbridge-同步与缓存实现)，图表显示见 [chart-ui.md](chart-ui.md)，下游需求见 [intraday-state.md](intraday-state.md)、[alert.md](alert.md)、[holdings-data.md](holdings-data.md)。

## 目标与前置条件

- Quote、SDK candle 到达即可使用，图表、名单、持仓与提醒不等待全部历史任务完成。
- 当天采用官方 SDK 实时 candle 追求时效；已闭合数据由官方历史查询持续修正。前置条件是官方历史响应中的有效 closed candle 为最终权威值。
- 所有消费者通过同一份最新数据计算，不识别 SDK/历史来源，不缓存不可失效的计算结果。历史修正按普通数值变化处理。
- 接受 SDK 在漏成交、短断线后出现暂定误差，包括尚未闭合的大周期。已知休眠/恢复重新初始化各周期起点；未识别的短断线影响在相应周期闭合后由历史查询修正。
- SQLite 是可重建的近期行情缓存，不是历史归档。每次全量查询只请求最近1000根，不分页；1000是单次请求数量，不是保存或显示上限。
- Regular 开始后的官方复权基准假定当日稳定；每个美东交易日零点后重新取得整份窗口，处理 split/adjust 变化。零点是本项目的准备时间，不是供应商承诺的最终规整时刻；新窗口验证成功前仍可查看旧缓存。

## 定位与范围

Longbridge 服务 Monitor 的 Daily / Intraday、名单、持仓行情、Alert 和 Intraday State，以及 Scan 的最新价格标记。完整行情范围为当前 Focus、SnapTrade 当前 Holdings（含当天清仓批次）及 Schwab 当前持仓、活动订单和 Sold Today 的并集，symbol 去重；只从当前账户/订单快照派生，不使用其他历史成交扩大范围。Trade 的账户与订单范围见 [Schwab Trade](schwab-trade.md)。这些 symbol 请求 Quote、Trade 和六周期行情，并进入既有 Alert 白名单。当前余仓的自动风险监控范围另见 Intraday State，不把已清仓批次加入风险监控。Schwab 的 Entries 和 Sold Today 只提供图表，持仓角色仅取真实余仓；模式切换与风险身份规则见 Intraday State。

正式服务在Scan与Monitor两种模式都订阅有效workspace完整Discover / Focus / Excluded（含Hidden）的Quote，不随模式、折叠、Filter或选中股票缩减。Focus / Holdings仍保留完整行情，其余成员仅Quote，不请求Trade/candle或历史、不写bars、不加入Alert。全部按symbol去重，名单变化按差集增删；切模式复用已有订阅和缓存。三名单通常少于200只，沿用官方批量订阅及快照，不新增分批上限。

唯一 SDK 入口为 `data_service/longbridge/client.py`。主账号提供应用使用的报价；官方 K 线与 SDK candle 通过统一入口选择所属账号，各账号独立复用 `AsyncQuoteContext`。context 持有连接、订阅和 candle 内存，关闭网页不停止后台。账号生命周期与访问台账只维护在 [多账号文档](longbridge-accounts.md)。

Scan 日 K 与指标使用 Massive，Monitor 使用 Longbridge；两源分别存库，共用 Bar、指标与显示，不拼接、交叉验证或补缺。

### 最新报价与 Overnight

SDK配置显式启用`enable_overnight=True`，Pre、Intraday（Regular）、Post和Overnight共用现有Quote订阅、快照和连接恢复；不为扩展时段创建独立连接或回补任务。三名单Quote在Regular及非Regular均常驻，切Scan/Monitor不退订；只有成员变化才按差集调整。

各时段在内存保留最后一份有效报价。`RealtimeFeed.output`统一以报价的`timestamp`选取最新值，通过`quote.latest`提供给显示层；无报价为null。不按当前时钟屏蔽旧时段，不按消息到达顺序或固定时段优先级选价；缺少新报价时继续显示最后值。来源直接保留官方`trade_session`，不推断新成交、不增加Last Post等提示。`quote.regular`和`quote.extended`保留原始分时段报价，供既有Regular指标与持仓等消费。

最新Scan日的Daily显示`quote.latest`；历史Scan不显示实时报价。Monitor双图在最新值来自Pre/Post/Overnight时显示独立价格标签，最新值为Intraday时继续使用原生candle价格；Intraday顶部价格同样读取latest，不另行选价。标签颜色按报价来源，而非当前时钟，具体外观只维护在Chart UI。所有报价只存内存；扩展报价不生成或更新candle、volume、指标或数据库，不参与Regular Alert/Intraday State。无新报价时不设置价格过期计时或额外恢复机制。

## 官方接口及特点

固定依赖 Longbridge Python SDK 5.0.0。官方历史查询使用 `ctx.candlesticks`，通过所属账号的行情 context 请求通道获取；实时 candle 使用同一所属 context。

| 接口 | 含义与本项目使用 |
| --- | --- |
| `ctx.subscribe(symbols, [Quote, Trade])` | 批量订阅完整范围的报价与逐笔成交；两种模式的其余名单成员只订阅Quote。单次最多500个symbol，没有20只分批限制。 |
| `ctx.set_on_quote(callback)` | 最新报价推送。主要字段为last_done、open/high/low、timestamp、日累计volume/turnover、trade_status、trade_session；用于最新价、ADR盘中状态、持仓估值与手动价格线。 |
| `ctx.quote(symbols)` | 批量报价快照，含Regular、prev_close和可用pre_market_quote/post_market_quote/overnight_quote。初始化补齐当前状态，此后每30秒刷新；快照不冒充推送计数。 |
| `ctx.subscribe_candlesticks(symbol, period, Intraday)` | 每次一个symbol/周期；首次返回最近最多1000根NoAdjust起点，并注册该周期持续计算。重复注册已存在的周期只返回SDK缓存。 |
| `ctx.set_on_candlestick(callback)` | `PushCandlestickMode.Realtime`下接收该周期完整OHLCV快照；既接收开放根更新，也接收闭合/换桶更新。应用用整根新值覆盖同timestamp，不累加volume。 |
| `ctx.candlesticks(symbol, period, count, ForwardAdjust, Intraday)` | 官方历史查询，count最多1000；响应可能含未闭合尾根，本项目只提交实际closed行。六周期分别查询，不从小周期合成。 |
| `ctx.unsubscribe_candlesticks(symbol, period)` | 删除SDK周期状态。显式Quote/Trade仍订阅时为本地删除，不套网络请求限速。随后重新注册才会重新取得官方起点。 |
| `ctx.unsubscribe(symbols, types)` | 移出范围时批量退订对应Quote/Trade；实际网络请求仍受公共额度约束。 |
| `ctx.static_info(symbols)` | 搜索/新增时验证ticker，不因此扩大行情订阅范围。 |

Quote / Trade是同一连接中的不同消息类型。Trade是逐笔成交，不是Bid/Ask盘口；字段包括price、volume、timestamp、trade_type、direction、trade_session，其中volume为该笔成交量。普通美股分钟candle由官方SDK合并Trade；Daily由SDK的Quote日行情逻辑更新。应用不处理逐笔加总，不通过Quote减历史量得到分钟量，也不自行生成大周期。

candle包含timestamp、open/high/low/close、volume、turnover、trade_session；volume/turnover为该根截至当前收到行情的累计值。SDK datetime通过统一解析转换为Unix秒。同一账号增加分钟周期主要增加初始化请求、SDK本地计算与应用callback，不为每个周期新增连接或持续Trade网络流；各周期仍各有初始化及官方closed查询成本。

六周期固定为 `1d / 5m / 15m / 30m / 1h / 2h`。SDK初始化只使用属于当前美东日期的全部有效candle，保留当天已结束根与开放根；此前的NoAdjust行不进入显示或数据库。历史库采用ForwardAdjust，当前日SDK原始值与其直接连接显示，不二次复权。SDK `is_confirmed`不决定SQLite提交。

官方参考：[Overnight配置](https://open.longbridge.com/docs/qa/broker#q7-enable-overnight-quote-in-openapi-sdk)、[批量订阅](https://open.longbridge.com/docs/quote/subscribe/subscribe)、[报价快照](https://open.longbridge.com/docs/quote/pull/quote)、[逐笔成交推送](https://open.longbridge.com/docs/quote/push/trade)、[最近K线](https://open.longbridge.com/docs/quote/pull/candlestick)、[Python SDK](https://longbridge.github.io/openapi/python/reference_all/)、[SDK 5.0.0 初始化/合并/恢复源码](https://github.com/longbridge/openapi/blob/v5.0.0/rust/src/quote/core.rs)。

## 统一读取与下游计算

内存 `ChartCache.live[(symbol, period)][timestamp]` 保存当天SDK序列；SQLite保存官方closed。统一读取按以下顺序合并：

1. 放入当天已经结束的SDK根。
2. 用SQLite同周期历史覆盖相同timestamp。
3. 按timestamp排序，当前开放根独立作为active，来自该周期SDK。

不维护逐根source/final标记。后到SDK包只改内存，读取时仍由数据库自然覆盖，不能把权威值改回去。SDK仅更新open时复用closed指标；SDK换桶、历史修正或替换导致最终closed序列变化时递增图表revision，重建该周期指标及volume参考。最终序列未变不重发历史。

图表不等待官方closed请求或下一根SDK open同时就绪：旧open到时后直接留在closed序列，下一根SDK到达即追加；历史稍后覆盖。新的开放根尚未收到时也不删除刚结束的根。Daily刷新没有5m依赖。全量请求先准备新数据，再一次替换，等待期间保持已有图表、报价和有效盘中数值。

图表五日量比、CumVol / LocalVol、EMA与ADR历史基准读取同一合并结果。ADR当天开高低及最新价直接取Regular Quote，不等待SDK Daily；Daily图和EMA preview仍使用官方SDK Daily。Quote中非零有限的open/high/low保留为日内字段，允许沿用同一美东日期已有值，不跨日继承；同时间戳快照不覆盖已有推送字段。

SDK推送、Quote或官方历史提交后立即调用既有盘中计算；秒级tick负责时间进度变化。ADR价格状态与两种量比独立就绪，缺ADR不阻塞分钟量，缺分钟量也不阻塞价格。volume区间仅计算标量，不生成K线。ADR样本截止昨天，相关历史revision变化时重算；不得永久缓存旧基准。临时缺少新根时保留上一份有效状态，首份数据缺失仍为空，不填零。

下游不区分数据来源，修正按现有规则重新计算数值、Badge与判断；In Play位置仍遵循既有5m稳定排序要求。手动价格线继续仅由Regular Quote判断，不用历史close替代最新价；已Triggered状态不撤销。新增、已知恢复后仍按既有规则静默建立首状态，不回放断线期间穿越；历史修正自身不另建通知或补报机制。

## 缓存、校验与替换

数据库为 `runtime/longbridge/bars.sqlite3`，主键 `(symbol, timeframe, ts)`；`batches`保存最新成功请求日期、时间、数量和rejected诊断。每个symbol/周期独立恢复：`session[0]`判断本交易日整窗是否准备过，数据库该周期的`MAX(ts)`表示已权威确认的最新closed起点；`as_of`仅记录请求时间。不引入另一份水位、逐根来源标记或全局“今天已拉取”开关。SDK暂定行不参与判断历史是否已修复。

全量count1000响应先校验、确认最新应closed目标有效且存在，再用一次SQLite提交删除并替换该symbol/周期整份旧窗口；失败保留旧值。正常增量count2覆盖/追加closed行，仅应用于同一交易日已成功初始化的窗口。盘中自然增长超过1000根无需处理；下一次全量成功后直接用新响应替换，不裁剪、分页或管理旧历史。

Regular时间网格由XNYS决定，包含DST、提前收盘与尾根。OHLC须正数且有限，volume须非负整数，turnover可为空；仅OHLC上下界矛盾保留官方值，追加`invalid_ohlc.jsonl`，不修正、不告警、不重试。非法时间戳、非Regular、非法价格/volume及同响应重复timestamp均拒绝；重复timestamp不任选一条。保留有效行并在当前batch记录rejected；最新closed目标缺失则整次请求失败。窗口内部允许短历史和缺口，不造零根、不用其他周期补K线。字段统一见 [Bar契约](upstream-daily-data.md)。

## 初始化、分级与恢复

| 时机 | 官方历史窗口 | SDK实时路径 |
| --- | --- | --- |
| 启动/重启 | 恢复每个symbol/周期的同日成功批次；仅补缺少的closed边界，无同日批次才count1000 | 先批量订阅Quote/Trade并取快照；依优先级初始化SDK周期，Quote回调持续工作 |
| 成员新加入/重新加入 | 同一恢复规则；可复用同日留存缓存 | 差集增加Quote/Trade与六周期 |
| 新美东交易日零点后 | 六周期整窗刷新，逐周期成功后替换隔日窗口 | 清理应用内隔日SDK序列，保留底层连接和注册 |
| Regular开盘瞬间 | 已准备的窗口继续使用，不触发额外全量刷新 | 不退订、不清空、不重建连接；直接处理首批实时消息 |
| 已知休眠/调度跳跃超过30秒 | 按交易日及各周期实际closed边界补缺；同日成功在途请求可继续使用 | 保留Quote/Trade、callback和context；各周期先本地退订再注册，取得新起点后替换旧SDK序列 |
| 应用级重连 | 同一边界检查，不无条件重拉六份整窗 | 在既有连接生命周期重新订阅；失败清理不了时释放context再建 |
| 单请求失败、缺目标、错过多个边界 | 对应周期count1000回补 | 维持其他已有行情 |
| 移出完整范围 | 取消该symbol任务，不主动追删磁盘数据 | 删除SDK序列/注册；仍在三名单时保留Quote-only，否则批量退订 |

现有调度器持续比较美东交易日；服务已运行且未休眠时到零点自动准备，开机或服务重启立即检查，真实休眠后由调度跳跃恢复检查。锁屏本身无需监听：进程仍运行就照常处理，实际休眠则唤醒后处理。不新增解锁事件、定时服务或9:25额外刷新。周末/休市沿用最近交易日，不因自然日期变化重复全量。

历史与SDK初始化都优先当前选中股票的5m、Daily及所选周期。其余SDK先按名单顺序为每只准备5m和15m，供CumVol/LocalVol尽早使用，再初始化Daily、30m、1h、2h；历史先准备各股Daily与5m，再补其他周期。六周期最终全部覆盖，没有等待整批成功的屏障。Quote批量建立后立即可显示，不等待其中任何周期。SDK周期初始化在途的新推送暂存，起点返回时按timestamp覆盖合并，避免较旧起点压过已到达的新值；这只是该请求的临时缓冲。

SDK自动短重连会恢复底层Quote/Trade订阅，不保证补回断线逐笔成交或重取全部周期起点。应用保留开市90秒无Quote推送watchdog、30秒报价快照与调度跳跃检测。已知恢复的重新初始化可修复开放大周期；其余时段允许暂定误差，最终依靠各周期历史修正。恢复期间先保留应用显示，再逐周期交替替换，不全局清空。

无缓存时每个symbol全量初始化为六次官方历史查询加六次SDK起点请求；N个symbol对应12N次周期请求，另有批量订阅/快照及SDK证券信息、连接请求。同日重启仍需六次SDK初始化，但可跳过closed目标未变化的历史请求；已知恢复也只补实际缺少的历史。本地candle删除不计入网络10次/秒额度。

## 闭合刷新、失败与状态

调度器检查各周期实际closed目标；5m最频繁，每到本周期闭合后2秒请求count2。15m/30m/1h/2h/Daily只在各自真正闭合后查询，不在每个5m重复拉取未变化的大周期。同日重启或恢复：目标相同则跳过，缺一根count2，缺多根count1000；按XNYS实际开盘对齐边界，不按停机分钟数判断。请求可跨盘前→Regular完成，同一交易日照常提交；跨交易日响应丢弃并重新排队。

各账号的实际网络请求预算独立，统一由 [多账号文档](longbridge-accounts.md) 定义，保留选中股票与SDK请求额度。同一历史任务不重复在途；优先处理closed修正，其次初始化。限制见 [官方文档](https://open.longbridge.cn/zh-CN/docs)。

历史失败首次最多重试三次，间隔2/5/10秒；耗尽显示错误，下一实际5m收盘后2秒启动最多三次的新轮次。当前其他有效数据继续使用。SDK周期订阅失败独立记录，并由既有30秒循环重试；Quote成功不清除candle错误。个别无法订阅symbol从失败批量中单独隔离，不挡住有效成员。

Daily+5m官方窗口成功后为basic，全部六周期成功后为full；Ready说明权威历史初始化进度，不是报价/SDK显示的开关。正常增量及同日刷新不撤销已成功状态；全量等待显示Refreshing，已有图表/数值持续可用。新交易日重新确认官方窗口。历史拒绝行、SDK错误和耗尽失败另行显示。图表选择、GET及诊断只读，不触发下载。

## 已确认的供应商数据特性

Daily / Quote日累计量与分钟量口径不同，Daily不能作为分钟candle的累计量替代；两者各自与相同口径历史比较。2026-10-07 Regular原始响应中，BMNR Daily / Quote为8,787,839，首根尚未闭合1h为3,333,474，该1h与同响应当天5m总量一致。供应商内部成交分类差额未确认。

SDK桶中途初始化可能与最终官方closed有小差异。2026-10-07 11:30–11:35 ET：BMNR为125,255 / 125,324，差69（0.055%）；MU为196,359 / 197,163，差804（0.408%），OHLC相同。连续接收的12:10–12:15 ET：BMNR两边99,281，MU两边259,532，OHLC也相同。这些是历史接口特性样本，不代表当前所有SDK值都无误；本轮验证事实只记录在 [validation.md](validation.md)。

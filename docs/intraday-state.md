# Intraday State：盘中状态

更新：2026-10-26。本文件是盘中状态、自动提醒、量比与In Play展示的唯一需求入口。手动价格线与统一未读交互只在 [alert.md](alert.md) 维护。开发遵循 [development-principles.md](development-principles.md)，模块入口为 [intraday_state/AGENTS.md](../data_service/intraday_state/AGENTS.md)，职责见 [development.md](development.md#intraday-state-实现)。

## 范围与原则

- 这是 symbol 当前状态的监控和描述。颜色持续同步状态，条件变化立即更新；不闪几秒、不锁定当天最高等级，不要求手动关闭或重新设置。
- 仅使用当前 Regular 行情，后台持续工作，不依赖浏览器或 Scan/Monitor 展示。完整监控范围为 Focus 候选与当前余仓 Holdings；具体上游订阅只在 [Longbridge 数据要求](longbridge-data.md) 维护。Discover/Excluded 的 Quote-only 不进入本模块。
- 当前账户角色由最近选择的 Monitor/Trade 决定：Monitor 使用 SnapTrade 余仓，Trade 使用 Schwab 余仓；Scan 延续上次账户角色。两套账户不累加数量，切换角色后沿用静默首状态。Schwab Entries/Sold Today 不作为 holding，已进入其交易显示区的 symbol 不重复作为 Focus 候选报警。
- 同 symbol 只计算一次，Holdings 优先于 Candidate。多持仓批次同步显示、声音去重；当天已清仓批次只保留复盘，不发持仓风险声音，也不因仍在 Focus 而作为候选重复提醒。
- 当前 Scan Focus 可以显示同一份 Longbridge 状态；Scan 日图仍使用 Massive，不用 Massive 指标或日 K 补充盘中计算。历史 Scan 不展示当前盘中状态。
- 只描述关注等级，不自动识别 Pivot、确认主升或作清仓指令；不下单、不接 Atomic feature 自动设置，不建设通用策略框架。

## ADR 与日线均线

ADR20 复用系统最近最多20根完成日 `(H-L)/L×100` 均值，样本截止上一交易日，不纳入今天未完成日；相关官方历史修正后立即重算。系统值5.0代表5%，计算分母为 `a=ADR20/100`。

- `Up_ADR=((last-low)/low)/a`
- `Down_ADR=((high-last)/high)/a`
- open/high/low 与 last 直接取已校验的同源当日 Regular Quote，不等待 SDK Daily 初始化。沿用官方原值，不修正 OHLC 矛盾；EMA preview仍使用SDK Daily。
- Candidate 的上行状态及 EMA 上穿声音要求 `last>open`；不满足时背景普通，不提升到动态区，继续接收行情以发现恢复。
- Holdings 上下行都监控，不使用 open 门槛，回撤状态优先显示。
- EMA10/20 复用现有日线图表的当前 preview，不冻结成昨日值，不新增另一套公式。
- 缺当前 Regular Quote开高低/价格或正ADR时，ADR价格状态为空，不当作正常或零；CumVol与LocalVol独立计算、独立显示。首份有效价格状态只建立起点，即使此前已显示量比也不发首次声音；EMA首份preview同样不补报上穿。

集中参数在 [config/intraday-state.json](../config/intraday-state.json)，启动读取；修改后重启后台。不新增参数编辑界面。当前默认：

| 参数 | 默认 | 状态 |
| --- | ---: | --- |
| up_notice | 0.6 | 浅蓝，上行关注 |
| up_urgent | 1.0 | 亮蓝白字，上行增强 |
| down_notice | 0.7 | 浅黄，持仓回撤预警 |
| down_urgent | 1.0 | 深红白字，持仓回撤紧急 |
| volume_levels | 1.1 / 2.0 / 3.0 | 三个量能等级 |

统一达到即进入（≥），高等级覆盖低等级。颜色只描述当前状态；数值不先按显示精度取整。ADR列显示主状态方向和两位倍数；Holdings尚未进入任一等级时，显示Up_ADR与Down_ADR中较大的一项（相等时显示Up），不因尚未达到回撤阈值而固定显示Up。Candidate继续显示Up。这个数值方向不改变颜色、排序等级或声音；tooltip始终显示上下行两项及截至昨日ADR20。精确配色只在 [Logo / Icon](ui.md#intraday-state-图形与颜色) 维护。

## 声音与恢复

- 进入关注等级或升级紧急等级时发声；持续停留不重复，退回再进入自动再次发声，不额外加冷却。
- EMA10/20 每次由下方到达/上穿都提醒，不要求手动重设。一次更新触发多个条件时只播放最紧急的一种，紧急优先，其次回撤，再其次上行。
- 任何降级都不发声。回撤颜色退去后露出原本已满足的上行颜色，不凭显示颜色变化误发上行声；根据各项规则自己的前后状态判断。
- 首次有效状态、新交易日、范围/角色改变及已知重连/休眠恢复后只建立起点，不补报历史穿越。刷新、重连网页只读状态，不发声。
- 所有自动报警与手动价格报警共用symbol未读提醒，规则见 [统一未读提醒](alert.md#统一未读提醒)。手动线的触发/灰线/generation保持独立。
- 共用[Alert后台声音与节拍](alert.md#后台声音与运行)，方向与等级分开传递；上行增强仍保留上行身份，不因使用紧急声音变成回撤。各报警独立并行，无优先级、排队或同symbol播放替换。来源及许可见 [声音资源](../data_service/alerts/sounds/SOURCES.md)。
- 声音资源与生成方式只在[声音资源](../data_service/alerts/sounds/SOURCES.md)维护；运行时只调用系统afplay。播放错误沿用Alert现有错误提示/日志，不改变状态或补播历史。

## CumVol：全天同进度累计量比

`CumVol(t)=今天Regular开盘至今实际累计量 / 最近五个交易日同进度累计量的平均值`。

今天与历史都用分钟candle成交量体系，不以Quote/Daily累计量除以分钟历史量。两种供应商统计口径的已知差异见Longbridge说明。

历史当前未完成5m槽按经过时间线性插值，只折算历史，不外推今日。第7分钟为 `V(0,5)+V(5,10)×2/5`；第26分钟为 `V(0,15)+V(15,20)+V(20,25)+V(25,30)×1/5`。

已完成区间按 `2h→1h→30m→15m→5m` 选择可完整落入区间的bar，按连续起点覆盖，每段只计一次；统一序列含当天SDK已结束根与官方历史覆盖值。不拼接或写回OHLC。大bar有效时可覆盖内部缺失的小bar；覆盖不了不能把缺口计为零。今日累计为已完成区间加当前SDK 5m实际量，不做今日时间外推。

每个历史日先独立完成同进度累计，再在固定前五个交易日中取可用样本均值；不拼接不同日期的片段均值，不向更早日期补样本。有效零量是样本，缺失不是零；半天缺少的下午范围跳过。无样本、均值为零或今日量不可用时显示`—`。时间按XNYS与纽约当地Regular对齐，涵盖DST和提前收盘。

## LocalVol：局部同进度量比

- 开盘前15分钟使用三个独立5m窗口：0–5、5–10、10–15。
- 第15分钟起使用独立15m窗口：15–30、30–45、45–60……，不在窗口中途换周期。
- 分子为当前SDK相应5m/15m窗口的实际累计量，分母为历史同窗口起点至相同经过进度的均值。历史尾部仍按5m插值；不以未完成窗口除以历史完整窗口。
- 第20分钟比较今天15–20与历史15–20；第26分钟比较今天15–26与历史`15–20 + 20–25 + 25–30×1/5`。
- 复用CumVol的区间计算、固定历史样本窗和缺失语义。tooltip明确当前5m/15m窗口。

## 展示与 In Play

- 只有一套默认名单展示。删除Grouped/Dynamic按钮、模式状态和浏览器偏好；当前Focus在Scan/Monitor共用In Play自动聚集，Regular外或历史Scan不聚集。
- 顺序为Pinned → In Play → 原有Surf/Bounce/Unclassified。In Play中为亮蓝 → 浅蓝 → 其他高于open；Pinned始终按人工Pin顺序，成员只出现一次。真实section、Tags、人工顺序不改写，降级后归位；Tags继续表达原分类。
- In Play复用现有section的标题、计数、折叠与空组隐藏。空section整个隐藏，无标题或No symbols；全表空时保留一份全局空状态。
- 排序键为价格离散等级 → CumVol离散等级 → LocalVol离散等级 → 原相对顺序，不按连续小数排序。价格升级立即前移；普通强弱、降级和量能重排在5m边界调整。
- 量能数值和Badge在行情或官方历史变化时立即重算，另由秒级tick推进历史插值；5m只约束位置更新，不延迟监控、数值或颜色，也不额外订阅1m周期。
- Focus价格与量能分区、低倍数隐藏、强色文字及未读波浪只在[UI Symbol模板](ui.md#symbol-row-template)维护；隐藏低值只影响显示，不改等级、rank和触发。
- 自动提取的In Play成员不参与人工拖动/Shift改序，不能拖入In Play修改真实section；其他原section保留原有编辑规则，Pin顺序仍可人工调整。重排复用节点，保持选中symbol、图表、焦点和滚动位置。
- Tag/Filter与搜索仍只影响可见结果，不停止后台监控。搜索沿用原名单查找，不建立另一种可选展示模式。
- Holdings独立显示，按既定风险等级优先排序，再按量能离散等级和已选列；明细/清仓尾部保持原语义。价格／财务胶囊边界见Holdings UI，未读与声音按symbol共享。

## 实现与验证边界

现有Python进程中的独立模块，不新增SDK context、服务、消息中间件或规则框架。派生状态在内存重建，不逐份Quote写SQLite；配置持久化，Manual业务库继续保留。只读GET与页面选择不触发下载、重排真实名单或声音。

验证仅覆盖本次状态/穿越、范围与恢复、量比及缺失、In Play稳定重排/选择/焦点、Holdings批次、统一未读与独立声音；TypeScript修改须build。真实数据只读既有范围与缓存，必要听辨明确启用临时声音；不扩展全项目回归、故障注入或回放框架。具体日期、覆盖和未覆盖只写 [validation.md](validation.md)。

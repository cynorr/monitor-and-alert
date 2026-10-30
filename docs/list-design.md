# List 模块设计

本文件定义归属与分类逻辑；显示与布局在 [List UI](ui.md#list-ui)，快捷键、单只操作和选择反馈只在 [List 交互](list-interactions.md) 维护。

## 背景与目的

个人美股工作流程：Scan → Tag → Monitor → Alert → Trade。List、Tag 与 Filter 维护于本文件；Alert 需求见 [alert.md](alert.md)，不开发交易。

Scan 与 Monitor 共用一份名单。目标是减少每日肉眼重复筛选，让代码扫描逐步主导发现、分类与淘汰；人工补齐尚未表达为 atomic feature 的判断。当前进入 Focus 仍由人工最终确认，后续重点完善 feature 和 Tag 条件，不另建服务或评分系统。

## 三个列表

| List | 用途 | Section |
| --- | --- | --- |
| Discover | 按 [Massive 数据要求](massive-data.md) 先完成证券与历史资格、ADR/MDV 初筛，再取 RFL 排名并集，等待选入 Focus | 按潜力 Tag 分组，未匹配为 Unclassified |
| Focus | 正式关注、实时看盘；成员跨日保留 | 按潜力 Tag 分组，未匹配为 Unclassified |
| Excluded | 当日机器排除与人工屏蔽 | In 14 Days、Broken、Extended、Under-50、Hidden |

同一 symbol 在三个列表中只有一个归属。Holdings 独立，不改变名单归属；同 ticker 底层行情去重。常规名单前端屏蔽 Holdings 已有 ticker，后端成员与规则结果保留。

Scan 全局搜索使用本地 Massive bars，确认新股后复用 add 保存为当日人工 Discover，并加入已有 Pinned 区首位、选中日 K。人工 Discover 在普通重新分类和同日重启后保留，点击 Refresh Scan 后清除人工保留资格，Setup/负面 Tag 如实计算，在显式 Refresh 前不因候选门槛或负面规则被移走；不伪造 candidate 或市场排名。新完成日或显式 Refresh 清理时删除人工 Discover 与全部 Pin，无跨日保留要求；需要长期关注时使用现有移入 Focus 操作。已有 Discover 搜索结果可置顶并选中，已有 Focus/Excluded 只选中、不改归属；Focus section 的显式新增保留原用途。

## 每日规则

新完成交易日只继承 Focus 与未满七个自然日的 Hidden。 用户点击 Refresh Scan 使用同一清理与分类逻辑：只保留这些成员作为输入，清除人工 Discover、人工 Focus 当日豁免、人工 Setup/Label、人工主 section、全部 Pin 与人工排序，随后重新匹配；Focus 仍接受下表自动淘汰。Hidden 保留原 excluded_at，不重新计时。已有数据准备状态继续复用，不重复下载或构建；保存的 Tag 定义与显示 Filter 不清除。同日 Refresh 不更改交易日期或将当天新成员伪装成跨日 carried。Discover 与自动 Excluded 每日按当天 candidate 和保存的 Tag 规则生成，不维护跨日机器排除成员名单。完整 feature 和 Growth 范围只在 [Massive 完整特征范围](massive-data.md#名单完整特征范围) 维护。

| 输入 | 完成日判断 | 最终归属 |
| --- | --- | --- |
| 当天 candidate | 匹配负面条件，且不属于保留的 Focus/Hidden | Excluded 对应机器 section |
| 当天 candidate | 不匹配负面条件，且不属于 Focus/Hidden | Discover，按 Setup 分组，否则 Unclassified |
| Focus | 匹配负面条件 | 淘汰出 Focus；仍是当天 candidate 则显示机器 Excluded，否则退出当前名单 |
| Focus | 不匹配负面条件 | 继续 Focus，失去 Setup 或候选资格不影响归属 |
| Hidden | 未满七个自然日 | 保留 Hidden，跳过名单规则判断 |
| Hidden | 满七个自然日 | 解除屏蔽；仅当天 candidate 重新参与普通分类，否则退出当前名单 |

机器 section 优先级为 In 14 Days → Broken → Extended → Under-50，保留全部实际匹配 Tag。机器结果只属于当天候选，可从行情截面、当前财报缓存和保存的Tag规则重建；不保存其成员身份、section 或机器 Tag 结论。增加负面规则不增加持久名单。Setup 只负责分组，不会自动进入 Focus。

缺失特征不视为已确认的负面匹配，也不推断为 Broken；已有 Focus 不因特征或 Setup 缺失自动淘汰。无历史机器 section 需要保留或恢复。

Hidden 保留七个自然日，期间即使不在 candidate 中也保留并计算完整特征，可以提前 Release 或加入 Focus。到期的非候选无需继续计算特征或追踪。

人工加入 / 保留 Focus 当天优先，显式 Refresh 或次日首次分类重新接受规则；机器标签仍如实显示。当日人工 Discover 沿用搜索新增约定。人工 Setup/Label、主 section、Pin 与顺序在显式 Refresh 或新日清理前按当日规则保存；这些人工信息不因自动 section 仅存在于内存而丢失。

## Tag、Section 与 Filter

Tag 使用现有 atomic feature 和财报倒计时条件，允许同时匹配多个。每日重算结果，禁止继承昨天的形态结论；人工补充只允许 Setup/Label，只对当前交易日有效；负面 Tag 完全由扫描条件决定。

潜力 section 来自保存的潜力 Tag，例如 Surf-10、Surf-20、Bounce-10、Bounce-20。多标签按保存顺序选主 section，人工可拖拽调整；同一 symbol 只显示一行。

Tag 的用途固定为 Setup、Earnings、Extended、Broken、Under-50 或 Label；Earnings对应In 14 Days机器section。Setup 用于 Discover/Focus 的潜力 section；Label 仅辅助观察，适合后续 prior-run 等局部特征。显示名称可修改，用途不随改名变化。缺少用途的旧定义按名字识别 Extended / Broken / Under-50，其余已有形态 Tag 转为 Setup；已保存的用途优先。当前 Under-50 Tag 使用 `ma_arrangement = under50` 条件，均线排列含义见 [Atomic Feature 参考](atomic-feature-reference.md#3-ma-arrangement)。分类使用保存的条件，不按名称硬编码条件。

Section 支持折叠、内部排序和跨 section 拖拽。新进入 section 的股票放到队首，同 section 内保留人工顺序。允许盘中操作改变 section；本次不新增基于实时 Quote 的形态规则。

Tag 选择是可空的显示偏好，点击已选 Tag 取消选择；未选时不应用保存 Tag 筛选。可保存零到十个命名 Tag，筛选草稿可独立编辑并保存为新 Tag。取消选择不删除定义，不影响每日自动分类。

Filter 仅改变显示，不移动名单、不改变实时订阅。自动分类与显示筛选使用同一字段目录和相同条件含义。

## 财报排除

`days_to_earnings`为下一次尚未发布财报的日期减当前美东日期，按自然日计算，允许为空。`In 14 Days`使用Earnings用途（role=earnings）及`0 ≤ days_to_earnings ≤ 14`条件，包含今天和第14天；缺失不匹配，不用999代替。阈值保存在该Tag的普通filters中，不增加独立配置或专用匹配函数。

当前有效名单使用这项特征，扫描日K即使截至昨日，财报倒计时仍从今天计算；历史Scan不回算财报，不把当前结论写入历史截面。日K和财报原始缓存各自保存，倒计时只在内存名单特征中补入，不修改日K表或scan.json。没有当日行情记录的保留成员也可使用财报日期。

Additional Info成功加载缓存后即可计算；财报日程成功提交并更新内存后通知Workbench自动重分类。美东自然日变化也重新计算，不要求当天网络请求成功。失败沿用上次成功缓存，完全无日期则为空；不等待公司资料、历史或远期财报下载，不影响Scan Ready。更新不重跑候选/排名/行情特征，也不执行Refresh的人工状态清理。

此项为最高优先级的机器section；Hidden七天屏蔽、当天人工Discover/Focus保留、Focus自动淘汰以及非候选淘汰后退出仍按上述名单规则执行。机器财报Excluded同样不保存跨日成员身份。财报日程仍为第三方预估，不增加其他来源或额外告警。

## 当日置顶

置顶是独立的当日软状态，不是保存的规则 Tag，也不改变 List、主 section 或原有 section 顺序。每个 List 可置顶多个 ticker，置顶区顺序独立，Scan/Monitor 共用；取消置顶回到自己的 section。同一交易日普通保存、重分类与服务重启保留置顶；显式 Refresh 清空；同 List 内换 section 保留，跨 List 移动（含规则导致的移动）取消。新完成交易日继承名单时清空全部置顶，和当天重新计算 Tag/section 的发布流程一致。Filter 与持仓屏蔽只影响可见结果，不取消置顶。

## Scan 与 Monitor

Scan 三列表日 K、指标与日分类均使用本地 Massive Daily，最新报价（含盘前/盘后/夜盘）按 [Longbridge 范围](longbridge-data.md#定位与范围) 共用连接。Monitor 展示 Focus 和独立 Holdings；只有 Focus/Holdings 使用完整 Monitor 行情和 Alert，Scan 的额外 Quote 不扩大这两个范围。

因此 Excluded 的盘中恢复不被实时发现；每日完成日扫描发现恢复。仍希望当天实时关注的股票，应明确留在 Focus。切换模式不停止后台 Focus 行情或 Holdings 刷新。

## 明确操作

- Add to Focus：清除排除状态、加入队首、开始实时监控；重新匹配与 section 首位规则见下节。
- Move to Hidden：从 Discover/Focus 或机器 Excluded 明确屏蔽七个自然日；来自 Focus 的名单订阅随归属移除。
- Move to Discover：结束 Focus 归属，或提前释放 Hidden；仅当天候选返回 Discover，并立即按当前规则分类。机器 Excluded 不提供人工释放到 Discover。
- Hidden 的 Release：等同从 Hidden 移到 Discover；当前负面规则仍可立即归入机器 section。

## 统一移入 Focus

这是手动与 Alert 入选 Focus 的唯一分类规则入口。实现：workspace._focus 清理来源结果，Workbench.focus_classifications 通过 list_rules.focus_classification 重新匹配，手动与 Alert 共用并一次保存。

- 从 Discover 或任一 Excluded section 移入 Focus，都使用同一流程，包括手动 Add to Focus、单只 Move to Focus，以及 [Alert 创建引起的入选](alert.md#创建时的名单处理)。
- 丢弃来源保存的 `tags`、`manual_tags`、`manual_tags_date`、原主 section 与 `manual_section_date`，解除排除状态；不复制 Discover/Excluded 的分类结果。只清该 symbol 的成员结果，不删除或修改 Tag 定义。
- 使用当前有效 workspace 对应的本地特征和当前已保存的 Tag 定义，复用 Focus 现有匹配逻辑重新计算全部匹配 Tag；不使用来源已保存的 Tag 列表、未保存编辑草稿或历史 Scan 的分类结果。
- 主 section 仅从重新匹配的 Setup Tag 中选取，多个匹配按当前保存的 Setup 顺序选择第一个，例如 Surf、Bounce；没有匹配则为 Unclassified。缺失特征沿用现有 Missing 匹配语义，不猜测、不为入选触发网络下载。
- 显式入选沿用当前的当日人工 Focus 优先：当天保留 Focus，重新算出的负面 Tag 可显示，但不会因本次入选立即回到 Excluded；显式 Refresh 或次日首次分类恢复自动名单规则。这不新增 Alert 策略或新的 Tag 判定条件。
- 分类完成后，将新成员放到对应 Focus section 的第一个，原有成员的相对顺序不变。
- 清理、重新匹配、section 与顺序在同一次名单操作中完成并同步保存，不先发布保留旧 Tag 或临时 section 的中间状态。
- 已经在 Focus 的 symbol 继续新增 Alert，不重算其入选状态、不清人工结果、不置顶。Focus 内手动跨 section、Shift 换序或组内拖动仍按现有人工调整规则，不被这次入选规则覆盖。
- Search/section `+` 将已有 Discover/Excluded symbol 明确加入 Focus 时，也按上述规则重新分类，不用入口预设 section 覆盖自动入选结果；全新 symbol 的 Search/section `+` 入口仍按现有新增契约处理。
- 历史 Scan 名单保持只读。历史图表上的 Alert 入选只作用于当前有效 workspace，使用当前规则重新匹配；不改历史名单，也不沿用历史 Tag。

## 实现边界

继续使用 workspace.json、现有截面和 preferences.json。旧 Focus / Wait 合并为 Focus；旧 Hidden 转为 Excluded / Hidden 并保留剩余期限。共享后台规则计算结果，不新增服务、通用规则框架或每日提醒；Quote 范围统一见 Longbridge 数据要求。

更新规则时重评已有本地截面；GET 和切页不触发下载。新 Daily / feature 成功后后台发布分类；失败保留完整旧结果并显示其日期。

## 盘中 In Play 展示

[Intraday State](intraday-state.md#展示与-in-play)提供当前Focus的In Play section，位于Pinned之后；原分组和Tags继续保留，价格和量能仅改变展示状态/顺序，不改真实三名单、每日Tag、主section、人工顺序或Pin。筛选/折叠不缩减后台监控，空section整个隐藏。完整聚集、稳定排序和编辑边界只在独立需求维护。

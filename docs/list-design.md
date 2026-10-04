# List 模块设计

本文件定义归属与分类逻辑；显示、布局和操作细则只在 [ui.md 的 List UI 章节](ui.md#list-ui) 维护。

## 背景与目的

个人美股工作流程：Scan → Tag → Monitor → Alert → Trade。本次只重构 List、Tag 与 Filter，不开发 Alert 或交易。

Scan 与 Monitor 共用一份名单。目标是减少每日肉眼重复筛选，让代码扫描逐步主导发现、分类与淘汰；人工补齐尚未表达为 atomic feature 的判断。当前进入 Focus 仍由人工最终确认，后续重点完善 feature 和 Tag 条件，不另建服务或评分系统。

## 三个列表

| List | 用途 | Section |
| --- | --- | --- |
| Discover | ADR/ADV 初筛后，RFL 1m/3m/6m 各前 50 的并集，等待选入 Focus | 按潜力 Tag 分组，未匹配为 Unclassified |
| Focus | 正式关注、实时看盘；成员跨日保留 | 按潜力 Tag 分组，未匹配为 Unclassified |
| Excluded | 暂不关注与机器提出的复核候选 | Broken、Extended、Hidden、Review |

同一 symbol 在三个列表中只有一个归属。Holdings 独立，不改变名单归属；同 ticker 底层行情去重。

## 每日规则

新完成交易日 Ready 后，重算 Discover、Focus、Excluded 的 feature 与 Tag；Hidden 跳过形态计算和潜力扫描。计算范围为扫描候选与现有非 Hidden 成员的并集，即使成员掉出 RFL 前 50 也继续判断。

- Discover 与 Focus 匹配 Broken / Extended，立即进入 Excluded 对应 section；同时匹配时 Broken 优先。
- Excluded 的非 Hidden 成员匹配负面条件，按当前规则归入 Broken / Extended；不满足负面条件且匹配潜力 Tag，进入 Review。
- Review 无 Dismiss 按钮、不要求每天清空。未选入 Focus 的股票继续保留；新负面规则仍可将其归入 Broken / Extended。
- Hidden 是尚未分类的人工排除原因，七天内跳过规则判断；可以手动释放或加入 Focus。
- 没有匹配 Tag、缺少数据都不等于 Broken，不据此淘汰 Focus。

Hidden / Extended / Broken 七个自然日到期解除本次排除；随后仍按当前规则分类。仍匹配负面条件就继续进入对应 section，不增加“刚释放保护”或条件变化检测。重复匹配不每日续期，只有到期后的新排除重新计时。Review 保留到人工处理或新的负面判断，不强制七天清空。

人工加入 / 保留 Focus 当天优先，次日重新接受规则；机器标签仍如实显示。人工形态补充和主 section 调整仅当天有效，Tag 定义和 Focus 成员长期保留。

## Tag、Section 与 Filter

Tag 使用现有 atomic feature 条件，允许同时匹配多个。每日重算结果，禁止继承昨天的形态结论；人工补充只对当前交易日有效。

潜力 section 来自保存的潜力 Tag，例如 Surf-10、Surf-20、Bounce-10、Bounce-20。多标签按保存顺序选主 section，人工可拖拽调整；同一 symbol 只显示一行。

Tag 的用途固定为 Setup、Extended、Broken 或 Label。Setup 用于潜力 section / Review；Label 仅辅助观察，适合后续 prior-run 等局部特征。显示名称可修改，用途不随改名变化。旧定义按名字识别 Extended / Broken，其余已有形态 Tag 转为 Setup。

Section 支持折叠、内部排序和跨 section 拖拽。新进入 section 的股票放到队首，同 section 内保留人工顺序。允许盘中操作改变 section；本次不新增基于实时 Quote 的形态规则。

Filter 仅改变显示，不移动名单、不改变实时订阅。自动分类与显示筛选使用同一字段目录和相同条件含义。

## Scan 与 Monitor

Scan 展示三个完整列表。Monitor 展示 Focus、独立 Holdings，以及折叠的 Review 入口。Discover、Hidden、Extended、Broken 不占 Longbridge symbol 额度；Review 使用本地 Massive Daily 预览，加入 Focus 后才订阅实时行情。

因此 Excluded 的盘中恢复不被实时发现；每日完成日扫描发现恢复。仍希望当天实时关注的股票，应明确留在 Focus。切换模式不停止后台 Focus 行情或 Holdings 刷新。

## 明确操作

- Add to Focus：清除排除状态、加入队首、开始实时监控。
- Exclude for 7 days：移入 Hidden，停止该名单带来的实时订阅。
- Move to Discover / Release：解除归属或屏蔽，仅当前扫描候选返回 Discover，并立即按已有规则分类。
- Review：合适就加入 Focus，一般就保留，不增加 Dismiss 操作。

## 实现边界

继续使用 workspace.json、现有截面和 preferences.json。旧 Focus / Wait 合并为 Focus；旧 Hidden 转为 Excluded / Hidden 并保留剩余期限。共享后台规则计算结果，不新增服务、通用规则框架、每日提醒或额外实时订阅。

更新规则时重评已有本地截面；GET 和切页不触发下载。新 Daily / feature 成功后后台发布分类；失败保留完整旧结果并显示其日期。

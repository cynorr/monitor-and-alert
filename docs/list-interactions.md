# List 交互

更新：2026-10-26。

## 背景与设计哲学

Scan 的核心工作是逐只查看候选，决定是否纳入 Focus；Monitor 用于持续看盘。交互直接围绕当前 active symbol，减少“勾选 → 选择目标 → 提交”的操作路径。按键尽量符合直觉，短组合留给高频操作，低频操作使用较长组合；只保留少量常用快捷键，不增加需要记忆的模式或隐式按键优先级。

操作完成后的反馈应一致，但只覆盖明确需要的场景，不为所有刷新、筛选和拖动建立新的全局选择机制。名单归属和刷新分类规则只在 [List 设计](list-design.md) 维护；外观、Tag/Filter 编辑和图标见 [UI](ui.md#list-ui)，独立持仓见 [Holdings UI](holdings-ui.md)。

## 导航与快捷键

active symbol 指当前黑色实线边框选中、图表正在展示的观察名单行。Holdings 使用独立选择来源，不参与这些名单修改。

| 范围 | 按键 | 动作 |
| --- | --- | --- |
| Scan / Monitor | ↑ / ↓ | 按当前可见顺序选上一只／下一只，跳过折叠组，不循环 |
| Scan / Monitor | Page Up / Page Down | 跳到前／后一个非空 section 的第一只，不循环 |
| Scan / Monitor | End / Command + G | 查看完整Focus中按当前排列最上方的未读Alert symbol |
| Monitor | Home / Command + U | 查看Holdings中按当前排列最上方的未读Alert symbol |
| Scan / Monitor | Shift + ↑ / ↓ | 同 section 内向上／下移动一位，保留选中；边界不动 |
| Scan / Monitor | Shift + Command + ↑ / ↓ | 置顶／取消置顶，明确设置，不是 toggle |
| Scan · Discover | Delete / Backspace | 移入 Hidden |
| Scan · Focus | Delete / Backspace | 释放 Focus 归属，按当前规则重新分类 |
| Scan · Hidden | Delete / Backspace | 解除屏蔽，按当前规则重新分类 |
| Scan · 机器 Excluded | Delete / Backspace | 无操作，不允许人工释放机器排除 |
| Scan · Discover | Shift + → | 加入 Focus |
| Scan · Excluded（含 Hidden） | Shift + ← | 加入 Focus |
| Scan · Focus | Shift + ← / → | 无操作 |

- Page 导航只在当前 List 内进行，不切 Discover/Focus/Excluded。Pinned、In Play 参与 section 导航，空组跳过，目标折叠时展开。
- Shift 移动复用原人工排序范围：Default order 的普通 setup section、Pinned；Scan RFL 排序时普通组不重排，机器 Excluded 普通组与 In Play 保持自动顺序。拖动及其原选择行为不变。
- 已置顶再按置顶、未置顶再按取消，均无操作、不跳下一只。取消置顶回到真实 section；若当前满足 In Play，仍按现有聚集规则显示。
- 输入框、搜索及可编辑内容保留文本编辑行为；历史 Scan 与受限会话不可修改名单，导航仍可用。
- Monitor 不新增 Delete/Backspace 名单操作。Scan 停用 Alert 的 Backspace 删除，只通过横线垃圾桶删除 Alert；Monitor 的既有 Alert 按键原样保留，详情见 [Alert](alert.md#图表交互)。

## 未读 Alert 导航

- 每次按键从当前排列找第一只未读symbol；选图即按 [Alert统一已读](alert.md#统一未读提醒) 清除未读，再按就找到下一只。没有未读时保持原选择，不弹提示；不保存遍历游标、队列或另一套排序。
- End与Command+G共用完整Focus导航，不含被Holdings接管显示的symbols；顺序与列表共用Pinned、In Play、原分组及组内顺序。包含折叠组，命中时展开；Scan当前在Discover/Excluded时切到Focus，保持原Tag与Filter。即使目标被Tag筛选隐藏，仍展示其chart，普通后台名单更新保留该选择；目标行可见时滚动定位，不修改筛选、Tag、名单归属或排序。
- Home与Command+U共用当前Holdings主行顺序，同symbol多批次选第一条主行，共享symbol已读；整体折叠时展开。Scan不跳Holdings、不切模式。这两组快捷键均不受当前选择来源限制；输入框、搜索与可编辑内容保留原键盘行为。
- Home/End仅单键生效，在Scan/Monitor均取消原生页面翻页／滚动，即使没有未读目标也不滚动。带修饰键的Home/End不映射；文本编辑中的行首／行尾行为保留。

## 单只名单操作

鼠标按钮和快捷键共用同一动作处理。Scan Discover 提供右箭头 Add to Focus、垃圾桶 Hide；机器 Excluded 提供左箭头 Add to Focus；Hidden 提供 Add to Focus 与回转箭头 Release；Focus 提供 Release。两模式均保留 Pin/Unpin。Monitor 的 Hide 行按钮维持原语义。

释放不保证返回 Discover：非当天 candidate 退出名单；候选无负面条件进入 Discover，仍有负面条件进入机器 Excluded。入选 Focus 复用后端统一重新匹配及 section 队首规则，不复制来源 Tag。详见 [List 明确操作](list-design.md#明确操作)。

没有行勾选框、Space 勾选、批量 Move to 工具栏、选中集合或批量移动接口。操作即时提交，成功后使用后端结果；失败保留原选择并显示错误。

## 自动下一只：限定白名单

| 对 active symbol 的操作 | 成功后的反馈 |
| --- | --- |
| Scan 隐藏 Discover、释放 Focus / Hidden | 留在来源 List，下一只 |
| Scan 从 Discover / Excluded 加入 Focus | 留在来源 List，下一只 |
| Scan / Monitor 置顶、取消置顶 | 当前 List 下一只 |

- 以操作前的可见顺序找后项，允许跨 section，不跨 List；跳过已不可见的成员。
- 无后项时选操作后当前可见名单的最后一只，不绕回开头；只剩一只则选该只，全空则清图。
- 黑框、图表和滚动位置一起更新。保存期间不先跳首行再跳候补；期间主动选择其他 symbol 或切换 List/模式后，不抢回选择。
- 操作未选中的行、失败和无实际变化不自动跳转。自动候补选图与其他选图方式一样，标记该symbol的Alert已读。
- 组内移动、拖动、Filter、折叠、Refresh、外部更新、搜索新增与 Alert 引起的入选不接入此流程，保持既有行为。Search 仍选中搜索目标，Alert 创建后仍停留该 symbol。

## Refresh Scan

复用已有数据准备流程；Ready 数据跳过下载与特征构建，但每次用户点击 Refresh 都执行与新交易日首次分类共用的人工状态清理，再按保存的规则重新分类并打开最新可用日。

保留范围、Focus 自动淘汰与 Hidden 到期规则只在 [List 每日规则](list-design.md#每日规则) 维护。普通报价更新、切页、浏览器刷新和服务重启不等同于点击 Refresh Scan。Refresh 引起的选择变化保持原实现，不接入自动下一只。

## Search 与 Add

- List 模块的 Tag 新增与 section 新增只使用一套加号按钮样式：26×26px、21px 字号、圆形 hover 背景；Tag 与 section 加号距面板右边同为8px。
- Search 与可编辑 Focus setup 组的 `+` 共用唯一行内输入，placeholder 始终为 `Search`，不使用新增弹窗。`/` 随时清空并开始搜索；Scan全局新股加入当日Discover置顶，Monitor仍加入Focus；Focus 组内 `+` 指定该 section 为新增目标。Esc 退出并恢复全名单。
- 即时筛选本地 ticker，仅显示匹配组，无空组或 No matches；没有本地结果时隐藏报价列头。搜索临时展示折叠组，选中结果只展开当前模式的对应组。
- 没有精确本地 ticker 时，停输一秒发起精确查询：Scan 读本地 Daily，Monitor 经后端官方 static_info。查询不保存、不订阅；输入变化或退出后丢弃旧响应。
- 有效新候选位于本地匹配前，显示蓝色 ticker、公司名和 Add。Enter 优先选择精确已有 ticker；已展示的新候选优先于局部匹配，否则选择首个本地匹配或发起/等待查询。确认新候选后沿用add保存、选图并退出；Scan全局Search新股进入Discover置顶并切到Discover、清除Tag显示筛选，section的+仍按显式目标加入。已有Discover可置顶并选中，已有Focus/Excluded只选择、不移动。
- 未找到 ticker 保持空结果，查询/保存失败保留行内错误。只支持美股正股，不新增模糊查询和其他市场入口。
- 上述指定 section 新增针对全新 symbol。已有 Discover/Excluded symbol 明确加入 Focus 时，分类以 [统一入选](list-design.md#统一移入-focus) 为准，不由 Search/section `+` 保留来源结果或强制目标组。


Trade 复用 Monitor 的 Focus 操作与快捷键；Holdings 未读导航切入独立 Schwab 表，只在真实持仓行查找未读，Entries/Sold Today 不增加提醒游标。同 symbol 的图表和手动 Alert 身份不随账户显示来源复制。

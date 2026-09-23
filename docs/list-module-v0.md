# List Module V0 — Development Specification

确认并实现：2026-09-24。本文保留本轮需求规格；当前运行行为、实现契约和 UI 维护分别见 [behavior.md](behavior.md)、[development.md](development.md)、[ui.md](ui.md)，验收见 [validation.md](validation.md)。

## 0. Goal

目的
* 是做一个动态的 list，section 里面的 ticker 有序关系，以及改变 ticker 属于的 section。 
* 增加新的 ticker 到 list

## Specification

Monitor 与 Scan 共享同一份 List 数据。

V0 只处理两个 List：

- `focus`
- `wait`

保持现有 `workspace.json` schema 和 `version` 不变。

不实现：

- 自定义 Section
- Section 增删
- `hidden` 管理
- `carried` 管理
- 文件锁
- 原子写入
- JSON validation
- crash recovery
- 并发冲突处理
- polling

---

## 2. Data Source

Scan workspace 根目录：

```text
~/qull-scan-workspace/days/
```

每日目录格式：

```text
YYYY-MM-DD/
    workspace.json
```

例如：

```text
~/qull-scan-workspace/days/2026-09-22/workspace.json
```

### Active Workspace

Monitor 启动时：

1. 读取 `~/qull-scan-workspace/days/`
2. 找出目录名符合 `YYYY-MM-DD` 且包含 `workspace.json` 的目录
3. 选择日期最大的目录
4. 将其中的 `workspace.json` 设置为当前 `active_workspace`

例如：

```text
2026-09-21/
2026-09-22/
2026-09-23/
```

则：

```text
active_workspace =
~/qull-scan-workspace/days/2026-09-23/workspace.json
```

日期目录采用 ISO 格式，因此可以直接按日期排序。

---

## 3. Filesystem Watch

使用 macOS filesystem event。

Python 实现优先使用：

```text
watchdog
```

只需要一个 watcher：

```text
~/qull-scan-workspace/days/
```

开启 recursive watch。

它同时负责两件事：

### 3.1 Scan 修改当前 Workspace

如果当前：

```text
active_workspace
```

发生修改：

```text
filesystem event
→ reload workspace.json
→ refresh Focus / Wait UI
```

无需手动刷新。

### 3.2 新交易日 Workspace 出现

当 `days/` 下出现新的目录或新的 `workspace.json`：

```text
filesystem event
→ resolve_latest_workspace()
→ 比较 active_workspace
```

如果发现更大的有效日期：

```text
active_workspace = new workspace.json
→ load
→ refresh UI
```

例如：

```text
active:
2026-09-22/workspace.json

new:
2026-09-23/workspace.json
```

Monitor 自动切换到：

```text
2026-09-23/workspace.json
```

因此 V0 不需要额外的手动 Refresh Workspace 按钮。

---

## 4. JSON Scope

Monitor 只管理：

```json
{
  "orders": {
    "focus": [],
    "wait": []
  },
  "statuses": {}
}
```

### Read / Write

允许修改：

```text
orders.focus
orders.wait

statuses[ticker].status
statuses[ticker].status_at
```

### Out of Scope

以下数据完全不属于 Monitor：

```text
orders.hidden
carried
```

Monitor：

- 不修改 `hidden`
- 不移动 ticker 到 `hidden`
- 不修改 `carried`
- 不根据 `carried` 改变 UI 行为

保存文件时保留它们原有内容。

---

## 5. Focus / Wait Model

`focus` 和 `wait` 都是有序 List。

JSON Array 顺序就是 UI 顺序：

```json
"focus": [
  "PAYS",
  "HTFL",
  "PLTU"
]
```

对应：

```text
PAYS
HTFL
PLTU
```

不增加额外的 `order` 字段。

### Uniqueness

同一个 ticker 在：

```text
focus
wait
```

之间互斥。

一个 ticker 最多存在于其中一个 List。

---

## 6. Reorder

用户可以在同一个 Section 内拖动 ticker。

例如：

```text
FOCUS

AAPL
NVDA
TSLA
```

拖动：

```text
TSLA
```

到第一位：

```text
TSLA
AAPL
NVDA
```

立即更新：

```json
orders.focus
```

### status_at

只有主动被拖动的 ticker：

```text
TSLA
```

更新：

```json
statuses["TSLA"]["status_at"] = today
```

被动发生位置变化的：

```text
AAPL
NVDA
```

不修改 `status_at`。

`status` 不发生变化。

### Write Timing

鼠标松开、drag operation 完成后：

```text
update memory
→ immediately write workspace.json
```

不 debounce。

不延迟保存。

---

## 7. Move Between Focus / Wait

Ticker 支持直接拖动：

```text
Focus → Wait
Wait → Focus
```

例如：

```text
NVDA

focus → wait
```

执行：

```text
remove NVDA from orders.focus

insert NVDA into orders.wait

statuses["NVDA"]["status"] = "wait"

statuses["NVDA"]["status_at"] = today
```

反方向同理。

跨 Section 后立即写入 `workspace.json`。

---

## 8. Delete

Ticker 可以从 Focus 或 Wait 删除。

例如：

```text
delete NVDA from focus
```

执行：

```text
remove NVDA from orders.focus
remove statuses["NVDA"]
```

不执行：

```text
move to hidden
```

并且不修改：

```text
orders.hidden
carried
```

删除完成后立即写入 `workspace.json`。

---

## 9. Add Ticker

Focus 和 Wait 标题右侧分别增加：

```text
+
```

例如：

```text
FOCUS                         +
WAIT                          +
```

从哪个 Section 点击 `+`，Ticker 就加入哪个 Section。

### Flow

```text
Click +
↓
输入 ticker
↓
Longbridge validate
↓
valid
↓
Add
```

---

## 10. US Market Only

Monitor V0 只支持美国证券。

用户 UI 只输入：

```text
NVDA
AAPL
TSLA
```

UI 不显示：

```text
.US
```

内部调用 Longbridge 时转换：

```text
NVDA → NVDA.US
```

---

## 11. Longbridge Validation

Ticker 添加前使用 Longbridge：

```python
QuoteContext.static_info()
```

进行验证。

例如：

```python
ctx.static_info(["NVDA.US"])
```

Longbridge 官方 `static_info` 接口要求 `ticker.region` 格式，并支持通过类似 `AAPL.US`、`NVDA.US` 获取证券基础信息。

### Successful Validation

如果 Longbridge 返回有效证券信息：

```text
NVDA
NVIDIA Corporation
```

允许添加。

### Failed Validation

如果 ticker 无效或 Longbridge 无法找到：

```text
do not add
```

显示简单错误即可。

不实现 fuzzy search。

不实现其他市场搜索。

---

## 12. Add Position

新 ticker 永远加入所选 Section 第一位。

例如原来：

```text
FOCUS

AAPL
TSLA
AMD
```

添加：

```text
NVDA
```

结果：

```text
FOCUS

NVDA
AAPL
TSLA
AMD
```

JSON：

```json
"focus": [
  "NVDA",
  "AAPL",
  "TSLA",
  "AMD"
]
```

同时：

```json
"NVDA": {
  "status": "focus",
  "status_at": "YYYY-MM-DD"
}
```

其中：

```text
status_at = 当前 macOS 本地日期
```

### Existing Ticker

如果 ticker 已经存在于 Focus 或 Wait：

```text
do not add duplicate
```

保持原位置和状态不变。

---

## 13. Write Strategy

V0 使用最简单的同步写入。

所有修改动作：

```text
Add
Delete
Reorder
Move Focus ↔ Wait
```

统一流程：

```text
modify in-memory JSON
→ write workspace.json immediately
```

不使用：

```text
lock
temporary file
atomic replace
write queue
debounce
delayed persistence
background persistence
```

用户完成操作时，磁盘上的 JSON 应立即反映最新状态。

---

## 14. External Update

Scan 修改当前 `workspace.json` 后：

```text
filesystem event
→ reload file
→ Focus / Wait UI refresh
```

不增加：

```text
drag conflict handling
concurrent edit handling
merge logic
version conflict detection
```

V0 假定 Scan 与 Monitor 不会被用户同时操作。

---

## 15. Minimal Data Functions

List 数据层只需要以下核心函数：禁止过度设计，禁止过度开发。比如如下函数即可（仅供参考，你可以根据现有代码风格自行命名，但是保持 minimal）

```python
resolve_latest_workspace()

load_workspace()

reload_workspace()

add_ticker(ticker, section)

delete_ticker(ticker)

move_ticker(ticker, target_section, target_index)

reorder_ticker(ticker, target_index)

save_workspace()
```

以及 filesystem watcher：

```python
start_workspace_watcher()
```

不建立额外的 repository/service abstraction。

---

## 16. Mutation Rules

| Action | orders | status | status_at | Save |
|---|---|---|---|---|
| Add | 加到 Section 第一位 | 设置 | today | immediately |
| Delete | 从 Section 删除 | 删除 | 删除 | immediately |
| Reorder | 改变当前 Section 顺序 | 不变 | dragged ticker → today | immediately |
| Focus → Wait | 两边 Array 更新 | `wait` | today | immediately |
| Wait → Focus | 两边 Array 更新 | `focus` | today | immediately |
| Scan external update | 不写 | 不写 | 不写 | reload only |
| New trading day | 不写 | 不写 | 不写 | switch + reload |

---

## 17. V0 UI

```text
FOCUS                                      +

PAYS
HTFL
PLTU
APPN
...


WAIT                                       +

FEIM
TWST
TITN
TEAM
...
```

Ticker 支持：

```text
click
drag reorder
drag Focus ↔ Wait
delete
```

Section 支持：

```text
collapse / expand
```

但 V0：

```text
不能创建 Section
不能删除 Section
不能修改 Section 顺序
```

固定只有：

```text
Focus
Wait
```

---

## 18. Implementation Principle

V0 原则：

```text
Simple
Direct
Synchronous
Single-user
File-based
```

只解决当前明确存在的问题。

不为以下场景提前设计：

```text
concurrency
multi-user
database
distributed sync
conflict resolution
crash recovery
schema migration
custom sections
```

`workspace.json` 继续作为 Scan 和 Monitor 之间唯一共享的数据源。

## 19. Confirmed Clarifications

- List 变化立即同步当前行情范围：新增订阅 Quote 并加载五个官方周期，删除取消订阅并停止后续下载；Scan 外部修改和新日期切换应用同样规则。排序和 Focus/Wait 互移不触发重新下载。
- 添加时不查询 hidden 成员；即使 ticker 在 orders.hidden 中，也可正常加入点击 + 的目标 Section。orders.hidden 与 carried 原样保留。

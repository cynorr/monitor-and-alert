# Scan 合并方案与落地记录

更新：2026-10-02。用户已确认 NoAdjust 与 Scan/Monitor 互斥模式。本次已完成代码合并、独立 Mock、当前名单/Tag 的一次复制及离线验收；已追加真实拆股复权库的核心计算测试，正式 NoAdjust 上游交付和 Longbridge live 验收尚未完成。

目标是一个应用、一套日 K 图表、一份人工名单、一套指标和原子特征。上游只提供全市场日 K；本项目负责候选生成、人工筛选和实时监控。

## 已核实的原始差异

| 项目 | 原 Scan | 原 Monitor |
| --- | --- | --- |
| bars 主键 | `(ticker, date)` | `(symbol, timeframe, ts)` |
| 标识 | `PAYS` | `PAYS.US` |
| Daily 时间 | 日期字符串 | 美东零点转 Unix 秒 |
| volume | REAL，大量小数 | 非负整数股数 |
| 实际输入 | Parquet | SQLite |
| 价格契约 | 注释要求拆股复权，文件口径未确认 | 官方 NoAdjust、regular、closed |
| ADV20 | 最近20条 `close × volume` | 原先优先 turnover，缺失估算；现已统一为 Scan 公式 |

检查的 Scan `bars.sqlite` 有 6,372,033 行、16,365 个历史 ticker；最新日 2026-09-30 有12,613行，其中11,650行 volume 带小数。Monitor 原库有51个历史 symbol、五个周期，最新 Daily 是2026-09-25。历史库成员不代表当前行情白名单。不同供应商的原始数值不保证相等。

`scan_stocks.py` 原本已经调用 features 的算子，重复来自两个生成任务及两个项目分别实现指标；因此采用迁入纯算子、收敛基础公式与组装流程的方式。

## 数据与互斥模式

- `runtime/daily.sqlite3`：上游全市场 closed Daily，本项目只读。完整契约直接交付 [upstream-daily-data.md](upstream-daily-data.md)。
- `runtime/bars.sqlite3`：现有 Longbridge 运行库，只写当前 Focus/Wait 的五个官方周期。
- 两者使用同一个 Bar、SQL reader 和指标实现，保留明确的来源。模式切换时释放另一模式的券商任务/订阅/context；不混库、不拼接历史、不新增服务或通用适配框架。
- Scan：只有日 K，使用选定日期 D 的上游数据；显示 Discover/Focus/Wait/Hidden。选择任何本地成员都不请求券商。
- Monitor：实时 Daily + Intraday，只有当前最新 workspace 的 Focus/Wait。名单筛选和图表选择不扩大行情范围。
- 两个模式共用一份当前 workspace；历史 Scan 日期只读。切换模式/日期重置图表选择与缓存上下文，WS 保留 request_id 和连接身份校验。

## 计算收敛

`indicators.py` 是 EMA/SMA/TR/Wilder ATR/ADR/ADV/RFL 的唯一实现，日 K Panel 只有一份。

ADR20 使用最近最多20根 `(H-L)/L × 100` 均值，ADV20 使用最近最多20根 `close × volume` 均值；不保留同名 turnover 版本。RFL 使用最近最多21/63/126根最低low。EMA 用首个 close 初始化，图表达到10/20个样本后显示；SMA50/ATR20 保留原 Scan 的完整窗口种子和空值语义。

生成流程已按2026-10-02的提速要求调整：完成日期 D → 全市场最多20根计算ADR≥5%、ADV≥$5M → 仅eligible最多126根计算三个RFL并分别排名 → 任一rank≤50即candidate → 仅candidate最多1000根计算均线/ATR/原子特征 → 保存一份 `days/D/scan.json`。取消Price≥5门槛；并列排名按固定symbol顺序使用 method=first；Tag和页面排序不重新排名。Refresh和无--date的CLI读取上游metadata.completed_date并生成最新日，当前细节以development/behavior/ui为准。

原子公式直接迁入 `features/atomic.py`，默认五日窗口。每次只保留一只证券的历史与全市场标量结果，避免把六百万根历史整体读进内存。生成运行在同进程后台线程，图表和GET读取不触发生成。

## 名单、Filters 与 Tags

`workspace.py` 同时承担四列表派生、继承和现有同步持久化；没有复制旧 WorkspaceStore/锁/服务。

- version2、裸 ticker、statuses、orders.focus/wait/hidden、carried、discover_order 保留；数据库/快照使用带 `.US` 的 symbol。
- Focus/Wait 跨日继承，即使不再candidate也保留。Discover由candidate与carried派生，不新增第二份成员表。
- Hidden按7个自然日计算：6天仍隐藏，7天仍是candidate时返回并标记Returned，后续新日不再保留过期状态；跨日继承要求前后两日candidate交集。
- 新日首次生成才继承，已有日期重算不覆盖人工状态。所有新操作status_at使用workspace日期，不批量重写旧值。
- 批量移动一次验证/写入，保持提交顺序在目标顶部。Delete解除Focus/Wait归属；Hide明确进入Hidden；返回Discover保留当天非candidate成员。
- 38项条件保留；数值≥/≤/范围，字段间AND、分类内OR、Any与缺失语义；RFL仅排序。字段目录只有一份JSON，筛选执行只有TypeScript一份。
- Tag是保存的过滤条件：Default常驻、最多10个、即时草稿、Save持久化、Cancel恢复；失败保留草稿。全选/批量移动针对可见结果，独立于图表选择。

## 正式路径

```text
data_service/
  workbench.py                 # 互斥模式生命周期
  store.py / indicators.py     # 共用读取与公式
  features/atomic.py           # 原子算子
  features/screening.py        # 初筛/排名/候选
  features/snapshot.py         # 纯计算截面组装
  scan.py                      # 上游读取、生成与日图
  workspace.py / preferences.py
  service.py / broker.py       # 既有 Monitor 调度和唯一 SDK 入口
ui/src/
  chart.ts / list.ts           # 共用图表/名单
  scan.ts / filters.ts / tags.ts / filter-catalog.json
runtime/
  daily.sqlite3 / bars.sqlite3
  preferences.json
  days/YYYY-MM-DD/scan.json
  days/YYYY-MM-DD/workspace.json
  scan-mock/                   # 独立合成数据和测试名单
```

当前真正使用的 `~/qull-scan-workspace` 中15份workspace和7个Tag已原样复制到runtime，最新2026-09-30：Focus34、Wait20、Hidden5。源文件保留；新入口默认只管理runtime中的一份。未导入旧Parquet候选/特征，避免把旧复权口径结果当作新NoAdjust结果；第一次新截面没有上一份候选时，所有候选均标记NEW。

复制进仓库的 `qull-scan-workspace/` 保留作参考并被git忽略；正式代码没有依赖它，也不运行其旧服务/HTML/生成任务。未删除用户复制的数据和Git仓库。

## 实施次序与剩余接入

已按“契约/公式 → Workspace与模式 → Filters/Tags”迁移，并在每步结束收敛重复逻辑。实际验证记录在 [validation.md](validation.md)，正式维护入口仍为development/behavior/ui。

剩余接入由上游按契约提供NoAdjust SQLite，然后显式生成完成日D，查看真实截面与日图。NoAdjust会改变跨拆股的RFL、ATR、EMA，原Scan复权结果不能直接作为等价验收基准。正式Longbridge live另行明确Focus/Wait子集与时限；本轮所有模式切换使用离线替身。

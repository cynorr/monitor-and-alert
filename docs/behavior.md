# 看盘服务运行逻辑

更新：2026-09-24。面向使用者；实现入口见 [development.md](development.md)，布局和交互见 [ui.md](ui.md)。

## 启动与接收

启动选择 `~/qull-scan-workspace/days/` 下目录名为 YYYY-MM-DD 且含 workspace.json 的最新日期，读取 focus/wait，开始接收当前名单的 Quote，同时加载历史。显式 `--workspace` 则固定使用该文件。每个 ticker 获取 Daily、5m、15m、30m、1h 最近 1000 根。正在形成的 candle 被过滤，盘中可能剩 999 根；短历史照常显示。没有分页，不连接旧历史，不追查历史断档（包括返回窗口内部的旧空档）。

Quote 统一接收和校验，regular 与 extended 按时段保存最新值，两者均不落盘。Regular 更新活跃 candle；extended 只显示最新价格。页面选股不改变券商订阅范围。关闭网页不停止后端。

## Focus / Wait 列表

需求来源：[List Module V0](list-module-v0.md)。

Monitor 与 Scan 共用当前 workspace.json，保留 schema 和 version。Focus、Wait 固定顺序，可折叠；数组顺序就是显示顺序。Section 右侧 + 输入美国 ticker（不带 .US），由同一 Longbridge context 的 static_info 验证后加入该 Section 首位。无效或验证失败不添加；已在 Focus/Wait 的 ticker 保持位置、状态和日期不变。

可拖动排序或跨 Section 移动，删除直接移出数组并删除对应 statuses 记录。新增、移动和排序只更新主动操作 ticker 的 status_at，使用本机本地日期；被动移位 ticker 不变。所有操作同步直接写回文件，完成即保存，无 debounce、队列、原子替换或文件锁。

不读取 hidden 的成员来决定行为，不修改 orders.hidden 或 carried。即使 ticker 在 hidden 数组内，也可正常加入 Focus/Wait；保留 statuses 记录的其他字段。

一个 watchdog 原生文件事件 watcher 递归监听 days：Scan 修改当前文件后自动重读；出现更大日期的 workspace.json 自动切换。外部更新只读、不回写，无轮询、合并或并发冲突处理。读取/保存失败显示简单错误。

名单增加会立即安排五个官方周期最近 1000 根，并订阅 Quote；移除会撤下下载任务、停止后续请求并取消 Quote 订阅，已有 SQLite 历史不删除。排序和 Focus/Wait 互移不重下载、不重订阅。Quote 订阅变更在现有 context 上执行；网络请求仍受现有预算约束。文件切换保留仍在名单中的行情状态。选中 ticker 被删除时选择第一项，名单为空时清空图表、保留新增入口和 WebSocket。

`--symbols` 验收会话始终限制在指定子集，禁用列表编辑；文件更新不会扩大该范围。模拟器仅编辑临时 workspace 副本，新增使用明确标记的模拟证券信息，不调用真实验证。

## 请求顺序与恢复

订阅恢复和到期 closed 更新优先；选中 ticker 的 5m、Daily 优先于其他历史，然后所选官方分钟周期。其余按 5m、Daily、15m、30m、1h 推进。

全局每秒最多 10 次、最多 5 个请求在途（[官方额度](https://open.longbridge.com/docs#rate-limit)）。10 是总量，不与 5 相乘；count=2 的一次调用仍只算一个请求。后台历史最多每秒 8 次、占 3 个槽，给交互保留 2 个请求/秒和 2 个在途位置。在途请求不强制取消，同一个 ticker/周期不会重复下载。

正常每根收盘后 2 秒调用最近 K 线 count=2，覆盖“最新一根还在形成”的情况；只保存已闭合数据。启动、检测到重连/休眠、跨过多个边界以及失败补缺，均使用 count=1000。没有第二个历史 API。

本轮缺失或请求失败后再重试 3 次（间隔 2/5/10 秒）。仍失败则显示错误并等待下一个 5m 收盘后 2 秒，再最多尝试 3 次。每轮对每个失败周期单独执行，其他 ticker 继续运行。成功后清除错误。只要求最新应闭合的目标存在；历史空档可能来自无成交或停牌，直接接受，不扫描连续性、不触发补缺。

SDK 负责底层连接恢复；应用保留 30 秒 snapshot、开市无全名单推送 watchdog。应用重新订阅成功时触发统一回补；SDK 内部不可见的短重连由 snapshot 与 closed 目标检查补足。

## OHLC 原值与比较日志

如果价格正数且有限，但 Open/Close 超出 Low/High，或 High 小于 Low，原值仍入库和绘图。上下界检测只追加到 runtime/invalid_ohlc.jsonl：ticker、周期、交易时段、bar 起止 Unix 秒与 ET、获取时间、原始 OHLCV。每次获取重复追加，不去重、不修复、不回补、不显示感叹号。

不使用 max/min 强制修正官方 OHLC。非数字、非法时间戳、负 volume 等无法正常使用的数据仍被拒绝；必要位置没有可用 bar 时按缺失恢复。成交额缺失可用于估算 ADV，价格不变。

## 图表周期与指标

官方闭合数据存 SQLite。Quote 产生的临时 5m、所有合成周期和指标仅在内存。

2h/4h 始终从 5m 合成。15m/30m/1h 缺少官方 bar 时，用相同函数合成替代；官方到达后随下一次现有 WebSocket 更新直接替换，不另等收盘。按实际开盘时间分组，不跨日，尾根按收盘时间结束。闭合合成 candle 的 5m 前缀缺失时不编造完整结果。

合成只改变周期，不扩展历史时间跨度：1000 根 5m 约覆盖 13 个普通交易日，2h/4h 也只有这段历史。均线样本不足时不显示该线。

两个图保留 EMA10/20，Daily SMA50、Intraday SMA65，以及 Daily ADR20/ADV20。Intraday active volume = 本根内已闭合部分的量 + 当前 5m 内 Quote 累计量的增量。已闭合部分优先按 1h → 30m → 15m → 5m 无重叠拼接，只使用完整落在本根起点到当前 5m 起点之间的官方 bar。结果缓存为标量，Quote 更新不重新求和。不能用全天 Quote 累计量减历史 K 线总量，因为两者累计差异会全部堆到 active。盘中启动、恢复、跳过时间桶或累计量回退时，没有可靠起点的 active volume 暂空；跨入下一连续 5m 后恢复。Daily 仍使用官方累计量。active 是按 Quote 观测时刻估算的临时量，收盘后由官方 K 线替换。上下界矛盾也可能体现在图表及派生指标中，因为本版保留官方原值。

## 页面状态

- Loading：Daily + 5m 尚未完成。
- 黄色 Ready：Daily + 5m 验证通过，保持到五周期完成。
- 蓝色 Ready：五个官方周期验证通过，3 秒后隐藏。正常每根收盘更新不会反复闪烁。
- 感叹号：回补重试耗尽，悬停查看缺失/请求失败等原因；连接中断也明确显示。

2h/4h 和临时合成结果不算官方周期下载完成。错误仍在重试时保留已有图表；成功即恢复。OHLC 上下界矛盾不影响 Ready、不进入错误提示。

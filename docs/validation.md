# 验证记录

## 2026-09-24：List Module V0

环境：macOS、Python 3.13、Longbridge SDK 5.0.0、watchdog 6.0.0。实现规格见 [list-module-v0.md](list-module-v0.md)。

- 最终离线回归：83 项通过（4.57 秒）；TypeScript check/build 与 git diff --check 通过。HTTP/WS 仅绑定本机，文件事件使用临时目录。
- 新增覆盖：同步落盘、主动/被动 status_at、重复添加不变、hidden/carried/其他字段保留、验证失败不写入、写入失败可重试、排队请求重新检查白名单、动态成员增删、空名单、原生文件修改/rename/新日期切换、Origin 校验及列表独立 WS 消息。
- 浏览器（隔离模拟器）：新增原 hidden 中的 ticker 到首位、同组指针拖动排序、跨组拖动、拖入折叠 Section、展开顺序、删除选中 ticker 后双图自动切换均通过；最终构建再次验证排序成功，未观察到 JavaScript 错误。模拟操作只修改临时 workspace 副本。
- 本轮真实 Longbridge：北京时间 2026-09-24 01:28:55 开始，65.04 秒，范围严格限定最新正式 Focus/Wait 中 WGS.US、NOWL.US、PAYS.US。单一 context、临时 workspace 和 SQLite；未修改正式 Scan 名单（前后 SHA-256 一致），测试连接已关闭。
- 实际 static_info 返回 PAYS/Paysign，空名单后添加 WGS 也验证成功。初始两股五周期就绪；PAYS 新增后五周期和 Quote 就绪。跨组、排序保持既有 SyncState/订阅，被动 ticker 日期不变，重复添加文件不变。删除 NOWL 后实际 unsubscribe，并撤下下载任务。
- 原生外部写入将名单改为 PAYS/NOWL，自动订阅/退订；更大日期的空 workspace 自动切换并退订全部，WS 继续发送空名单。重新添加 WGS 后恢复五周期 full，重连收到完整图表快照。
- 该轮记录 23 次 recent-1000 历史调用、2 次 static_info、4 次 subscribe、4 次 unsubscribe（含退出清理），收到 14 次 Quote 推送；结束时无耗尽错误，WGS stage=full，4 项正常收盘任务处于等待节点。未将等待正常更新表述为数据缺失。
- 首次尝试已验证增删/移动/外部更新，但验收脚本比较 /var 与 /private/var 别名导致超时；修正测试路径后以上完整重跑通过。首次记录不作为完整验收依据。
- 完整通过证据：`/private/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/list-v0-live-8_z3b6a3/report.json`。
- 未覆盖：全名单长时间运行、物理断网/休眠、移动触屏。错误路径使用离线测试；未额外查询真实无效 ticker，未操作生产名单。

## 2026-09-23：Intraday active volume 修复（当日美东上午）

- 离线回归：68 项通过，2.26 秒。覆盖全天累计差异不进入 active、大周期无重叠覆盖、缺少 5m、缓存复用及修订失效、六个分钟周期、跨日/跳桶/恢复/计数回退。前端代码未修改。
- 本轮 live 仅观察现有服务的 MRNA.US 最新 5m：美东 2026-09-23 10:55–11:00；未新建券商连接、未请求旧交易日测试集。
- 22 次只读观测确认：桶内 `Quote累计量 - active量` 基准不变，active 量始终非负；首个观测 113,633，最后一个收盘前观测 214,853；官方 closed 返回后替换为 161,673，下一桶观测为 7,629，没有把全天累计差异堆到新柱。
- active 是 Quote 采样估算，不承诺等于官方分钟量；本轮预估与官方仍有差异。闭合后使用官方量，不能通过任意缩放或修正价格/成交量伪造一致。
- 证据：`/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/mrna-volume-final-ugv35ac3/report.json`。本轮只验收成交量修复，不宣称全名单所有周期无错误或全天稳定运行。

## 2026-09-23：架构精简

当前实现规则见 [behavior.md](behavior.md)，开发入口见 [development.md](development.md)。下面记录本轮执行证据，不代表持续在线状态。

环境：macOS、Python 3.13、Longbridge SDK 5.0.0。测试使用当前 workspace 白名单及临时 SQLite；未修改生产数据库，临时服务均已停止。

- 离线：58 项通过（2.23 秒）；TypeScript check/build 通过。最后将模拟器 HTTP 启动改为复用正式入口后，相关 5 项再通过（1.12 秒）。
- 覆盖：OHLC 原值与重复追加日志、最新目标缺失/请求失败的重试轮次、历史断档接受、重连期间在途任务、8/2 限流和 3+2 并发、官方替换合成、2h/4h、DST/提前收盘、Quote 恢复、HTTP/WS 与模拟器跨周期。
- 浏览器：保留矛盾 OHLC 后图表可绘制，无 JavaScript 错误；2h/4h 切换正常。黄色 Ready 跨多次观察持续显示；官方 15m 延迟时已有 5m 合成显示。蓝色 Ready 的 3 秒隐藏已在较短延迟的前一次模拟验收中验证。
- 最终全名单 live：美东 2026-09-22 13:39:50 起运行 150 秒，45/45 ticker 的五个官方周期 full，pending=0、errors={}。收到 1,799 次 Quote 推送、737 条图表消息；WS 重连收到完整快照。
- 同轮请求：225 次 count=1000、44 次正常 count=2；跨过 13:40 收盘节点。没有额外补缺请求。1000 请求允许返回更短历史，最短存储窗口 158 根。OHLC JSONL 追加 466 条，均未造成错误状态或重试。
- 真实 Quote 重订阅：PAYS/HTFL/PLTU，首次各五周期共 15 次 count=1000；主动取消再订阅后，全部 15 项进入统一恢复，再请求 15 次 count=1000，恢复 full、无错误，随后收到新推送。此测试不等同于物理断网或操作系统休眠。

最终全名单证据：`/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/longbridge-check-4v431g4y/report.json`；同目录 `invalid_ohlc.jsonl` 可与 TradingView 手工比较。

重订阅证据：`/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/longbridge-recovery-80yla527/report.json`。

前一轮 live 曾检查返回窗口内连续性，导致 REPL 的三个分钟周期与 USDE Daily 因旧空档重试；这些周期的最新目标均存在。最终已删除历史连续性检查并重跑以上全名单验收。前一轮产物 `longbridge-check-b8zmpv5b` 仅供差异追溯，不代表最终行为。

本轮未重新完整操作所有既有布局/日联动手势；chart.ts 与 layout.ts 未改动，历史验收范围见下表。长时间运行、物理断网和系统休眠仍需另行观察。

## 历史证据摘要

以下规则属于旧版本，不能作为当前需求：严格 OHLC 拒绝、定点修复、history offset、readiness v2、历史连续性补齐均已删除。

| 日期 | 当时验证 | 范围与限制 |
| --- | --- | --- |
| 2026-09-20 | 52 项离线测试通过 | 旧 OHLC 拒绝/定点修复，不代表当前保留原值方案 |
| 2026-09-20 | 40 项离线测试、TypeScript 通过；45 ticker 完整模拟跨周期/交易日 | 浏览器验证三栏拖动、短历史 spacing、自由十字线、交易日联动；未连券商 |
| 2026-09-20 | 首版 34 项离线测试通过 | 初版双图/HTTP/WS；已被后续布局与状态语义取代 |
| 2026-09-18 19:31 UTC | 17 项测试、45 ticker 真实接口、3,060 次 Quote 推送 | 当时重订阅恢复及 5m closed 更新通过；258,795 根旧规则库审计；部分官方 OHLC 被拒绝，不能表述成全量 Ready |

旧实测产物曾保存于 runtime/full-universe-http.json、full-universe-report.json、recovery-smoke.json、invariant-audit.json；文件若仍存在，仅作历史数据，正式服务不消费这些报告。

移动触控、全天稳定运行和实际系统长时间休眠恢复仍未完整验收。模拟测试、短时 live 和历史记录分别标明，不相互替代。

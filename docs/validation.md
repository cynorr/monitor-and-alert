# 验证记录

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

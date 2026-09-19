# 实测与交付记录

验证时间：2026-09-18T19:31:44.369160+00:00

本轮交付 Data Service 与本地只读 HTTP 数据接口。具体 Alert 策略、通知和看盘页面尚未实现。

## 已完成验证

- 自动化测试：17 项通过。
- 安装验证：`pip install -e '.[test]'` 和 `longbridge-data universe` 成功。
- 实际请求范围：workspace 当前 45 个 focus/wait ticker；配额记录与数据库 symbol 均无范围外标的。
- 全量运行：45/45 ticker 有 regular quote 状态；取证时 Quote 为 LIVE，已收 3060 次推送。
- HTTP：health、universe、quotes、bars、readiness 均正常；本地请求 AAPL.US 返回 400，未透传到 Longbridge。
- 真实恢复：主动断开并重建 Quote 订阅后，官方 snapshot 恢复价格和累计成交量；收到新推送。
- 闭合更新：PAYS 5m 从 1789759200 更新为新闭合的 1789759500（UTC Unix 秒）。
- SQLite 全量复核：258,795 根，均通过 closed / regular timestamp / OHLCV 校验，仅包含规定的五个周期。
- 离线验证：重新读取 SQLite 重建 readiness，未依赖原 JSON。

## 当前数据可用性

| 状态 | 数量 |
| --- | ---: |
| 严格 READY | 26 |
| 降级可用 | 7 |
| 历史基线可用合计 | 33 |
| FULL_READY | 2 |

FULL_READY 与 READY 是独立维度。FULL_READY 通过：CRCL.US, GDXU.US。

暂不可用于历史比较：PAYS.US, PLTU.US, IRD.US, FTH.US, FWDI.US, AMLX.US, TXG.US, AGEN.US, USDE.US, CRMG.US, ARCT.US, EDRY.US。

部分 Longbridge 官方 K 线存在 open 超出 high/low 的情况。例如 PAYS 在美东 2026-09-08 09:30 的 5m：open=13.510、high=13.500；BLSH 在 2026-09-18 09:30 的 5m：open=36.220、low=36.250。已按原文档规则拒绝这些行并记录，未修改价格、合成 K 线或放宽校验。该差异究竟是供应商统计口径还是数据错误，尚未向供应商核实。

有限时长全量测试已完成冷启动并进入常规运行，结束时部分有界修复任务仍待处理；不能把它解释为所有异常均完成三轮重试。服务正式运行时将继续按有界策略处理。

## 证据与启动

- `runtime/full-universe-http.json`：全量 HTTP 快照、每个 ticker 的验证详情。
- `runtime/full-universe-report.json`：全量运行结束快照。
- `runtime/recovery-smoke.json`：真实重连和正常闭合更新。
- `runtime/invariant-audit.json`：全库数据不变量检查。
- `runtime/data_ready.json`：由 SQLite 重建的状态，包含缺失/拒绝时间戳。

测试服务已停止。正式启动：

```bash
.venv/bin/python -m data_service serve
```

详见 [README.md](README.md)；设计修订已追加到 Longbridge-Data-Service-Design.md 第 21 节。

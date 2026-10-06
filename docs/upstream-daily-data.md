# 共用 bars 契约

更新：2026-10-05。本文件只维护共用 Bar 表、来源边界与完成日契约。Massive 的获取、复权、ADR/ADV、ETF/历史过滤、独立配置和增量构建统一见 [massive-data.md](massive-data.md)。

## 路径与所有权

- `runtime/massive/daily.sqlite3`：Massive 模块唯一写入，Scan 与 Review 只读。
- `runtime/longbridge/bars.sqlite3`：Longbridge 唯一写入，只跟踪当前 Focus 与已接受 Holdings 的并集。
- `--runtime` 修改整个运行根；显式 `--daily-db` 只读消费外部 SQLite 并禁用内置 Massive 获取。

两个来源共用格式、读取、指标及图表，不拼接历史或交叉验证，不在读端二次复权。旧项目数据已迁入正式runtime，正式运行不依赖复制项目目录。

## 唯一共用表结构

```sql
CREATE TABLE bars (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    turnover REAL,
    PRIMARY KEY (symbol, timeframe, ts)
);
CREATE INDEX bars_by_time ON bars(timeframe, ts, symbol);
```

统一使用 `.US` 标识。保留 Massive ticker 原始标点，不猜类别股映射。Daily ts 为交易日 America/New_York 零点转换的整数 Unix 秒，DST 由时区处理。输出 volume 必须是实际 SQLite integer；OHLC 必须正数有限，volume 非负，时间及闭合边界有效。

仅上下界矛盾仍保存官方原值并追加 invalid_ohlc.jsonl，不修正、不告警、不重试。原始行与转换后行继续按各来源契约校验。turnover 允许 NULL，不影响日 K 或 ADV 计算。

## 来源与完成状态

Massive 使用拆股复权、HALF_UP 整数成交量及 `massive_daily` 供应商时段，规则统一在 Massive 文档。Longbridge 保持官方 NoAdjust、regular、closed 和非负整数成交量；仅保存官方 1d/5m/15m/30m/1h，2h/4h 等合成只在内存。Longbridge 后续复权不在当前版本范围。

全市场完成日必须由 Massive 写端明确提交 `metadata.completed_date`，不得从 MAX(ts) 推断全市场 Ready。构建成功后写完成元数据。只用普通SQLite提交，不增加并发读快照或跨构建回滚；本地写入失败直接报错、删除派生库，下次从原始JSON重建。下游特征核对行情版本，候选配置在手动生成时读取。

Scan 和 Monitor 复用 indicators.py 及 Daily 图表，页面选择决定来源。同日重算按既有人工名单维护，新日首次生成继承 Focus。历史迁移/验收事实见 [validation.md](validation.md)，不能作为本轮 live 证据。

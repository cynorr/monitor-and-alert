# Massive Daily 与共用 bars 契约

更新：2026-10-03。用户本轮明确：Massive采用拆股复权与四舍五入整数成交量；Longbridge保持NoAdjust、regular及整数成交量。两源只统一格式、读取、指标及显示，不拼接历史或交叉验证。此要求取代2026-10-02两源统一NoAdjust的交付约定。

## 路径与所有权

- `runtime/massive/daily/*.json`：原始Massive grouped Daily，adjusted=false；累积保留、不覆盖有效文件、不加入Git。
- `runtime/massive/splits.json`：两年窗口滚动覆盖，保留窗口之前历史；唯一可加入Git的运行数据。
- `runtime/massive/daily.sqlite3`：Massive模块唯一构建和发布，Scan只读。
- `runtime/longbridge/bars.sqlite3`：Longbridge唯一写入，只跟踪当前Focus与已接受Holdings的并集。
- `runtime/pipeline-status.json`：各阶段状态及最后完整成功产物，不包含extended拉取字段。

`--runtime`修改整个运行根；显式`--daily-db`消费其他已交付SQLite并禁用内置Massive获取。三份复制项目只作参考，正式运行不依赖它们。

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

Massive timeframe固定1d。Daily ts为交易日America/New_York零点转换的整数Unix秒，DST由时区处理。symbol保留Massive ticker原始标点并追加.US，不猜类别股代码映射。只有完成目标日发布后消费者才可使用，不能从MAX(ts)推断全市场Ready。

Massive原始volume允许供应商小数；复权后按Decimal ROUND_HALF_UP转为非负整数，不以小数反推价格复权状态。价格与VWAP按拆股累计因子调整，成交量除同因子。turnover可用同根VWAP乘未取整量，不能用close×volume冒充真实成交额；缺可靠输入时NULL。ADV20仍使用唯一close×volume均值，turnover不参与。

Massive保留供应商Daily时段口径，metadata必须明确session=massive_daily，不冒充regular。Longbridge继续regular、closed、NoAdjust，成交量为官方非负整数。Longbridge未来复权不在本版本范围。所有读取与图表不再额外复权。

OHLC必须正数有限；上下界矛盾保留值并追加invalid_ohlc.jsonl，不修正、不告警、不重试。输出volume必须实际SQLite integer。每symbol保留截至完成日最多1000根，短历史接受，不补造交易日。Massive原始文件的累积保存不受SQLite最近窗口限制。

## 完成日与Ready

SQLite metadata发布completed_date、input_revision、adjustment=split_adjusted、volume_rounding=half_up、source=massive_grouped_daily、session=massive_daily及turnover口径。临时库全部构建成功后才原子替换，失败保留旧库。

正式启动或手动任务按Daily→split→SQLite→features执行；已Ready跳过。features发布scan.json后才记录对应完成日、输入版本和精确到秒的完成时间。状态文件是检查入口，但必须核对产物，遗留running或不同版本不能冒充Ready。失败保留上一次可用结果，重试耗尽显示错误。

Scan与Monitor继续复用indicators.py和同一Daily图表。Massive复权与Longbridge原始价格差异允许存在，选择页面明确决定来源。人工workspace同日重算不覆盖，新日首次生成才继承。

## 本轮迁移

2026-10-03复制的558份原始日文件和split已逐文件SHA-256核对，原目录保留。旧runtime/daily.sqlite3和runtime/bars.sqlite3亦保留；后者含全市场Daily和分钟线，不直接迁入新的Longbridge运行库。历史验收不能作为本轮live证据，实际覆盖见validation.md。

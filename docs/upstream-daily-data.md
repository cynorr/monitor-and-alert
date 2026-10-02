# 上游全市场日 K 数据交付要求

更新：2026-10-02。供上游项目直接实施；本项目已按此格式开发并提供独立 Mock 数据。用户已确认价格统一采用 **NoAdjust（不复权）**。

## 交付范围与路径

上游只产出全市场日 K SQLite，不需要产出候选、指标、原子特征、Tag 或名单。默认交付到 `runtime/daily.sqlite3`；其他位置用本项目的 `--daily-db /absolute/path/daily.sqlite3` 指定。

本项目只读该文件。Monitor 的 Longbridge 数据仍由本项目写入 `runtime/bars.sqlite3`。两个文件共用 bars 契约、读取函数和指标公式；上游不写 Monitor 运行库，也不拼接两个供应商的历史。

NoAdjust 是最终消费口径：Monitor 已显式请求 Longbridge NoAdjust，保存之后不再做复权；Scan 也不拉取或应用 adjust table。上游如果内部使用复权表，应在交付阶段取得真正的原始 OHLC 和原始成交量，而不是交付复权后的值等待本项目更正。已复权的小数 volume 四舍五入不能恢复原始成交量。

2026-10-02 实际交付检查：当前放在 `runtime/bars.sqlite3` 的新库九列/主键/索引符合结构要求，但 metadata 声明 `adjustment=split_adjusted`、`volume_rounding=half_up`、`session=massive_daily`。用户再次确认维持 NoAdjust；请重新提供原始 OHLCV 到 `runtime/daily.sqlite3`，并确认只含 regular 时段。仅修改 metadata 不算转换；本轮对该真实库的计算测试不代表正式数据口径验收通过。

## 唯一正式表结构

```sql
CREATE TABLE bars (
    symbol    TEXT    NOT NULL,
    timeframe TEXT    NOT NULL,
    ts        INTEGER NOT NULL,
    open      REAL    NOT NULL,
    high      REAL    NOT NULL,
    low       REAL    NOT NULL,
    close     REAL    NOT NULL,
    volume    INTEGER NOT NULL,
    turnover  REAL,
    PRIMARY KEY (symbol, timeframe, ts)
);
CREATE INDEX bars_by_time ON bars(timeframe, ts, symbol);
```

请按以上九列交付 bars 表。`ticker`、`date`、`vwap`、`transactions` 不进入这张表；其他上游内部信息可以放在独立表，本项目不读取。

| 列 | 类型与含义 |
| --- | --- |
| symbol | 大写、包含 `.US`，例如 `NVDA.US`、`PAYS.US`；与 Longbridge 的证券标识一致。类别股等特殊代码需明确映射，不能猜测点号/连字符转换。 |
| timeframe | 固定字符串 `1d`。 |
| ts | 该交易日美东零点对应的整数 Unix **秒**。见下一节。 |
| open / high / low / close | USD 价格；有限正数；NoAdjust；仅 regular 时段，已正式收盘。 |
| volume | 与该根 regular 日 K 同口径的原始非负整数股数；SQLite 实际存储类型为 integer。 |
| turnover | 同根日 K 的 USD 成交额，非负有限值；缺少可靠数据时写 SQL NULL，必须保留此列。 |

主键不重复；同日修订更新原行。可以保留更长历史，但消费者每次只使用截至所选日最近 1000 根，不翻页、不查历史连续性。短历史、新股、停牌按实际可用记录处理，不补造缺失日 K。

## Daily 时间戳规则

`ts` 对应交易日的 `America/New_York` **00:00**，随后转换为 Unix 秒。它不是 UTC 零点、09:30 开盘时刻或16:00收盘时刻。夏冬令时必须由时区处理，不能固定减四/五小时。

```python
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

trading_day = date.fromisoformat('2026-09-30')
ts = int(datetime.combine(trading_day, time.min,
                          ZoneInfo('America/New_York')).timestamp())
assert ts == 1790740800
```

冬令时例子：`2026-01-02` 对应 `1767330000`。日期只按美东还原；表内不再维护另一个 date 主键。遵循实际美国交易日与提前收盘时间；整根 regular 日 K 正式闭合之后才能交付。

示例行（示意数据）：

```sql
INSERT INTO bars VALUES
('NVDA.US', '1d', 1790740800, 180.0, 185.0, 178.0, 183.0, 1000000, NULL);
```

## 本次旧数据必须处理的差异

已检查复制项目的 `bars.sqlite` 和 Monitor 的 `runtime/bars.sqlite3`：

- 旧 Scan 是 `(ticker, date)` 主键，需要变为 `(symbol, timeframe, ts)`；旧 `volume REAL` 需要变为原始整数股数。
- 旧 Scan 最新日 2026-09-30 共 12,613 行，其中 11,650 行 volume 带小数。请先查明小数来源并提供原始整数成交量。本项目不会 round、截断或缩放这些值。
- 旧 Scan 注释要求 split-adjusted，数据库没有足以确认实际复权口径的元信息。不能仅改列名后宣称 NoAdjust；请确认历史 OHLC 和 volume 的来源及口径。
- 上下界矛盾（例如 close > high）保留供应商原值；本项目追加 `invalid_ohlc.jsonl`，不修正、不告警、不重试。非正数/非有限 OHLC、非法时间戳、负数或小数 volume 不符合契约。
- 若提供 turnover，不用 `close × volume` 冒充真实成交额；只有 VWAP 与 volume 属于同一根、同一时段、同一单位时才可提供其乘积，否则写 NULL。

## 完成日发布与触发

先完成交易日 D 的全市场数据库事务并提交，再显式通知本项目生成 D 的 Scan。不能写入首批股票后就通知，也不能用 `MAX(ts)` 代替全市场完成信号。旧日修订与新日写入保持同一表结构，不需要额外任务服务。

服务未启动时，在本项目根目录运行：

```bash
.venv/bin/python -m data_service scan --date 2026-09-30
.venv/bin/python -m data_service serve --mode scan
```

也可以添加 `--daily-db /absolute/path/daily.sqlite3`。离线 scan 不读凭证、不请求券商；与 serve 共用 runtime 单实例锁。服务已运行时，通过现有本地接口触发（应用必须处于 Scan）：

```http
POST /v1/scan
Content-Type: application/json

{"date":"2026-09-30","generate":true}
```

该接口在同一进程后台线程完成计算。选择图表或 GET 查询不会生成 Scan，也不会下载行情。新日期首次生成才继承名单；同日重新生成只更新计算快照，保留人工 Focus/Wait/Hidden 及排序。

## 本项目负责的计算

价格、ADR、ADV 初筛后，按 RFL1M/3M/6M 截面分别排名，任一前50进入候选。公式只有一份：

- ADR20 = 最近最多20根 closed 日 K 的 `(high-low)/low × 100` 均值。
- ADV20 = 最近最多20根 `close × volume` 均值，单位 USD；不读取 turnover 代替此公式。
- RFL1M/3M/6M = `(最新close / 最近最多21/63/126根最低low - 1) × 100`。
- EMA、SMA、ATR 和所有原子特征由本项目计算；不要在上游 bars 表增加这些列。

Scan 与 Monitor 使用同一公式。不同供应商的原始 OHLCV 若有差异，结果仍会不同；这是来源差异。

## 上游交付验收

交付时同时说明已完成的美东交易日 D、价格 NoAdjust/regular/closed 和 volume 单位。确认：

1. 九列及主键/索引符合上面的 DDL；symbol 映射已完成。
2. ts 为整数秒，并覆盖夏冬令时、提前收盘；没有未收盘日 K。
3. OHLC 为正数有限值；volume 实际存储为非负 integer；turnover 为有效值或 NULL。
4. 同日重复发布没有重复主键，完成信号只在全市场提交之后发出。
5. 消费端可以执行 `scan --date D`，随后查看日 K、筛选和移动名单。

本项目 Mock 样例：`scripts/build_scan_mock.py` 生成同表结构的 `runtime/scan-mock/daily.sqlite3`，包含两天快照、短历史样本和独立测试名单。Mock 仅供开发，不代表真实行情验收。

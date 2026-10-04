# 原子特征定义与用途

本文对应当前 `features/` 实现和 Tag 筛选目录。Tag 是用户保存的一组条件、参数与用途；每日匹配得到股票标签。原子特征只描述结构，名单分类由 [list-design.md](list-design.md) 的规则决定，不自动判定买卖。

## 1. 共同口径

- 单位为 `ticker + date`，每行只使用截至目标日期的行情。
- 默认窗口为最近 5 个交易记录，包含当天；按 ticker 的交易序列计数，不按日历日计数。
- `O/H/L/C` 分别为开盘、最高、最低、收盘。`body_low = min(O,C)`，`body_high = max(O,C)`。
- EMA10、EMA20：以首个收盘价初始化，`EMA_t = α C_t + (1−α) EMA_(t−1)`，`α = 2/(周期+1)`。
- SMA50：最近 50 个收盘价的算术平均，未满 50 条时为空。
- `TR = max(H−L, |H−前收|, |L−前收|)`；首日使用 H−L。
- ATR20：首 20 个 TR 平均值作为起点，此后 `ATR_t = (19 ATR_(t−1) + TR_t)/20`。
- EMA、ATR、连续天数、最近事件均使用全部可用历史；可用历史之前的事件不可推断。
- `k` 表示以 ATR 为单位的距离或跨度。除特别注明外，当前价格距离使用当前 ATR。
- 数值缺失保留为空，不当作 0。已启用的条件不匹配空值；Any 不排除空值。
- 窗口统计要求完整窗口及所需指标；已有 ADR / ADV / RFL 允许使用不足窗口的现有记录。

## 2. Market

| 字段 / 界面 | 定义 | 用途 |
|---|---|---|
| `close` / Price | 当前收盘价 | 限制价格区间 |
| `adr20` / ADR · 20d | 最近 20 日 `(H−L)/L × 100` 的均值 | 比较相对日内波动，单位 % |
| `adv20` / Dollar volume · 20d | 最近 20 日 `C × Volume` 的均值 | 限制成交金额；存储为美元，滑块显示 $M |

`rfl1m / rfl3m / rfl6m = (当前 C / 最近 21/63/126 日最低 L − 1) × 100`。保留数据和排序，不提供筛选项。

## 3. MA arrangement

统一字段为 `ma_arrangement`，每个 ticker 只有一个类别：

| 界面 / 存储值 | 定义 |
|---|---|
| EMA10 lead / `ema10_lead` | EMA10 > EMA20 > SMA50 |
| EMA20 lead / `ema20_lead` | EMA20 > EMA10 > SMA50 |
| Under 50 / `under50` | SMA50 > EMA10 > EMA20，或 SMA50 > EMA20 > EMA10 |
| Straddle / `straddle` | EMA10 > SMA50 > EMA20，或 EMA20 > SMA50 > EMA10 |
| Others / `others` | 均线均有值，但至少两条严格相等 |
| Missing / `missing` | 必要均线尚未形成 |

上述四种主类别只覆盖严格排列。相等不自动归入 lead、Under 50 或 Straddle。分类按钮可多选，同字段所选类别之间 OR，与其他字段之间 AND。

该字段用于描述均线相对位置，斜率另由 Geometry 描述；均线排列本身不等同于上涨或下跌速度。

## 4. Invalidation：EMA 带的距离与持续时间

令 `band_high = max(EMA10, EMA20)`，`band_low = min(EMA10, EMA20)`。

| 字段 / 界面 | 定义 | 用途 |
|---|---|---|
| `extended_k` / Above EMA band | `(C−band_high)/ATR20` | 衡量收盘向上偏离 EMA 带的程度；正数为高于上沿，负数为低于上沿 |
| `broken_k` / Below EMA band | `(band_low−C)/ATR20` | 衡量收盘向下偏离 EMA 带的程度；正数为低于下沿，负数为高于下沿 |
| `below_days` / Consecutive closes below band | 截至当天连续满足 `C < band_low` 的交易日数 | 区分首次跌破与持续跌破 |

连续比较使用各日自己的 EMA 带；不受五日窗口限制。当天 `C ≥ band_low` 即重置为 0，包括刚好相等。

不再计算或存储 `EXTENDED` / `BROKEN` flag。举例：用户可把 `broken_k ≤ 1`、`below_days ≥ 2`、`ema20_slope_5d ≤ 0` 保存为 Broken Tag，表示连续跌破至少两日、跌破深度不超过 1 ATR、EMA20 斜率非正。名称不改变公式；这个示例包含斜率等于 0 的情况。

## 5. Geometry：方向与速度

对最近五日某个价格序列 `x_0…x_4`，计算所有 `i < j` 的 `(x_j−x_i)/(j−i)`，取中位数，即 Theil–Sen 原始斜率。再除以当前 C 并乘以 100：

`normalized_slope = median(pairwise slopes) / 当前 C × 100`

单位为 `%/交易日`。正数为向上、负数为向下、0 为水平。使用交易记录下标，不按跨周末的日历时间扩大分母。中位数减少单点异常对斜率的影响。

| 字段 | 价格序列 | 用途 |
|---|---|---|
| `low_slope_5d` | L | 低点抬高或降低的方向 |
| `high_slope_5d` | H | 高点扩张或回落的方向 |
| `body_low_slope_5d` | min(O,C) | 实体下沿的方向，减弱下影线影响 |
| `body_high_slope_5d` | max(O,C) | 实体上沿的方向，减弱上影线影响 |
| `close_slope_5d` | C | 收盘价格路径的方向 |
| `ema10_slope_5d` | EMA10 | 短期均线方向 |
| `ema20_slope_5d` | EMA20 | 较慢的短期均线方向 |
| `sma50_slope_5d` | SMA50 | 中期均线方向 |

所有斜率都用当前 C 归一化，不是五日收益率，也不各自除以该序列起点。

## 6. Tightness：近期跨度

| 字段 / 界面 | 定义 | 用途 |
|---|---|---|
| `body_range_k_5d` / Body range · 5d | `(max(body_high)−min(body_low))/当前 ATR20` | 五日全部实体覆盖的跨度；不是实体长度的均值 |
| `close_range_k_5d` / Close range · 5d | `(max(C)−min(C))/当前 ATR20` | 收盘聚集程度 |
| `median_true_range_k_5d` / Typical daily range · 5d | `median(TR_t/ATR20_t)`，取最近五日 | 典型单日波幅；每一天使用自己的 ATR |

数值越小通常表示相应维度更紧。实体跨度、收盘跨度和单日波幅描述不同现象，可在 Tag 中独立组合。

## 7. Support：价格与目标 EMA 的关系

以下每项分别计算 EMA10、EMA20 两套，字段前缀为 `ema10_` 或 `ema20_`。下表 `M` 表示目标 EMA。

| 字段后缀 / 界面 | 定义 | 用途 |
|---|---|---|
| `close_distance_k` / Close distance | `(当前 C−当前 M)/当前 ATR20` | 收盘在均线哪一侧、离均线多远 |
| `low_distance_k` / Low distance | `(当前 L−当前 M)/当前 ATR20` | 当日最低价在均线哪一侧 |
| `low_abs_distance_median_k_5d` / Typical low distance · 5d | `median(|L_t−M_t|/ATR20_t)` | 五日低点通常离均线多近；取绝对值，不区分上下 |
| `touch_days_5d` / Low touches · 5d | 五日满足 `|L_t−M_t| ≤ 0.5 ATR20_t` 的天数 | 低点进入均线附近带的频率 |
| `close_below_days_5d` / Closes below · 5d | 五日满足 `C_t < M_t` 的天数 | 五日内收盘低于均线的累计频率 |

前两个距离带符号，正数在上方、负数在下方。Touch 的带宽仍固定为 0.5 ATR，Tag 调整的是触碰天数阈值，不会重新定义算子的触碰带宽。Close below 是窗口累计数，允许不连续，与 `below_days` 不同。

## 8. Interaction：穿越、收回与穿透

同样分别计算 EMA10 / EMA20。定义：

- 下穿：前一日 `C ≥ M`，当天 `C < M`。
- 上穿：前一日 `C < M`，当天 `C ≥ M`。
- Reclaim：当天 `L < M` 且 `C ≥ M`。只看当日低点与收盘，不要求前一日收盘在均线下方。

| 字段后缀 / 界面 | 定义 | 用途 |
|---|---|---|
| `days_since_close_downcross` / Since close down-cross | 最近一次下穿距今的交易记录数 | 下穿事件的新近程度 |
| `reclaim_count_5d` / Reclaims · 5d | 最近五日满足 reclaim 的天数 | 日内跌破后收回的频率 |
| `days_since_reclaim` / Since reclaim | 最近一次 reclaim 距今的交易记录数 | 最近收回发生在何时 |
| `close_cross_count_5d` / Close crosses · 5d | 五日窗口内部四对相邻收盘的上下穿次数 | 收盘在均线两侧往返的频率 |
| `max_penetration_k_5d` / Deepest penetration · 5d | `max(max((M_t−L_t)/ATR20_t, 0))` | 五日最深的日内向下穿透，未穿透时为 0 |

事件当天 `days_since = 0`，昨天为 1；无事件为空。最近事件搜索不限五日。五日 cross 最大为 4，不计窗口第一天从窗口外带入的穿越。Reclaim 最多为 5，同一天可以同时是 close cross 和 reclaim。

## 9. 筛选与保存

- 每个字段都可 Any；全部 Any 显示当前列表所有成员。
- 数值使用 ≥、≤ 或闭区间，边界包含在内；不提供严格 >、< 控件。
- 同一 Tag 内不同条件 AND，均线分类的多个选项 OR。
- 草稿变化立即预览，但仅 Save 写入 Tag。Cancel 恢复已保存参数。
- 列表成员来自现有工作区，筛选不会把全市场 ticker 自动加入列表。
- 输出共 51 列：11 基础列、5 连续指标、34 数值原子特征、1 均线分类。界面共 38 项：34 原子数值、1 分类、Price / ADR / ADV。

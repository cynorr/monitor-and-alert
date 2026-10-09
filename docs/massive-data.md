# Massive 数据要求

更新：2026-10-08。本文件是 Massive 下载、证券目录、候选资格、ADR/ADV、RFL、名单完整特征和构建策略的唯一要求入口。共用 Bar 表结构见 [upstream-daily-data.md](upstream-daily-data.md)，名单生命周期见 [list-design.md](list-design.md)，图表展示见 [ui.md](ui.md)。

## 独立配置与处理顺序

候选条件集中在 [config/massive.json](../config/massive.json)，每次生成直接重读。修改配置/目录后通过命令行主动重算，操作见 [Massive 操作](../README.md#massive-操作)；不跟踪配置/目录版本，不自动重算。配置错误直接报错。

| 配置 | 当前值 | 含义 |
| --- | --- | --- |
| exclude_etfs | true | 所有 ETF 均不参与候选排名，含单股、多倍、做多/做空 ETF |
| min_daily_bars | 50 | 截至扫描日实际存在至少 50 根有效、已完成日 K |
| adr20_min_pct | 5.0 | ADR20 至少 5% |
| adv20_min_usd | 5000000 | ADV20 至少 $5M |
| rfl_top_n | 50 | RFL 1m / 3m / 6m 分别取前 50，取并集 |

顺序：当日有 bar → 目录确认非 ETF → 有效历史门槛 → ADR/ADV → RFL 计算与全市场排名 → 候选及保留成员的完整特征。被挡住的证券不占 RFL 名次；属于已有 Focus 或 Excluded 的证券仍按下述范围计算完整特征。目录未知不当作非 ETF；公司资料不参与资格判断。未增加 Price、Test Issue、权证、优先股或 ADR 类别规则。

“50 日”采用实际日 K 根数，目的为确保 SMA50 有样本；不是上市后的 50 个自然日，也不查询或推测 IPO 日期。停牌/缺数据按实际记录计数，未来 bar 不计入；即使名义上市已很久但本地不足 50 根，也暂不成为候选。价格正数有限、volume 非负整数、时间及闭合边界有效；仅 OHLC 上下界矛盾仍保留官方原值并记录日志，继续采用项目共用校验规则。

上述门槛只决定自动扫描候选。Focus 和全部 Excluded（含 Hidden）继续用本地数据计算完整特征，不因未入选候选或 RFL 前 50 而省略。Hidden 七天内跳过名单规则判断，仍计算特征；归属与期限见 [list-design.md](list-design.md#每日规则)。Holdings 独立，不根据扫描资格删持仓，也不扩大 Longbridge 订阅。

## Nasdaq Trader ETF 筛查目录

免费官方文件：[nasdaqlisted.txt](https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt)、[otherlisted.txt](https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt)。字段含义以 [Symbol Directory Definitions](https://www.nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs) 为准，ETF 使用官方 Y/N 字段，不依靠名称猜测。

独立维护命令：

```bash
.venv/bin/python scripts/pull_symbol_directory.py --runtime runtime
.venv/bin/python scripts/pull_massive.py --runtime runtime
```

首个脚本只获取这两个文本文件，各请求一次；也可用成对的 `--nasdaq-file` / `--other-file` 导入本地原文。使用项目共用代理，网络失败直接报错。解析必要表头、每行字段数、ETF Y/N、重复证券和最后 File Creation Time，两文件有效才写 `runtime/symbol-directory.json`。不读取 Massive 凭证，不查询券商。

缓存是普通 JSON，使用 `.US` 标识；Nasdaq 使用 Symbol，其他交易所使用 ACT Symbol，不增加协议别名转换。只保存官方 ETF 布尔标记，不保存或提供 Security Name；公司资料由独立 [Additional Info](additional-info.md) 维护。下载 UTC 时间和文件创建时间仅供查看，不参与规则版本判断。少数供应商符号不匹配时，扫描不接纳未确认类别，不推测映射。

Massive 准备和扫描只消费本地目录，GET 不触发更新。目录不存在或损坏时，新扫描失败并保留旧结果，提示先运行独立脚本。应在每日准备前更新目录，当前没有定时拉取任务。历史扫描重算也使用当前目录，不能将当前分类冒充历史某日的上市名录。

Grouped Daily 仍是一份全市场响应，ETF 筛选节省本地扫描计算；免费目录避免额外使用 Massive 证券资料接口和带宽。已经保存的原始 Daily 不删除或按筛选结果改写。

## 唯一指标口径

- ADR20：最近最多 20 根实际已完成记录的 `(high-low)/low × 100` 均值，单位为百分比。
- ADV20：同一窗口的 `close × 整数 volume` 均值，单位 USD；不是平均股数，也不使用 turnover。
- RFL1m / 3m / 6m：分别使用最近最多 21 / 63 / 126 根实际记录的最低 low，计算 `(当日 close / 最低 low - 1) × 100`。不足完整窗口时沿用实际可用记录；候选历史资格另按上述门槛判断。
- 只对通过全部资格与 ADR/ADV 条件的证券排名。并列按 symbol 稳定顺序 `rank(method=first)`；三个周期入选任一即成为候选。

唯一公式维护于 `indicators.py`，筛选条件维护于 `features/screening.py`。日图和 Scan 使用同一公式，不重复存逐根指标。

### 名单完整特征范围

完整特征计算范围为当日候选 ∪ Focus ∪ 全部 Excluded，包括 Broken、Extended、Under-50 和 Hidden。新日首次生成读取最近前一日名单，将其 Focus 和 Excluded 合并到特征计算范围；同日重算使用已保存的当日名单。继承成员不需要重新满足候选资格、ADR/ADV 门槛或进入任一 RFL 前 50，仍按截至扫描日的本地历史计算均线、ATR、原子特征及 `rfl1m` / `rfl3m` / `rfl6m` 数值。Growth 显示使用这三个 RFL 数值，不新增另一套公式或字段。

继承名单不另行排名。已参加候选筛选的成员保留该阶段产生的全市场名次；未参加排名的成员名次保持空缺。补全完整特征和 RFL 数值不改变 `eligible`、`candidate` 或已有名次，也不沿用昨日的特征结论。Hidden 的屏蔽期限只影响名单规则判断，不减少特征计算范围；数据不足的字段继续保留缺失，不编造历史或据此判为 Broken。

## 原始数据与复权

`runtime/massive/daily/YYYY-MM-DD.json` 保存 grouped Daily 的 `adjusted=false&include_otc=false` 原始响应，累积保留，有效已有文件不覆盖。首次按两年交易日获取；以后仅补最近 14 个自然日范围内缺失的文件。目标按 XNYS 和 ET18点门槛确定，不请求尚未成熟的当天数据。

`runtime/massive/splits.json` 以 Daily 的同一成熟交易日为目标；本地覆盖包含目标日及向前两年窗口时跳过，周末/休市日不重复获取。需要获取时完整分页覆盖目标交易日向前两年窗口，替换该窗口记录并保留更早历史；核对覆盖、比例与唯一 ID 后才原子发布。不得根据候选列表缩减拆股覆盖。Massive 请求共享至少 15 秒的开始间隔；不在此轮增加类型/名称/IPO 查询。

在执行日前，价格及 VWAP 乘累计 `split_from/split_to`，成交量除该因子后用 Decimal ROUND_HALF_UP 转为 SQLite 非负整数。turnover 仅由可靠同根 VWAP × 未取整的复权量得到，否则 NULL；ADV 仍采用 close × 最终整数 volume。Daily 保留 Massive 的供应商时段口径，metadata 写 `session=massive_daily`，不宣称仅 regular。与 Longbridge 不拼接历史或交叉校验，读库/计算/显示不再二次复权。

## SQLite 增量与全量重建

正式产物是 `runtime/massive/daily.sqlite3`，不建立 bars.parquet。metadata只保存已消费文件的大小/mtime清单、实际split结果摘要、完成日及既有行情口径。普通新日只解析并追加新文件；已有文件和split结果未变时不重新处理历史。

任何已消费文件变化、移除、插入较早日期，或实际split结果变化，都删除派生SQLite，重新merge截至目标日的全部raw。缺少上述清单的旧库也直接重建，不维护迁移框架或逐ticker修复。每ticker最多1000根，允许短历史，不补造日期。

使用SQLite普通批量写入及commit，不增加事务协调、失败回滚机制、临时库原子替换、输入竞态检查或读端并发快照。写入失败直接报错，删除不完整SQLite；下次运行全量重建，原始JSON保留。读取期间若库不可用，显示错误，不另加查询兜底或旧库恢复逻辑。

metadata最终写completed_date、input_revision、split_adjusted、half_up、source、session及turnover口径。只有明确完成日是完成状态，不从MAX(ts)推断。

正式启动、普通massive命令和页面Refresh共用Daily → split → bars → features；四阶段目标统一为最新成熟交易日，逐步跳过已完成产物，全部Ready直接跳过。失败后重试仅执行尚未完成或输入已变化的阶段。Daily/split网络获取保持既有有界重试；bars/features本地失败只报错，不自动重试。缺目录/坏配置先于Massive请求检查。Ready只核对完成日与既有行情input_revision；候选配置和目录在生成时读取。强制重算仅由CLI显式执行；`massive --force`重新获取split并生成特征，已有raw保留，SQLite按现有规则跳过/追加/重建。

状态为runtime/pipeline-status.json的daily/splits/bars/features。失败显示错误；同日名单按既有人工状态维护，新日继承Focus和全部Excluded。切页、选图及GET均不下载。开发遵循 [开发准则](development-principles.md)，仅验证本次功能，优先用真实数据和现有服务。

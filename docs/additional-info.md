# Additional Info

更新：2026-10-07。本文件是附加信息定位、数据源、处理和刷新规则的唯一维护入口。模块入口为 [data_service/additional_info/AGENTS.md](../data_service/additional_info/AGENTS.md)，实现契约见 [development.md](development.md)，具体图表排版只在 [chart-ui.md](chart-ui.md#headers-and-information) 维护。

## 定位

公司名、行业大类/小类、市值和财报日期都是可缺失的当前参考信息。独立缓存于 `runtime/additional-info/info.sqlite3`，不绑定 Massive 截面、Monitor 行情、Holdings 或 Workspace，不参与筛选、排名、订阅、估值、Alert 或 Ready。

所有读取只用内存缓存；缺失隐藏相应信息，刷新失败保留上次成功结果。启动核心任务后单独安排附加信息后台任务，不等待其读取或下载。Scan/Monitor/Review/Holdings 选择共用同一 symbol 查询；历史 Scan 仍显示当前参考信息，不冒充所选日历史市值或公司资料。

## 数据源

- 公司资料：[Nasdaq Screener 整表](https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true)。每次一份完整响应，使用 `symbol / name / sector / industry / marketCap`，保留整个原始行；country、ipoyear 等不参与当前功能。
- 财报：[Nasdaq Earnings Calendar](https://www.nasdaq.com/market-activity/earnings)，接口为 `https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD`。每次获取某日整个市场，不逐 ticker 查询。保留 EPS、预测 EPS、surprise、财政季度、报告时段等原始字段，本期只显示日期。
- 两者都是 Nasdaq 网站使用的公开接口，允许 schema 变化或请求失败。全响应校验成功才提交；失败记录在独立状态中，不进入图表行情错误或 Scan 状态。
- Screener 不覆盖所有证券，尤其 ETF。未覆盖直接留空，不做额外补足。Nasdaq Trader Symbol Directory 仅用于既有 ETF 筛查，不能用 Screener 的出现/缺席推断 ETF。
- 财报未来日期可能是预估，并非公司已确认日期；界面提示和 tooltip 保留这一含义。[Nasdaq 说明](https://www.nasdaq.com/market-activity)。查询未来 120 天不保证每家公司已有下一次事件。

## Python 处理

保留原始 JSON 与 `raw_name`，每次更新都生成可空 `company_name`。仅去除明确的证券属性后缀，包括 Class、Common Stock/Shares、Ordinary Shares、ADS/ADR、Warrants/Units 等；保留公司法律名称和 Inc./Corporation/plc。不按第一个连字符粗暴截断，不建立逐 ticker 名称表。

证券只接受与工程相同的美股 ticker 字符形式，统一追加 `.US`；不猜测供应商的 slash、优先股或其他协议别名。无法匹配的 symbol 直接缺失。

sector 与 industry 分别保留 Nasdaq 原分类，缓存和传输不截断字段；显示精简由前端完成，规则见下文。市值保留十进制美元字符串，只显示有限正值；空值、零值和无效值为空，不用实时行情重新计算。

财报日期取请求的日历日期，避免误用上一年报告日或财政季度日期。报告时段保留原值。存在有效实际 EPS（包括零和负值）才标记为已发布；仅计划日期过去不能认定已发布。原始其他指标保留，不计算或显示 beat/miss。

## 刷新与保存

正式服务自动独立刷新；Mock、模拟器及 `--symbols` 会话不自动联网。使用共用 MARKET_PROXY，但不读取任何 API 凭证或调用券商。公开请求串行，开始间隔至少一秒；单次超时30秒，网络失败最多再重试三次，间隔2/5/10秒。格式/本地保存错误直接报告，不自动重试构建。

- 公司整表：每个纽约自然日成功一次，显式刷新可重新获取。
- 首次财报：过去120天至未来120天。先获取过去7天至未来45天，随后补缺历史，再补远期。
- 每日财报：过去7天至未来45天。
- 每周远期：未来第46至120天；成功后七个自然日再更新。
- 每个成功的财报日期独立保存更新时间和原始响应；已完成日期在中断后不重复获取。近期失败停止当次财报任务，次日或显式刷新继续未完成日期。
- 历史累积保留，不周期性重取过去7天以外的已保存历史。未来改期或取消由对应日期的新完整响应替换，旧计划不会因日期过去自动变成已发布报告。

公司整表和单个财报日期各用一次普通 SQLite 提交，成功后更新内存。数据库独立，不等待行情写库；缺失/损坏读取只影响附加信息。状态记录来源更新时间、当次进度和错误。没有新版本迁移、通用适配或跨数据库事务。

自动任务以纽约自然日安排，持续运行时跨日刷新；关闭服务取消任务。GET 不联网，显式 POST 立即安排任务并返回状态，不等待结果。忙时明确返回正在刷新；附加信息成功不切页、不改选中 symbol、不重绘历史 bars。

## 显示语义

Daily 显示可空公司名和精简分类；公司名在 symbol 右侧底部对齐，分类位于 symbol 下一行，ADR/ADV 顺移一行。市值显示在 Intraday 周期按钮下方，例如 `Market Cap 1.5B`，可见文字不带美元符号；tooltip 保留完整美元数值和更新时间。Scan 没有 Intraday，因此不显示市值。财报位于 Daily 右上角 Go to latest 圆形按钮左侧，样式与 Intraday 的 ET time 相近。位置、字号和颜色的唯一详细规范见 Chart UI。

分类最多显示两个不同名称，以 ` · ` 分隔。分别取 sector 和 industry 第一个冒号前的名称，删除括号内说明并合并空白；两者忽略大小写相同则只显示 sector，不把冒号后的更细分类提升为第二级。缺少一级时只显示已有名称，两者都缺失则隐藏。例如 `Health Care / Biotechnology: Biological Products (No Diagnostic Substances)` 显示 `Health Care · Biotechnology`，`Finance / Finance: Consumer Services` 只显示 `Finance`。tooltip 也使用精简文字，原分类仍在缓存和响应中保留。

这是 Nasdaq 分类的显示精简，不转换到 TradingView 的类别名称。TradingView 使用 [FactSet Industries and Economic Sectors](https://www.tradingview.com/support/solutions/43000724300-sector-industry/)，与 Nasdaq 的分类体系不同。

按纽约当前自然日计算，不使用 Scan 所选日期；最近七天内有已发布报告时优先 `Last earnings report · N days ago`，否则显示 `Next earnings report · In N days`。当天分别使用 `Last earnings report · Today` / `Earnings today`。没有下一次时仍可显示最近已发布报告；没有可用事件则隐藏。下一次日程带 `Estimated` 提示。单数使用 `1 day`。

长公司名、分类和财报文字单行省略；财报优先省略说明文字，保留天数。tooltip 提供完整文本、实际日期及数据更新时间。字段缺失保持空白，不显示缺失警告，不阻碍现有图表。

# Market Monitor

个人美股工作台：Scan 全市场筛选与日 K 看 setup，Monitor 实时 Daily + Intraday 看盘。两个页面共用 Focus、日 K 图表和指标；正式服务切页时行情与账户刷新持续后台运行。单进程 Python、SQLite、同源 WebSocket。

[开发准则](docs/development-principles.md) · [List 需求与设计](docs/list-design.md) · [List UI](docs/ui.md#list-ui) · [Alert 需求](docs/alert.md) · [Chart UI](docs/chart-ui.md) · [Holdings 数据](docs/holdings-data.md) · [Holdings UI](docs/holdings-ui.md) · [Logo / Icon](docs/ui.md#logo--icon) · [运行逻辑](docs/behavior.md) · [开发维护](docs/development.md) · [UI 总入口](docs/ui.md) · [验证记录](docs/validation.md) · **[Longbridge 数据要求](docs/longbridge-data.md)** · **[Massive 数据要求](docs/massive-data.md)** · [共用数据契约](docs/upstream-daily-data.md)

Alert 与统一移入 Focus 已实现；完整需求分别见 [Alert](docs/alert.md) 与 [List 入选规则](docs/list-design.md#统一移入-focus)，模块维护入口为 [data_service/alerts/AGENTS.md](data_service/alerts/AGENTS.md)。

## 启动

首次安装需 Python 3.11+：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
```

| 启动方式 | 命令 | 数据 |
| --- | --- | --- |
| Monitor（默认） | `.venv/bin/python -m data_service serve` | 当前 Focus 的 Longbridge 行情，runtime/longbridge/bars.sqlite3 |
| Scan | `.venv/bin/python -m data_service serve --mode scan` | 后台准备全市场 runtime/massive/daily.sqlite3 和最新完成日特征 |
| Scan Mock | `.venv/bin/python -m data_service serve --mode scan --runtime runtime/scan-mock --mock-scan` | 独立合成日 K 和测试名单，MOCK 标记 |
| Monitor 模拟器 | `./simulator/start.command --speed 30` | 临时库/名单，SIM 标记 |

前三种在 http://127.0.0.1:8765/ 打开；模拟器在 http://127.0.0.1:18765/ 。命令同时启动后端和网页，不需另起前端。停止使用 Ctrl+C，关闭网页不停止后端。同一 runtime 只允许一个实例。

本轮已生成 `runtime/scan-mock`。新环境首次创建 Mock：

```bash
.venv/bin/python scripts/build_scan_mock.py
```

Mock 生成器要求目标目录没有现成 daily.sqlite3；重复试验用 `--output runtime/scan-mock-2`。包含48只合成证券、两天截面和短历史样本，名单独立于正式runtime。Scan Mock启动与选股不读凭证；页面主动切换Monitor会按该runtime的Focus启用Longbridge。完整离线实时模拟使用独立模拟器。

正式服务启动后，后台执行一次 Massive 准备：检查原始 Daily 和 split → 构建拆股复权 SQLite → 生成最新日 Scan 特征；已经 Ready 则跳过。网络获取最多尝试四次，退避 2/5/10 秒，并受共享限速约束。本地构建失败直接报错，删除不完整的派生库，下次运行从原始文件重建。没有周期轮询，页面切换和 GET 不触发下载。

手动运行同一任务（不启动 Longbridge 或 SnapTrade）：

```bash
.venv/bin/python scripts/pull_symbol_directory.py
.venv/bin/python scripts/pull_massive.py
```

Nasdaq Trader 目录更新独立于 Massive，仅保存官方 ETF 标记用于筛查。扫描先排除 ETF、未确认类别与不足 50 根有效日 K 的证券，再做 ADR/ADV 和 RFL 排名。可编辑条件集中于 [config/massive.json](config/massive.json)，数据要求统一见 [Massive 数据要求](docs/massive-data.md)。普通新日直接追加 SQLite；旧文件或 split 变化则删除 SQLite 后全量重建。配置和目录变更由命令行重算应用，不做自动版本跟踪。

服务未运行时也可用 `.venv/bin/python -m data_service massive`，与启动、页面 Refresh 共用准备流程。任务 Ready 返回0，阶段失败返回2。手动命令与服务共用 runtime 单实例锁。显式 `--daily-db` 只读消费外部库，不启用内置 Massive 下载。日常刷新与维护重算的操作见下方 [Massive 操作](#massive-操作)。

默认代理为 `http://127.0.0.1:7899`，Massive、SnapTrade 与 Additional Info 共用；`MARKET_PROXY` 覆盖地址，显式空值关闭代理。Massive 凭证来自 `MASSIVE_API_KEY` 或 Git 忽略的 `massive-token.txt` 单行文件，不输出到日志。Longbridge SDK 的接入不由此配置改变。

数据统一放在 `runtime/massive/`、`runtime/longbridge/`、`runtime/holdings/`、`runtime/additional-info/`，人工名单与偏好保持现有路径。Massive 原始 `daily/*.json` 累积保留且不加入 Git；`splits.json` 是唯一允许入 Git 的运行数据。split 每次完整获取两年窗口，替换窗口内记录并保留更早历史，校验成功后原子覆盖。Massive 采用拆股复权，成交量 HALF_UP 四舍五入为整数；Longbridge 仅服务 Monitor，其数据口径与可重建缓存规则统一见 [Longbridge 数据要求](docs/longbridge-data.md)。两者共用指标与图表，数据互不干涉。

Scan 正常时仅显示日期下拉，不重复显示 Ready 日期和完成时间；处理中、失败或目标日未完成时显示阶段及目标日期。自动准备完成不切换页面、不抢走历史日期；手动 Refresh 补齐并打开最新可用日，已完成则直接打开。新日第一次生成继承 Focus 和 Excluded。首份截面准备中可以先打开页面。

默认跟随 `runtime/days/YYYY-MM-DD/workspace.json` 最新日期。旧 Scan 数据、15份历史名单与7个Tag已迁入正式runtime，两个复制的 Scan 项目目录已删除。新环境可复制既有workspace/preferences，或先生成首份Scan。`--workspace` 固定文件，`--runtime` 修改整个运行目录；原生文件事件自动重读名单与跟随新日期。

Monitor凭证来自longbridge-token.txt，沿用App Key/Secret/Token，不输出到日志。默认官方.cn，`--region global`切换接入点。只请求/订阅当前Focus及Holdings；历史库、Discover、Hidden不决定券商白名单。

Holdings 使用 SnapTrade Personal 的 Client ID / Consumer Key / Account ID，标签与值各占一行，保存在 git 忽略的 `snaptrade-token.txt`（权限600）。没有该文件时不启用持仓；`--holdings-credentials` 指定其他路径。正式服务启动立即刷新，Scan/Monitor 均每30秒获取当前USD股票/ETF多头及买卖活动；失败保留上次完整结果，下个周期再取。Scan Mock、独立模拟器、`--symbols`有界验收不获取真实持仓或 Massive 数据。

买卖归属配置为 `runtime/holdings/sequences.txt` 与 `merge_buys.txt`，每次刷新重读；本机已从 `schwab-review` 复制现有规则，原项目保留。新环境需复制这两个文件（无手工关联时可留空）；`--holdings-rules` 可指定目录。单份原始缓存为 `runtime/holdings/latest.json`。SnapTrade 数据获取独立于 HTTP 和前端，正式入口仍是 `data_service serve`，无需旧8766/8000服务；旧持仓进程应停止，避免重复占用同一账户额度。

## Additional Info

公司名、行业大类/小类、市值与财报日期独立后台刷新，允许缺失，不等待或影响 Ready。数据源、Python 名称处理、保存和调度的唯一规范见 [Additional Info](docs/additional-info.md)，模块维护入口为 [additional_info/AGENTS.md](data_service/additional_info/AGENTS.md)。

运行中可用 `POST /v1/additional-info`，JSON 为 `{"action":"refresh"}`；立即返回，不等待下载。`GET /v1/additional-info` 查看独立状态，加 `?symbol=AAPL.US` 只读当前信息。服务停止后可独立运行：

```bash
.venv/bin/python scripts/pull_additional_info.py --runtime runtime
```

`--companies-only` 只更新公司整表；财报验证可用成对的 `--earnings-start` / `--earnings-end` 限定日期。命令共用 runtime 锁，无需券商或 Massive 凭证。

## Massive 操作

日常开机启动服务即可准备最新日；服务已运行但最新日还没准备好时，点击 **Refresh Scan**。四阶段均按最新成熟交易日判断，完成的步骤跳过，失败后再次点击从未完成步骤继续。已有完整产物不会重复下载或生成；正在查看历史日时，点击后打开最新可用日。

目标日仍采用美东 **18:00** 门槛：之前使用上一交易日，之后才准备当天。周末和休市日沿用上一交易日，不重新拉 split 或构建派生产物。日期下拉中的日期都是已经生成的截面；失败原因在阶段提示悬停中查看。

修改候选配置或证券目录后，需要主动重算。先停止 Python 后台服务（Ctrl+C），再用已有本地 SQLite 重算最新完成日：

```bash
.venv/bin/python -m data_service scan
```

此命令只重新生成候选与特征，并按当前 Tag 规则分类，不下载 Daily/split。仅修改候选配置时，无需重新获取证券目录；需要更新目录时先运行 `scripts/pull_symbol_directory.py`。指定日重算可加日期：

```bash
.venv/bin/python -m data_service scan --date 2026-10-05
```

需要强制更新 split 并重算派生产物时，仍在服务停止后使用维护入口：

```bash
.venv/bin/python -m data_service massive --force
```

它重新获取目标交易日的两年 split 窗口、核对并按需构建 SQLite、重新生成最新日候选与特征。有效 raw Daily 保留；同日重算以人工状态为分类基础，不清空名单。完成后按原启动命令启动服务。普通 Refresh 不承担重置；Tag 在页面保存时已经本地重新分类，无需上述命令。

## 使用

Alert 声音由 Python 后台直接播放，使用 macOS 自带音频命令，无需安装独立应用或授权系统通知。继续使用上面的 `data_service serve` 命令启动；后台保持运行即可，Safari/Chrome 关闭或在后台不影响检测和声音。未处理卡片持久化，刷新或重启后仍恢复，恢复时不重播声音。声音与运行要求见 [Alert 后台声音](docs/alert.md#后台声音与运行)。

- 图表按住 **Command + Option** 左键创建，价格取鼠标水平线；点击横线选中后 **Backspace** 删除，上下拖动改价并重新激活。
- Regular 到达/穿越后灰线与左下角卡片保留到手动关闭或跳转。Scan Discover/Excluded 创建先按当前 Tag 规则加入 Focus。

- 列表面板内切换Scan/Monitor；后台Monitor任务、订阅和SnapTrade刷新持续运行。两个SQLite来源共用读取/计算，不拼接历史。
- Scan：选交易日、Discover/Focus/Excluded、38项Filters、保存的Tags、RFL排序。按 [Massive 配置](docs/massive-data.md#独立配置与处理顺序) 初筛后，三组 RFL 排名取并集；无候选 Price 门槛。候选与全部Focus/Excluded（含Hidden）均有完整特征及Growth使用的三种RFL数值，不为继承名单另行排名，详见 [计算范围](docs/massive-data.md#名单完整特征范围)。勾选和图表选中独立；批量移动当前可见结果。历史日期名单只读，Refresh跳过已完成日。
- Focus跨日保留；Discover与Focus匹配负面Tag直接进入Excluded。Hidden/Extended/Broken七个自然日到期后按当前规则重新分类；Review保留待审核，无Dismiss。Hidden七天内跳过名单规则判断，仍计算完整特征。删除Focus移入Hidden，Release/Move to Discover明确解除归属；新入section置顶。
- 共用Daily日 K：所有图使用统一、可人工调整的默认bar spacing，缩放后各自保留；EMA10/20、SMA50、OHLC/Range、ADR20/ADV20、成交量随十字线切换。可见历史长度随间距与面板宽度变化。Scan为所选日的closed数据；Monitor增加Quote活跃日 K。显示与集中人工参数只在 [Chart UI](docs/chart-ui.md) 维护。
- Monitor：5m/15m/30m/1h/2h/4h、SMA65、交易日联动、实时行情；2h/4h由5m在内存合成。
- Search 和 section 的 + 共用内联输入；Scan候选查询只读本地库，Monitor使用同一Longbridge context的static_info，确认后才保存。快捷键和新增位置见 [List UI](docs/ui.md#list-ui)。
- Monitor与Scan共享Focus分组、Tag/Filter、拖动、Shift+上下排序与折叠。每行允许补充当日Tag；Monitor仅显示Focus与折叠Review，本地Daily预览Review不扩大实时订阅。
- Monitor 的 Holdings 固定在下方名单滚动区之外，可整体折叠；按买入批次展示及展开 Buy/Sold 明细，允许同 ticker 多个批次与名单重复，不写 workspace。余仓盈亏、当天建仓基准、Days和当日清仓保留的唯一需求见 [Holdings 数据](docs/holdings-data.md)；显示、排序和布局见 [Holdings UI](docs/holdings-ui.md)。Longbridge 最新价（含盘前/盘后/夜盘）重算市值和盈亏，缺价回退最后成功的 SnapTrade 价格；cash 来自 SnapTrade，Account Value 为当前持仓市值加 cash。
- ADR20 = 最近最多20根`(H-L)/L × 100`均值；ADV20 = 最近最多20根`close × volume`均值，两模式同公式。
- Monitor 缓存刷新与 Ready 的数据含义见 [Longbridge 数据要求](docs/longbridge-data.md)，弱提示和颜色见 [Chart status](docs/chart-ui.md#chart-status)。Scan 图表显示所选日期，准备状态只在未完成或失败时显示。

## 命令与接口

```bash
.venv/bin/python -m data_service universe
.venv/bin/python -m data_service reconcile
.venv/bin/python -m data_service verify
.venv/bin/python -m pytest -q
npm run check --prefix ui
npm run build --prefix ui
npm run test --prefix ui
```

reconcile是有界真实近期窗口初始化，verify不联网。live验收需明确当前Focus子集与时限，见开发文档。有限Monitor命令：0检查通过、2存在缺失、1启动失败；scan成功为0。

| 接口 | 内容 |
| --- | --- |
| GET /health | 当前模式、Quote连接、待处理任务/错误 |
| GET /v1/scan | 当前名单、日期、偏好和模式 |
| POST /v1/mode | `{"mode":"scan"}` 或 `{"mode":"monitor"}` |
| POST /v1/scan | 选择日期`{"date":"D"}`；补齐并打开最新可用日`{"generate":true}`；指定日重算只用 CLI |
| POST /v1/preferences | 同步保存完整Tag/显示偏好 |
| GET /v1/filter-catalog | 唯一38字段目录 |
| POST /v1/list | 查询、新增、删除、拖动；两模式共用三列表/主section移动及当日Tag补充 |
| GET /v1/chart?symbol=PAYS.US&timeframe=4h | 只读图表；Scan只含Daily |
| GET /v1/universe、/v1/quotes、/v1/bars、/v1/readiness | Monitor诊断 |
| GET /v1/holdings | 只读持仓、刷新状态和当前估值；不触发下载 |
| WS /v1/stream | 唯一图表/名单更新通道 |

WS选择含`type=select`、symbol、timeframe、request_id、mode。模式/日期切换及重连发送完整快照；日 K未变时只发预览/状态。状态包含loading/basic/full、errors与refreshing。

UI构建产物和Lightweight Charts已随仓库提供，正常启动无需npm/CDN。模拟器详见 [simulator/README.md](simulator/README.md)。Alert 以独立需求文档为准；不增加下单、消息中间件或通用适配框架。

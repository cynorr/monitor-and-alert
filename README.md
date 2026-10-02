# Market Monitor

个人美股工作台：Scan 全市场筛选与日 K 看 setup，Monitor 实时 Daily + Intraday 看盘。两个模式互斥，共用 Focus/Wait、日 K 图表和指标。单进程 Python、SQLite、同源 WebSocket。

[运行逻辑](docs/behavior.md) · [开发维护](docs/development.md) · [布局/交互](docs/ui.md) · [验证记录](docs/validation.md) · [合并方案](docs/scan-merge-plan.md) · **[上游数据交付要求](docs/upstream-daily-data.md)**

## 启动

首次安装需 Python 3.11+：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
```

| 启动方式 | 命令 | 数据 |
| --- | --- | --- |
| Monitor（默认） | `.venv/bin/python -m data_service serve` | 当前 Focus/Wait 的 Longbridge 行情，runtime/bars.sqlite3 |
| Scan | `.venv/bin/python -m data_service serve --mode scan` | 上游全市场 runtime/daily.sqlite3，需先生成完成日 |
| Scan Mock | `.venv/bin/python -m data_service serve --mode scan --runtime runtime/scan-mock --mock-scan` | 独立合成日 K 和测试名单，MOCK 标记 |
| Monitor 模拟器 | `./simulator/start.command --speed 30` | 临时库/名单，SIM 标记 |

前三种在 http://127.0.0.1:8765/ 打开；模拟器在 http://127.0.0.1:18765/ 。命令同时启动后端和网页，不需另起前端。停止使用 Ctrl+C，关闭网页不停止后端。同一 runtime 只允许一个实例。

本轮已生成 `runtime/scan-mock`。新环境首次创建 Mock：

```bash
.venv/bin/python scripts/build_scan_mock.py
```

Mock 生成器要求目标目录没有现成 daily.sqlite3；重复试验用 `--output runtime/scan-mock-2`。包含48只合成证券、两天截面和短历史样本，名单独立于正式runtime。Scan Mock启动与选股不读凭证；页面主动切换Monitor会按该runtime的Focus/Wait启用Longbridge。完整离线实时模拟使用独立模拟器。

正式 Scan 接入：按 [上游契约](docs/upstream-daily-data.md) 放置 SQLite，全市场交易日写入完成后运行：

```bash
.venv/bin/python -m data_service scan
.venv/bin/python -m data_service serve --mode scan
```

`scan` 默认读取上游 `metadata.completed_date`，也可用 `--date 2026-10-01` 指定已完成交易日。`--daily-db` 可指定其他上游文件位置；图表查询不触发下载或计算。

日常刷新只需三步：上游更新 `runtime/daily.sqlite3` 并提交 `metadata.completed_date` → 页面切入 Scan → 点击 **Refresh Scan**。按钮生成并打开上游最新完成日，不依赖日期下拉框当前选项，不需要另跑脚本。同日刷新保留人工名单；新日首次生成继承 Focus/Wait。历史日期下拉框用于查看已生成的日期；指定旧日重算可在服务停止时运行 `scan --date D`。服务运行时生成统一通过按钮或 `POST /v1/scan {"generate":true}`，CLI 与服务共用单实例锁。

`serve` 不带参数默认进入 Monitor；`--mode scan` 才直接进入 Scan。放置 SQLite 后仍需先运行 `scan --date D`，生成 `runtime/days/D/scan.json`，页面才能切入 Scan。只有 workspace.json 或 SQLite 时，切换会报错。上游文件名即使叫 bars.sqlite3，也应交付到 `runtime/daily.sqlite3`；不要覆盖 Monitor 的 `runtime/bars.sqlite3`，或将 `--daily-db` 指向同一个 Monitor 运行库。

默认跟随 `runtime/days/YYYY-MM-DD/workspace.json` 最新日期。当前真实使用的旧目录已一次复制到runtime，源文件保留：15份名单、7个Tag，最新2026-09-30，Focus34/Wait20。新环境可复制既有workspace/preferences，或先生成首份Scan。`--workspace` 固定文件，`--runtime` 修改整个运行目录；原生文件事件自动重读名单与跟随新日期。

Monitor凭证来自longbridge-token.txt，沿用App Key/Secret/Token，不输出到日志。默认官方.cn，`--region global`切换接入点。只请求/订阅当前Focus/Wait及Holdings；历史库、Discover、Hidden不决定券商白名单。

Holdings 使用 SnapTrade Personal 的 Client ID / Consumer Key / Account ID，标签与值各占一行，保存在 git 忽略的 `snaptrade-token.txt`（权限600）。没有该文件时不启用持仓；`--holdings-credentials` 指定其他路径。启动 Monitor 立即刷新，之后每30秒获取当前USD股票/ETF多头及买卖活动；失败保留上次完整结果，下个周期再取。Scan、Scan Mock、独立模拟器、`--symbols`有界验收不获取真实持仓。

买卖归属配置为 `runtime/holdings/sequences.txt` 与 `merge_buys.txt`，每次刷新重读；本机已从 `schwab-review` 复制现有规则，原项目保留。新环境需复制这两个文件（无手工关联时可留空）；`--holdings-rules` 可指定目录。单份原始缓存为 `runtime/holdings/latest.json`。SnapTrade 数据获取独立于 HTTP 和前端，正式入口仍是 `data_service serve`，无需旧8766/8000服务；旧持仓进程应停止，避免重复占用同一账户额度。

## 使用

- 列表面板内切换Scan/Monitor；切回Scan时停止Monitor任务和订阅。两个SQLite来源共用读取/计算，不拼接历史。
- Scan：选交易日、Discover/Focus/Wait/Hidden、38项Filters、保存的Tags、RFL排序。ADR20≥5%、ADV20≥$5M 初筛，三组 RFL 各取前50，任一入选即候选；不设候选 Price≥5 门槛。只为候选建立均线/ATR/原子特征；其他成员保留 ADR/ADV，原子条件按缺失处理。勾选和图表选中独立；批量移动当前可见结果。历史日期名单只读，同日Refresh保留人工状态。
- Focus/Wait跨日保留；Hidden按7个自然日，仍是候选时第7天返回Discover并标记Returned。新候选标记NEW。删除Focus/Wait解除归属；Hide明确隐藏七天。
- 共用Daily日 K：九个月初始范围、EMA10/20、SMA50、OHLC/Range、ADR20/ADV20、缩放/十字线。Scan为所选日的closed数据；Monitor增加Quote活跃日 K。
- Monitor：5m/15m/30m/1h/2h/4h、SMA65、交易日联动、实时行情；2h/4h由5m在内存合成。
- /搜索，回车选中或新增到Focus首位；+指定新增到Focus/Wait。Scan候选查询只读本地库，Monitor使用同一Longbridge context的static_info。保存同步落盘。
- Monitor支持Focus/Wait拖动、Shift+上下排序、删除、折叠；Scan默认排序下也可调整Focus/Wait顺序。
- Monitor的Holdings在Focus/Wait上方，有独立九列（盘中隐藏Ext为八列）和整体折叠；点击行显示同一Daily/Intraday。所有行单行显示，Net Liq、P/L、P/L Day及对应Total显示整数。Sold为0时数值留空并隐藏展开三角；其余批次可展开，先列各笔Buy，再列Sold。日期在Net Liq对应列、股数在Sold对应列、实际成交价放在Chg%对应列，不增加明细列头。P/L %（含Total和卖出明细）与Chg%显示一位小数；主表不再有Trade Price。点击列头只降序，再点同列取消；换列替换原排序，买卖明细随主行移动。页面启动按完整表格内容测量最紧凑列表宽度，展开明细需要更多空间时自动加宽，剩余宽度由双图平分，不恢复旧宽度比例。Chg%/Ext沿用观察名单口径，P/L Day按当前剩余股数与前一常规收盘价计算、跟随最新时段。允许与观察名单重复，不校验其观察名单归属、不写workspace。Longbridge最新价（含盘前/盘后/夜盘）重算市值和盈亏；缺价回退最后成功的SnapTrade价格。cash来自SnapTrade，Account Value为当前持仓市值加cash。
- ADR20 = 最近最多20根`(H-L)/L × 100`均值；ADV20 = 最近最多20根`close × volume`均值，两模式同公式。
- Monitor Loading → 黄色Ready（Daily+5m）→ 蓝色Ready（五周期，3秒后隐藏）；Scan显示所选日期。仅OHLC上下界矛盾保留原值并追加invalid_ohlc.jsonl，不修正或告警。

Monitor启动/恢复/补缺仅请求最近1000根，closed更新count=2，过滤未收盘；接受短历史，不分页或查历史缺口。全局10请求/秒、5并发；后台历史最多8请求/秒、3并发。

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

reconcile是有界真实历史同步，verify不联网。live验收需明确当前Focus/Wait子集与时限，见开发文档。有限Monitor命令：0检查通过、2存在缺失、1启动失败；scan成功为0。

| 接口 | 内容 |
| --- | --- |
| GET /health | 当前模式、Quote连接、待处理任务/错误 |
| GET /v1/scan | 当前名单、日期、偏好和模式 |
| POST /v1/mode | `{"mode":"scan"}` 或 `{"mode":"monitor"}` |
| POST /v1/scan | 选择日期`{"date":"D"}`；最新完成日生成`{"generate":true}`；指定日生成`{"date":"D","generate":true}` |
| POST /v1/preferences | 同步保存完整Tag/显示偏好 |
| GET /v1/filter-catalog | 唯一38字段目录 |
| POST /v1/list | 查询、新增、删除、拖动；Scan支持批量四列表移动 |
| GET /v1/chart?symbol=PAYS.US&timeframe=4h | 只读图表；Scan只含Daily |
| GET /v1/universe、/v1/quotes、/v1/bars、/v1/readiness | Monitor诊断 |
| GET /v1/holdings | 只读持仓、刷新状态和当前估值；不触发下载 |
| WS /v1/stream | 唯一图表/名单更新通道 |

WS选择含`type=select`、symbol、timeframe、request_id、mode。模式/日期切换及重连发送完整快照；日 K未变时只发预览/状态。状态仅loading/basic/full与errors。

UI构建产物和Lightweight Charts已随仓库提供，正常启动无需npm/CDN。模拟器详见 [simulator/README.md](simulator/README.md)。不增加Price Alert、下单、消息中间件或通用适配框架。

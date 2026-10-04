# Market Monitor

个人美股工作台：Scan 全市场筛选与日 K 看 setup，Monitor 实时 Daily + Intraday 看盘。两个页面共用 Focus、日 K 图表和指标；正式服务切页时行情与账户刷新持续后台运行。单进程 Python、SQLite、同源 WebSocket。

[List 需求与设计](docs/list-design.md) · [运行逻辑](docs/behavior.md) · [开发维护](docs/development.md) · [布局/交互](docs/ui.md) · [验证记录](docs/validation.md) · [早期合并记录](docs/scan-merge-plan.md) · **[数据契约](docs/upstream-daily-data.md)**

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

正式服务启动后，后台执行一次 Massive 准备：检查原始 Daily 和 split → 构建拆股复权 SQLite → 生成最新日 Scan 特征；已经 Ready 则跳过。失败阶段最多尝试四次，退避 2/5/10 秒，网络请求另受共享限速约束；耗尽后显示错误并保留上次完整结果。没有周期轮询，页面切换和 GET 不触发下载。

手动运行同一任务（不启动 Longbridge 或 SnapTrade）：

```bash
.venv/bin/python scripts/pull_massive.py
```

服务未运行时也可用 `.venv/bin/python -m data_service massive`，默认跳过已 Ready 的任务；加 `--force` 可重新获取 split 并重建 bars/特征，已有原始 Daily 保留。任务 Ready 返回0，阶段失败返回2。手动命令与服务共用 runtime 单实例锁；服务运行时用 Scan 的 **Refresh Scan**。显式 `--daily-db` 只读消费外部库，不启用内置 Massive 下载；可用 `scan --date D` 离线重算指定日。

默认代理为 `http://127.0.0.1:7899`，Massive 与 SnapTrade 共用；`MARKET_PROXY` 覆盖地址，显式空值关闭代理。Massive 凭证来自 `MASSIVE_API_KEY` 或 Git 忽略的 `massive-token.txt` 单行文件，不输出到日志。Longbridge SDK 的接入不由此配置改变。

数据统一放在 `runtime/massive/`、`runtime/longbridge/`、`runtime/holdings/`，人工名单与偏好保持现有路径。Massive 原始 `daily/*.json` 累积保留且不加入 Git；`splits.json` 是唯一允许入 Git 的运行数据。split 每次完整获取两年窗口，替换窗口内记录并保留更早历史，校验成功后原子覆盖。Massive 采用拆股复权，成交量 HALF_UP 四舍五入为整数；Longbridge 仍为 regular、NoAdjust 和整数成交量，两者不拼接历史，共用指标及图表。

Scan Ready 显示最新特征完成日与精确到秒的 ET 完成时间；它与当前正在查看的历史日期独立。自动准备完成不切换页面、不抢走历史日期；手动 Refresh 生成并打开最新日。同日重算保留人工名单，新日第一次生成继承 Focus。首份截面准备中可以先打开页面。

默认跟随 `runtime/days/YYYY-MM-DD/workspace.json` 最新日期。当前真实使用的旧目录已一次复制到runtime，源文件保留：15份名单、7个Tag，最新2026-09-30，Focus34/Wait20。新环境可复制既有workspace/preferences，或先生成首份Scan。`--workspace` 固定文件，`--runtime` 修改整个运行目录；原生文件事件自动重读名单与跟随新日期。

Monitor凭证来自longbridge-token.txt，沿用App Key/Secret/Token，不输出到日志。默认官方.cn，`--region global`切换接入点。只请求/订阅当前Focus及Holdings；历史库、Discover、Hidden不决定券商白名单。

Holdings 使用 SnapTrade Personal 的 Client ID / Consumer Key / Account ID，标签与值各占一行，保存在 git 忽略的 `snaptrade-token.txt`（权限600）。没有该文件时不启用持仓；`--holdings-credentials` 指定其他路径。正式服务启动立即刷新，Scan/Monitor 均每30秒获取当前USD股票/ETF多头及买卖活动；失败保留上次完整结果，下个周期再取。Scan Mock、独立模拟器、`--symbols`有界验收不获取真实持仓或 Massive 数据。

买卖归属配置为 `runtime/holdings/sequences.txt` 与 `merge_buys.txt`，每次刷新重读；本机已从 `schwab-review` 复制现有规则，原项目保留。新环境需复制这两个文件（无手工关联时可留空）；`--holdings-rules` 可指定目录。单份原始缓存为 `runtime/holdings/latest.json`。SnapTrade 数据获取独立于 HTTP 和前端，正式入口仍是 `data_service serve`，无需旧8766/8000服务；旧持仓进程应停止，避免重复占用同一账户额度。

## 使用

- 列表面板内切换Scan/Monitor；后台Monitor任务、订阅和SnapTrade刷新持续运行。两个SQLite来源共用读取/计算，不拼接历史。
- Scan：选交易日、Discover/Focus/Hidden、38项Filters、保存的Tags、RFL排序。ADR20≥5%、ADV20≥$5M 初筛，三组 RFL 各取前50，任一入选即候选；不设候选 Price≥5 门槛。为候选及Focus/非Hidden Excluded建立均线/ATR/原子特征；Hidden跳过形态扫描。勾选和图表选中独立；批量移动当前可见结果。历史日期名单只读，同日Refresh保留人工状态。
- Focus跨日保留；Discover与Focus匹配负面Tag直接进入Excluded。Hidden/Extended/Broken七个自然日到期后按当前规则重新分类；Review保留待审核，无Dismiss。Hidden七天内跳过形态扫描。删除Focus移入Hidden，Release/Move to Discover明确解除归属；新入section置顶。
- 共用Daily日 K：九个月初始范围、EMA10/20、SMA50、OHLC/Range、ADR20/ADV20、缩放/十字线。Scan为所选日的closed数据；Monitor增加Quote活跃日 K。
- Monitor：5m/15m/30m/1h/2h/4h、SMA65、交易日联动、实时行情；2h/4h由5m在内存合成。
- /搜索，回车选中或新增到Focus首位；+指定新增到Focus。Scan候选查询只读本地库，Monitor使用同一Longbridge context的static_info。保存同步落盘。
- Monitor与Scan共享Focus分组、Tag/Filter、拖动、Shift+上下排序与折叠。每行允许补充当日Tag；Monitor仅显示Focus与折叠Review，本地Daily预览Review不扩大实时订阅。
- Monitor的Holdings在Focus上方，有独立九列（盘中隐藏Ext为八列）和整体折叠；点击行显示同一Daily/Intraday。所有行单行显示，Net Liq、P/L、P/L Day及对应Total显示整数。Sold为0时数值留空并隐藏展开三角；其余批次可展开，先列各笔Buy，再列Sold。日期在Net Liq对应列、股数在Sold对应列、实际成交价放在Chg%对应列，不增加明细列头。P/L %（含Total和卖出明细）与Chg%显示一位小数；主表不再有Trade Price。点击列头只降序，再点同列取消；换列替换原排序，买卖明细随主行移动。页面启动按完整表格内容测量最紧凑列表宽度，展开明细需要更多空间时自动加宽，剩余宽度由双图平分，不恢复旧宽度比例。Chg%/Ext沿用观察名单口径，P/L Day按当前剩余股数与前一常规收盘价计算、跟随最新时段。允许与观察名单重复，不校验其观察名单归属、不写workspace。Longbridge最新价（含盘前/盘后/夜盘）重算市值和盈亏；缺价回退最后成功的SnapTrade价格。cash来自SnapTrade，Account Value为当前持仓市值加cash。
- ADR20 = 最近最多20根`(H-L)/L × 100`均值；ADV20 = 最近最多20根`close × volume`均值，两模式同公式。
- Monitor Loading → 黄色Ready（Daily+5m）→ 蓝色Ready（五周期，3秒后隐藏）；Scan图表显示所选日期，列表显示最新Scan Ready日期与完成时间。仅OHLC上下界矛盾保留原值并追加invalid_ohlc.jsonl，不修正或告警。

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

reconcile是有界真实历史同步，verify不联网。live验收需明确当前Focus子集与时限，见开发文档。有限Monitor命令：0检查通过、2存在缺失、1启动失败；scan成功为0。

| 接口 | 内容 |
| --- | --- |
| GET /health | 当前模式、Quote连接、待处理任务/错误 |
| GET /v1/scan | 当前名单、日期、偏好和模式 |
| POST /v1/mode | `{"mode":"scan"}` 或 `{"mode":"monitor"}` |
| POST /v1/scan | 选择日期`{"date":"D"}`；最新完成日生成`{"generate":true}`；指定日生成`{"date":"D","generate":true}` |
| POST /v1/preferences | 同步保存完整Tag/显示偏好 |
| GET /v1/filter-catalog | 唯一38字段目录 |
| POST /v1/list | 查询、新增、删除、拖动；两模式共用三列表/主section移动及当日Tag补充 |
| GET /v1/chart?symbol=PAYS.US&timeframe=4h | 只读图表；Scan只含Daily |
| GET /v1/universe、/v1/quotes、/v1/bars、/v1/readiness | Monitor诊断 |
| GET /v1/holdings | 只读持仓、刷新状态和当前估值；不触发下载 |
| WS /v1/stream | 唯一图表/名单更新通道 |

WS选择含`type=select`、symbol、timeframe、request_id、mode。模式/日期切换及重连发送完整快照；日 K未变时只发预览/状态。状态仅loading/basic/full与errors。

UI构建产物和Lightweight Charts已随仓库提供，正常启动无需npm/CDN。模拟器详见 [simulator/README.md](simulator/README.md)。不增加Price Alert、下单、消息中间件或通用适配框架。

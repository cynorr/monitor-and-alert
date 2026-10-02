# 验证记录

## 2026-10-02：真实上游库核心测试与复权口径确认

环境：macOS、现有 Python3.13 虚拟环境、pandas/numpy。只读用户新交付的 `runtime/bars.sqlite3`；6372033 根日 K、16365 个历史 symbol，metadata 明确完成日为 2026-09-30。未启动后端或浏览器，未调用券商，未跑前端测试、全量回归或全链路。

- 九列、主键、时间索引符合结构契约；完成日12613行，symbol 均含 .US、OHLC 正数、volume 实际存储为非负 integer。全市场生成按生产 build_day 读取每只截至完成日最多1000根，逐根验证价格、成交量、turnover、实际交易日/ET时间戳与闭合边界。源库大小/修改时间未变。
- 六个真实样本：NVDA、TSLA、AAPL、AAAA、ACCV、ACIG，覆盖557/305根及仅1根日 K。ADR/ADV/RFL与独立公式核算一致；EMA及Wilder ATR与手工递推一致；Scan 日图的均线/ADR/ADV一致，无active。35个原子字段逐一与原 Scan 算子比较，值及缺失语义一致。
- 完整2026-09-30截面：12613只，622只eligible，90只candidate；三个RFL排名（含并列symbol顺序）和前三组各50名的候选并集与独立排序一致。生成及截面核对耗时94.45秒；JSON可序列化。结果写在临时目录，没有发布到正式days，也没有覆盖人工名单。
- 本轮实际数据口径尚未通过正式验收：metadata 是 split_adjusted、volume half_up，session 是 massive_daily，不能据此确认 regular-only。用户再次确认最终维持NoAdjust与原始成交量，所以上游需重新提供原始OHLCV到runtime/daily.sqlite3；本轮计算通过不等于两来源口径一致。
- 核实broker.py直接请求NoAdjust，没有后续adjust table处理。补充README与上游交接文件：默认serve进入Monitor；直接Scan用serve --mode scan；首次须scan --date D生成截面。上游日库与Monitor运行库物理分离。

报告：`runtime/scan_core_report.json`。未覆盖：真正NoAdjust原始成交量交付、regular时段来源确认、真实Longbridge请求及与上游逐根比较；此次不执行这些网络或全链路验收。

## 2026-10-02：Scan 合并与互斥模式

环境：macOS，Python3.13，Longbridge SDK5.0.0（未连接），pandas3.0.6、numpy2.5.3，Node25.3.0、TypeScript5.9.3。本轮全部运行使用合成SQLite、临时目录或离线券商替身。

- Python完整离线回归：110项、11个subtests通过；包含既有行情/日历/重试/恢复/合成回归和迁入原子算子、指标种子/空值、指定日截断、统一ADR/ADV/EMA、小数volume拒绝、形成日拒绝、OHLC原值/日志、Hidden6/7/8天、carried、批量写入/同日重算、HTTP/WS/Origin、历史只读、切换失败保留Monitor、偏好保存失败保留内存、互斥模式/白名单收缩。
- TypeScript check/build通过；Node Filters/Tags6项通过：38字段唯一、数值闭区间/严格上界、AND/分类OR、Any与缺失、非有限值、滑杆异常范围和小数阈值保留、草稿/保存隔离、Tag唯一名和十个上限。git diff --check通过。
- 浏览器离线替身：Scan日 K与ADR/ADV显示；新Tag编辑、阈值即时过滤、排序保留草稿、Save、重载恢复；两只候选批量移入Focus后，Monitor立即显示同一份成员，隐藏Discover/Hidden，切回Scan恢复上游日图；历史日期禁用名单编辑。该Monitor为FakeBroker，不是Longbridge live。
- 正式CLI的Scan Mock另验：用不存在的凭证路径启动并成功退出，明确不读取凭证；Hide → Hidden → Return Discover置顶、同日Refresh保留人工顺序，页面控制台无error/warn。截图：`runtime/scan-mock/preview.png`。所有验收服务已停止。
- 数据迁移：从原正式`~/qull-scan-workspace`复制15份workspace与7个Tag，保留字节内容和源文件；最新2026-09-30，Focus34/Wait20/Hidden5。universe离线解析54个Focus/Wait。未生成正式NoAdjust截面、未改原来源或Monitor bars的市场行。
- 上游交接文件：upstream-daily-data.md。复制Scan数据库的列/行数/小数volume已只读核实；没有将旧复权未知数据自动转换为正式NoAdjust输入。

未覆盖：真实上游NoAdjust全市场发布、类别股symbol映射、小数volume根因、两个供应商的逐根等价、全市场生成耗时、Longbridge连接释放的真实账户验收、物理断网/休眠/长时间运行和移动触屏。现有Monitor实时算法使用离线回归覆盖；历史live记录不作为本轮证据。

## 2026-09-24：默认周期与搜索显示微调

- 环境：macOS、现有真实服务 `127.0.0.1:8765`。TypeScript build 通过；Node 直接检查构建后的默认周期函数，10 个开盘前、5/15/30 分钟边界、1h 上限及冬夏令时样例通过。
- 页面只读检查：当前美东 15:07 默认选中 1h；搜索 PAYS 只显示 Focus，Wait 隐藏，无回车提示；regular 报价的 Ext 留白。未修改正式名单或创建券商连接。
- 未跑全量/Python 测试；未重新查询真实 Longbridge 候选或验证无效 ticker 返回。候选配色等纯样式留待肉眼验收。

## 2026-09-24：统一内联搜索与新增

- TypeScript check/build、git diff --check 通过；仅运行候选查询/HTTP 与列表修改规则两个相关离线测试，2 项通过（2.60 秒），未跑全量测试。
- 查询成功返回 ticker/name，不写文件、不扩展白名单、不创建下载任务；无效查询返回错误且文件不变。原移动测试覆盖主动项日期、被动项不变、跨组和同步落盘。
- 用户现有真实服务页面：/ 后输入、搜索中再次 / 清空、回车选中 PAYS 并恢复完整列表、Wait + 使用同一输入框、Esc 退出均通过。未修改正式名单，未新建券商连接。
- 现有隔离模拟器临时名单：Shift+下使 PAYS 与 NVDA 换序，选中仍为 PAYS；AMD 停输后候选出现在列表，回车后位于 Focus 首位、选中 AMD 并清空搜索；Wait + 输入 TSLA 后直接回车，添加到 Wait 并选中。临时服务已停止。
- 本轮未对真实 Longbridge 重新验收新的 lookup 动作；其复用既有 static_info 验证。当前已运行 Python 服务需重启一次加载新动作。样式数值未测试，按用户要求留待肉眼验收。

## 2026-09-24：前端样式与搜索快捷键微调

- 仅前端改动：合并重复 CSS，统一字号、圆形图标按钮、三栏标题分割线；调整选中行、指标文字、时段胶囊位置和新增框。
- TypeScript check/build、git diff --check 通过。未运行 Python/全量测试，纯样式数值按用户要求不做自动化测试，交由用户肉眼验收。
- 在用户现有 `127.0.0.1:8765` 服务检查：按 / 后直接输入 PAYS 可过滤列表；新增框为空；新增框内 / 不抢焦点。未提交名单修改、未另建券商连接、未重启现有服务。
- 当前为 regular 时段，扩展时段胶囊未做现场验证；本轮只调整其 DOM 位置和高度，不改变时段判定。

## 2026-09-24：List Module V0

环境：macOS、Python 3.13、Longbridge SDK 5.0.0、watchdog 6.0.0。实现规格见 [list-module-v0.md](list-module-v0.md)。

- 最终离线回归：83 项通过（4.57 秒）；TypeScript check/build 与 git diff --check 通过。HTTP/WS 仅绑定本机，文件事件使用临时目录。
- 新增覆盖：同步落盘、主动/被动 status_at、重复添加不变、hidden/carried/其他字段保留、验证失败不写入、写入失败可重试、排队请求重新检查白名单、动态成员增删、空名单、原生文件修改/rename/新日期切换、Origin 校验及列表独立 WS 消息。
- 浏览器（隔离模拟器）：新增原 hidden 中的 ticker 到首位、同组指针拖动排序、跨组拖动、拖入折叠 Section、展开顺序、删除选中 ticker 后双图自动切换均通过；最终构建再次验证排序成功，未观察到 JavaScript 错误。模拟操作只修改临时 workspace 副本。
- 本轮真实 Longbridge：北京时间 2026-09-24 01:28:55 开始，65.04 秒，范围严格限定最新正式 Focus/Wait 中 WGS.US、NOWL.US、PAYS.US。单一 context、临时 workspace 和 SQLite；未修改正式 Scan 名单（前后 SHA-256 一致），测试连接已关闭。
- 实际 static_info 返回 PAYS/Paysign，空名单后添加 WGS 也验证成功。初始两股五周期就绪；PAYS 新增后五周期和 Quote 就绪。跨组、排序保持既有 SyncState/订阅，被动 ticker 日期不变，重复添加文件不变。删除 NOWL 后实际 unsubscribe，并撤下下载任务。
- 原生外部写入将名单改为 PAYS/NOWL，自动订阅/退订；更大日期的空 workspace 自动切换并退订全部，WS 继续发送空名单。重新添加 WGS 后恢复五周期 full，重连收到完整图表快照。
- 该轮记录 23 次 recent-1000 历史调用、2 次 static_info、4 次 subscribe、4 次 unsubscribe（含退出清理），收到 14 次 Quote 推送；结束时无耗尽错误，WGS stage=full，4 项正常收盘任务处于等待节点。未将等待正常更新表述为数据缺失。
- 首次尝试已验证增删/移动/外部更新，但验收脚本比较 /var 与 /private/var 别名导致超时；修正测试路径后以上完整重跑通过。首次记录不作为完整验收依据。
- 完整通过证据：`/private/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/list-v0-live-8_z3b6a3/report.json`。
- 未覆盖：全名单长时间运行、物理断网/休眠、移动触屏。错误路径使用离线测试；未额外查询真实无效 ticker，未操作生产名单。

## 2026-09-23：Intraday active volume 修复（当日美东上午）

- 离线回归：68 项通过，2.26 秒。覆盖全天累计差异不进入 active、大周期无重叠覆盖、缺少 5m、缓存复用及修订失效、六个分钟周期、跨日/跳桶/恢复/计数回退。前端代码未修改。
- 本轮 live 仅观察现有服务的 MRNA.US 最新 5m：美东 2026-09-23 10:55–11:00；未新建券商连接、未请求旧交易日测试集。
- 22 次只读观测确认：桶内 `Quote累计量 - active量` 基准不变，active 量始终非负；首个观测 113,633，最后一个收盘前观测 214,853；官方 closed 返回后替换为 161,673，下一桶观测为 7,629，没有把全天累计差异堆到新柱。
- active 是 Quote 采样估算，不承诺等于官方分钟量；本轮预估与官方仍有差异。闭合后使用官方量，不能通过任意缩放或修正价格/成交量伪造一致。
- 证据：`/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/mrna-volume-final-ugv35ac3/report.json`。本轮只验收成交量修复，不宣称全名单所有周期无错误或全天稳定运行。

## 2026-09-23：架构精简

当前实现规则见 [behavior.md](behavior.md)，开发入口见 [development.md](development.md)。下面记录本轮执行证据，不代表持续在线状态。

环境：macOS、Python 3.13、Longbridge SDK 5.0.0。测试使用当前 workspace 白名单及临时 SQLite；未修改生产数据库，临时服务均已停止。

- 离线：58 项通过（2.23 秒）；TypeScript check/build 通过。最后将模拟器 HTTP 启动改为复用正式入口后，相关 5 项再通过（1.12 秒）。
- 覆盖：OHLC 原值与重复追加日志、最新目标缺失/请求失败的重试轮次、历史断档接受、重连期间在途任务、8/2 限流和 3+2 并发、官方替换合成、2h/4h、DST/提前收盘、Quote 恢复、HTTP/WS 与模拟器跨周期。
- 浏览器：保留矛盾 OHLC 后图表可绘制，无 JavaScript 错误；2h/4h 切换正常。黄色 Ready 跨多次观察持续显示；官方 15m 延迟时已有 5m 合成显示。蓝色 Ready 的 3 秒隐藏已在较短延迟的前一次模拟验收中验证。
- 最终全名单 live：美东 2026-09-22 13:39:50 起运行 150 秒，45/45 ticker 的五个官方周期 full，pending=0、errors={}。收到 1,799 次 Quote 推送、737 条图表消息；WS 重连收到完整快照。
- 同轮请求：225 次 count=1000、44 次正常 count=2；跨过 13:40 收盘节点。没有额外补缺请求。1000 请求允许返回更短历史，最短存储窗口 158 根。OHLC JSONL 追加 466 条，均未造成错误状态或重试。
- 真实 Quote 重订阅：PAYS/HTFL/PLTU，首次各五周期共 15 次 count=1000；主动取消再订阅后，全部 15 项进入统一恢复，再请求 15 次 count=1000，恢复 full、无错误，随后收到新推送。此测试不等同于物理断网或操作系统休眠。

最终全名单证据：`/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/longbridge-check-4v431g4y/report.json`；同目录 `invalid_ohlc.jsonl` 可与 TradingView 手工比较。

重订阅证据：`/var/folders/92/4bfk_p7n05ld409p32hn7k_m0000gn/T/longbridge-recovery-80yla527/report.json`。

前一轮 live 曾检查返回窗口内连续性，导致 REPL 的三个分钟周期与 USDE Daily 因旧空档重试；这些周期的最新目标均存在。最终已删除历史连续性检查并重跑以上全名单验收。前一轮产物 `longbridge-check-b8zmpv5b` 仅供差异追溯，不代表最终行为。

本轮未重新完整操作所有既有布局/日联动手势；chart.ts 与 layout.ts 未改动，历史验收范围见下表。长时间运行、物理断网和系统休眠仍需另行观察。

## 历史证据摘要

以下规则属于旧版本，不能作为当前需求：严格 OHLC 拒绝、定点修复、history offset、readiness v2、历史连续性补齐均已删除。

| 日期 | 当时验证 | 范围与限制 |
| --- | --- | --- |
| 2026-09-20 | 52 项离线测试通过 | 旧 OHLC 拒绝/定点修复，不代表当前保留原值方案 |
| 2026-09-20 | 40 项离线测试、TypeScript 通过；45 ticker 完整模拟跨周期/交易日 | 浏览器验证三栏拖动、短历史 spacing、自由十字线、交易日联动；未连券商 |
| 2026-09-20 | 首版 34 项离线测试通过 | 初版双图/HTTP/WS；已被后续布局与状态语义取代 |
| 2026-09-18 19:31 UTC | 17 项测试、45 ticker 真实接口、3,060 次 Quote 推送 | 当时重订阅恢复及 5m closed 更新通过；258,795 根旧规则库审计；部分官方 OHLC 被拒绝，不能表述成全量 Ready |

旧实测产物曾保存于 runtime/full-universe-http.json、full-universe-report.json、recovery-smoke.json、invariant-audit.json；文件若仍存在，仅作历史数据，正式服务不消费这些报告。

移动触控、全天稳定运行和实际系统长时间休眠恢复仍未完整验收。模拟测试、短时 live 和历史记录分别标明，不相互替代。

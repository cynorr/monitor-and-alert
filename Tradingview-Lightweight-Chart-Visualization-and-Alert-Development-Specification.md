# Market Monitor — 图表与实时数据开发规格

更新：2026-09-20。状态：已确认需求。实现状态及运行方式见 README 和 docs/data/README.md。

## 1. 范围

- 左侧 Daily、中间可切换 5m / 15m / 30m / 1h、右侧股票列表；可拖动列宽，图表默认等宽，各含价格与成交量 pane。
- 使用本地 Lightweight Charts 5.2.0，保留版权与归属信息。
- 股票列表仅使用启动加载的 focus / wait，支持搜索、选择；不支持运行中编辑名单。
- Price Alert 的显示、交互、存储、计算和通知全部不在本版范围。
- Python 负责行情、日历、临时 candle、指标及缓存；TypeScript 负责 UI 和图表显示。
- 单进程、SQLite、本地浏览器，不引入额外数据库或消息中间件。

## 2. 连接和数据契约

Longbridge Quote 长连接 → Python data → 本地 WebSocket → UI。

- HTTP 提供历史与初始图表快照；WebSocket 推送行情、活跃 candle、官方 closed bar、指标及状态。
- 浏览器不直接连接 Longbridge，不写 authoritative bars。
- 切换 ticker / 周期提高对应任务优先级，不改变后端白名单行情订阅。
- 重连重新获取快照，以请求标识、连接代次和数据版本防止旧数据覆盖新图。
- UI 关闭不影响继续运行的后端缓存与调度。
- UTC Unix 秒用于存储与传输；交易规则、图表标签使用 America/New_York。
- regular 与 pre/post/overnight 分开；扩展时段只显示价格，不修改 regular candle。

## 3. 官方历史与调度

- SQLite 只保存官方 NoAdjust、regular-session、已收盘的五个周期。
- 每次后端冷启动重新拉各 ticker、各周期最近最多 1000 根，过滤未收盘 bar 后 UPSERT。
- 优先当前 ticker 的 5m 和 Daily，再加载其他 ticker 的 5m、Daily，后台补 15m / 30m / 1h。
- 切换到未加载周期时立即提高其优先级；Quote 和 BarScheduler 从启动时运行，不等待历史初始化结束。
- 所有行情 API 共享每秒最多 10 次、最多 5 个在途请求的预算，复用一个行情 context。
- 到期更新和连接恢复优先于后台历史；单 ticker 失败不阻断其他 ticker。
- 正常更新用 candlesticks(count=2)，闭合后 +2 秒请求，失败按 2 / 5 / 10 / 30 秒退避。
- 持续服务在重试耗尽后等待 30 秒继续补齐，不依赖下一根 bar 边界；一次性 reconcile 在有界重试后结束。
- 休眠或跨多个区间恢复时扩大到最近 1000 根，检查缺口；必要的超窗前缀使用 history API。
- 后端持续运行时 UI 重开复用缓存，检查并补缺，不重新启动完整冷启动。
- 非法官方 bar 不落盘；不补零、不合成 closed bars；质量问题显示 ticker warning。

## 4. 活跃 candle

### 当前 5m

- 后端内存维护，按 Quote 时间戳与交易日历分桶。
- 区间第一条有效 last_done 初始化 O/H/L/C，后续更新 high、low、close。
- 中途启动或缓存丢失时用第一条有效价格作为 open；不回补当前未收盘区间内部价格。
- 断线恢复同一区间继续更新，跨区间创建新 candle。
- 临时 candle 不落盘、不转成官方 closed bar；到边界后等待官方 bar 填入对应历史位置。
- 误差持续到下一个 5m 边界及官方数据到达时刻。

### 较大周期

当前 15m / 30m / 1h / Daily 由其区间内官方 closed 5m 与当前临时 5m 合并：首根 open、最大 high、最小 low、最新有效 regular last_done 作为 close。

- 每次官方 5m 到达修正相关活跃 candle。
- 自身收盘后，该历史位置只使用对应周期的官方 bar。
- 1h 从 09:30 起算，末段按实际收盘截短；处理假期、DST、提前收盘。
- 组合结果仅用于内存展示，不写 authoritative bars。

### 成交量

`当前区间 volume = 当日 regular Quote 累计 volume − 当日该区间开始前所有官方 closed 5m volume`

- 前缀完整且交易日、时段一致时才显示差值。
- 前缀未齐或上一根仍在等待时，活跃 volume 暂不显示，价格照常更新。
- 负差值或口径异常显示 warning，不伪造为零。
- Daily 活跃 volume 直接使用当日 regular Quote 累计量。

## 5. READY 与显示状态

- READY：ticker 的 Daily 和 5m 完成本轮同步，追到各自当前应有的最后一根 closed bar。
- FULL_READY：五个周期全部满足上述条件。
- 当前图表单独判断所选周期是否追上，不被其他未加载周期阻断。
- 各周期保存同步目标、最新闭合时间、缺口和验证时间；目标随当前时间前进。
- 不再用 300 日 / 12 日样本门槛决定图表 READY。
- 历史不足、缺 K 允许降级展示合法数据并显示 ticker warning；缺失数据不得宣称完整。

| UI 状态 | 行为 |
| --- | --- |
| 加载 | 首次补齐、未加载周期、恢复补齐 |
| 正常 | 不显示通知；READY / FULL_READY 保留为数据 API 状态 |
| 连接中断 | 连接失效至恢复 |
| ticker warning | 紧凑图标与英文悬停详情；不显示多行错误横条 |

- 正常运行后，官方 bar 从应闭合时刻起超过 15 秒仍未有效取得即警告；恢复后清除。
- 初始补旧历史使用加载状态，不逐根报告旧历史延迟。
- 后台持续检查连接、缺口与更新延迟。
- 不显示休市状态；显示完整历史及 pre/post price。
- 不设置独立指标状态，样本不足的均线直接不画。

## 6. 指标与缓存

- Python 统一计算，缓存在内存，不建立指标数据库。
- 官方 OHLCV、turnover 保存在现有 SQLite；临时 candle 和指标不落盘。
- 从完整加载窗口计算再裁剪；缩放不改变指标起点。

### EMA / SMA

- 两图都显示对应周期 close 的 EMA10、EMA20、SMA50。
- EMA 以加载序列首个 close 初始化，alpha=2/(N+1)，满 N 根显示。
- SMA 满 N 根显示。
- 包含活跃 candle；每条 Quote 从上一根 closed bar 的 EMA 基准计算预览，不能把 Quote 当成新 bar 递推。
- 官方 UPSERT 后使受影响缓存失效并重算。

### ADR20

仅 Daily，最近 20 个已完成交易日：

`ADR20 = mean((high - low) / low) × 100%`

### ADV$20（20 日均额）

仅 Daily，最近 20 个已完成交易日官方 turnover 的平均值。

- 缺失或非法 turnover 使用 `volume × (open + close) / 2`，提示估算。
- ADR / ADV$ 样本不足按窗口内有效样本计算，ticker 提示样本数；不使用更早交易日填补窗口缺失，不补零。
- 不复权口径，本版不实现公司行动调整。

## 7. 界面与交互

交互唯一维护入口：[docs/ui/chart-interactions.md](docs/ui/chart-interactions.md)。界面仅英文，核心是双图看盘与列表切换。

- 三栏可调宽度、无品牌顶栏或图表底栏，紧凑列表与胶囊控制。
- 无网格，teal/red candle 与成交量，EMA10 蓝 / EMA20 黄 / SMA50 红。
- Daily 约九个月初始窗口，短历史靠右且不拉宽 candle；实时刷新与调整列宽保持当前 candle 间距。
- 使用原生十字线、pane、滚动和缩放 API；按美东交易日联动两图。
- HTTP / WebSocket 请求代次、重连快照与后端缓存保持不变。

## 8. 验收

- 任意时刻启动，当前 ticker 优先，其他 ticker 在全局限额内并发推进。
- 初始化期间 Quote、到期更新不停止。
- 验证缺失 open、断线、跨桶、官方替换、较大周期修正及成交量前缀未齐。
- READY 随最新应闭合时间变化，15 秒延迟及数据问题可见。
- 重复 Quote 不造成 EMA 漂移，官方覆盖后指标重算。
- 快速切股/周期、刷新、重连不串数据、不反复重置视口。
- 默认测试离线，不读取真实凭证；离线与券商 live 证据分别记录。
- 独立模拟器提供一致 Quote 与五周期 closed bars，注入交易时钟，复用实际调度/验证；仅写临时库，不新增故障注入或回放框架。

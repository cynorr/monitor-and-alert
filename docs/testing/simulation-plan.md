# 盘中数据模拟器：已确认范围与实现

更新：2026-09-19。用户已明确大幅精简此前方案；此前的 SimBroker、业务时钟、历史生成、异常模拟和全链路验证方案全部取消，不作为后续待办。

## 当前目标

一个独立的盘中行情数据生成器，通过真实 WebSocket 长连接发送 Longbridge Quote JSON 格式的数据，仅供下游 UI / Alert 开发使用。

```text
simulator/server.py → WebSocket JSON Quote → 下游模拟显示 / Alert 模式
正式历史服务 → 真实历史数据 → 下游历史基线
```

模拟器不经过 DataService、Validator 或 READY，不导入正式 data 模块。正式数据服务保持原有校验和数据规则；用户要求的“跳过验证”仅适用于这个独立模拟数据源。

## 当前文件

| 文件 | 用途 |
| --- | --- |
| `simulator/server.py` | 白名单读取、随机行情、WebSocket 自动推送 |
| `simulator/start.command` | 一键创建独立环境、安装依赖并启动 |
| `simulator/requirements.txt` | 唯一依赖 websockets |
| `simulator/README.md` | 启动、消息格式及客户端接入示例 |

macOS 双击 start.command，或执行 `./simulator/start.command`。地址为 `ws://127.0.0.1:18766`，连接即收数据，无订阅指令，每个 symbol 每秒一条 JSON。首次启动需联网安装依赖，此后可离线使用。

## 数据口径

- 启动重读 workspace，仅发送 focus/wait；不监控文件变化。
- 随机起始价、上涨/下跌/震荡倾向、合理正数价格及非负递增成交量；各客户端共享市场状态。
- JSON 字段和类型参照 [官方 Quote 推送](https://open.longbridge.com/zh-CN/docs/quote/push/quote)。价格/成交额为字符串，时间为 UTC Unix 秒，session/status/tag 为整数 0。
- 每条消息提供全部字段。传输使用 JSON WebSocket，不是官方二进制协议，官方 SDK 不直接接入。
- 使用实际时间戳，持续标记 Intraday；不改 macOS 时间，不模拟日历、开收盘或跨日。进程启动到停止视作一次模拟盘中会话。
- 模拟价格不与真实历史价自动对齐。历史数据由已有真实服务另行提供；模拟器不负责混合或校准两种来源。

## 明确不实现

历史与 K 线接口、snapshot 请求接口、订阅协议、鉴权、READY、数据验证流水线、故障注入、断线重试框架、虚拟时钟、回放、场景引擎、数据库、真实 API 请求。

不复制过去复杂的测试方案，不为了边界情况继续加框架。开发验收仅检查一键启动和实际 WebSocket 连续推送的核心路径。

正式图表 UI 已实现，消费 Data API 的 HTTP/WebSocket；模拟器输入切换尚未接入该 UI。Price Alert 不在本版范围。不要宣称已有 Data API 自动切换或模拟 UI/Alert 全流程验收。

删除 `simulator/` 即移除模拟功能；正式生产依赖与代码没有 simulator 引用。

## 本次验收

2026-09-19，macOS / Python 3.13，使用一键脚本启动并通过真实本地 WebSocket 接收 180 条消息，覆盖当前全部 45 个 focus/wait symbol。确认 15 个 Quote 字段及类型、序号/时间/累计量递增，样本中有 24 个上涨、19 个下跌、2 个持平。测试后停止服务，可随时用同一脚本启动。

这是本地模拟数据推送验收，未调用 Longbridge，未进行尚未实现的 UI/Alert 全流程测试。正式 data Python 代码与项目依赖未修改。

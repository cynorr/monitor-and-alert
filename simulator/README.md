# 盘中 Quote 模拟器

只做一件事：通过 WebSocket 持续推送盘中随机行情，供 UI / Alert 开发使用。

## 一键启动

macOS 双击 **start.command**，或在项目根目录执行：

```bash
./simulator/start.command
```

首次启动自动创建本目录的 Python 虚拟环境并安装唯一依赖 `websockets`（需要 Python 3.11+ 和联网安装）。后续启动可离线运行。关闭窗口或按 Ctrl+C 停止。

连接 **ws://127.0.0.1:18766**，无需发送订阅消息：立即收到所有 ticker 的当前状态，之后每个 ticker 每秒一条 JSON 文本消息。所有客户端共享同一份行情。

```javascript
const feed = new WebSocket('ws://127.0.0.1:18766');
feed.onmessage = ({ data }) => {
  const quote = JSON.parse(data);
  console.log(quote.symbol, quote.last_done, quote.volume);
};
// 停止接收：feed.close();
```

## 数据

启动时读取根目录 `workspace.json`，仅选 `statuses` 为 `focus` / `wait` 的 ticker。随机分配起始价格和成交活跃度，轮流采用上涨、下跌、震荡倾向；价格在初始价 ±30% 内波动，成交量非负递增。

使用 [Longbridge Quote 推送的 JSON 字段及类型](https://open.longbridge.com/zh-CN/docs/quote/push/quote)：

```json
{
  "symbol": "PAYS.US",
  "sequence": 12,
  "last_done": "18.520",
  "open": "18.500",
  "high": "18.530",
  "low": "18.480",
  "timestamp": 1789738212,
  "volume": 3600,
  "turnover": "66672.000",
  "trade_status": 0,
  "trade_session": 0,
  "current_volume": 300,
  "current_turnover": "5556.000",
  "tag": 0
}
```

价格和成交额为字符串；时间戳是当前真实 UTC Unix 秒；成交量和状态为整数。`trade_session=0`、`trade_status=0`、`tag=0` 始终表示正常盘中实时数据。每条消息提供全部字段，没有外层 envelope。

`volume` 从本次进程启动开始累计，`current_volume` 为最近一个生成周期的增量；各客户端接入不会重置市场。固定随机种子方便观察，重启会重置模拟行情。初始价格独立随机生成，不与真实历史收盘价对齐。

无需更改 macOS 时间：休市也持续输出 Intraday 标记；不模拟交易日历或完整交易日，不做跨日重置。下游的**模拟显示/Alert 模式**应直接消费这些消息，不再经过正式数据服务的交易时段或 readiness 检查。

这是 JSON 业务数据格式一致的 WebSocket 数据源，不是 Longbridge 二进制协议服务器，官方 SDK 不直接连接它。未来 UI/Alert 需要接入该 WebSocket；当前仓库尚未实现这些消费者。

## 保持独立

没有历史数据、K 线接口、验证器、READY、异常场景、重试框架、数据库或虚拟时钟。不连接真实 API、不读取 token、不改动正式 data 逻辑。历史数据由正式服务按现有方式另行提供。

文件只有 `server.py`、`start.command`、`requirements.txt` 和本说明。删除整个 `simulator/` 即可移除，无需修改正式项目依赖或代码。

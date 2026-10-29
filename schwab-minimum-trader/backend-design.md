

# Schwab Local Trading Backend
## V1.2 后端设计与 API 规范

**状态：保留的交易网关设计文档；2026-10-27 统一风控值。当前 Market Monitor 集成入口见 [Schwab Trade MVP](../docs/schwab-trade.md)，代码维护于 `data_service/schwab_backend.py`，旧脚本为兼容入口。下文独立端口/SSE 部分为原项目运行方式。**  
**语言：Python 3.12+**  
**运行环境：macOS / Mac mini**  
**主程序：`schwab_backend.py`**  
**监听地址：`127.0.0.1:5678`**

---

# Part 1 — 架构与运行机制

## 1. 项目目标

构建一个运行在个人 Mac mini 上的 Schwab Trading Backend，统一提供：

- Schwab 账户、持仓及 Margin 查询。
- 当前订单查询及状态监控。
- 实时 Bid/Ask 行情。
- 当日 High/Low 查询及建议交易价格。
- 五种固定交易操作。
- 成交通知与本地事件推送。

系统面向个人 Swing Trading。

不涉及高频交易、多用户或公网部署。

### 1.1 设计原则

**简单优先**

只实现明确需要的功能，不为理论上的极端情况增加额外架构。

**Schwab 是唯一真实数据源**

账户、持仓、订单及成交状态以 Schwab 为准。

内存缓存不构成独立交易账本。

**交易操作原子化**

每个交易函数最多发起一次 Schwab 写请求。

不隐藏取消、替换或其他交易操作。

Schwab 原生 OTO 父子订单视为一次交易请求。

**最小参数暴露**

客户端不能指定资产类型、订单类型、交易时段或订单策略结构。

**人工确认**

Backend 只执行调用方明确提交的交易参数，不自动决定交易价格或数量。

**最小必要校验**

只保留数量、价格关系、交易金额及风险边界检查。

**正常运行可恢复**

Mac mini 可以锁屏、睡眠、关机或断网。

运行环境恢复后，Backend 自动尝试恢复认证、REST 查询和 Streaming 连接。

不干预设备的电源管理。

---

## 2. 功能范围

### 2.1 支持

| 分类 | 功能 |
|---|---|
| Authentication | Schwab OAuth |
| Account | 账户资金、Margin、Buying Power |
| Positions | 当前股票及 ETF 持仓 |
| Orders | 当前订单及父子订单 |
| Quotes | 实时 Bid/Ask |
| Price Reference | 当日 High/Low、建议突破及止损价 |
| Market Trading | 市价买入、市价卖出 |
| Breakout Trading | Buy Stop DAY → Sell Stop GTC |
| Order Management | 修改止损、取消订单 |
| Streaming | 订单活动、实时行情 |
| Notification | 成交声音 |
| Local API | REST + SSE |

### 2.2 不支持

- 期权相关功能。
- Limit、Stop Limit、Trailing Stop。
- 卖空交易功能。
- Movers、股票扫描器。
- 自动策略下单。
- 本地历史行情数据库。
- 历史交易绩效分析。
- 本地 Margin 计算模型。
- 多账户切换。
- 公网访问及远程用户。
- 自动组合撤单、改单、下单。
- 自动重试交易写请求。
- 复杂交易状态机。
- 复杂网络安全系统。
- 专门针对低价股的交易规则。
- 额外的突破价格偏离度限制。
- Mac mini 防休眠或唤醒控制。

---

## 3. 技术架构

### 3.1 技术栈

| 组件 | 技术 |
|---|---|
| Backend | FastAPI |
| HTTP | httpx |
| WebSocket | websockets |
| 本地推送 | SSE |
| 数据模型 | Pydantic |
| 金额计算 | Decimal |
| 凭据存储 | macOS Keychain |
| Keychain 接口 | keyring |
| Runtime Storage | RAM |
| 常驻服务 | launchd LaunchAgent |

不使用专门的 Schwab Python SDK。

使用通用 HTTP、WebSocket 和 JSON 库实现 Schwab 协议。

### 3.2 整体结构

```text
                  Charles Schwab
                        |
               +--------+--------+
               |                 |
             REST            WebSocket
               |                 |
               |          ACCT_ACTIVITY
               |          LEVELONE_EQUITIES
               |                 |
               +--------+--------+
                        |
                        v
             schwab_backend.py
             ─────────────────
             OAuth + Keychain
             REST Client
             Streaming Client
             Runtime Cache
             Trading Gateway
             SSE Broadcaster
             Sound Notification
                        |
                        v
               127.0.0.1:5678
                        |
                 REST API + SSE
                        |
               +--------+--------+
               |                 |
          Local Client A    Local Client B
```

只有 Backend 连接 Schwab。

客户端不能接触 Schwab Token。

### 3.3 本地端口

固定：

```text
Host: 127.0.0.1
Port: 5678
```

API Base URL：

```text
http://127.0.0.1:5678/api/v1
```

要求：

- 单进程。
- 单 Uvicorn Worker。
- 不监听 `0.0.0.0`。
- 不开放公网端口。
- 不部署反向代理。
- 不需要本地 HTTPS 业务服务器。

---

## 4. OAuth 与 Keychain

### 4.1 Token 存储

使用 Keychain 保存：

```text
client_secret
oauth_tokens  # 单条 JSON，包含 access_token、refresh_token、expiration
```

`CLIENT_ID`、`CALLBACK_URL`、`ACCOUNT_HASH`、风控额度和 `ALLOWED_ORIGINS` 直接定义在主程序顶部，不使用外部配置文件。

Token 不写入源码、JSON 文件或日志。

### 4.2 Token 生命周期

Access Token 的有效期以 Schwab 返回的 `expires_in` 为准。

正常情况下约为 30 分钟。

Refresh Token 通常约 7 天需要重新授权，实际以 Schwab 的认证结果为准。

### 4.3 并发刷新

所有 REST 请求及 WebSocket 登录共用同一个 Token Manager。

Token Manager 内部使用：

```python
token_refresh_lock = asyncio.Lock()
```

每次需要认证时：

1. 检查当前 Token 是否即将过期。
2. 如果有效，直接使用。
3. 如果需要刷新，获取异步锁。
4. 获得锁后再次检查有效期。
5. 仅在仍需刷新时请求新 Token。
6. 将新凭据写入 Keychain。
7. 释放锁。

建议刷新提前量：

```python
TOKEN_REFRESH_MARGIN_SECONDS = 60
```

这个数值仅用于提前刷新，不代表 Token 实际有效期。

其他请求等待同一次刷新完成。

OAuth 正常刷新由 Token Manager 统一处理，避免 REST 和 WebSocket 同时刷新。

### 4.4 手动重新授权

CLI：

```bash
python schwab_backend.py auth
```

流程：

1. 生成 Schwab Authorization URL。
2. 用户通过浏览器完成授权。
3. 复制完整 Callback URL。
4. 粘贴到 CLI。
5. CLI 校验 OAuth `state` 并提取 Authorization Code。
6. 请求新 Token。
7. 保存至 Keychain。

Callback URL 使用 Schwab Developer Portal 中注册的 HTTPS 地址。

例如：

```text
https://127.0.0.1
```

不要求本机实际启动 HTTPS 服务监听该地址。

### 4.5 重新授权后自动恢复

当 Backend 进入 `AUTH_REQUIRED`：

- 暂停需要 Schwab 认证的操作。
- 保持本地 REST Server 运行。
- 使用现有后台定时任务，每 5 秒检查一次 Keychain。
- 检测到有效的新 Token 后，恢复初始化流程。
- 重新连接 Schwab Streaming。

不需要人工重启 Backend。

如果 Keychain 暂时不可访问，继续保持 `AUTH_REQUIRED`，等待下一轮检查。

---

## 5. 启动、睡眠与断网恢复

### 5.1 启动行为

**本地 API Server 不依赖 Schwab 网络初始化成功才能启动。**

流程：

```text
Start Backend
      |
      v
Start FastAPI
      |
      v
Load Keychain Credentials
      |
      v
Initialize Schwab Client
      |
      v
Fetch Account / Orders
      |
      v
Connect WebSocket
      |
      v
Ready
```

如果 Schwab 初始化失败：

- FastAPI 继续运行。
- `/health` 显示当前错误状态。
- 后台继续尝试恢复。

### 5.2 初始化失败重试

适用：

- 开机时尚未联网。
- DNS 暂时不可用。
- Schwab 服务暂时无法连接。
- 网络请求超时。

规则：

```python
INIT_RETRY_SECONDS = 5
```

每 5 秒重新尝试初始化。

初始化成功后进入正常运行状态。

这项重试只涉及认证和读取，不涉及交易写请求。

### 5.3 睡眠与唤醒

Backend 不执行：

```text
caffeinate
pmset
wakeonlan
```

不控制 Mac mini 电源状态。

运行行为：

| 系统状态 | Backend 行为 |
|---|---|
| 正常运行 | REST + Streaming |
| 锁屏但系统未睡眠 | 继续运行 |
| 睡眠 | 网络及定时任务可能暂停 |
| 唤醒 | 尝试恢复网络、认证和 Streaming |
| 断网 | REST 失败，Streaming 断开或超时 |
| 网络恢复 | 自动重新连接和同步 |
| 关机 | Backend 不运行 |
| 重新开机并登录用户会话 | LaunchAgent 启动 Backend |

LaunchAgent 不要求 root 权限。

### 5.4 WebSocket 假死检测

WebSocket 启用 Ping/Pong：

```python
ping_interval = 20
ping_timeout = 20
```

连接失败或心跳超时：

1. 结束旧连接。
2. 等待自动重连。
3. 检查 OAuth Token。
4. 重新执行 `ADMIN LOGIN`。
5. 恢复订阅。
6. REST 同步 Account 和 Orders。

使用 `websockets` 自带的重连和退避能力，不自行开发网络检测系统。

这些参数及重连方式由 `websockets` 官方文档支持。[websockets](https://websockets.readthedocs.io/en/latest/reference/asyncio/client.html?utm_source=chatgpt.com)

### 5.5 恢复边界

睡眠或关机期间：

- 不接收实时事件。
- 不播放成交声音。
- 不执行 REST 轮询。
- 不保存漏掉的 Streaming 消息。

恢复后：

- 重新获取当前账户与订单快照。
- 不补播离线期间的历史成交声音。
- 不自动重新发送任何交易指令。

Schwab 已接受的订单继续由 Schwab 管理。

---

## 6. Runtime State

全部业务数据保存于内存。

```python
state = {
    "account": None,
    "positions": [],
    "orders": {},

    "quotes": {},
    "subscribed_symbols": set(),

    "notified_fills": set(),

    "stream_connected": False,
    "auth_status": "unknown",

    "account_updated_at": None,
    "orders_updated_at": None,
}
```

不使用 SQLite 或 runtime JSON。

重启后重新从 Schwab 获取数据。

### 6.1 REST 轮询

| 数据 | 频率 |
|---|---|
| Account + Positions | 5 秒 |
| Orders | 5 秒 |
| Quotes | 按需 |

Account 与 Positions 共用：

```http
GET /accounts/{accountHash}?fields=positions
```

Orders：

```http
GET /accounts/{accountHash}/orders
```

订单查询传入：

```text
fromEnteredTime = 当前时间 - 59 天
toEnteredTime = 当前时间
```

不添加 `status=WORKING` 过滤。

正常基础请求量约：

```text
Account: 12/min
Orders:  12/min

Total:   24/min
```

### 6.2 数据更新

每次 REST 查询成功后更新对应的完整快照。

失败时：

- 保留最后成功的数据。
- 保留其更新时间。
- 更新 Health 状态。

同一类刷新任务不能并发重叠。

收到订单 Streaming 事件后，额外触发一次 REST 刷新。

---

## 7. Schwab Streaming

### 7.1 连接

通过：

```http
GET /trader/v1/userPreference
```

获取 Streaming 参数。

Backend 建立一条 WebSocket。

订阅：

```text
ACCT_ACTIVITY
LEVELONE_EQUITIES
```

### 7.2 ACCT_ACTIVITY

订阅参数：

```text
Key: Account Activity
Fields: 0,1,2,3
```

处理：

- 订单活动事件。
- 完全成交事件。
- 触发 Account / Orders 刷新。

完全成交：

```text
OrderFillCompleted
```

收到新的完全成交事件：

1. 内存去重。
2. 广播 `order_filled`。
3. 异步播放本机提示音。
4. 触发 REST 刷新。

其他订单活动事件触发订单快照更新。

### 7.3 LEVELONE_EQUITIES

**只订阅三个字段：**

| Field | 内容 |
|---|---|
| `0` | Symbol |
| `1` | Bid Price |
| `2` | Ask Price |

不订阅 Last、High、Low、Volume 等其他 Streaming 字段。

公开的 Schwab Streaming 字段定义支持按字段订阅。[GitHub](https://github.com/alexgolec/schwab-py/blob/main/schwab/streaming.py?utm_source=chatgpt.com)

### 7.4 Symbol 订阅

V1 采用按需订阅。

首次调用：

```http
GET /api/v1/quotes/NVDA
```

Backend：

1. REST 获取 Quote。
2. 将 NVDA 加入 `subscribed_symbols`。
3. 如果 Streaming 已连接，发送对应订阅。
4. 后续接收 NVDA Bid/Ask 更新。

已订阅的 Symbol 不重复添加。

不同 Symbol 使用 Streaming `ADD` 增加订阅。

首次建立订阅集合时使用 `SUBS`。

重连后使用 `SUBS` 恢复内存中的 Symbol 集合。

V1 不实现自动退订。

### 7.5 实时行情内存

Streaming 只维护：

```python
{
    "symbol": "NVDA",
    "bid": Decimal("140.20"),
    "ask": Decimal("140.22"),
    "updated_at": "..."
}
```

Bid 和 Ask 独立更新。

例如 Schwab 只推送 Bid 时，不清空 Ask。

### 7.6 Quote REST 与 Streaming 的关系

| 数据 | 来源 |
|---|---|
| 实时 Bid | Streaming |
| 实时 Ask | Streaming |
| Day High | REST |
| Day Low | REST |
| 建议 Buy Stop | REST High + 固定偏移 |
| 建议 Sell Stop | REST Low |

REST 用于初始化和手动刷新。

Streaming 负责持续更新 Bid/Ask。

当 Streaming 正常时，REST 不覆盖已经建立的 Streaming Bid/Ask 缓存。

当 Streaming 不可用时，REST 可以更新 Bid/Ask。

不做复杂的逐笔时间戳排序。

### 7.7 手动刷新

```http
GET /api/v1/quotes/NVDA?refresh=true
```

必须实际请求 Schwab REST Quote。

刷新后更新：

- Day High。
- Day Low。
- 建议 Buy Stop。
- 建议 Sell Stop。
- REST Bid/Ask 备用数据。

成功响应中的 Bid/Ask 优先取当前有效的 Streaming 缓存；未取得 Streaming 报价时使用本次 REST 结果。

请求失败时返回错误，不伪装成刷新成功。

### 7.8 建议价格

不建立 `/price-guide` 接口。

在 Quotes API 中返回：

```python
suggested_buy_stop = day_high + BREAKOUT_OFFSET
suggested_sell_stop = day_low
```

默认：

```python
BREAKOUT_OFFSET = Decimal("0.01")
```

High/Low 未建立时，建议价格返回 `null`。

建议价格不会自动写入交易订单。

Backend 始终使用客户端最终提交的价格。

---

# Part 2 — 交易网关与安全规则

## 8. 固定交易函数

V1 仅提供五个函数：

```python
def buy_market(
    symbol: str,
    qty: int
) -> OrderResult:
    ...


def sell_market(
    symbol: str,
    qty: int
) -> OrderResult:
    ...


def buy_breakout(
    symbol: str,
    qty: int,
    buy_stop: Decimal,
    sell_stop: Decimal
) -> OrderResult:
    ...


def replace_stop(
    order_id: int,
    new_stop: Decimal
) -> OrderResult:
    ...


def cancel_order(
    order_id: int
) -> OrderResult:
    ...
```

价格使用 Decimal。

数量使用严格整数。

不提供通用 `place_order()`。

---

## 9. 固定订单参数

```python
ASSET_TYPE = "EQUITY"
SESSION = "NORMAL"
```

| 操作 | 类型 | Duration |
|---|---|---|
| Buy Market | MARKET | DAY |
| Sell Market | MARKET | DAY |
| Breakout Parent | BUY STOP | DAY |
| Breakout Child | SELL STOP | GOOD_TILL_CANCEL |
| Replace Stop | SELL STOP | 保留原值 |

所有订单均为 `NORMAL` Session。

不允许客户端修改上述参数。

---

## 10. 交易风险边界

### 10.1 配置

```python
MAX_ORDER_AMOUNT_USD = Decimal("45000")  # 仅限制买入
MAX_LOSS_PER_TRADE_USD = Decimal("2000")
MAX_STOP_LOSS_RATIO = Decimal("0.15")

BREAKOUT_OFFSET = Decimal("0.01")
```

不设置：

```text
MIN_STOCK_PRICE
MAX_STOCK_PRICE
MAX_BREAKOUT_OFFSET_RATIO
```

不增加低价股特殊限制，也不限制突破价相对现价的最大偏离度。

### 10.2 通用校验

检查：

- Symbol 有效。
- 交易资产为股票或 ETF。
- 数量为正整数。
- 价格为有效的有限正数。
- 买入单笔金额不超过配置上限；市价卖出和修改止损不受该上限限制。

不使用 Python `assert` 执行交易边界。

### 10.3 Breakout 校验

必须满足：

```python
0 < sell_stop < buy_stop
```

以及：

```python
(buy_stop - sell_stop) / buy_stop <= MAX_STOP_LOSS_RATIO
```

金额：

```python
qty * buy_stop <= MAX_ORDER_AMOUNT_USD
```

估算价差风险：

```python
qty * (buy_stop - sell_stop) <= MAX_LOSS_PER_TRADE_USD
```

另外检查：

```text
Buy Stop > 当前 Ask
Sell Stop < 当前 Bid
```

**不增加行情更新时间阈值。**

提交前，Backend 执行一次 REST Quote 请求，用于取得当次校验所需的 Bid/Ask。

若 Schwab 未返回有效报价，则拒绝提交。

该请求不会修改用户已确认的 Stop 价格。

价格精度及 Tick Size 的最终合法性由 Schwab 订单接口校验；Backend 不引入针对 $1 价格的特殊规则。

### 10.4 Market Buy

输入：

```text
symbol
qty
```

Backend：

- 获取一次 REST Quote。
- 使用 Ask 估算买入名义金额。
- 校验金额上限。
- 提交 MARKET BUY。

不自动创建止损单。

### 10.5 Market Sell

输入：

```text
symbol
qty
```

Backend：

- 查询当前持仓。
- 确认卖出数量不超过持有的多头数量。
- 提交 MARKET SELL。

对于已有 GTC Sell Stop：

- 不自动取消。
- 不自动修改。
- 不自动合并操作。
- 不假定 Schwab 一定拒绝重复卖出。

现有活动卖单通过 Orders API 提供，供调用方在人工确认时查看。

### 10.6 不增加自动复合操作

例如：

```text
Cancel Stop → Market Sell
```

必须是两次独立操作。

`replace_stop()` 同样不能在 PUT 失败后，自动执行 DELETE + POST。

---

## 11. Breakout Order

Schwab 原生 TRIGGER：

```text
Parent
  BUY STOP
  DAY
  NORMAL
       |
       v
Child
  SELL STOP
  GOOD_TILL_CANCEL
  NORMAL
```

使用一次 Schwab POST 请求提交完整父子结构。

父子股数相同。

不由 Backend 在父单成交后额外创建止损单。

部分成交时的实际子单行为以 Schwab 返回的订单状态为准。

---

## 12. Replace Stop

允许目标：

- 普通已激活 Sell Stop。
- 父 Buy Order 已成交后激活的 Sell Stop 子单。
- Schwab 当前订单状态允许替换。

当前接入也允许 `PENDING_ACTIVATION` 的普通 `NORMAL` Sell Stop：可在盘前、盘后或夜盘申请修改等待常规时段激活的止损价格，该状态不以 `editable=false` 作为本地拒绝条件。`AWAITING_PARENT_ORDER` 仍不允许；其他支持状态仍要求 `editable=true`。保持原有效期、数量、标准触发方式和一次 PUT，不改变执行 Session，也不改用 Cancel + Place；实际接受或拒绝由 Schwab 响应决定。

不修改：

- `AWAITING_PARENT_ORDER` 的子单。
- 尚未独立激活的子单。
- 已成交、取消或替换完成的订单。

执行：

1. GET 原订单。
2. 校验类型和状态。
3. 仅修改 Stop Price。
4. PUT Replace 一次。
5. 提取新 Order ID。
6. 触发后台 REST 刷新。
7. 立即返回 `verified: false`，订单快照由后台查询更新。

数量优先读取订单腿部，缺失时回退至顶层。确认是有限正整数后转为整数，仅放入请求腿部的 `quantity`；非整股数量不截断。缺少数量或原有效期时返回明确的 `ORDER_CONFLICT`，不猜测参数。

普通 STOP 仅用 session、duration、orderType、orderStrategyType、stopPrice、orderLegCollection 重建请求，不回填或校验路由、复合策略和 positionEffect 等状态字段；价格保持精确十进制字符串。显式税批次（包括 FIFO）和非空特殊指令继续保留。数量必须以股数计；仅支持固定价格、标准触发的 STOP，自定义触发依据、联动或激活条件返回 ORDER_CONFLICT，避免改价时重置触发方式。替换请求使用默认路由，不保留手动指定的执行路由。

不手动执行 Cancel + Place。

---

## 13. Cancel Order

只接收：

```text
order_id
```

使用 Schwab 原生：

```http
DELETE /accounts/{accountHash}/orders/{orderId}
```

只对指定目标发起取消请求。

OTO 父子单的联动取消行为由 Schwab 自身执行。

Backend 不额外取消其他订单。

---

## 14. Schwab 交易响应

### 14.1 Place

```http
POST /orders
```

公开 OpenAPI 定义的成功响应：

```http
201 Created
Location: .../orders/{orderId}
```

Body 为空。

从 `Location` 提取 Order ID。

### 14.2 Replace

```http
PUT /orders/{orderId}
```

成功：

```http
201 Created
Location: .../orders/{newOrderId}
```

更新本地引用。

### 14.3 Cancel

```http
DELETE /orders/{orderId}
```

成功：

```http
200 OK
```

Body 为空。

以上响应方式与公开 Trader OpenAPI 定义一致。[GitHub](https://github.com/Patch-Code-Prosperity/Schwab-API-Sandbox/blob/main/account_orders_openapi.yaml?utm_source=chatgpt.com)

成功接收写请求后，统一返回 `verified: false`，由后台 REST 查询同步当前订单状态。

---

## 15. 写请求错误与并发

### 15.1 禁止自动 Retry

以下操作不自动重试：

```text
POST Place
PUT Replace
DELETE Cancel
```

网络超时且无法判断结果时：

```text
ORDER_RESULT_UNKNOWN
```

不自动重新发送请求。

### 15.2 防重复

采用进程内轻量锁：

- 同一次操作不能同时提交两次。
- 同一订单不能同时 Replace 和 Cancel。
- 操作结果未知时，要求人工核对；请求结束即释放锁，用户核对后可明确提交新请求，无需重启。

不增加数据库或持久化订单状态机。

### 15.3 本地访问控制

- 只监听 `127.0.0.1`。
- 验证本地 Host。
- 写请求检查允许的浏览器 Origin。
- POST/PUT 接受 JSON。
- 拒绝未定义交易字段。
- 不开启通配符 CORS。
- 不返回 OAuth Token。

允许的 Origin 在主程序顶部 `ALLOWED_ORIGINS` 常量中固定。

此处的访问控制用于防止普通网页误调用，不设计对抗已控制本机的恶意进程。

---

# Part 3 — REST 与 SSE 接口契约

## 16. 通用规范

Base URL：

```text
http://127.0.0.1:5678/api/v1
```

JSON 命名：

```text
snake_case
```

### 16.1 数据类型

| 数据 | 类型 |
|---|---|
| Symbol | string |
| 下单数量 `qty` | integer |
| 持仓数量 `quantity` | decimal string |
| 订单数量 `quantity` | decimal string |
| 已成交数量 `filled_quantity` | decimal string |
| Price / Money | decimal string |
| Order ID | string |
| Timestamp | ISO 8601 string |
| Optional | null |

下单数量必须为正整数。

查询数量使用十进制字符串，兼容 Schwab 返回的非整数持仓数量。

### 16.2 统一错误

| HTTP | Code | 说明 |
|---|---|---|
| 400 | `BAD_REQUEST` | 请求不合法 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 409 | `ORDER_CONFLICT` | 当前订单操作冲突 |
| 422 | `VALIDATION_FAILED` | 参数类型或格式错误 |
| 422 | `RISK_LIMIT_EXCEEDED` | 超过交易边界 |
| 502 | `SCHWAB_REJECTED` | Schwab 明确拒绝 |
| 503 | `AUTH_REQUIRED` | 需要重新授权 |
| 503 | `SCHWAB_UNAVAILABLE` | Schwab 服务不可用 |
| 504 | `ORDER_RESULT_UNKNOWN` | 写操作结果未知 |

统一错误结构：

```json
{
  "result": "error",
  "error": {
    "code": "RISK_LIMIT_EXCEEDED",
    "message": "单笔交易金额超过限制",
    "details": null
  }
}
```

未知交易结果：

```json
{
  "result": "unknown",
  "error": {
    "code": "ORDER_RESULT_UNKNOWN",
    "message": "订单结果未确认，请人工核对",
    "details": null
  }
}
```

调用方不得对 `ORDER_RESULT_UNKNOWN` 自动重新提交。

---

## 17. 查询 API

### 17.1 Account

```http
GET /api/v1/account
```

Response：

```json
{
  "liquidation_value": "125000.00",
  "long_market_value": "98000.00",
  "cash_balance": "12000.00",
  "available_funds": "25000.25",
  "buying_power": "54000.00",
  "intraday_buying_power": "120000.50",
  "stock_buying_power": "65000.50",
  "day_trading_buying_power": "0.00",
  "margin_balance": "15000.00",
  "maintenance_requirement": "24500.00",
  "updated_at": "2026-10-15T14:30:00Z"
}
```

示例数值不代表真实账户。

所有余额使用券商原值，不推算杠杆、贷款或风险余量。新增映射：

| 输出字段 | Schwab 原始来源 |
| --- | --- |
| `available_funds` | `currentBalances.availableFunds` |
| `intraday_buying_power` | `currentBalances.intradayBuyingPowerAmount` |
| `stock_buying_power` | `projectedBalances.stockBuyingPower` |

`day_trading_buying_power` 继续返回旧字段 `currentBalances.dayTradingBuyingPower`，不替代新的 Intraday BP。`cash_balance` 和 `margin_balance` 独立返回，不合成为 Cash & Sweep。前端保留负号、使用中性显示，可悬停查看字段来源。

缺失字段返回 `null`。

### 17.2 Positions

```http
GET /api/v1/positions
```

Response：

```json
{
  "positions": [
    {
      "symbol": "NVDA",
      "asset_type": "EQUITY",
      "quantity": "100",
      "average_price": "135.00",
      "market_value": "14100.00",
      "day_profit_loss": "210.00",
      "open_profit_loss": "600.00",
      "day_profit_loss_percent": "1.51"
    }
  ],
  "updated_at": "2026-10-15T14:30:00Z"
}
```

`open_profit_loss` 直接映射 `positions[].longOpenProfitLoss`；`day_profit_loss` 与 `day_profit_loss_percent` 保留当日口径。前端使用平均价 × 股数为分母计算持仓浮盈百分比，不拼接历史买单。缺失字段仍为 null，REST/SSE 共用相同映射。

### 17.3 Orders

```http
GET /api/v1/orders
GET /api/v1/orders?symbol=NVDA
GET /api/v1/orders?refresh=true
```

Response：

```json
{
  "orders": [
    {
      "order_id": "123456789",
      "parent_order_id": null,
      "symbol": "NVDA",
      "instruction": "BUY",
      "order_type": "STOP",
      "strategy_type": "TRIGGER",
      "quantity": "100",
      "filled_quantity": "0",
      "stop_price": "140.50",
      "duration": "DAY",
      "session": "NORMAL",
      "status": "AWAITING_STOP_CONDITION",
      "cancelable": true,
      "entered_at": "2026-10-15T14:20:00Z",
      "executions": [],
      "child_orders": [
        {
          "order_id": null,
          "parent_order_id": "123456789",
          "symbol": "NVDA",
          "instruction": "SELL",
          "order_type": "STOP",
          "strategy_type": "SINGLE",
          "quantity": "100",
          "filled_quantity": "0",
          "stop_price": "136.20",
          "duration": "GOOD_TILL_CANCEL",
          "session": "NORMAL",
          "status": "AWAITING_PARENT_ORDER",
          "cancelable": false,
          "entered_at": null,
          "executions": [],
          "child_orders": []
        }
      ]
    }
  ],
  "updated_at": "2026-10-15T14:30:00Z"
}
```

`order_id`、`parent_order_id`、`entered_at` 允许 `null`。

`cancelable` 在没有可靠返回值时允许 `null`。

保留 Schwab 原始订单状态及父子关系。

#### 逐笔成交与 Sold Today

每个订单包含 `executions` 数组，从股票订单的 `orderActivityCollection` 中提取 `activityType=EXECUTION`、`executionType=FILL` 的全部 `executionLegs`。未成交时返回 `[]`，父子订单分别保留各自的成交明细。

```json
{
  "activity_id": "11",
  "leg_id": "1",
  "quantity": "30.0",
  "price": "140.25",
  "time": "2026-10-16T13:56:38Z"
}
```

`activity_id` 和 `leg_id` 来自券商并转为字符串，所属订单 ID 为外层 `order_id`。数量、价格为十进制字符串，时间转为 UTC ISO 8601。保留数量、价格和时间相同的独立成交，不以该三元组去重；活动 ID 和腿 ID 不被当作全局唯一成交 ID。

前端 Sold Today 使用同一订单快照：递归包含子单，以订单 ID 去除重复出现的订单，只选 `SELL` 且 `FILLED` 的股票订单。最后一笔实际成交时间落在 `America/New_York` 当天时，整笔订单计入当天；数量取 `filled_quantity`，成交总额为逐笔数量乘价格之和，均价为总额除股数。按股票汇总，展开保留逐笔明细；总额未扣费用，不计算已实现盈亏。未提供成交明细时不以委托时间、报价或止损价推测成交。

范围按用户交易习惯限定：订单几秒内全部成交，不处理跨日分批成交或部分成交后撤单；止损单最多两周更新一次，位于现有 59 天查询窗口内。卖出部分持仓后剩余持仓仍在 Holdings，当天买回也不隐藏 Sold Today。

不新增 `/api/v1/closed-trades` 或其他 Endpoint，不调用 transactions，不增加轮询、数据库或对账状态；后端仅规范化成交明细，前端从首次 GET 和后续 SSE 完整快照恢复当日记录。`order_filled` 仅用于短暂提示，不承担历史恢复。

### 17.4 单个订单

```http
GET /api/v1/orders/{id}
```

返回对象与 Orders 数组中的单项结构一致。

### 17.5 Quotes

```http
GET /api/v1/quotes/{symbol}
GET /api/v1/quotes/{symbol}?refresh=true
```

Response：

```json
{
  "symbol": "NVDA",
  "bid": "140.20",
  "ask": "140.22",
  "day_high": "140.50",
  "day_low": "136.20",
  "last_price": "140.21",
  "close_price": "138.00",
  "suggested_buy_stop": "140.51",
  "suggested_sell_stop": "136.20",
  "updated_at": "2026-10-15T14:30:01Z"
}
```

报价缺失时，对应字段返回 `null`。

`last_price`、`close_price` 分别映射 quote.lastPrice、quote.closePrice；原有报价请求参数保持 `fields=quote`，不增加数据组或请求次数。前端仅按纽约工作日 09:30–16:00 与正值 High/Low 选择默认价，其他时间或缺失时依次参考 Ask/Bid、Last、Close，并标记来源；原建议价格字段语义不变。

Price Guide 不提供独立 Endpoint。

`refresh=true` 必须触发 Schwab REST 查询。

---

## 18. 交易 API

### 18.1 Market Buy

```http
POST /api/v1/orders/market-buy
```

Request：

```json
{
  "symbol": "NVDA",
  "qty": 100
}
```

### 18.2 Market Sell

```http
POST /api/v1/orders/market-sell
```

Request：

```json
{
  "symbol": "NVDA",
  "qty": 100
}
```

### 18.3 Breakout Buy

```http
POST /api/v1/orders/breakout-buy
```

Request：

```json
{
  "symbol": "NVDA",
  "qty": 100,
  "buy_stop": "140.50",
  "sell_stop": "136.20"
}
```

### 18.4 Replace Stop

```http
PUT /api/v1/orders/{id}/stop
```

Request：

```json
{
  "new_stop": "138.00"
}
```

### 18.5 Cancel Order

```http
DELETE /api/v1/orders/{id}
```

无须 Request Body；如携带 Body，忽略其内容，只取消路径指定的 Order ID。

### 18.6 成功响应

创建订单：

```json
{
  "result": "accepted",
  "order_id": "123456789",
  "verified": false
}
```

替换订单：

```json
{
  "result": "accepted",
  "old_order_id": "123456789",
  "new_order_id": "123456790",
  "verified": false
}
```

取消订单：

```json
{
  "result": "accepted",
  "order_id": "123456789",
  "verified": false
}
```

创建、替换、取消的成功响应统一使用 `verified=false`，表示本次响应尚未通过后续查询确认最终订单状态。

Market Buy、Market Sell 和 Breakout 创建成功返回 HTTP 201。

Replace 成功返回 HTTP 200 或 201，由本地接口统一采用 200，并返回上述 JSON。

Cancel 请求成功返回本地 HTTP 202。

---

## 19. SSE 事件

Endpoint：

```http
GET /api/v1/events
```

Content-Type：

```text
text/event-stream
```

使用四种事件：

| Event | 用途 |
|---|---|
| `snapshot_updated` | 账户、持仓、订单快照 |
| `order_filled` | 完全成交 |
| `quote_updated` | 实时 Bid/Ask |
| `stream_status` | Streaming 状态 |

### 19.1 snapshot_updated

```text
event: snapshot_updated
data: {"account":{...},"positions":[...],"orders":[...],"updated_at":"2026-10-15T14:30:00Z"}
```

数据结构与 REST 查询保持一致。

新客户端连接时，立即发送当前可用快照。

### 19.2 order_filled

```text
event: order_filled
data: {"order_id":"123456789","symbol":"NVDA","occurred_at":"2026-10-15T14:30:01Z"}
```

由 Schwab 成交事件触发。

### 19.3 quote_updated

只发送 Bid/Ask：

```text
event: quote_updated
data: {"symbol":"NVDA","bid":"140.20","ask":"140.22","updated_at":"2026-10-15T14:30:01Z"}
```

不包含 High/Low、建议价格或其他行情指标。

### 19.4 stream_status

```text
event: stream_status
data: {"connected":false,"timestamp":"2026-10-15T14:30:00Z"}
```

重连成功后发送：

```text
event: stream_status
data: {"connected":true,"timestamp":"2026-10-15T14:30:10Z"}
```

### 19.5 成交声音

Backend 统一播放声音。

使用：

```python
async def play_fill_sound() -> None:
    proc = await asyncio.create_subprocess_exec(
        "afplay",
        "/System/Library/Sounds/Glass.aiff"
    )
    await proc.wait()
```

作为独立异步任务执行。

不阻塞 Schwab WebSocket 接收循环。

当前进程内同一完全成交事件最多播放一次。

---

## 20. Health

```http
GET /api/v1/health
```

Response：

```json
{
  "service": "running",
  "auth_status": "valid",
  "schwab_rest": "connected",
  "schwab_stream": "connected",
  "account_initialized": true,
  "orders_initialized": true,
  "last_account_update": "2026-10-15T14:30:00Z",
  "last_orders_update": "2026-10-15T14:30:00Z"
}
```

状态允许：

```text
auth_status:
  valid
  refreshing
  auth_required

schwab_rest:
  connected
  unavailable

schwab_stream:
  connected
  connecting
  disconnected
```

Streaming 断线不意味着整个 Backend 不可用。

---

## 21. 完整 Endpoint 清单

| Method | Endpoint | 功能 |
|---|---|---|
| GET | `/api/v1/account` | 账户、Margin |
| GET | `/api/v1/positions` | 持仓 |
| GET | `/api/v1/orders` | 订单列表 |
| GET | `/api/v1/orders/{id}` | 指定订单 |
| GET | `/api/v1/quotes/{symbol}` | 行情和建议价格 |
| GET | `/api/v1/health` | 服务健康状态 |
| GET | `/api/v1/events` | SSE |
| POST | `/api/v1/orders/market-buy` | 市价买入 |
| POST | `/api/v1/orders/market-sell` | 市价卖出 |
| POST | `/api/v1/orders/breakout-buy` | 突破买入 |
| PUT | `/api/v1/orders/{id}/stop` | 修改止损 |
| DELETE | `/api/v1/orders/{id}` | 取消订单 |

**共 12 个 Endpoint，5 个交易写操作。**

---

## 22. 代码组织

采用：

```text
schwab_backend.py
test_trading.py
```

单个 Backend 文件内部按职责分区：

```text
01 Configuration
02 Data Models
03 Keychain & OAuth
04 Schwab REST Client
05 Schwab Streaming Client
06 Runtime Cache
07 Trading Gateway
08 SSE & Notifications
09 Local API Routes
10 Startup & CLI
```

不拆分成多个微服务。

不使用数据库。

不使用 Docker。

不使用自定义加密系统。

---

## 23. 上线验收

| 项目 | 必须通过的测试 |
|---|---|
| OAuth | 首次授权、Access Token Refresh |
| OAuth 恢复 | 手动重新授权后无需重启服务 |
| Token 并发 | 多个请求不会同时刷新 Token |
| 启动 | 无网络时服务仍可启动并提供 Health |
| 睡眠 | 唤醒后能够自动恢复连接 |
| 断网 | WebSocket 能检测断线并重新订阅 |
| Account | 正确返回 Margin 和 Buying Power |
| Positions | 正确查询当前持仓 |
| Orders | 正确识别父子单和当前状态 |
| Quote | 实时 Bid/Ask 正确推送 |
| 手动刷新 | 确实请求 Schwab REST |
| Breakout | OTO STOP DAY → STOP GTC 正确提交 |
| Market | 市价买入、市价卖出正确提交 |
| Replace | 新 Order ID 正确解析 |
| Cancel | 正确取消指定订单 |
| Location Header | 正确解析订单 ID |
| Unknown | 写请求超时不自动重试 |
| SSE | 多个客户端均可收到更新 |
| Sound | 成交提示异步播放 |
| Restart | 无数据库即可恢复当前数据 |

实盘启用前，还需使用实际 Schwab Production App 验证 OTO 子单激活、部分成交和 Replace 行为。

---

## 24. 最终设计约束

V1.2 的核心配置：

```text
Deployment:
    Mac mini
    localhost only
    single process

Backend:
    Python
    FastAPI
    single file

Storage:
    RAM only
    macOS Keychain for credentials

Schwab:
    REST API
    one WebSocket

Streaming:
    ACCT_ACTIVITY
    LEVELONE_EQUITIES (Bid/Ask only)

Local Communication:
    REST
    SSE

Trading:
    Market Buy
    Market Sell
    Breakout Buy
    Replace Stop
    Cancel Order

Risk:
    max order amount
    max estimated loss
    max stop ratio

Recovery:
    automatic REST recovery
    automatic WebSocket reconnect
    serialized token refresh
    automatic Keychain token reload

Excluded:
    database
    complex state machine
    automatic write retry
    automatic composite trading operations
    low-price special rules
    price deviation limits
    hardware power management
```

---

## 25. 开发冻结原则

后续开发遵守以下约束：

**一、不得增加隐式交易操作。**

每个函数只执行其名称对应的交易动作。

**二、不得增加通用订单参数。**

新增订单类型必须通过新增独立函数实现。

**三、不得引入业务数据库。**

当前状态通过 Schwab 获取。

**四、不得自动重试交易写请求。**

读取、认证和 Streaming 可以恢复；交易执行不自动重新提交。

**五、不得干预 Mac mini 的睡眠、关机和网络状态。**

程序只负责在恢复运行后重新建立服务。

**六、不得增加未经要求的交易限制。**

保留明确约定的金额和止损边界，不扩展为一般性交易风控引擎。

---

**V1.2 文档结束。**

这次修订之后，架构仍然保持原有规模。真正新增的只有一把 Token 刷新锁、WebSocket 心跳与重连、启动初始化重试，以及 Keychain 重新授权检测。

这四项不会改变业务 API，也不需要数据库或复杂状态机。它们解决的是同一个具体问题：**Mac mini 停止运行一段时间后，恢复网络时 Backend 不应需要人工修复才能继续工作。**

需要保留的实现边界是：睡眠和断网期间不提供实时监控，恢复后重新同步；已经提交到 Schwab 的服务器端订单不依赖本地 Backend 持续运行。

**主要核查依据：**

- [Schwab 官方 OAuth 认证说明](https://developer.schwab.com/user-guides/get-started/authenticate-with-oauth)
- [Schwab 官方 OAuth Restart 与 Refresh](https://developer.schwab.com/user-guides/apis-and-apps/oauth-restart-vs-refresh-token)
- [Schwab Accounts & Trading OpenAPI](https://github.com/Patch-Code-Prosperity/Schwab-API-Sandbox/blob/main/account_orders_openapi.yaml)
- [Schwab Streaming 字段及订阅参考](https://github.com/tylerebowers/schwabdev/blob/main/docs/pages-raw/stream.md)
- [Python websockets 官方客户端及重连文档](https://websockets.readthedocs.io/en/latest/reference/asyncio/client.html)

**文档状态：V1.2 可作为开发基准；券商相关执行行为以 Production 验收结果为准。**

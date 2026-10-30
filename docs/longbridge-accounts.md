# Longbridge 多账号与访问台账

本文件是 Longbridge 账号配置、K 线选号、访问统计与保存规则的唯一维护入口。行情范围、复权、缓存与恢复见 [Longbridge 数据说明](longbridge-data.md)；实现职责见 [开发维护](development.md)。

## 账号与连接

本机 `config/credentials.json` 的 `longbridge.accounts` 是有序列表，每项包含稳定的 `id`、`app_key`、`app_secret`、`access_token`。首项为主账号，负责应用使用的 Quote、快照、搜索验证及原有 Quote/Trade 订阅。增加第三、第四个账号只需追加配置并重启，不修改代码。

每个账号拥有独立的 SDK context、限流和并发预算，首次需要时创建并持续复用，不替换其他 context 的 token。每账号沿用10次/秒、5个在途，后台全量8次/秒、3个在途。SDK仍是5.0.0，唯一入口仍为 `data_service/longbridge/client.py`。

同一 symbol 的官方 K 线查询和 SDK candle 初始化使用绑定账号。副账号为其 candle 保留 SDK 所需的 Quote/Trade，应用不从副账号读取或展示另一份 Quote；所有 candle 回调送入现有 Monitor 处理流程。退订、恢复和账号变化按实际所属 context 执行，旧 context 的 candle 不能覆盖新所属 context 的推送。最后一个周期移除后清理副账号该 symbol 的底层订阅。

所有账号的官方 closed 仍写入同一 Longbridge bars 库，当天 SDK 序列仍进入同一 ChartCache；下游不增加账号字段或另算指标。Massive 保持独立。行情失败沿用现有逐周期重试，不因普通超时自动换账号。

## 统一访问入口与分配

项目的 `candles()` 和 `subscribe_candles()` 统一进入 `LongbridgeClient.kline_request()`。这里同步完成选账号、更新内存记录，再执行 SDK 请求；不在每个周期、下载器或图表各加统计。

进入这个 K 线入口就记一次访问，覆盖最后时间；不区分成功、失败、返回值或SDK内部缓存。Quote/Trade推送、快照、搜索、图表读取及退订不进入访问台账。项目使用最近 K 线及 SDK candle，没有调用 `history_candlesticks_by_*`。

分配规则：

1. symbol 本月已绑定且账号仍在配置中，继续使用原账号，全部周期及重试共用。
2. 本月首次访问或上次访问属于旧月份，按配置顺序选择本月不足90只的第一个账号。
3. 全部账号达到90只后，按相同顺序使用剩余至100只的名额。
4. 全部账号达到100只时，只有新 symbol 的K线请求报告本地容量已满；已有 symbol、主账号报价及其他后台功能继续运行。

90与100集中在 `longbridge/usage.py` 的常量，不增加规则配置系统。分配和更新中间不await，多个周期同时初始化不会把同一symbol分给不同账号。跨日复用内存和磁盘记录；月份由时间戳按 `Asia/Hong_Kong` 的自然月归纳，不使用美股交易日。跨月重新分配导致所属账号变化时，利用现有逐周期重新初始化路径迁移 candle，保留显示与主报价连接。

## 单份台账

`runtime/longbridge/usage.json` 是唯一持久化台账，启动读入内存，结构为：

```json
{
  "AAPL.US": {"account": "account_1", "last_access_at": 1793368800}
}
```

只存symbol、账号ID与最后访问Unix秒，不存month、逐次日志、凭证或另一份计数。普通请求查字典并更新时间；新symbol选号或只读查询时才归纳当月数量。旧月份记录可被该symbol的新访问覆盖，不保留月份快照。

这是从启用起本runtime记录的K线访问数，不是供应商官方用量：不追补启用前的请求，也不合并其他程序或其他runtime的请求。发起失败与SDK缓存返回同样计入。账号ID属于账户身份，更新token沿用ID；不要把相同ID改给另一个实际账号。

## 保存与退出

访问只更新内存，数据改变时设dirty。单一后台任务每10秒检查，有变化才生成JSON快照并用 `asyncio.to_thread` 直接覆盖文件；没有变化不写。保存中出现新访问保留dirty供下一轮处理，所有保存经过同一个入口并串行执行。

正常Ctrl+C在现有关闭流程等待正在写入的任务并补存最后记录。请求路径不等待写盘；保存失败记录日志并保留dirty，下一轮再保存。直接覆盖，不使用临时文件、备份或额外数据库。强杀/断电接受末轮记录丢失；文件缺失时从空台账开始；无法解析时明确提示并从空台账继续，不阻止行情启动。

## 查看

不增加看盘UI。以下命令只读文件与配置，不连接SDK、不写盘、不占服务锁，可在服务运行时使用：

```bash
.venv/bin/python -m data_service longbridge-usage
```

输出统计月份、统计时区、各配置账号的本月标的数、总数和台账路径；month仅在这个查询结果中生成。

真实接口验收脚本 `scripts/live_check.py` 使用临时bars库和正式访问台账，共用runtime单实例锁，运行前先停止正式服务，避免两个进程覆盖同一份JSON。

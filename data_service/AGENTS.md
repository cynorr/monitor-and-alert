# Data Service 局部维护约定

本目录承载正式数据层及图表所需的纯 Python 派生数据。读 [模块维护手册](../docs/data/README.md) 的文件地图及 [开发规格](../Longbridge-Data-Service-Design.md) 后再改。

- 正式 SDK 请求归 `broker.py`；Quote 状态/恢复归 `quotes.py`；时间边界归 `calendar.py`。
- `downloader.py` 负责 fetch/parse/filter/UPSERT，不写 readiness；`validator.py` 只从 SQLite 和批次证据验证，不做下载。
- `store.py` 维护持久化不变量；`service.py` 协调工作流。不要把 UI 展示、Alert 公式或随机行情生成加到 service.py。
- `http_api.py` 是传输层，对外提供 HTTP 快照、静态图表和 WebSocket；保持同源访问与 Origin 检查。
- charts.py 只维护内存活跃 candle；indicators.py 是指标唯一实现。临时数据和指标不落入官方 bars。
- 不增加 Trade/Depth/Broker subscription，不本地累加累计成交量，不合成官方 closed bars。
- readiness v2 按当前具体闭合时刻验证；READY 为 Daily+5m，FULL_READY 为五周期。短历史和缺口分别提示，不伪造完整。
- 任何模拟器依赖、场景分支和测试数据生成留在独立目录。模拟器在独立目录提供行情源，通过实例级 clock 注入复用本目录流程；不全局改写时间、不绕过验证、不写正式数据库。
- 修改 OHLCV、交易时段、已闭合判断或批次范围时，覆盖相关错误路径测试，不仅测正常返回。

回归命令：`.venv/bin/python -m pytest -q`（从仓库根目录执行）。安装、实测命令和当前限制见根 README 与维护手册。职责变化时同步文档，不要求未来维护者重读旧聊天。

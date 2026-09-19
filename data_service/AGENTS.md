# Data Service 局部维护约定

本目录只承载正式数据层。读 [模块维护手册](../docs/data/README.md) 的文件地图及 [开发规格](../Longbridge-Data-Service-Design.md) 后再改。

- 正式 SDK 请求归 `broker.py`；Quote 状态/恢复归 `quotes.py`；时间边界归 `calendar.py`。
- `downloader.py` 负责 fetch/parse/filter/UPSERT，不写 readiness；`validator.py` 只从 SQLite 和批次证据验证，不做下载。
- `store.py` 维护持久化不变量；`service.py` 协调工作流。不要把 UI 展示、Alert 公式或随机行情生成加到 service.py。
- `http_api.py` 是传输层，当前对外只有只读 HTTP。不要假定已有 UI WebSocket/SSE。
- 不增加 Trade/Depth/Broker subscription，不本地累加累计成交量，不合成官方 closed bars。
- 300 日/12 日严格 READY、短历史降级和 FULL_READY 的语义不可相互替代；数据缺口不能当作新股历史不足。
- 任何模拟器依赖、场景分支和测试数据生成留在独立目录。当前独立模拟器仅向下游推盘中 Quote，不接入本目录，不要求添加时钟、SimBroker 或绕过正式校验。
- 修改 OHLCV、交易时段、已闭合判断或批次范围时，覆盖相关错误路径测试，不仅测正常返回。

回归命令：`.venv/bin/python -m pytest -q`（从仓库根目录执行）。安装、实测命令和当前限制见根 README 与维护手册。职责变化时同步文档，不要求未来维护者重读旧聊天。

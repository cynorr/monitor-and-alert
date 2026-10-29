# Schwab 交易网关参考

当前产品、启动和界面唯一入口是 [Schwab Trade MVP](../docs/schwab-trade.md)。正式服务由项目根目录的 `data_service serve` 启动，使用现有工作台，不另起 HTTP 或前端服务。

- [backend-design.md](backend-design.md)：保留的原交易网关协议与安全设计；集成范围以主文档为准。
- `schwab_backend.py`：兼容入口，转入唯一实现 `data_service/schwab_backend.py`。
- `test_trading.py`：使用假凭证、MockTransport 的网关协议测试。

从项目根目录运行网关测试：

```sh
.venv/bin/python -m pytest -q schwab-minimum-trader/test_trading.py
```

OAuth 授权及当前运行方式见主文档，不运行旧独立服务。

# Additional Info 维护入口

先读项目根 README 和 [开发准则](../../docs/development-principles.md)。公司资料/财报的需求、数据源、清理、刷新和传输语义只在 [docs/additional-info.md](../../docs/additional-info.md) 维护；具体图表排版只在 [Chart UI](../../docs/chart-ui.md#headers-and-information) 维护。用户当前要求优先。

本目录也收纳`symbol_directory.py`的证券属性获取；其ETF筛查、获取时机和保存要求只在 [Massive数据要求](../../docs/massive-data.md) 维护，不并入公司资料/财报服务。

- 公司资料/财报是可缺失的独立附加信息，不依赖Massive、Longbridge、Holdings、Workspace或特征算子，不影响候选排名或Ready。财报缓存加载/更新成功后只通过on_earnings_change通知Workbench；当前名单的日期特征与排除由Workbench和List负责，规则见[List设计](../../docs/list-design.md#财报排除)。
- `nasdaq.py` 只负责两个明确的 Nasdaq 网站接口、响应校验及 Python 名称/字段清理；`service.py` 管独立 SQLite、内存读取、刷新与调度。不新增通用数据源框架或第二个服务。
- `symbol_directory.py`独立处理Nasdaq Trader证券目录及官方ETF标记，保留原有CLI与`symbol-directory.json`路径；与上述公司表/财报接口分别获取，不互相补缺、不连带刷新。
- 公司/财报服务仅使用 Screener 公司信息及按日整市场财报日历。未覆盖的证券直接留空，不从 ETF 目录、券商、行情或其他来源补足。
- 保留原始响应和名称；清理函数必须用于每次更新，不维护逐 ticker 人工名称表。未知证券格式不猜测映射。
- 请求、解析和写库在独立后台任务中完成。HTTP GET、图表选择和名单操作只读取内存；附加信息消息不改变 bar revision 或行情状态。
- 财报区分预估日程与有实际结果的已发布报告。刷新成功才替换对应日期；失败保留上次数据。不要加入 beat/miss 展示、交易规则或自动 Alert。
- 正式服务才自动联网。Mock、模拟器和 symbol 子集验证不启动真实附加信息刷新；离线测试只使用临时缓存和明确的测试响应。
- 验证优先使用本轮真实 Nasdaq 数据；网络验收限定日期范围和请求数，补充相关规则用例即可。更新需求文档、职责入口和验证记录，不把历史记录当成本轮 live 证据。

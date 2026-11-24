# Market Monitor · Android prototype

独立 Kotlin / Compose APK。平板自己保存日线、计算 Scan、维护名单与 Additional Info；实时报价直连 Longbridge 账号 2。没有 Python、localhost 服务或 Mac 网络依赖。产品范围见 [运行逻辑](../docs/behavior.md#android-prototype)，布局见 [UI](../docs/ui.md#android-prototype)。现有业务文档仍是指标和名单规则的唯一规范。

## 安装与使用

安装包：`output/market-monitor-0.1.0.apk`。直接打开 APK，系统提示时选择继续安装。按本人明确要求，此私用测试包预置账号 2 与 Massive 凭证，首次启动自动载入，不需要输入或导入；不作公开发布。

APK 带有初始全市场历史、拆股、名单、偏好和资料缓存，因此安装包较大。首次启动展开本地数据，显示文件及字节进度；后续复用。所有写入均在 Android 应用私有目录。更新 APK 保留本地数据；卸载应用会删除数据。

- 点名单行查看 Daily；拖动、双指缩放、长按十字线；`↦` 恢复视图。
- Discover / Focus / Excluded、已保存 Tag、Filters、RFL 排序沿用现有语义。
- 行尾 `⋮` 提供适用的 Pin / Unpin、Add to Focus、Move to Hidden、Release、Move to Discover。
- Search 只搜索本地股票；人工 Discover 当日有效，长期关注用 Add to Focus。
- 历史日期只读，不显示当前 Quote。Refresh 补齐成熟日并按原规则重新分类。
- Data 菜单可独立刷新 Additional Info、更新 Nasdaq Trader 目录。
- 恢复前台重连 Quote；分钟 K、实时日 K、持仓、提醒、交易和熄屏监控暂缓。

## 构建与安装

Android Studio 打开本目录，使用 Studio 自带 JBR、SDK 37 和 Build Tools 36；`local.properties` 填本机 SDK 路径，不进入 Git。在仓库根运行：

```sh
android/tools/build.sh
.venv/bin/python android/tools/install.py
```

安装脚本只操作 `com.cyno.marketmonitor`，通过 adb stdin 配置必要凭证，不停止、重启或写入 Mac 服务。

`prepare_seed.py` 以 SQLite 只读备份导出本机数据；`prepare_reference.py` 生成真实数据对照；`prepare_credentials.py` 只选账号 2 和 Massive，生成 Git 忽略的私用 asset，不输出值。seed、凭证、构建缓存和 APK 均不进入 Git。原生凭证不交给图表 WebView。

## 源码

| 文件 | 职责 |
| --- | --- |
| `Workbench.kt` | 页面状态、名单操作、日期、前台任务与选择身份 |
| `MainActivity.kt` | Compose 界面、触摸菜单、单个图表 WebView |
| `Models.kt` / `ScanMath.kt` | Bar、日历、纯指标、排名和名单规则转译 |
| `LocalStore.kt` | seed、SQLite、截面与 workspace |
| `Massive.kt` | 原始日文件、完整 split 分页、复权、派生库准备 |
| `AdditionalInfo.kt` | 公司 / 财报缓存和独立更新、目录更新 |
| `LongbridgeQuotes.kt` | 官方签名、Quote 协议、快照、心跳、差集订阅与重连 |
| `Credentials.kt` | 私用默认值和 Android Keystore 加密保存 |
| `assets/chart.js` | Lightweight Charts 5.2.0 Daily 绘制，不计算指标 |

交易日历由现有 XNYS 导出，覆盖 2024–2028 年。没有通用适配层或跨平台框架。

## 验证

`./gradlew :app:testDebugUnitTest` 执行定向 JVM 验证。真实参考由准备脚本生成到 `.tools/reference/`，不联网。显式账号 2 live 检查设置 `ANDROID_QUOTE_CREDENTIALS`，仅两只股票 Quote、40 秒结束。

`DeviceScanTest` 在联网更新前，用同日期 / 复权版本的初始数据核对全市场指标、候选及三组排名。结果和未覆盖范围见 [验证记录](../docs/validation.md)。

Lightweight Charts™ by [TradingView](https://www.tradingview.com/)，LICENSE / NOTICE 随 APK 提供；连接实现参考 Longbridge 官方公开协议及 Go SDK。

# 故障协作基线 v0.2.0

保留协调、应用、数据库和恢复分析四个正式智能体。官方 ADP 发现及十个梧桐业务任务已完成，组合故障恢复和正常状态运行记录包含在本基线中。

运行入口：`integration/wutong_incident.py`。源码同时包含它仍依赖的 `run_pilot.py` 与 `wutong_smoke.py`，以及固定版本官方 SDK/CLI。

依赖清单来自本次实际环境，包含 cryptography。证书和私钥继续保存在原项目的 `integration/private/incident/`；本包通过 BASELINE.json 记录配置位置。

组合故障：503→200，8 个任务、2 次恢复操作、6.190 秒；正常状态：200→200，2 个任务、0 次恢复操作。诊断采用规则，业务服务为本机 HTTP/SQLite。

平台旧回声测试身份的资料已归档在 archive/old-test-agents.json；其清理状态见项目 integration/incident/platform-cleanup.json。

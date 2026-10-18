# NEW7 首次平台部署与健康验收（2026-10-18，历史截面）

本轮在已有开发机上实际部署独立 NEW7 容器项目，并用七个新版正式身份完成一次平台健康运行。它记录六域 AMQPS 任务往返和健康业务流程；当时尚未开展故障恢复、接管或 E3。后续[正式 E3](new7_e3_20261018.md)已闭合 45 格（37 确认、8 格 M1 未确认），8877 巡检的[第九次点观察](../evidence/new7-runtime-followup-20261018/inspect-ninth-cycle.json)和[七源真实卷 stdout 采集](../evidence/t06-real-volume-stdout-20261018/README.md)另有独立证据；正式接管、Kafka/Monitor 入库和 24 小时验收仍待完成。

## 部署和运行范围

- Compose project 为 `incident-pilot-new7`，10 个容器包括 PostgreSQL、应用 v1/v2、Nginx 和六个资源域。主机只映射回环 38081/38082/38088，不映射数据库端口。
- application、database、database-backup、ops、verification、onboarding 各持本身份的只读配置与证书挂载；主备数据库域共享本项目操作账本。运维域独占 Docker socket，并限定本项目 app-v2。协调者资源凭据计数为 0。
- 已实际构建一个新 agent 镜像与两个应用镜像，六域及应用的运行 image ID 与构建结果一致。三个已配置的业务容器健康检查通过，Nginx 没有配置 Docker healthcheck，由后续公共订单流程验证。原 14 个容器 ID 保留。
- 首次健康运行的协调者为独占的一次 Windows 进程，8877 当时仅预留；其后持续巡检已启动，见上方后续证据。同 AIC 不并行启动第二个 Inbox 消费者。

七角色证书实际签发和离线核验见[证书摘要](../evidence/platform-certificates-20261018/summary.json)；七个 AIC 的官方 ADP 只读身份及端点核对见[元数据观察](../evidence/platform-certificates-20261018/adp-identity-observation.json)。私钥、EAB、资源环境和展开配置留在本机私有目录。

## 实际健康结果

| 项目 | 本次实际结果 |
| --- | --- |
| 平台任务 | 六域各 1 项 describe，另 5 项 observe 和 1 项 verify；12 个不同 IFC 任务均有有效产物 |
| 正式消息核对 | 72 条消息：12 Start、12 Complete、48 条状态；每项依次有 accepted、working、awaiting-completion、completed |
| 业务观察 | 30.003 秒；30 次请求全部成功；10 个创建→查询→取消完整流程 |
| 失败与未决 | failed、unknown、unresolved、pending 均为 0 |
| 修改及模型 | act、resume、模型调用、故障注入均为 0；健康订单流程仍实际创建和取消订单 |
| 日志账本 | 24 条 journal 快照对应 12 个逻辑任务，各有 awaiting-completion 和 completed；最新状态均完成、有效在途 0、接管 0 |
| 收尾 | 本次自有群组正常 close；6 项本地检查为真，捕获的 SDK 清理警告 0；前台监督 wait 实际退出 0 |

独立只读审阅 24 项检查全部通过。任务终态、产物、账本和业务观察分别核对，任务 completed 不单独作为业务恢复结论。关闭证据限 SDK 返回和本地终态，未另查远端 broker/ACL 库存。

公开证据分为[健康运行](../evidence/new7-platform-runtime-20261018/healthy-amqps.json)、[容器与就绪核对](../evidence/new7-platform-runtime-20261018/runtime-readiness.json)、[任务/账本/收尾对账](../evidence/new7-platform-runtime-20261018/task-reconciliation.json)；协调者凭据分发审计另见[独立扫描记录](../evidence/new7-platform-runtime-20261018/credential-scan.json)。这些投影保留实际结果与原始来源摘要，不上传原始消息、配置或私密材料。

## 复现和待验收事项

首次准备、隔离挂载、独占身份和命令见[NEW7 部署说明](../deploy/NEW7.md)。agent 镜像先单独构建一次，再构建 app-v1/app-v2，最后 `up --no-build`，避免六域并发构建同一个 tag。已有项目不重复初始化资源目录；同 AIC 的健康入口、E3 和持久工作台按顺序独占运行。

本机已启用隐藏、受本次运行所有者管理的 WSL 前台保持辅助，供当前开发运行使用。它是本地 artifact 辅助，不是已安装的登录自启或系统服务；两次只读观察中容器 StartedAt 保持不变。此前启动时间变化的原因仍未确认，不能据此断言 WSL 自动退出就是根因，也不能据短时记录宣称 24 小时或 7×24 在线。

本页首次健康截面不覆盖故障恢复、主备接管、E3 或持久工作台；后续 E3 和 8877 巡检结果见上方独立证据。正式主备接管、系统登录/重启及 24 小时长期验收仍待完成。此前本地模型健康事故、原矩阵 40+1 中断及独立后续四格、旧平台与旧 18 例保持各自来源，不能与本次合并为一个实验。答辩 PPTX 继续按用户安排暂缓。

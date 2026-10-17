# E1 真实资源实验待授权

实现与相关验证已完成；正式启动被自动审批审查拒绝，进程未创建、未注入。拒绝原因为这批具体的 PostgreSQL 故障注入、写修复和进程退出缺少用户明确授权。此文提供完整可审阅范围。

拟执行 18 个案例，共用本机原生订单资源（8081/8082/8088）和持久 term/业务账本：

- E1-a：观察后、修改前、账本 applied 后结果发布前三个实验数据库 worker 真实退出点，各 3 次，共 9 次。
- E1-b：固定 applied 后退出，对从头恢复、完整真实业务对话、ResumePackage 三种交接方式各 3 次，共 9 次。
- 每例由独立 evaluator 使应用数据库角色只读并重建连接制造 F07；恢复通过域 MCP 修改与应用连接池修复完成。仅带实验标识的数据库 worker 调用 os._exit，原生业务服务本身不因该 hook 退出。
- 同一操作 ID 和共享账本贯穿接管；unknown 不盲重试，旧 fence 必须拒绝；记录真实 MCP 修改调用数。
- 每例恢复后执行至少 30 秒、10 个完整订单流程，再独立 restore 并检查健康基线；清理失败即停止后续案例。
- 本轮模型 calls/tokens 均为 0。使用本地进程目录，不将结果称为正式平台 ADP 接管。

待授权的精确 PowerShell 命令：

```powershell
& '<workspace>\.venv\Scripts\python.exe' '<workspace>\eval\handover_experiment.py' --include-breakpoints --repeats 3 --approve-high --output '<workspace>\eval\results\local\E1-native-20261017'
```

已完成只读准备命令（exit 0）：

```powershell
& '<workspace>\.venv\Scripts\python.exe' '<workspace>\eval\handover_experiment.py' --prepare-only --output '<workspace>\artifacts\E1-ready-20261017'
```

2026-10-17T11:00:51Z 四个公开端点均 HTTP 200，版本分别为 v1/v2/v2/v2，详见 health-preflight.json。source-manifest.json 是准备阶段源码快照；准备进程已退出，正式执行须在最终源码上重新导入并冻结，不能声称旧代码仍在内存运行。

源码：incident/local_transport.py、eval/resume_experiment.py、eval/handover_experiment.py、eval/resume_support.py；网关 data-only handover/hash 兼容补丁在 acps_mcp_bridge/bridge.py。行为测试与证据摘要见 tests-evidence.json，实验解释见 docs/resume_evaluation.md。

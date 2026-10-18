# 参与者失联诊断与 F19 本地实验

F19针对运维智能体自身退出：订单业务可能保持健康，但参与者任务无法继续。协调器把参与者可达性与订单结果分开保存；参与者仍待人工处理时，业务验证通过也不会自动结案。

## 判定依据

`incident/coordinator/amp_facts.py`只解析明确提供的AMP heartbeat/access文件，按精确AIC、原始时间戳及log_id归并。确认失联同时要求：

1. 记录到该参与者的真实任务deadline到期或通道断开，两者分别标为`deadline_expired`与`channel_lost`。
2. 此后实际尝试调用官方管理状态查询，记录发布失败或等待回复超时；区分未发出、已发布和实际回复，发布成功本身不能当回复。
3. 此前已看到该AIC有效心跳，该心跳按真实时间过期，且失败后没有新的心跳、接收侧访问或管理回复与失联结论冲突。

默认heartbeat/access/任务证据时效分别为45/60/60秒。故障前的成功访问保留在事实中，但不证明之后仍可达；故障后的接收侧响应（包括500错误）说明参与者仍在响应，不等于订单业务健康。Leader侧发送access不冒充对方响应。缺日志、无效/未来时间、错误AIC或过时证据均不确诊。

协调器只对观察任务的通信失败补充该诊断，不会据此重放结果未知的修改。事实不足时仍转人工，并保留“待核实”。独立业务验证及参与者恢复结论分别记录；取消独立验证会保存中断和未结案状态。

## 传输配置

本地stdio自动读取本次transport目录里该worker的heartbeat/access。梧桐传输需要在协调者配置中明确提供`participant_amp_paths`，格式为`{"目标AIC": ["明确的amp_heartbeat_*.jsonl路径", "明确的amp_access_*.jsonl路径"]}`；不扫描证书、env或其他运行目录。没有可访问的远端AMP文件就保留未知，不代表Monitor没有数据。

可选`participant_health_timeout_seconds`为管理请求/回复的界限，默认2秒、允许大于0且不超过30秒。`participant_health_wait_seconds`默认0，允许0到60秒：只有已记录任务失败、管理无回复且存在尚未过期心跳时，才有界等待该心跳的实际到期，并重新读取期间的新证据。F19实验显式设置等待50秒，不修改系统时间或伪造`now`。

## 隔离实验入口

```powershell
python eval/participant_failure_experiment.py --order-url http://127.0.0.1:28088 --output eval/results/local/F19-owned-<新标识>
```

输出目录必须不存在。先按部署说明启动独立订单靶场；入口仅接受loopback的18088/28088/38088公开订单端口。实验新建自己的运维与验证worker，运维只挂只读公共HTTP健康MCP适配，不带数据库、Docker socket或写工具。该适配不声称读取Nginx配置或实际Docker状态。

运维worker在真实只读观察完成、回执提交前通过显式实验hook自退出。runner只保留自己创建的进程对象，不从PID或名称寻找、终止既有进程。真实stdio EOF按通道断开记录，不冒称任务deadline超时。协调器用实际管理查询、Emitter心跳和独立30秒/10完整订单流程给出结论；之后新建专用worker验证复原，原事件保留人工处理状态。

通用`eval/inject.py F19 apply`仍拒绝缺少上述所有权与实验上下文的调用。F19使用此专用入口；F15继续使用其精确中断点接续实验入口，不能用业务只读故障替代智能体故障。

## 证据范围

2026-10-17的专用本地实验已实际exit0，14:33:47.817Z开始、14:35:13.904Z结束。新建运维worker自退出81；此前正常管理Get有真实回复，退出后的查询在发布阶段失败，记录为`no_reply`而非已发送；同AIC心跳实际经过45.0099秒到期。故障前成功access仍保留，不能否定之后的通道断开。

参与者缺席时，独立订单验证30.015秒、30次请求全部成功、10个完整流程，失败/未知/未完成意图均0。协调器保持`needs_attention`，`participant_recovered=false`和`incident_resolved=false`；没有act、审批或模型调用。新专用worker的describe、管理Get和新心跳检查通过，但不自动改写原事故。四个直接worker的实际退出码为81/0/0/0；未独立核实孙进程清理。见[真实F19精简证明](../evidence/participant-failure/F19-owned-20261017/verification.json)与[原件定位说明](../evidence/participant-failure/F19-owned-20261017/README.md)。

专用worker复原并正常清理后，另做独立H00：控制观察30.297秒、30次请求全成功、10个完整流程，失败/未知/未完成意图均0，`healthy_control_confirmed=true`、`recovery_confirmed=false`；未重复注入或改变资源设置。见[复原后的H00](../evidence/participant-failure/F19-owned-20261017/post-restore-h00.json)。

工作台在真实浏览器加载上述原件事故状态的精确只读副本，13项显示检查及三个视图截图视觉检查通过；能同时看到业务当前健康与参与者仍需人工处理。这验证显示路径，不冒称从UI发起了一次新F19。浏览器和专用8770预览均已关闭，已有工作台未改。见[浏览器结果](../evidence/participant-failure/F19-owned-ui-20261017/results.json)。

AMP事实15项、传输适配31个不同检查、runner12项、协调器新增9项分别记账；其中31项含历史失败后针对性复跑，初次失败记录保留。既有协调器22项记录仅复用相应未变路径，与传输fixture有交叠，不合并成唯一总数。精简离线证明见[AMP](../evidence/participant-failure/offline-20261017/amp-facts.json)、[传输](../evidence/participant-failure/offline-20261017/transport.json)、[runner](../evidence/participant-failure/offline-20261017/runner.json)与[协调器](../evidence/participant-failure/offline-20261017/coordinator.json)。

本地stdio实验不证明新身份已运行、正式ADP接管、AMQPS失联、Monitor入库或长期在线。参与者恢复与业务恢复也不互相代替。

# NEW7 正式E1接续：待实施的最小适配

状态：2026-10-18源码审阅形成的实施方案，尚未应用patch或运行本方案的测试、AMQPS、模型、Docker或数据库实验。E3闭合后再按独立运行范围推进；本方案不扩大E3授权。

[后续三项优先工作](post_e3_priorities_20261018.md) · [巡检启动边界](new7_inspect_preparation_20261018.md) · [协作任务清单](https://github.com/RoboSynth/multi-agent-interconnect/blob/3c539acc574ee99e35fe23d64776eb5a64bccfaf/docs/%E5%8D%8F%E4%BD%9C%E4%BB%BB%E5%8A%A1%E6%B8%85%E5%8D%95_20261018.md)

## 结论与可复用部分

旧E1-a/b/c入口不能只替换NEW7配置后直接运行。保留已有TakeoverManager、journal、IFC、共享OperationLedger和fence，适配实验runner、正式域的精确中断探针与交接信息接口。先验收E1-a的`after_applied`一格，再扩三个断点和E1-b；E1-c单独证明同一旧进程复活后的脑裂拒绝。

| 可复用能力 | 源码入口 | 保留的控制语义 |
| --- | --- | --- |
| 正式发现/接管 | [wutong_transport.py](../incident/wutong_transport.py) | 重新ADP发现、排除失败AIC、describe校验完整资源scope、升fence、resume；applied跳过、received以原ID续办、unknown先对账 |
| 主备共享账本 | [agents.yml](../deploy/agents.yml)、[bridge.py](../acps_mcp_bridge/bridge.py) | 主备共享database-agent-state；沿用advance_fence、只读对账与旧fence拒绝 |
| 三种交接表示 | [bridge.py](../acps_mcp_bridge/bridge.py) | 已有from_scratch/full_history/resume_package及handover_sha256校验；信息元数据不改变operation、fence或权限 |
| 原精确退出/计数 | [local_worker.py](../incident/local_worker.py) | 观察后未提交、record_received后未修改、applied后未提交，退出81/82/83；复用CountedMcpClient但修正其local传输标签 |
| NEW7目标与F07 | [targets.py](../eval/targets.py)、[inject.py](../eval/inject.py) | 绑定独立project、端口、挂载、镜像、源码、主备AIC及初选主库 |
| 监督与正常关闭 | [正式健康入口](../eval/platform_smoke.py)、[E3监督审阅源码](../evidence/new7-e3-preparation-20261018/wrappers/README.md) | 复用自有组正常close、清洁env、真实Popen.wait及独立HTTP H00；新建输出与收据 |

以下位置以审阅时版本为准，实施前按实际Git提交复核。

## 八个具体缺口

1. **旧runner固定native/stdio。** [resume_experiment.py](../eval/resume_experiment.py)的inject固定native，依赖`config['workers']`并创建local backup，使用LocalAipStdioTransport；[handover_experiment.py](../eval/handover_experiment.py)同样固定本地。[resume_support.py](../eval/resume_support.py)的健康端口与authority_snapshot也按旧workers查找。增加显式transport/backend/target适配，不能换成380xx后仍访问旧原生资源。

2. **正式数据库域无精确退出钩子且会自动重启。** [__main__.py](../acps_mcp_bridge/__main__.py)和[platform.py](../acps_mcp_bridge/platform.py)无experiment/crash参数；Bridge在execute之后才submit，适合实验包装器复用原三个钩子。通用inject拒绝F15，不能用F07冒充。只在独立E1 overlay将主库restart设为no，记录实际81/82/83退出；不要改当前E3部署。

3. **正式传输缺E1-b的resume factory。** Local传输已有可选`resume_payload_factory`及“只能改args”的不变量；Wutong直接构造默认resume。给Wutong增加同形可选factory，发送前复用字段、审批、fence和budget校验；默认None维持原行为，无需新账本或接管框架。

4. **旧history_reader会漏掉正式事故历史。** [resume_support.py](../eval/resume_support.py)按sessionId等于incident_id过滤；正式链路的群组session与IFC incident独立，describe逻辑ID也不同。在takeover_started固定消息序号，按Start/IFC及Product的incident_id关联taskId、去重，只取该序号之前的实际业务记录。HandoverRecorder可接收可选history_reader，保留local默认；故障后的重新发现/describe不能混入“故障前完整对话”。

5. **计数接口不同，成功产物不等于真实MCP副作用。** 正式传输没有旧runner的messages_path/events/amp_directory/call_on_worker接口；正式worker也未使用CountedMcpClient。复用计数包装器和current_payload上下文，按operation_id保存退出前已刷新的trace，区分调用、applied、幂等skip和未知结果。主备都计数，仅主启用退出钩子；CountedMcpClient增加保持旧默认的mode参数，不能给AMQPS记录local-aip-stdio标签。协调者仅接收安全统计，不持资源env。

6. **E1-c不能沿用Windows本地PID暂停。** [old_primary_replay_experiment.py](../eval/old_primary_replay_experiment.py)依赖本地worker、NtSuspendProcess和stdio。正式评测控制器应对已核实的主库容器pause/unpause，证明同一容器、同一主Python进程恢复，不能kill后新PID代替。正常transport.call会改写act的active_fence，旧令牌探针须定向旧AIC并保留原payload/fence。

7. **预期主库退出另列，不放宽E3的StartedAt守卫。** E1控制器固定原container/image/source/挂载，只允许记录中的主库预期退出与恢复；恢复后重新完整核查，再为F07复原建立新attestation。其它域变化仍拒绝，不修改E3 expected_domains约束或复用E3结果目录。

8. **旧source freeze会递归带入历史结果。** resume_support对eval的rglob可能收进eval/results快照。新runner复用[eval/run.py](../eval/run.py)的有界源冻结规则，再显式绑定实验包装器、overlay及配置哈希，不复制历史日志或私密目录。

## 最小实施顺序

1. 新建薄`eval/platform_resume_experiment.py`，默认只校验文件，显式execute才进入独立控制器。只为E1启用automatic_takeover；持续使用原term_namespace/term_journal及共享账本。目标、健康端口、F07 setup/restore来自DockerTarget，先只验E1-a/after_applied。
2. 增加实验专用数据库worker与E1 overlay，复用现有Bridge/Policy/MCP/Ledger/runtime。钩子只对明确experiment、incident、主AIC和工具生效；before_modification先审批并record_received，after_applied已持久化且尚未提交产物。可用只读实验模块挂载，核实际import路径/SHA，不建立第二套业务实现；改变入口前由所有者关闭旧消费者，避免同AIC双Inbox。
3. 窄增Wutong可选resume factory和HandoverRecorder可选history_reader。factory不能改operation/logical ID、fence、审批、预算或kind。E1-b沿用确定性续办，实际模型/token为0；UTF8 bytes/4只能称估算。
4. E1-c先选显式更高fence接纳：同一自有组describe主备→主确认旧fence→pause主→备确认新fence并修改一次→发布旧fence请求后unpause同进程→旧AIC返回rejected_stale_fence。两端保持组成员；这证明正式链路脑裂拒绝，自动ADP接管由E1-a/b另证。

自动接管会force_remove旧AIC并撤销成员ACL，可能删除队列/关闭连接。因此不能在E1-a后直接假定旧成员仍可收原组任务；若要证明“自动接管后重新入组”，另验邀请/入群流程。

## 实施后需要的离线验证（当前未运行）

- 复用现有Wutong transport的applied不重复、received原ID重试、unknown不重放、资源隔离与TTL检查，仅补factory信息替换及控制字段篡改拒绝。
- fake executor/exit callback验证三个钩子的顺序、持久化与submit边界；backup、未armed、错误incident不得退出，主备计数按operation隔离。
- 合成group session≠incident、故障后describe与重复状态，证明仅提取故障前业务信息；local history兼容保持。
- stub控制器拒绝错project/service/image/PID，验证pause后同身份unpause、finally恢复和close失败保留原错误。
- 默认/缺授权入口在任何GET、AMQP、模型、Docker或输出创建前停止；实际实验另保真实退出、正常close、独立v2 H00和source/config/trace证据。

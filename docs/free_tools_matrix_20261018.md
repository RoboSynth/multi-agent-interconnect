# 完整工具M1本地矩阵：中断与独立后续批次

原计划为 `M1-full-tools-matrix-20261017`：F01/F02/F06/F07/F10 × M0/M1/M2 × 3次，共45个唯一格；M1为 `free-tools-v1`。实际原进程在第41格中途丢失，原批不能记为完整45格。第42–45格已另存独立continuation并真实完成，原第41格保持中断，没有重新执行后替换原结果。

按原45个计划位置盘点，两阶段共44条终态（原40＋后续4）：37条满足协调完成且独立持续恢复（33＋4）、7条未满足，另1格已注入中断。该覆盖说明不将两阶段称为一次完整45格单批，也不混入历史实验。

各段均为本地 `local-aip-stdio`、native资源和本机Qwen3-1.7B-Q8_0。它们不与历史观察选择版M1的v2/v3组合45格、两批F01 pilot、旧E1-a/E1-b18次接管或F19合并，也不代表正式新版梧桐E3。

## 原批已封存的状态

监督器于2026-10-18 01:05:53.198245 UTC启动，矩阵子进程于01:05:53.806760 UTC启动。153份源码冻结ID为 `local-free-tools-final-F19-cleanup-20261018`，receipt SHA256为 `e9816eb44b50a8b1c4c5ead2f72c713165f004b114ec7e8e753765d048b01a24`；本地完整冻结快照不等于全部公开上传。

| 原批项目 | 已有证据 |
| --- | --- |
| 终态记录 | 40条，严格等于原45计划前40项；最后一条为F10/M1/repeat2 |
| 协调完成且独立持续恢复 | 33/40；另7条未满足该复合判据，失败仍保留 |
| 第41格 | F10/M2/repeat2已注入、原incident仍running，无终态结果 |
| 原矩阵/监督OS退出码 | 均未知；进程句柄丢失，没有实际wait退出证明 |
| 原最终H00 | 不存在 |
| 原件 | 502文件、16959669字节逐字节封存；SQLite DB/WAL/SHM分别保留，不以打开数据库或修复替代原件 |

`completed` 仅为协调状态，不能单独计作恢复。上表33条要求协调完成与独立观察器持续健康同时成立；40条终态也不表示40条均完成或恢复。`seconds` 包含诊断、动作及域验证，恢复时间属于1 rps采样估计。各方法进一步统计仅引用原批公开投影，不用未完成行或历史批次填足45格。

原件封存及40条结果的公开入口为 [原40格中断证据](../evidence/model-evaluation/local-free-tools-matrix-20261018/)。本页不为未知退出码补写exit1，也不把单独健康检查当原矩阵完成证明。

## 第41格与四个未启动格

F10/M2/repeat2对应 `inc-ff2d1f3b412046e8`，01:52:42.231294 UTC开始，末事件01:52:48.021475 UTC；原记录为running、842个已记录token，一项 `ops.containers` 观察task仍pending。独立workload保留14条请求：5成功、9未知，没有summary。成功apply的onset为3972.593，注入进程记录最后一条为F10/apply/returncode0，之后无该格restore记录。它是已注入但缺终态的中断格，不归为未启动或恢复成功。

以下四个原未启动格已在独立continuation真实完成：

| 原序号 | 场景/方法/重复 | 原seed | 原pool预热次数 | 后续记录 |
| --- | --- | --- | --- | --- |
| 42 | F10/M0/repeat2 | 202 | 1 | completed；独立持续恢复确认 |
| 43 | F10/M2/repeat3 | 303 | 2 | completed；独立持续恢复确认 |
| 44 | F10/M0/repeat3 | 303 | 2 | completed；独立持续恢复确认 |
| 45 | F10/M1/repeat3 | 303 | 2 | completed；独立持续恢复确认 |

后续批次状态为 已独立完成四格，四格均协调完成且独立持续恢复，独立目录/证明为 [独立四格证据](../evidence/evaluation-continuation-four-20261018/)；实际终态数 4/4，其中满足协调完成且独立持续恢复 4/4；实际OS退出码为 0。实例参数对齐证明为 精确四键顺序、方法定义、原seed/pool、JSON与JSONL、153源码及不可变配置全部匹配。四格子进程由Popen.wait记录exit0，结束于02:09:51.785569 UTC；前台监督会话11989随后实际exit0（执行器终态chunk18437a），监督finished记录时间为02:10:23.461781 UTC。它们不推定原中断进程的退出码。

同seed和预热配置只说明原计划参数对齐，不能证明原PID、revision、模型进程或运行时间线连续。原运行器没有resume/skip入口；后续目录、执行记录与监督证明必须另列。原批40条、在途41和后续4格分开记账，不称一次完整45格，不把分段成功率或耗时当同一连续运行结论。

独立健康检查状态为 独立HTTP H00通过，证据为 [独立四格证据](../evidence/evaluation-continuation-four-20261018/)：观察 30.328 秒，完成 10 个流程，失败/未知/未决为 0/0/0。该独立窗口共有30次请求、全部成功，healthy_control_confirmed=true、recovery_confirmed=false；健康采样跨度为30.297秒，control_observation_seconds为30.328秒，两者不混用。后续新请求健康不能自动解除第41格原未知意图或补齐其恢复终态。H00单列，不进入故障恢复分母。

## 保留的产品差异与模型失败

F02/M1/repeat2当时仍指向旧v1，普通create/query/cancel可成功；产品验证器漏检 `order_api_version=v2`，因此协调者可报completed。独立观察器已检查v2，未确认持续恢复。原格按冻结代码和结果保留，后续候选修复不能补记它成功。

F06/M1/repeat1第8次模型请求收到HTTP400。原incident直接provider字段为 `code=400`、`type=exceed_context_size_error`、`n_prompt_tokens=10422`、`n_ctx=8192`，请求超过上下文2230 tokens；公开投影入口为 [model-call-outcomes.json](../evidence/model-evaluation/local-free-tools-matrix-20261018/model-call-outcomes.json)，定位该格 `calls` 第8条的 `provider_error`。原incident SHA256为 `9366d33ca6826755ba4de4ee904fc6db5c1dd728cccbdce9e42ea22c7d3aaf07`。服务端日志和原相邻usage诊断作为辅助证据保留。

该格8次请求的前7次已知usage合计15559 tokens，失败请求无usage，`token_usage_complete=false`；客户端 `prompt_token_upper_bound=29406` 是估计，不能当实际输入token。该失败不通过增加上下文、改M1兜底或重跑同格从原结果中删除。原始模型上下文、资源凭据和完整私密运行快照不进入公开文档。

## 修订与验收

三组修订与native就绪候选的应用状态为 已应用11个源码/测试/部署文件并完成本地验收：6项fresh导入/CLI均exit0，native start实际exit0、公共入口v2，产品验证器30.031秒/30次全成功/10流程通过，实际导入/CLI及公共产品验证证明为 [应用及导入汇总](../evidence/development-candidates-20261018/application-and-imports.json)。此前离线证明只覆盖以下范围，不改变原批结果：

| 候选 | 最小行为 | 不同相关检查 |
| --- | --- | --- |
| 公共订单版本契约 | generic `OrderObserver` 默认None兼容；产品验证器及原回执显式v2；评测器保留 `VersionedClient(client).request(...)`；坏响应不推进intent，同key unknown语义保留 | 15：8新focused+6既有原请求+1既有共享client；导入引导修订另有外部cwd导入证明，行为结果复用；[离线版本证明](../evidence/development-candidates-20261018/offline-order-version-contract.json) |
| 矩阵完整性/H00报告 | 精确键与已声明元数据校验并列实际检查行数；H00独立面板/来源，fault index排除H00；候选图布局单独审阅 | 14：5既有兼容+9新检查；最后一项的有/无H00 apply两子例局部复跑，其余复用；候选合成图和原40格实际图分别审阅，来源独立；[离线报告证明](../evidence/development-candidates-20261018/offline-report-integrity.json) |
| 固定窗口稳定性 | 可选UTC `[start,end)` 和显式期望AIC；ceil槽数、floor归位、每槽最多一次；缺席身份进分母，旧默认输出兼容 | 21：8旧+12新项目测试+1artifact完整输出对照；修订后13受影响项复跑+8复用，不相加成34；[离线固定窗口证明](../evidence/development-candidates-20261018/offline-stability-window.json) |


Native启动的默认路由原本已在文件缺失时初始化到v2，已有v1路由会被保留；根因不是默认写v1。就绪候选仅要求公共order_port同时ok=true与api_version=v2，保留v1/v2直连探针和已有route，失败提示检查route并采用适用的正常restore，不自动清除故障现场。PowerShell7.6.5对原/候选AST均0解析错误；随后已实际执行native start并exit0（执行器chunk ba28a5），公共入口v2，且下述公共产品路径验证通过；现有route保持，见[native启动证明](../evidence/development-candidates-20261018/native-start.json)。

最终本地状态以final-validation.json的LOCAL_CODE_UPDATE_VALIDATED为准，验证时间2026-10-18 02:18:09.722363 UTC；早期应用收据中import/runtime pending为阶段历史，原件保留。产品验证实际调用VerificationPartner经公共8088入口，transport为direct-local-product-call、formal_platform=false：30.031秒、30请求全部成功、10完整流程，失败/未知/未决均0，product_status=ok、business_recovered=true。该调用未携带第41格未知原请求（original_request_resolution=not_required），不算为其完成对账；也不复算原40或独立四格结果，见[公共产品验证](../evidence/development-candidates-20261018/verification-public-http.json)。

三组计数分别报告，不相加成一个项目唯一测试总数，也不是45次真实实验。证明入口为 [应用及导入汇总](../evidence/development-candidates-20261018/application-and-imports.json)。这些已应用修订与原批冻结源码、中断原件分别保存。

Windows登录巡检只完成配置与进程锁准备，未安装真实任务、未验收登录/重启后实跑；固定窗口统计测采样完整度，不是TTL在线率、实际宕机时长或长期运行证明。后续四格的独立HTTP H00已通过，但不证明新版梧桐E3、Monitor/Kafka入库、连续24小时或7×24验收；证书与答辩PPTX继续按用户安排暂缓。

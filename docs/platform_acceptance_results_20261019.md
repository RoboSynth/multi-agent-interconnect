# 正式平台 22 项验收结果（2026-10-19）

本页是本批终态入口。后文链接的 10-18 记录、源码准备及离线检查均保留原时间截面；它们不覆盖本页的真实失败、恢复与停止记录。接手仍从[开发者接手指南](开发者接手指南_20261018.md)及[本地环境与操作](本地开发环境与操作_20261018.md)进入。

本批准备22项，实际尝试22项：通过18、失败4；未尝试0。失败照原结果保留，发布不要求全部通过。

来源：冻结计划索引、[结果汇总](../evidence/platform-acceptance-20261019/summary.json)、[真实批次终态](../evidence/platform-acceptance-20261019/batch-terminal.json)和[闭合访问/凭据检查](../evidence/platform-acceptance-20261019/closed-access-credentials.json)。冻结结果 SHA：`02d8550cecdb2d4fe7a93918802487686d0809757c9d56e28b100c521ce8a60a`；源码提交：`c1c09e569ef67b7f0f0c2b2e8a948afec53f0c31`。未提供的指标显示“未提供”，不补零。

## 分组与逐例

E1-a 为三断点各三次，E1-b 为三方法各三次，E1-c 为三次旧主同进程恢复，F12/E5 为一次原请求键对照。执行把 F12 调整到末尾，准备计划顺序与 SHA 不变。以下 OS exit 是单例真实子进程退出码；批次阶段退出另列，不把 failed 改成成功。

| 组别 | 点/方法 | 计划数 | 通过 | 失败 | 未尝试 |
| --- | --- | --- | --- | --- | --- |
| E1-a | after_observation | 3 | 2 | 1 | 0 |
| E1-a | before_modification | 3 | 3 | 0 | 0 |
| E1-a | after_applied | 3 | 3 | 0 | 0 |
| E1-b | from_scratch | 3 | 3 | 0 | 0 |
| E1-b | full_history | 3 | 0 | 3 | 0 |
| E1-b | resume_package | 3 | 3 | 0 | 0 |
| E1-c | before_modification | 3 | 3 | 0 | 0 |
| F12/E5 | 单例 | 1 | 1 | 0 | 0 |

| plan key | 状态 | OS exit | 关组 | 恢复 | H00请求/成功/流程/失败/未知/未解决 | cleanup事件 |
| --- | --- | --- | --- | --- | --- | --- |
| e1a-after_observation-r1 | failed | 1 | 未提供 | 未提供 | 未提供 | 无所列cleanup事件 |
| e1a-before_modification-r1 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1a-after_applied-r1 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1b-from_scratch-r1 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1b-full_history-r1 | failed | 1 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1b-resume_package-r1 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1c-before_modification-r1 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| f12e5-r1 | passed | 0 | 6/6真 | True | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1a-after_observation-r2 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1a-before_modification-r2 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1a-after_applied-r2 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1b-from_scratch-r2 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1b-full_history-r2 | failed | 1 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1b-resume_package-r2 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1c-before_modification-r2 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1a-after_observation-r3 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1a-before_modification-r3 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1a-after_applied-r3 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1b-from_scratch-r3 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1b-full_history-r3 | failed | 1 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1b-resume_package-r3 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |
| e1c-before_modification-r3 | passed | 0 | 6/6真 | completed | 30/30/10/0/0/0 | 无所列cleanup事件 |

“关组”展示原结果的检查，恢复/H00 是各自独立字段；缺失不会借用后来的环境恢复补齐。MCP 计数列为 wrapper invocation/return/without-return，既不是物理修改次数，也不能用 without-return 单独证明已经发出调用；完整逐 operation 明细保留在结果汇总。

| plan key | 主/备invocation/return/without-return | 同PID与startticks | stale拒绝数 | 旧请求状态 |
| --- | --- | --- | --- | --- |
| e1a-after_observation-r1 | 未提供 | 未提供 | 未提供 | 未提供 |
| e1a-before_modification-r1 | database-backup:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1a-after_applied-r1 | database:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1b-from_scratch-r1 | database:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1b-full_history-r1 | 未提供 | 未提供 | 未提供 | 未提供 |
| e1b-resume_package-r1 | database:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1c-before_modification-r1 | database-backup:1/1/0 | True | 1 | rejected_stale_fence |
| f12e5-r1 | 未提供 | 未提供 | 未提供 | 未提供 |
| e1a-after_observation-r2 | database-backup:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1a-before_modification-r2 | database-backup:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1a-after_applied-r2 | database:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1b-from_scratch-r2 | database:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1b-full_history-r2 | 未提供 | 未提供 | 未提供 | 未提供 |
| e1b-resume_package-r2 | database:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1c-before_modification-r2 | database-backup:1/1/0 | True | 1 | rejected_stale_fence |
| e1a-after_observation-r3 | database-backup:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1a-before_modification-r3 | database-backup:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1a-after_applied-r3 | database:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1b-from_scratch-r3 | database:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1b-full_history-r3 | 未提供 | 未提供 | 未提供 | 未提供 |
| e1b-resume_package-r3 | database:1/1/0 | 未提供 | 未提供 | 未提供 |
| e1c-before_modification-r3 | database-backup:1/1/0 | True | 1 | rejected_stale_fence |

## 首例环境失败与后续恢复

首例`e1a-after_observation-r1`原状态为failed，真实exit=1；原错误类：error_class=TimeoutError, close_error_class=ConnectError, restore_or_H00_error_class=ValueError。首次进入case前的launcher失败1次另列，不能与正式case失败合并。

| 恢复阶段 | 原状态 | 错误类 | 独立H00请求/成功/流程/失败/未知/未解决 |
| --- | --- | --- | --- |
| environment-recovery/resource-restore/result.json | failed | ValueError | 未提供 |
| environment-recovery/resource-restore-v2/result.json | passed | 未提供 | 30/30/10/0/0/0 |

正常关闭首失败群组的原 failed、`dissolve_notify_failed` 和 `no_cleanup_warnings=false` 保留。独立 passive 复查仅说明所查资源不存在，不能改写正常关组的失败或 warning；其中未曾创建的名字同样可能不存在。

| 原关组阶段 | 原状态 | 检查 | warning |
| --- | --- | --- | --- |
| environment-recovery/owned-group-close/attempt-1/result.json | failed | 7/8真 | dissolve_notify_failed |

| 独立检查 | 状态 | 覆盖 | exchange/queue | disposition |
| --- | --- | --- | --- | --- |
| environment-recovery/owned-group-close/passive-verification/result.json | passed | coordinator_and_forced_initial_database_only | 1/2 | partial_or_unconfirmed |
| environment-recovery/owned-group-close/passive-verification-v2/result.json | passed | all_seven_bound_identities | 1/7 | resources_verified_absent |

## E1-b 传输大小、失败与修复版本

以下三类证据分别列出：准备时计量、publisher 返回后保存的真实发送捕获、替代方确认。发送不等于收到确认，也不等于实验通过；确认缺失保持未提供。

| 方法 | 重复 | 状态 | 准备完整IFC | 捕获完整IFC | handover子对象 | 已确认完整IFC | 双package表示 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| from_scratch | 1 | passed | 1162 | 1162 | 338 | 1162 | False |
| full_history | 1 | failed | 18164 | 18164 | 17340 | 未提供 | False |
| resume_package | 1 | passed | 30591 | 30591 | 15046 | 30591 | True |
| from_scratch | 2 | passed | 1165 | 1165 | 340 | 1165 | False |
| full_history | 2 | failed | 18168 | 18168 | 17343 | 未提供 | False |
| resume_package | 2 | passed | 30590 | 30590 | 15046 | 30590 | True |
| from_scratch | 3 | passed | 1165 | 1165 | 340 | 1165 | False |
| full_history | 3 | failed | 18168 | 18168 | 17343 | 未提供 | False |
| resume_package | 3 | passed | 30588 | 30588 | 15045 | 30588 | True |

完整 IFC 字节包括整个 `args`，不是 handover 子对象大小。当前 resume_package 同时出现在 `args.resume_package` 与 `args.handover.package`。冻结汇总中首轮`e1b-resume_package-r1`捕获的完整IFC为30591字节，handover子对象为15046字节；同package双表示且值相等=True。该数字只描述该例，不代替其余重复。 不据子对象大小宣称结构化方案更省字节；三次重复以表内各自实际记录为准。`bytes/4` 只是估计，不是 tokenizer 计数或模型 usage。

已定位的 full_history 失败链涉及正式历史条目新增的可选 `aip_session_id` 与 Bridge 原白名单不一致，以及拒绝响应 `operation=None` 掩盖原 reason。独立修复只允许合法 session 元数据、先保留拒绝原因并维持 unknown 不重发；[离线修复证据](../evidence/handover-wire-fix-20261019/verification-summary.json)为 5 个新增方法与 34 个受影响既有方法，共 39 个不同方法通过，[独立审查](../evidence/handover-wire-fix-20261019/peer-review.json)另存。该修复已独立提交为`2b4e28b1bed6978710abb1a0cdf8835a5a6149bf`，原批冻结源为`c1c09e569ef67b7f0f0c2b2e8a948afec53f0c31`；修复未部署到本批冻结镜像、未在正式平台复验，原 full_history 失败不改判。

## T05 / T62 与捕获边界

闭合分析 overall_passed=False，T05双端匹配=False，T62=True，捕获覆盖完整=True。检查文件214份，已知秘密值68项；raw命中0、decoded命中0、解析/解码错误0。缺少必需捕获0项。

| plan key | Start | 期望/实际access | 缺失/多余 | 未完整生命周期 | 双端匹配 |
| --- | --- | --- | --- | --- | --- |
| e1a-after_observation-r1 | 6 | 12/11 | 1/0 | 1 | False |
| e1a-before_modification-r1 | 14 | 28/27 | 1/0 | 1 | False |
| e1a-after_applied-r1 | 13 | 26/25 | 1/0 | 1 | False |
| e1b-from_scratch-r1 | 14 | 28/27 | 1/0 | 1 | False |
| e1b-full_history-r1 | 11 | 22/21 | 1/0 | 1 | False |
| e1b-resume_package-r1 | 13 | 26/25 | 1/0 | 1 | False |
| e1c-before_modification-r1 | 14 | 28/28 | 0/0 | 1 | True |
| f12e5-r1 | 18 | 36/36 | 0/0 | 0 | True |
| e1a-after_observation-r2 | 14 | 28/27 | 1/0 | 1 | False |
| e1a-before_modification-r2 | 14 | 28/27 | 1/0 | 1 | False |
| e1a-after_applied-r2 | 13 | 26/25 | 1/0 | 1 | False |
| e1b-from_scratch-r2 | 14 | 28/27 | 1/0 | 1 | False |
| e1b-full_history-r2 | 11 | 22/21 | 1/0 | 1 | False |
| e1b-resume_package-r2 | 13 | 26/25 | 1/0 | 1 | False |
| e1c-before_modification-r2 | 14 | 28/28 | 0/0 | 1 | True |
| e1a-after_observation-r3 | 14 | 28/27 | 1/0 | 1 | False |
| e1a-before_modification-r3 | 14 | 28/27 | 1/0 | 1 | False |
| e1a-after_applied-r3 | 13 | 26/25 | 1/0 | 1 | False |
| e1b-from_scratch-r3 | 14 | 28/27 | 1/0 | 1 | False |
| e1b-full_history-r3 | 11 | 22/21 | 1/0 | 1 | False |
| e1b-resume_package-r3 | 13 | 26/25 | 1/0 | 1 | False |
| e1c-before_modification-r3 | 14 | 28/28 | 0/0 | 1 | True |

访问双端匹配与生命周期完整分列：中断任务缺 Complete 仍如实报告。JSON、JSONL、AMP 表示有重叠，不相加成独特流量；零命中不能覆盖缺文件、坏行或解码失败。此检查不是全部 broker/管理消息、官方 Monitor 入库、签名验签、长期在线或历史未知订单消解。

## 终态与停止范围

真实阶段退出：阶段1:exit1, 阶段2:exit0, 阶段3:exit0。本批自有项目停止收据status=stopped，remaining_running_owned=0。停止范围只以该收据为准，不据旧停机记录断言所有Windows服务或其他项目均关闭。

新独立 H00 的 pending=0 不解除旧批次的 7 个未知阶段；本批也不改旧 NEW7 E3 的 45 终态、37 确认、8 M1 未确认、11 条坏行及原 exit1。原始结果、失败、warning、修复版本与停止证据分别保留。

## 完整 P0 中仍需独立完成的验收

| 范围 | 剩余工作与边界 |
| --- | --- |
| T00 | 访问量/排行、Kafka TLS/认证与 Monitor 权限、匿名 AIC 与身份上限，以赛方答复为准；实验结果不是规则答复。 |
| T01 / 上游贡献 | GitHub 两 draft PR、四 Issue 及两套含重叠用例的 SDK 本地 suite 已有；AtomGit、最终 vendor 归属和上游 CI 仍独立处理，不重复开 PR/Issue。 |
| T02 / T07 / T63 | 短时巡检、保活与 30 分钟采样不代替登录/重启自启、24 小时无人工干预及更长窗口；不据本批开启 drills/high 自动审批。 |
| T05 | 本批18例各少1条双端access，共18条缺端，原因待追踪，当前T05未通过；3个E1-c与F12双端匹配通过。21例中断生命周期与F12完整生命周期另列，不用T62零命中替代访问对账。 |
| T06 | 已有真实七源卷 stdout、offset/续读证据；官方 Kafka 入库、Monitor 验签/查询、Discovery 展示仍待真实接入资料和证据。rename/copytruncate 不由本批补证。 |
| T11 / T96 | 同机新项目/新卷和缓存构建不代替新机器 15 分钟部署并一次跑通 F10；需独立机器实际记录。 |
| T12 / T32 / T61 | 按逐例结果判断本批 F15/E1、F12 能证明的范围，处理真实失败；方案要求的场景、重复与正式 AMQPS 证据仍逐项核。已有本地 F19 证据不重置，正式范围保持原降级边界。 |
| T22 | 正常审批和 stale-fence 拒绝不等于完整 E2-c 越权集逐条 audit 的 100% 拦截；沿用既有实现，缺证据另验。 |
| T44 / T50 | 工作台计划、审批历史、对账和浏览器证据已有；F10＋F15 连贯主演示及正式后台画面/录制仍需对应材料。 |
| T45 / T60 | 旧 E3 与本批分开，不重写 M1 失败、未知订单或性能结论；必要改进使用新源、新输出和对应授权。 |
| T90—T95 | 报告/佐证稿需吸收本批失败与限制；正式 3–5 分钟 MP4、最终材料、匿名扫描、分享目录与另账号可访问分别验收。PPTX 按用户安排暂缓。 |

已有身份/证书、业务契约、网关/ACS、资源域、接续基础和调度实现不整体重置；也不凭本批实验宣布全部 P0 完成。后续实跑须新输出目录、准确源/镜像/配置绑定、身份独占及对应范围授权。

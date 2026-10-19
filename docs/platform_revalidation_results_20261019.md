# 接续修复的正式平台复验结果（2026-10-19）

本批准备12例，实际尝试12例：通过11、失败1、未尝试0。原22例仍为18通过/4失败，保留原冻结版本和原判，不合并成功率。

冻结源码 `c75554d6b6de3bdaba53677e678a6fd35e4fef80`；本批仅覆盖 E1-a after_observation 与 E1-b 三种交接方式，不替代其余断点、E1-c 或 F12 的独立验收。

[完整证据入口](../evidence/platform-revalidation-20261019/PUBLICATION.md)汇集日志采集、失败诊断和投影绑定。

来源：[逐例与判据](../evidence/platform-revalidation-20261019/summary.json)、[进程终态与收尾](../evidence/platform-revalidation-20261019/closure-and-recovery.json)、[T05/T62闭合检查](../evidence/platform-revalidation-20261019/closed-access-credentials.json)。缺失指标写“未提供”，不补零。

## 分组与逐例

| 组别 | 断点/方法 | 计划 | 通过 | 失败 | 未尝试 |
| --- | --- | --- | --- | --- | --- |
| E1-a | after_observation | 3 | 3 | 0 | 0 |
| E1-b | from_scratch | 3 | 3 | 0 | 0 |
| E1-b | full_history | 3 | 2 | 1 | 0 |
| E1-b | resume_package | 3 | 3 | 0 | 0 |


| plan key | 状态 | OS exit | 关组检查 | 恢复 | 最终H00 秒/请求/成功/完整流程/失败/未知/未解决 |
| --- | --- | --- | --- | --- | --- |
| e1a-after_observation-r1 | passed | 0 | 6/6真 | completed | 30.016/30/30/10/0/0/0 |
| e1b-from_scratch-r1 | passed | 0 | 6/6真 | completed | 30.016/30/30/10/0/0/0 |
| e1b-full_history-r1 | failed | 1 | 6/6真 | completed | 30.0/30/30/10/0/0/0 |
| e1b-resume_package-r1 | passed | 0 | 6/6真 | completed | 30.015/30/30/10/0/0/0 |
| e1a-after_observation-r2 | passed | 0 | 6/6真 | completed | 30.0/30/30/10/0/0/0 |
| e1b-from_scratch-r2 | passed | 0 | 6/6真 | completed | 30.0/30/30/10/0/0/0 |
| e1b-full_history-r2 | passed | 0 | 6/6真 | completed | 30.016/30/30/10/0/0/0 |
| e1b-resume_package-r2 | passed | 0 | 6/6真 | completed | 30.016/30/30/10/0/0/0 |
| e1a-after_observation-r3 | passed | 0 | 6/6真 | completed | 30.0/30/30/10/0/0/0 |
| e1b-from_scratch-r3 | passed | 0 | 6/6真 | completed | 30.0/30/30/10/0/0/0 |
| e1b-full_history-r3 | passed | 0 | 6/6真 | completed | 30.0/30/30/10/0/0/0 |
| e1b-resume_package-r3 | passed | 0 | 6/6真 | completed | 30.016/30/30/10/0/0/0 |

关组列是本地六项正常关闭检查与告警判据，不是独立查询全部 broker ACL。恢复和新 H00 各自留证，不能改判接管失败或解除旧未知订单。

## 完整 IFC 字节比较

各格按 r1 / r2 / r3 排列，单位为 UTF-8 字节；计量对象是完整 IFC 文本，不包含 MQ/AMQP 封包。准备、publisher 返回后的实际发送捕获、替代方确认分别统计；发送捕获不是确认。

| 方法 | 准备完整IFC | 捕获完整IFC | 确认完整IFC | 捕获handover子对象 |
| --- | --- | --- | --- | --- |
| from_scratch | 1174 / 1174 / 1177 | 1174 / 1174 / 1177 | 1174 / 1174 / 1177 | 340 / 340 / 342 |
| full_history | 未提供 / 18413 / 18418 | 未捕获（0） / 18413 / 18418 | 未提供 / 18413 / 18418 | 未提供 / 17579 / 17583 |
| resume_package | 31017 / 31017 / 31022 | 31017 / 31017 / 31022 | 31017 / 31017 / 31022 | 15255 / 15255 / 15258 |

共有3例捕获包含 `args.resume_package` 与 `args.handover.package` 双表示；完整 IFC 才表示整个传输文本，不能把 handover 子对象大小当作完整传输量，也不据此宣称结构化交接节省字节。失败例缺失发送或确认时，不借用其他重复补齐。

## full_history-r1 失败与原批区别

本例保留 `failed`、runner exit `1`；原错误类：error_class=TimeoutError。该投影中的 resume 发送捕获数为 `0`，确认匹配为 `未提供`。

[首例独立运行补证](../evidence/platform-revalidation-20261019/diagnostics/full-history-r1-diagnosis-r2.md)记录重新发现时的 `official_discovery_failed / ConnectError`；未发送resume，未发生备用接管。主端trace有一次修改调用、一次非错误返回及after_applied退出钩子（意图exit83），但daemon历史die查询无返回，实际主容器退出码仍未知。现有证据不能确定连接失败的网络根因。

[第二例独立核验](../evidence/platform-revalidation-20261019/diagnostics/full-history-r2-review.md)确认7条合法会话历史被备用接受、发送与确认指纹相同，备用返回`skipped_already_applied`，未重复修改。第三例由正式逐例结果和匹配的发送/确认留证。本批全历史组为2/3，原批3次Bridge白名单拒绝保持原判。

## 进程停止与访问/凭据检查

| 阶段session | 实际OS exit | terminal |
| --- | --- | --- |
| 39454 | 1 | true |
| 10154 | 0 | true |

最终自有项目 stop=`stopped`，剩余运行 owned 容器=`0`，Compose stop exit=`0`；keeper terminal=`true`、exit=`0`。阶段退出码分别保留，外层首轮审阅 gate 的 exit1 不替代逐例结论。停止范围限本批项目，不推断其他应用已关闭。

| 检查 | 实际结果 |
| --- | --- |
| T05双端匹配 | false |
| Start / 预期access / 实际access | 158 / 316 / 304 |
| 缺失 / 多余 / 不完整生命周期 | 12 / 0 / 12 |
| T62 / 捕获覆盖完整 | true / true |
| 扫描文件 / 已知值 | 133 / 73 |
| raw / decoded命中 / 解析解码错误 | 0 / 0 / 0 |
| 闭合分析overall | false |

访问双端匹配、任务生命周期、凭据零命中分别判断；同一捕获的 JSON/JSONL/AMP 表示有重叠，不累计成独特流量。本批结果不改原22例的 T05 缺端及其独立诊断，也不代替 Monitor 入库或访问排行。

## 仍需独立完成

[Kafka/TLS 与 Monitor 实际接入和权限](../evidence/platform-revalidation-20261019/official-config-check/official-monitor-config-check-20261019.md)、官方入库及验签；独立新机器15分钟部署并跑通F10；24小时及更长稳定窗口；完整连续F10＋F15主演示与正式视频/佐证/匿名/分享材料；旧未知阶段、T05缺端和T01的AtomGit/最终fork绑定/上游CI继续分别处理。E2-c已有本地组件证据，仍不等同平台身份和生产CA验收。

[12页技术报告修订二](../deliverables/development-report-20261019-revision2/technical-report-development.pdf)的证据截止仍是412f791，未纳入本批12例，原PDF保持不变；它不是最终T90或全部P0完成证明。

生成依据 SHA256：

- `summary.json`：`d2e9f7ee61df106f10e15f7582e2e7ec5b47e1b3d4c32e0af33e4c56e17a8de1`
- `closure-and-recovery.json`：`025fffdeb61ec1f1916d5753420089f93ea9e057f717aa3188a6c8e589caadd0`
- `closed-access-credentials.json`：`e4c0622ead334c42a79095bbd64b2aaaa6bc318d75e95e4e873a47c49a55197e`

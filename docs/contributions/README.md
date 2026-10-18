# 上游贡献审阅包

2026-10-18 更新：新增[两个独立上游审阅包](upstream-review-20261018/README.md)，已对当前官方 `94077d1` 实际应用并验证；排序 3 项通过、日志修复前 2 负例失败 / 修复后 5 项通过，未变的 25 项接续检查复用历史证据。MessageEmitter 单独成 PR；四条 Issue 与两个 PR 的本地 payload 仍为草稿，外部 fork / Issue / PR 均未提交。下方保留原 2026-10-17 观察及旧 12 文件快照说明。


本目录是 T80 的四条 Issue 草稿与 T34 的 PR 说明，均未对外发布。
目标仓库为 [AIP-PUB/ACPs-community](https://github.com/AIP-PUB/ACPs-community)。
实现基线为 `3985c1330209f075c124669cc9d31f0e75448140`，SDK 包版本为 `2.2.0`。
材料描述 2026-10-17 本项目的观察，不把固定版本问题扩写为当前所有版本的问题。

| 文件 | 类型 | 主要依据 |
| --- | --- | --- |
| [01-task-result-order.md](01-task-result-order.md) | 缺陷 | 正式 AMQPS 的真实 journal；三项乱序回归 |
| [02-mq-endpoint-docs.md](02-mq-endpoint-docs.md) | 部署文档改进 | 正式站点公开 bundle 的 localhost 配置；随后成功使用的正式 Group API |
| [03-group-access.md](03-group-access.md) | 功能建议 | 新增可选 access 适配、Start 重放测试、本地任务对账 |
| [04-discovery-alive.md](04-discovery-alive.md) | 查询语义及接入文档改进 | 相同 AIC 条件下，仅改变 extFilter，HTTP 均 200，匹配数 0→2 |
| [PR-sdk-resumable.md](PR-sdk-resumable.md) | SDK PR 说明 | 实际源文件、示例、回归与接续验收 |

`payloads/` 的四个 Issue JSON 只含 GitHub 创建 Issue 所需的 title/body；PR JSON
保留待审阅的 head 占位，不能直接提交。正文与 payload 由本目录的
`prepare_review_payloads.py` 保持一致；脚本只读写本地文件。

`evidence/summary.json` 是最小脱敏摘录，去除了 provider、账号资料、私钥、EAB、
业务正文和参与者实际 AIC。未复制整份 journal 或原始 AMP 日志。

本地原始证据索引如下，路径相对项目根目录：

| 编号 | 原始材料 | 本包使用的内容 |
| --- | --- | --- |
| E01 | eval/results/platform/container-postgres-mcp-20261017-initial/coordinator/journal.sqlite | task_events.event_id 3/4/5 的状态与发送方时间；task_attempts 最后为 working |
| E02 | tests/test_task_ordering.py | 迟到 working 不回退、较新 Continue 可回 working、事件保留与终态保护三项 |
| E03 | integration/two-agent/endpoint-followup-20261017/REGISTRY-TOOLTIP-EXCHANGES.json 与 registry-client-list.response.txt | 公开 JS URL、响应 200、VITE_MQ_AUTH_URL 及弹层渲染路径 |
| E04 | integration/two-agent/RESULT.json | 正式 Broker / Group API 地址、双向两轮完整任务、退出成功 |
| E05 | vendor/ACPs-community/acps-sdk/tests/resumable/test_resumable.py | 官方 Group client 的可选统计、重放及失败语义测试 |
| E06 | eval/results/local/scheduling-native-20261017/access-reconciliation.json | 33 次 Start、双方合计 66 条 access、无多计漏计；仅本地 stdio 对账 |
| E07 | integration/incident/discovery-root-cause.json | requests[0] default 与 requests[1] all-alive-statuses 的完整请求/响应 |
| E08 | integration/two-agent/approved-agent-discovery-by-aic.json | 早先按 AIC 查询为空的原始响应；只作为症状补充 |
| E09 | eval/results/local/F15-native-20261017-initial/results.json | 三个真实本地进程崩溃点、PG MCP 修改各一次、重复零次、旧 fence 拒绝 |
| E10 | eval/results/platform/container-postgres-mcp-20261017-order-fix-v2/results.json 与 coordinator/messages.jsonl | 修复后的正式 ADP/三身份 describe/完整生命周期、实际 PG MCP 只读观察成功 |
| E11 | eval/results/local/model-fairness-formal-v2-20261017/sdk-snapshot-addendum.json 与 source/vendor/ACPs-community/acps-sdk/ | 正式乱序修复前 67 份 SDK 文件快照；保留历史实验实际导入的字节 |
| E12 | docs/contributions/sdk-review-20261017/manifest.json、acps-sdk-high-score.patch 与 validation.json | 冻结 v0.2 SDK 到当前 SDK 的独立 12 文件补丁；临时副本 apply-check 与应用后逐文件 hash 一致 |

SDK 独立审阅补丁由 `prepare_sdk_patch.py` 调用既有 `sdk_patch(root, baseline)` 生成，
不调用完整业务 overlay 导出器。旧 `artifacts/high-score-source-20261017/` 的 11 文件
SDK 补丁缺少后续乱序修复，不与本次 12 文件补丁混用。补丁默认不覆盖已有输出目录，
manifest 记录基线、逐文件来源 SHA256 与既有 3+25 项测试引用，未为导出重复运行测试。

SDK 导出快照建立时，新 E1 曾因缺用户明确资源授权而被拒绝。之后用户授权并完成本地
18 例最终验证：E1-a 为 8 连续、1 控制器中断后仅续验，E1-b 各策略 3 连续。数据库 MCP
修复共 18 次、重复 0，旧 fence 18/18 拒绝，实际模型用量 0；独立分析问题 0。
原中断、旧 F15 三个单次结果和三身份正式只读复验分别保留，不把这些称为正式 ADP
接管验收。详见[接管评测记录](../resume_evaluation.md)，只读 SDK 导出快照及补丁字节保持不变。

MQ 的 `transport=AMQP`、URL 的 `amqps://` 和能力值 `amqp:0.9.1` 属于不同字段。
本轮未找到仅改变某个 MQ 协议值就造成发现失败的成对原始请求，故没有单独声称这一类
平台缺陷。Issue 02 仅建议在示例中说明字段关系。

T80 的“至少四条已发布 Issue 链接”和 T34 的“已提交 PR 链接”仍需用户审阅后实际发布；
本地草稿与 payload 不计为这两项验收完成。

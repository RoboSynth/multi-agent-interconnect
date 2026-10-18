# 历史基线证据说明

本文摘录2026年10月17日的既有记录，供团队阅读历史README；不替代原始结果文件，不代表本轮新增运行。原始任务消息、身份与任务标识、私有配置和本机路径继续保留本地。

<a id="two-agent"></a>
## 双向梧桐任务

原摘要记录结束时间为 `2026-10-17T03:58:57.973043+00:00`：两轮任务均完成，`run_success=true`、`exit_code=0`、`connections_closed=true`；两轮状态均为 accepted → working → awaiting-completion → completed。这里只摘录状态和退出事实，不附回传消息、AIC、群组或任务ID。

既有[公开安全摘要的mq字段](contributions/evidence/summary.json)保留双向成功与两轮状态；[当时接入说明](../integration/BUILD-VERIFICATION.md)记录范围。原件 `integration/two-agent/RESULT.json` 的SHA256为 `d24a75f033a4d6d94b5f26cfc4a16a10cf7ed6bc9d123f882bd13efd0ae5c76d`。本段事实来自该历史摘要，未重新连接或运行平台。

<a id="campaign-425"></a>
## 旧425项本地场景与断言

2026年10月17日最终报告列出：

| 测试分类 | 场景/断言数 | 符合预期 | 失败 |
|---|---:|---:|---:|
| 状态一致性 | 195 | 195 | 0 |
| 协议与边界 | 192 | 192 | 0 |
| 故障恢复 | 38 | 38 | 0 |

合计425项包含重复和种子变化，不等于425种独立故障。符合预期也包含安全停止和转人工。原报告另存早期30及28条原始失败计数、harness误报分析、首次启动门禁失败和最终退出v1进程误判；这些历史失败未被本说明改写。累计1439项包含中间轮次、失败和复测，不作为新增独立样本数。

该轮使用官方SDK v2.2.0、本地独立进程、HTTP/SQLite和规则诊断；未接入梧桐mTLS/正式AIC、大模型或官方ADP。部分归档未保留原始HTTP状态码，不能事后重建其精确数值。它不证明当前PostgreSQL版本、正式平台接管或长时在线能力。

原件 `artifacts/campaign-20261017-final-v2/REPORT.md` 的SHA256为 `9907dac7ffeb61e817646d3cd8c3ba596cd363824a6606074fa17fed1e78b989`。本说明只摘录上述表格与边界；原报告含本机绝对路径，完整原件与中间失败仍在本地保留。

<a id="first-rejection"></a>
## 首次注册驳回

`2026-10-17T03:21:45.653944+00:00` 的首次驳回快照中，两份提交的provider均为空对象；协调者另缺有效Endpoint或webAppUrl。原记录不能证明其它字段已通过，也不能推出平台对创新、企业资格或实名要求作了何种判断。它不是当前仍被驳回的状态声明；后续正式获批与真实任务往返分别见对应记录。

[既有公开原因研究](../integration/two-agent/rejection-research/REPORT.md)已经区分提交时即为空与服务器后来覆盖provider的推测。本段不复述逐身份URL或登记资料。原件 `integration/two-agent/rejection-analysis-v1.json` 的SHA256为 `b3b30a8ee9346de252cb4c763816a30996030101db6342cfc3ce6ad2e428a50b`。

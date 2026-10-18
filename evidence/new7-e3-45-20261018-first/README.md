# NEW7 E3: 37/45 confirmed recovery

This is the NEW7 AMQPS / Docker cohort with context32768. All45 rows, failed/unconfirmed cells and missing usage remain visible. Matrix/outer exits and the independent final H00 are in verification.json and final-h00.json. Successful act-task products include idempotent skips; they are not actual restart counts. Token panels use reported usage only; missing provider usage is unknown and costs may be lower bounds. The old native/context8192 cohort and single capacity request are separate evidence.

Existing scheduling_report/plot_results supply all statistics. The figure title alone has the recorded exact label correction. The exported comparison figure passed root visual review; failures and limitations are retained.


## 中文结果说明与限制

1. 本批为同一冻结版本的 NEW7 AMQPS / Docker、context32768 正式矩阵：45 个唯一终态，37 格确认持续恢复、8 格 needs_attention。M0 与 M2 各 15/15，M1 为 7/15；原矩阵与外层监督实际退出均为 1，失败完整保留。本批五场景中，M2 总协调耗时中位数均高于 M0，且产生模型 token 成本，不能据此宣称全面性能领先。旧 native/context8192 结果和单次容量调用另列。

2. 8 个未确认格均为 M1 的本地 POST 前保守 token 预算拒绝，没有对应的新模型 POST，不计入表内按已发送请求记录的 model_failures。已记录模型调用共 277 次、usage 完整、648020 tokens：M1 为 163 次/512027 tokens，M2 为 114 次/135993 tokens，M0 为 0。成功 act 产物 162 包含幂等跳过；资源域返回状态为 applied 78、skipped_already_applied 84、rejected_precondition 18，它们不是实际物理副作用数或 MCP 调用数。详见[独立审阅](independent-review.json)。

3. 原 workload 仍有 7 个未完成意图阶段：5 create、2 cancel，其中 F01/M1/r3 的 cancel 尚未发送，其余 6 个阶段存在原 POST 尝试/unknown 历史。独立只读观察仅做 7 次原键回执 GET，全部 404；没有补单、取消或重提，404 不足以证明未执行，也没有解决这 7 个旧流程。最终新 H00 为 30.016 秒、30 次成功请求、10 个完整流程，failed/unknown/unresolved/pending 均为 0；它不解除旧键。见[旧未决意图](pending-intents.json)与[独立 H00](final-h00.json)。

4. T62 对 5 个明确文件、8,228,226 字节及 63 个已知私密值作有界检查，原文与可解析字段命中均为 0；AMP 的 4509 个物理行中有 11 行 JSON 解析失败，其余 4498 行可解析。因此该运行期扫描 overall passed=false，不能写成全面解析通过，也不能据解析失败声称凭据泄漏。详见[原安全扫描投影](credential-scan.json)。本公开文件包的发布扫描与该运行期扫描是不同检查。

5. 首次只读 postcheck 只有路由原始字节检查失败：末态为 CRLF，初始文件为 LF，单条 upstream 指令语义相同。之后实际进行 1 次文件写入恢复精确 LF，公开 ready GET 为 v2；没有 Nginx reload、Docker/数据库动作或追加故障。原失败观察、原恢复记录及其“0 actions”字段过宽的澄清都按 SHA 保留；不回写矩阵末态摘要。见[收尾与换行复原](postcheck.json)。

6. 捕获 stderr 为 110 字节、1 行 broker 主动 cancel。四类指定 SDK cleanup 事件未记录，正常自有群组 close 通过；这不等于所有 warning 为 0，也不是全 broker/ACL 库存审计。图已完成实际视觉审阅；原统计、全部失败行及 PNG/SVG 数值保持不变。

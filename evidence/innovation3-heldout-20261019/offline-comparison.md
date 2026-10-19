# G4：冻结 E3 的离线动作与耗时核对

保留原 45 格及全部失败；本次没有运行新故障、平台或模型。

| 方法 | 恢复/15 | 诊断正确/15 | 观察总数 | act 尝试/ok | high 调用 | 无关 act 尝试/applied | 幂等跳过 | 耗时中位秒 | token 总数 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M0 | 15 | 15 | 108 | 24/24 | 12 | 0/0 | 0 | 42.657 | 0 |
| M1 | 7 | 3 | 20 | 132/114 | 99 | 47/14 | 84 | 43.64 | 512027 |
| M2 | 15 | 15 | 99 | 24/24 | 12 | 0/0 | 0 | 86.906 | 135993 |

applied 是账本返回，不代表已证明实际产生一次物理副作用；幂等跳过单列。high 调用包含重放和被拒的请求。

M0/M2 的无关 act 尝试分别为 0/0，无关 applied 返回分别为 0/0，未显示 M2 减少无关修改。M2 观察 99 次、M0 108 次，减少 9 次（8.3%），但两者都恢复 15/15、15/15，M2 耗时更长。

M2 总耗时 1325.670 秒，其中模型请求 623.720 秒（47.0%）、观察任务 145.536 秒、act 36.622 秒（含审批）、独立验证任务 518.499 秒。模型请求是最大可优化项；其内部推理/排队不可分，验证任务中实际业务窗口与其他开销已在逐行 timing 中分列。

按原任务顺序回放，57 次模型请求位于必选/唯一个观察或最终验证位置，原时间线上合计 307.656 秒。新 M2v2 只跳过这些无排名选择的位置；该数值不能当作新版节省耗时，后续模型输出和任务顺序可能改变，必须真实配对复验。

M0 只固定观察顺序，修复仍继承同一个 EvidencePlanner；F01+F07 不会自动超出它的修复能力。F04 设计已存在，但原 M0/M2 均缺池容量回退规则，新增注入支持不等于有了恢复优势。

- No new model, platform, resource or fault execution.
- Cause-related actions use evaluator ground truth only in offline analysis, never in coordinator inputs.
- Applied products are operation ledger reports; physical side-effect counts remain unknown.
- Idempotent skips are retained separately and never counted as physical modifications.
- No separate broker queue, pure inference or observation network RTT telemetry exists.
- M0 shares EvidencePlanner repairs with M2; F01+F07 is not guaranteed to defeat M0.
- Retrospective avoidable model seconds are not measured M2v2 savings.

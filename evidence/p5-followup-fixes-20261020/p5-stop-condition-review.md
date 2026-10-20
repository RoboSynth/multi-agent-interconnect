# P5 稀疏预测与提前停止：只读诊断

核查范围：本轮冻结 `p5-local60-20261020/matrix-r1` 与 canonical `751cf46` 的 planner/engine/tests。两份 planner 源码一致；没有修改本轮 source/results。

## 已发生的真实失败

`matrix-r1/incidents/inc-577ee931f2114e52.json`（F06 / M2v2 / repeat 1）：模型一次调用 HTTP 200、validated、7.0 秒；入口确认 running/v2。模型存活候选分别只预测 route=v2、application=unreachable、read_only=ro、blocking=blocked，遗漏的预测仍是 unknown。

剩余 `application.status`、`db.read_only_status`、`db.blocking_sessions` 的 discrimination/score 全为 0。实际只运行两项入口观察与最终 verification；修复 0 次，business_recovered=false，status=needs_attention。这不是模型 HTTP 失败，也不是已经完成充分诊断。

## 根因位置

- `incident/coordinator/hypothesis.py:45-55,185-189` 明确允许稀疏预测，提示词声明缺预测是 unknown，不是 impossible。
- `incident/coordinator/planner.py:73-84` 的区分度只统计“两候选都预测同一工具且结果互斥”的候选对。一个工具只有一个候选预测时，无法形成这样的候选对，所以 D=0；这是当前分数定义，不能据此证明无须观察。
- `incident/coordinator/incident_planner.py:39-57` 只选择 D>0 的工具，没有候选确认路径。
- `incident/coordinator/engine.py:357-371` 未选探测就转最终验证；由于仍有候选，all-candidates-contradicted 的重生成也不会触发。
- `tests/test_p5_incident_scheduling.py:171-177` 把单一候选 D=0 直接停止当作预期，现有复合故障测试使用较完整 rule_hypotheses，未覆盖真实合法稀疏模型输出。

## F07 / F10 的影响边界

同样稀疏预测在 F07 的 running/v2 入口后也会留下 application/只读/阻塞候选，D=0，尚未查只读就停止。F10 先有 v1 的确定路由证据，因此会修路由；若业务快检仍失败且数据库候选仍只有各自单项预测，后续仍可能 D=0 而漏查只读。以上是共享控制流推断；本诊断时本轮尚未产生它们全部真实结果，不能写成已观察到的 F07/F10 结论。

## 最小修复与行为验证

保留现有正区分度排序。仅当没有正区分度探测可选时，从存活候选明确预测、尚未观察、平台确实提供且预测不是“所有结果皆可”的工具中，按成本选一项作候选确认，再按新证据重算。缺预测不补成正常/异常值，不因此排除候选；不把所有未观测工具加入兜底，不并发扫完所有域。停止仍须保留现有最终业务验证，不能把候选确认等同修复成功。

必要离线行为测试：真实形状的稀疏候选在 F06 能查阻塞并精确修复；F07 查只读并保留池 revision 安全约束；F10 路由修复后的快检失败继续查数据库；单候选未确认预测会补查；缺预测不会被证据排除；全结果预测/无候选相关工具不会触发无意义全查；快检通过后不查额外域，最终验证不变。

MR/F01 的 504 症状识别属于另一个基线缺陷，必须单独修复和披露；本轮 MR 失败不能作为 M2v2 创新优势。

## 独立修复供审核（未合回 canonical）

worktree：`incident-pilot/artifacts/p5-sparse-confirmation-20261020/checkout`，分支 `codex/p5-sparse-confirmation-20261020`，基于 `751cf46`。

- `3c148a8`：只改 IncidentPlanner 的零区分度确认路径、相关行为测试和未来实验 M2v2 定义。正区分度仍优先；无正区分度时仅选一个明确且非全结果预测，缺预测继续是 unknown。未来方法编号 `evidence-ranked-per-incident-v4`，本轮 v3 记录保持原样。
- `17704b8`：公共症状分类把 HTTP 504 与已有 502 一同识别为 entry_error，503 保留 write_error 语义；MR 固定剧本本身未扩展。真实首例记录（`inc-3c9541e9e9594ac6`）的三个 504/unknown 公共事件保存为离线 fixture；测试确认走 restart/route 剧本，未触及数据库。未来方法编号 `symptom-runbook-guarded-v2`。
- 邮件格式 patch 在上述 worktree 的同级 `patches/`；两个提交可分别审核。

验证：修改前新增稀疏测试出现 5 个预期失败；修复后对应 18 项全通过。加入 MR fixture 后修改前 2 个预期失败，最终 P5 离线 20 项（含 HTTP 502/504/503 三个子场景）、公开订单版本/未知结果语义 8 项全部通过。日志在该 worktree 同级 `tests-before.log`、`tests-after.log`、`mr-tests-before.log`、`mr-tests-after.log`、`public-version-tests.log`。这些是模拟资源/模型的离线行为结果，不是新故障实验，不证明真实修复成功率或创新收益。

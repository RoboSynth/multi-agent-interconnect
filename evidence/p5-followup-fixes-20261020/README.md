# P5 后续修复：离线审核包

两个修复在独立 worktree 完成，基于 `751cf465222839db7bd87ec31a2ad0c52317359a`，分支 `codex/p5-sparse-confirmation-20261020`。本轮60格结束、健康检查及停机完成后，原审核提交已通过`935e325`合入开发分支，补丁与原离线日志保留在本目录。

**本目录保留28项原离线行为测试；合并长编号修复后的47项相关组合检查也已通过，仍不能宣称真实修复率、耗时或创新效果已经改善。** [已闭合60格](../p5-local60-20261020/README.md)继续使用冻结的M2v2 v3 / MR v1，原source、results、失败及方法定义保持不变。未来新批次使用新定义并重新验证，不覆盖或混算旧结果。[组合检查](../highscore-continuation-20261020/integration-validation.json)

## 两个独立提交

| 提交 | 最小变更 | 未来方法定义 |
| --- | --- | --- |
| `3c148a8` | 正区分度排序不变；零区分度时，按成本逐项确认存活候选明确、未观察且非全结果的预测。缺预测继续是 unknown，不补全为正常或异常，不扫描所有未观察工具。 | M2v2 `evidence-ranked-per-incident-v4` |
| `17704b8` | 公共症状分类把 HTTP 504 与已有 502 一同视为入口错误，保留 503 写错误语义；使用真实 F01 公共症状记录作离线 fixture，未扩展 MR 固定剧本。 | MR `symptom-runbook-guarded-v2` |

本轮 60 格仍为 `evidence-ranked-per-incident-v3` / `symptom-runbook-guarded-v1`。MR 对 504 的误分类是基线缺陷，不能作为 M2v2 的创新优势。

## 文件与验证

- [根因、代码位置与修复边界](p5-stop-condition-review.md)：F06 真实失败的稀疏预测证据，以及 F07/F10 的同构控制流风险。
- [补丁 1：稀疏预测确认](patches/0001-Confirm-sparse-incident-predictions-before-zero-disc.patch)。
- [补丁 2：504 公共症状分类](patches/0002-Classify-gateway-504-as-entry-symptom-for-the-guarde.patch)。
- [P5 离线行为测试：20 项通过](test-logs/p5-offline-20.log)：稀疏预测 F06/F07/F10、单候选确认、unknown 与全结果边界、按需停查、审批及 revision、最终验证；含 502/504/503 三个分类子场景。
- [公开订单版本语义：8 项通过](test-logs/public-order-version-8.log)：保留未知结果、原请求键、版本契约和完整订单流程语义。

测试在 Windows 独立 worktree 运行，资源与模型均为离线模拟；没有新启动故障实验、模型 API、云端身份或群组。测试命令为 `python -m unittest discover -s <worktree>/tests -p test_p5_incident_scheduling.py -v`，以及同样入口的 `-p test_public_order_version.py`。本目录日志直接复制已完成的验证记录，整理时没有重复运行测试。

原始 worktree 与修改前失败日志保留在本机 `incident-pilot/artifacts/p5-sparse-confirmation-20261020/`。邮件格式patch包含完整变更与真实公共症状fixture；已按审核版本合入，不替换本轮冻结实验代码。组合检查没有重跑真实故障。

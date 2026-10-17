# 完整工具 M1：两批 F01 开发验收

首批持续恢复2/3，保留M1 unknown；共享route守卫修复后三方法各一次均恢复3/3。两批分开统计，不计作完整工具M1的45项正式矩阵，也不与历史M1-observe混合。

| 批次 | 方法 | 恢复 | ok修改 | MCP修改调用 | high/额外high | 模型调用/token | 总协调+验证秒 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| first | M0 | True | 1 | 1 | 1/0 | 0/0 | 35.609 |
| first | M1 | False | 0 | 1 | 0/0 | 2/2109 | 10.031 |
| first | M2 | True | 1 | 1 | 1/0 | 7/7175 | 67.407 |
| shared-guard-v2 | M0 | True | 1 | 1 | 1/0 | 0/0 | 35.407 |
| shared-guard-v2 | M1 | True | 2 | 2 | 2/1 | 6/8996 | 37.219 |
| shared-guard-v2 | M2 | True | 1 | 1 | 1/0 | 7/7597 | 72.328 |

首批M1的0个ok修改不等于无资源调用：它真实执行一次route MCP，返回error，账本unknown。必要Nginx窗口保留2条reload信号notice与7条/health 499原文及行号。reload信号不是重载完成证明；日志与源码支持health确认超时后恢复路径再reload的因果推断，MCP错误正文未完整归档，不能补造。

修复在共同资源域加入route expected_before=v1，三方法共用；v2 M1仍选过错误route和缺证据pool动作，均被拒绝，随后多做一次不必要的db.restore_writes高权限动作。业务恢复不等于动作最优，M1 repair_action_match仍false。

同声明输入包括F01症状、工作负载seed101、模型seed42、temperature0、top_p1、max_tokens768、40任务/40模型调用/65536token/600秒预算。版本边界包括Bridge与共同policy守卫变更；自适应交互、模型响应及已有资源revision/PID可能不同，不能称两批完全相同运行状态。

`seconds`包含协调与30秒独立验证。1rps首次恢复/最早30秒10流程确认另列，不能将总耗时叫纯恢复时延。v2 M1比M0更少观察，但成功修改和高权限调用更多；M2本次仍比M0耗时更长。单次样本不作总体效率结论。

`diagnosis_exact_match`比较协调器按事实映射的diagnosed_causes与评测真值；不把该指标称为模型显式根因解释准确率。

每cohort的model-responses.json只保留真实响应、usage、参数和HTTP/finish状态，未导出prompt/context/schema；模型hash/采样/预算在experiment.json。输入hash索引保留原始证据定位，原始事故/消息/域日志/注入记录留本机。

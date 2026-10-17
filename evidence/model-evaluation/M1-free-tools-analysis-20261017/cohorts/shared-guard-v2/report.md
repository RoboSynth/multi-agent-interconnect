# 完整工具 M1：F01 开发验收（shared-guard-v2）

三方法各一次，业务持续恢复 3/3。本批是开发验收，不是45项正式矩阵；不与历史M1仅选择观察的结果合并。

| 方法 | 状态/持续恢复 | 观察数 | ok修改任务 | 真实MCP修改调用 | high调用/其中额外 | 总协调+验证秒 | 首次恢复估计秒 | 模型调用/token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M0 | completed/True | 7 | 1 | 1 | 1/0 | 35.407 | 7.734 | 0/0 |
| M1 | completed/True | 1 | 2 | 2 | 2/1 | 37.219 | 6.671 | 6/8996 |
| M2 | completed/True | 6 | 1 | 1 | 1/0 | 72.328 | 10.687 | 7/7597 |

`modifications`只计返回ok的act任务；真实MCP调用由域system事件独立计数，可能返回错误或没有形成成功修改。`high_privilege_calls`只计high风险调用，风险write的route动作不在其中。

耗时`seconds`包含诊断、模型等待、审批和独立30秒域验证，不是纯修复时延。首次恢复为统一1rps观察估计；最早30秒/至少10流程确认见case-rows，失败保留null。

M0不调用模型；M1自由选observe/act/verify，无规则回退；M2为模型假设加确定性排序。所有方法共用工具、资源域守卫、审批、账本和预算。

`diagnosis_exact_match`按协调器从事实映射的diagnosed_causes与评测真值集合比对；它不证明自由工具M1输出了显式根因解释。

模型证据仅导出真实响应、usage、采样及参数；完整prompt/context/schema保留本机，未复制。usage总token包含prompt与completion，provider报告的cached_tokens原样保留，不将缓存token误算为0。

修复后M1依次选择containers→restart→route_rollback(rejected)→pool_rebuild(rejected)→restore_writes→verification。它最终恢复业务，但比M0/M2多一次不必要的high调用和一次ok修改；动作精确匹配仍false。route/pool拒绝没有对应MCP修改调用，原route未知失败保留在首批。

共享route expected_before=v1守卫在三方法中同时生效，未向模型加入F01答案。该变更发生在首批失败后，版本分开列出；同场景、种子、模型、预算不等于每次自适应模型对话完全相同。v2控制进程已捕获exit0，三项完整恢复仅支持本次开发验收。

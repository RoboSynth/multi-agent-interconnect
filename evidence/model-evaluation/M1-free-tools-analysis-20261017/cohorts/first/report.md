# 完整工具 M1：F01 开发验收（first）

三方法各一次，业务持续恢复 2/3。本批是开发验收，不是45项正式矩阵；不与历史M1仅选择观察的结果合并。

| 方法 | 状态/持续恢复 | 观察数 | ok修改任务 | 真实MCP修改调用 | high调用/其中额外 | 总协调+验证秒 | 首次恢复估计秒 | 模型调用/token |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M0 | completed/True | 7 | 1 | 1 | 1/0 | 35.609 | 7.781 | 0/0 |
| M1 | needs_attention/False | 1 | 0 | 1 | 0/0 | 10.031 | None | 2/2109 |
| M2 | completed/True | 6 | 1 | 1 | 1/0 | 67.407 | 10.766 | 7/7175 |

`modifications`只计返回ok的act任务；真实MCP调用由域system事件独立计数，可能返回错误或没有形成成功修改。`high_privilege_calls`只计high风险调用，风险write的route动作不在其中。

耗时`seconds`包含诊断、模型等待、审批和独立30秒域验证，不是纯修复时延。首次恢复为统一1rps观察估计；最早30秒/至少10流程确认见case-rows，失败保留null。

M0不调用模型；M1自由选observe/act/verify，无规则回退；M2为模型假设加确定性排序。所有方法共用工具、资源域守卫、审批、账本和预算。

`diagnosis_exact_match`按协调器从事实映射的diagnosed_causes与评测真值集合比对；它不证明自由工具M1输出了显式根因解释。

模型证据仅导出真实响应、usage、采样及参数；完整prompt/context/schema保留本机，未复制。usage总token包含prompt与completion，provider报告的cached_tokens原样保留，不将缓存token误算为0。

首批M1观察到应用退出后误选route_rollback；操作unknown且协调停止，无盲重试。成功修改0同时存在真实MCP修改调用1，returned is_error=true。必要Nginx窗口原文记录2条reload信号notice和7条GET /health 499。日志与工具源码支持health确认超时后恢复路径再reload的归因，该因果判断是推断，不把reload信号当作重载完成证明。nginx-evidence.json只保留必要9行，活跃源日志hash指采集时快照；原MCP错误正文未完整归档，不能补造异常原文。

原控制进程已退出但未捕获操作系统退出码；报告生成exit0只表示离线派生成功，不代表原实验无失败。

# 本地调度对比与证据口径

`eval/run.py` 在同一套真实 Windows 进程、Nginx、PostgreSQL 和独立资源域
worker 上运行场景。传输是 `local-aip-stdio`，不是正式平台 AMQPS/ADP 验收。

三种方法共享工具、事实、域内策略、审批签名、操作账本和业务验证。

| 方法 | 实际决策范围 | 模型失败处理 |
| --- | --- | --- |
| M0 | 冻结顺序全部观察，再按确认事实处置 | 不调用模型 |
| M1 | 模型自由选择下一项未完成观察；共享事实确认后的处置规则 | 停止本次排查，记 `llm_failed`，不转用规则选择 |
| M2 | 模型输出假设与工具预测，按区分度/成本排序，动态调整依赖与处置 | 每轮最多两次，失败转规则并记录 `rules`/`mixed` 与次数 |

M1 的准确名称是“自由观察选择 + 共享处置”，不代表模型可任意调用写工具。
三种方法都先执行共同要求的冲突复探、连接池 revision 确认，再进行各自的观察选择。
M0 的模型成本是零；M1/M2 使用相同模型和上限，实际调用数、token 由各自方法决定。

固定参数为 `temperature=0, top_p=1, seed=42, max_tokens=768`。默认每次排查
最多 40 项 AIP 任务、40 次模型请求、65536 个模型总 token、600 秒协调时限。
请求前以 UTF-8 字节上界和固定封装余量预留输入，再限制输出；服务端 usage
仍为统计依据。返回缺少 usage 时标 `token_usage_complete=false`，数值仅是已知部分。
失败请求也计调用数，已收到的失败输出也计 token。

模型预测只接受五项观察的枚举：`exited/running`、`v1/v2`、
`reachable/unreachable`、`ro/rw`、`blocked/clear`。提示包含各工具的输入 schema、
事实键、可观察枚举和成本；建议性文字不能作为预测通过校验。

正式矩阵命令（先保证原生资源的独占注入窗口）：

```powershell
.\.venv\Scripts\python.exe eval\run.py `
  --config runtime\local-coordinator.json `
  --runtime deploy\native-runtime.json `
  --scenarios F01,F02,F06,F07,F10 --methods M0,M1,M2 --repeats 3 `
  --approve-high --enable-llm `
  --model-base-url http://127.0.0.1:8089/v1 --model Qwen3-1.7B-Q8_0 `
  --instance-seeds 101,202,303 --output eval\results\local\YOUR_NEW_RUN
```

`--approve-high` 只预授权该运行器的实验室修复，仍生成绑定动作参数和 operation_id
的真实审批证明。审批请求/决定时间保留在事件中，汇总另计等待秒数。
每个场景的三次重复轮换方法顺序。重复使用不同的请求内容种子与 0/1/2 次
健康连接池预热；PID、阻塞会话和 revision 随真实实例变化。这个留出范围是
同类故障下的负载/资源实例参数，不是新故障家族或跨部署泛化实验。

背景观察器从注入前 3 秒开始，以 1 rps 贯穿故障和协调过程，保留原请求键、
取消键、回执核验与未知状态。每次请求时限 0.8 秒，避免锁等待形成补发突刺；
成功响应还必须含 `order_api_version=v2`，从而识别旧路由的契约缺失。
故障至少暴露 3 秒后启动协调。资源域验证器另外执行相同的 30 秒、1 rps
独立复核；两条流分别记录，不能把验证期间总请求量写成恒定 1 rps。

时间字段不能混用：

| 字段 | 定义 |
| --- | --- |
| `seconds` | 协调启动到诊断、处置和域内业务验证结束的总耗时 |
| `recovery_observed_seconds` | 注入开始到最后一次坏样本之后的首次成功，属于 1 rps 采样估计 |
| `recovery_confirmed_seconds` | 注入开始到持续健康至少 30 秒、完成至少 10 个流程且原意图清空的确认时间 |
| `approval_wait_seconds` | 已决定的高风险审批等待时间之和 |

正式 v2 运行保留的原始 `recovery_confirmed_seconds` 实际取观察器停止时刻，可能晚于
最早达标时刻。为保留原始证据，离线运行 `eval/scheduling_report.py <运行目录>`，
由注入进程的真实 onset 和逐请求记录重算最早满足窗口与意图完成的前缀，结果存为
`analysis-rows.json` 的 `recovery_confirmed_earliest_seconds`。图表使用该修正字段，
不覆盖原始 results。首次恢复估计 `recovery_observed_seconds` 不受此问题影响。

协调者只按真实观察事实记录 `diagnosed_causes`。场景编号和真实根因仅在评测器
端，`diagnosis_exact_match` 对比两个根因集合。该值表示证据确认的诊断是否匹配，
不把模型候选假设的自然语言命中率当成相同指标。修改匹配和不必要高权限调用
也仅由评测器对照预登记的必要修复集合计算。

每次运行保留 `experiment.json`（模型/源码摘要、参数和预算）、`source/` 冻结源码、
逐项 `results.jsonl`、汇总 JSON/CSV、incident 原始模型输出/usage/HTTP 错误、
持续请求 JSONL、原始 AIP 消息和私有注入记录。失败和中止保留，不从统计中
挑除；另行修复后的运行使用新目录。`model-fairness-smoke-20261017` 是较早的
单场景烟测，未包含本正式背景流协议；被中止的单次矩阵有 `interruption.json`，
不混入正式 45 次统计。`model-fairness-formal-20261017` 是共享冲突复探缺陷确认后
中止的首次正式尝试，也保留 `interruption.json`；修复后完整矩阵使用新目录。

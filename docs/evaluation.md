# 本地调度对比与证据口径

`eval/run.py` 在同一套真实 Windows 进程、Nginx、PostgreSQL 和独立资源域
worker 上运行场景。传输是 `local-aip-stdio`，不是正式平台 AMQPS/ADP 验收。

## 2026-10-18矩阵收尾修复与运行状态

`eval/run.py` 已将每格前置restore、观测器构造/启动和后续运行置于同一受保护范围。清理观测器的finish即使抛错，内层finally仍尝试最终场景restore；多个错误保留Python异常上下文链，外层仍关闭transport。16项离线测试实际通过，含8种前置复原、部分启动、finish、apply与清理失败组合，核对清理顺序、transport.close一次、失败分支不生成成功行。测试使用mock，不调用真实模型或资源；[精简结果](../evidence/evaluation-cleanup-20261018/results.json)保留最初测试环境失败及后续通过依据。finally是正常Python异常路径的保障，强制结束进程不能保证执行，restore抛错仍保持失败。

完整工具free-tools-v1原45格在第41格中断，原40终态中33项协调完成且独立持续恢复、7项未满足；第41格F10/M2/repeat2已注入但无终态，原OS退出码未知、无原最终H00。第42–45格已在独立continuation全部持续恢复，子进程及前台监督实际exit0；其后独立HTTP H00为30.328秒/30次全成功/10流程。覆盖原45计划的统计为44终态、37确认、7未确认、1中断，仍不是一次完整45格单批。详见[中断与独立后续结果](free_tools_matrix_20261018.md)。

153份公开源码已冻结到`local-free-tools-final-F19-cleanup-20261018`，最终receipt SHA256为`e9816eb44b50a8b1c4c5ead2f72c713165f004b114ec7e8e753765d048b01a24`。协调配置按原始字节锁定；native配置只排除顶层`managed`进程登记，端口、二进制路径及其他字段按canonical JSON锁定，分别记录原始文件与登记变化。最终receipt、配置和完整source快照保留本机，不进入团队公共内容白名单。

原监督未留下实际finished/OS退出码及最终H00，原件已封存，不能推定exit1。独立四格的精确键、方法定义、seed/pool、JSON/JSONL、153源码和不可变配置检查均通过，实际Popen.wait与前台终态各exit0；独立健康窗口不能替代第41格原未知意图和失败清理核验。原40、在途41、后续4和H00分别保留，下文v2/v3与F01 pilot仍为历史批次。

## 方法与历史证据

三种方法共享工具、事实、域内策略、审批签名、操作账本和业务验证。
图表与相应测试另需 `requirements-report.txt`；本机已在 `.venv-report` 安装，
核心运行器使用 `.venv`。

| 方法 | 实际决策范围 | 模型失败处理 |
| --- | --- | --- |
| M0 | 冻结顺序全部观察，再按确认事实处置 | 不调用模型 |
| M1 | 模型自由选择下一次观察、带参数的受控修改或业务验证；不提供排序或修复计划 | 停止本次排查，记 `llm_failed`，不转用规则选择 |
| M2 | 模型输出假设与工具预测，按区分度/成本排序，动态调整依赖与处置 | 每轮最多两次，失败转规则并记录 `rules`/`mixed` 与次数 |

当前 M1 实现为 `free-tools-v1`，观察、修改和验证都由模型选择，修改仍经过共同的
域内前置条件、审批、隔离令牌和幂等账本。M0/M2 的冲突复探与 revision 确认由调度器
组织；M1 需自行选择相应观察，域内守卫同样拒绝缺少或过期的前置条件。
明确的拒绝可作为后续选择的反馈；修改结果未知、执行中、需对账或旧令牌则停止。
旧 `FreeModelSelector` 保留用于复查历史“自由观察选择 + 共享处置”结果。
M0 的模型成本是零；M1/M2 使用相同模型和上限，实际调用数、token 由各自方法决定。

固定参数为 `temperature=0, top_p=1, seed=42, max_tokens=768`。默认每次排查
最多 40 项 AIP 任务、40 次模型请求、65536 个模型总 token、600 秒协调时限。
请求前以 UTF-8 字节上界和固定封装余量预留输入，再限制输出；服务端 usage
仍为统计依据。返回缺少 usage 时标 `token_usage_complete=false`，数值仅是已知部分。
失败请求也计调用数，已收到的失败输出也计 token。

M2 的模型预测只接受五项观察的枚举：`exited/running`、`v1/v2`、
`reachable/unreachable`、`ro/rw`、`blocked/clear`。提示包含各工具的输入 schema、
事实键、可观察枚举和成本；建议性文字不能作为预测通过校验。

矩阵命令（真实故障运行需明确授权，并保证原生资源的独占注入窗口）：

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

H00 使用独立健康对照判据，不要求先出现故障：实际观察至少30秒、至少10个完整流程，
窗口内失败、未知和未决请求均为0，且协调任务中没有任何资源修改尝试，才记
`control_passed=true`。`modification_attempts` 计所有 `kind=act` 的任务，包含
ok、unknown、拒绝和未派发；仅 `modifications=0` 不足以证明健康对照通过。
H00 的 `continuous_recovery_confirmed` 为 false，恢复时延为空；报表以
`healthy_control_groups` 单列，不进入 `fault_recorded_cells`/`recovery_rate` 分母。
旧H00记录缺少尝试计数或独立窗口证明时，不补记通过，也不重写原始结果。
local/native 与 Wutong/docker 复用同一判定。

`finish()` 先提出停止请求，由采集协程在完整请求chunk结束后检查资格并停止，
防止第30次请求刚达标就又开始第31次创建，留下半个流程。尚未调用 `finish()`
时继续采样；若请求停止时已有未完成意图，会在余量内继续核验到安全边界。
截止仍未达资格时 `observation_deadline_exhausted=true`，不会记通过；故障场景
采用相同停止规则。

仅观察公共业务HTTP的H00入口可用下列API；每次使用新 `run_id`，避免旧回执复用。
它会创建、查询和取消普通测试订单，不读取资源env，也不创建智能体群组或注入故障。
`healthy_control_confirmed` 仅证明业务观察；完整运行器另外核对资源修改尝试为0。

```python
from pathlib import Path
from uuid import uuid4
from eval.observation import ContinuousObserver

observer = await ContinuousObserver(
    "http://127.0.0.1:8088", Path("output/YOUR_NEW_H00"), seed=101,
    run_id="h00-" + uuid4().hex[:12], healthy_control=True,
).start()
summary = await observer.finish(grace_seconds=35)
```

T12尚未覆盖全部§5.2：F15复用独立接续实验器，F19仍在通用注入器中明确为
Unsupported，运维参与者失联的AMP证据判定未实现。本轮不扩写F19，不重跑已有E1。

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

本次闭合数据位于 `eval/results/local/`：

完整工具M1的开发验收另存 `M1-full-tools-pilot-20261017` 与
`M1-full-tools-pilot-v2-20261017`，均为F01三方法各一次。首批为2/3持续恢复：M1观察
应用退出后选择路由回退，配置已v2仍实际调用MCP，健康确认失败后进入unknown并停止。
其 `modifications=0` 只表示没有ok动作回执，不表示没有修改尝试；实际route MCP调用1次。
共享域补 `expected_before=v1` 后，v2三方法均持续恢复，控制器exit0；M1的
`ops.restart` 和 `db.restore_writes` 各一次，后者为不必要高权限动作，未从记录删去。
两版分别保留，不以成功复验覆盖失败，也不将这一单场景开发验收合并为正式45项矩阵。

以下v2/v3和主对比中的M1为历史观察选择版本，不能说明完整自由工具循环效果。free-tools-v1现有原40终态、第41格中断与独立后续4格，按[本批说明](free_tools_matrix_20261018.md)分段披露；F02验证器版本差异、M1上下文超限及缺失usage保留。后续代码应用状态亦以该页为准，不追溯改写原始结果。

- `model-fairness-formal-v2-20261017`：完整 45 项，36 项持续恢复，45 项证据诊断匹配。
  F01/F02/F07/F10 的 36 项全部恢复；原 F06 九项失败完整保留。
- `model-fairness-F06-v3-20261017`：仅定向修复 F06 后的九项，全部恢复。
  注入器改用 `orders_app`，规划器沿 `blocking_pids` 选择根会话，SQL 安全函数未放宽。
- `model-fairness-comparison-20261017`：按场景版本组织的主对比 45 项全部持续恢复、
  诊断匹配。原 F06 九次错误等待者目标与失败单列在 `historical-F06-v2.*`。

主对比各场景内的三种方法使用相同源码版本、模型、预算和实例参数；这是两个明确
版本的分场景复用，不是一次单源码冻结的 45 项实验。项目源码差异仅有
`incident/coordinator/planner.py` 和 `eval/inject.py`。两版 `source/`、源码摘要和 SDK
补充快照均保留。v2 的一个 transport 和五个域 worker 在 SDK 乱序补丁前各启动一次，
没有逐项重启，接管事件为零；`sdk-provenance.json` 记录了这些依据。F06-v3 使用
补丁后的 SDK，不能把本地串行结果冒充正式平台乱序验证。

三次重复的采样恢复时间中位数（秒）：

| 场景 | M0 | M1 | M2 |
| --- | --- | --- | --- |
| F01 | 7.844 | 6.109 | 10.469 |
| F02 | 5.156 | 6.250 | 15.265 |
| F06（v3） | 5.328 | 7.125 | 25.766 |
| F07 | 5.406 | 7.547 | 25.218 |
| F10 | 8.985 | 9.562 | 33.515 |

本地 Qwen3-1.7B-Q8_0 的实际结果不支持 M2 更快。每方法 15 项中，M0/M1/M2
总探测次数为 108/99/99，M2 比固定流程少 8.3%，与自由观察基线相同；模型生成
开销使 M2 在五类场景的恢复中位数都更高。模型 token 总量为 0/57335/122372，
实际模型请求数为 0/99/114。主对比中模型失败与规则回退均为零，usage 均完整。
这些是本部署与该小模型的观测，不推导为模型或方法的一般优越性。

原始模型输出、usage 与 HTTP 状态保留在 incident 记录；`context.local_hypotheses`
因列表引用可能显示后来新增的本地提示，不应称为逐字原始请求。实际发出的用户 JSON
在请求前已序列化；响应内容与 token 统计不受此日志视图问题影响。同步材料另导出
仅包含原始响应、usage 和请求参数的 `model-response-evidence.jsonl`。

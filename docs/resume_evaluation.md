# 本地接管实验 E1

本文件独立于已闭合的模型实验。真实平台 ADP/AMQPS/mTLS 接管需另行验收；这里使用官方 AIP 消息与独立本地域进程，通过 stdio 和本地进程目录完成接管。

执行入口：

```powershell
& '.venv/Scripts/python.exe' eval/handover_experiment.py --include-breakpoints --repeats 3 --approve-high --output eval/results/local/E1-native-20261017
```

必须独占原生 8081/8082/8088 业务资源。每个案例先独立注入器 restore，验证四个公开健康端点及应用域只读状态，再注入 F07。案例结束 restore 并重复健康验证。SQLite 权威 term 与业务账本保留，不因输出目录变化而清空；每个案例记录前后 term、账本路径、当前 fence 和累计状态计数。

E1-a 覆盖观察结果发布前、修改调用前、账本 applied 后但结果发布前三个真实进程退出点，各三次。核对原操作 ID 贯穿接管、真实 MCP 修改调用恰好一次、旧 fence 拒绝、接管候选 describe/资源域匹配以及完整的业务恢复验证。

E1-b 固定在 applied 后退出，各策略三次，轮换顺序：

| 方法 | 接管时可用信息 | 共享机制 |
|---|---|---|
| from_scratch | 目标、原逻辑/操作身份、原及替代 fence；缺少事实时重新观察 | 相同域账本与 applied 跳过 |
| full_history | 真实采集的 Start IFC 请求与业务 Product，保留 AIP task ID | 相同 TTL、安全审批和工具 |
| resume_package | SDK ResumePackage 的结构化事实、操作状态与剩余工作 | 相同修复步骤和业务验证 |

完整业务对话导出自原生 messages.jsonl，包含故障前已发出但未返回的动作请求；生命周期原文另存。替代参与者查找开始后的消息不混入故障前对话。原始 observed_at 加相同 TTL 决定事实可用性，交接不会更新观察时间。完整对话与 ResumePackage 采用相同的最新有效事实选择逻辑；从头恢复也能使用共同账本的 applied 结果，只补采缺失的应用 revision，不人为重复全部诊断。

可选 resume_payload_factory 默认关闭，生产默认 resume 参数仍是 advance_fence/resume_package。实验 handover.control 内的原操作 ID、原 fence、替代 fence 均校验；工厂不能改顶层身份、审批、预算或推进 fence 的布尔值。替代域对实际收到的 handover 返回规范 JSON 的 SHA256。确定性 continuation 从原生捕获的已发送 payload 读取信息、核对回执哈希及字节数，再执行剩余流程；它不是新模型推理，数据库参与者也没有承担跨域业务规划。

三种方法均继续执行真实 application.pool_rebuild(expected_revision)，然后由独立验证域执行至少 30 秒、10 个完整订单流程。数据库效果重复次数来自域 AMP 的 mcp_modify_invocation 计数，不能根据只读状态反推；应用修复另记录自身账本结果。unknown/executing 仍只允许资源核验，无法确定时失败并保留记录，不自动重做。

这是确定性控制器的交接信息比较，真实模型 calls/tokens 均为 0。交接信息的 UTF-8 字节数与 bytes/4 估算 tokens 单列，不能解释为实际模型用量或模型节省。剩余工作耗时含业务验证，不叫纯恢复延迟。零重复效果由共用账本提供，不能据此宣称 ResumePackage 独有优势。

源码在套件启动时复制并写 source-manifest.json。父进程预先导入两种实验和 engine；每案例新建域进程，运行前检查其 worker、合约、业务、桥与 SDK 源码哈希未变化。后续独立的协调器代码开发不混入已导入父进程。结果保留各案例 results、事件、原生传输、真实业务对话/交接 payload、MCP 调用计数、健康与权威状态；注入器诊断仅保存在 private 目录。

2026-10-17 本地 18 例已闭合并通过独立核验：E1-a 为 8 例连续完成、1 例控制器中断后只续验；E1-b 三策略各 3 例连续完成。总计 17 连续、1 续验，不称一个控制器连续完成 18 次。每例数据库 MCP 修复调用 1 次，共 18 次，重复 0 次，旧 fence 18/18 拒绝；每例最终业务观察均为 30 秒、30 请求、10 完整流程，清理健康通过。实际模型 calls/tokens 均为 0。

最初启动曾被自动审批审查拒绝，之后用户明确授权这 18 次实验。11:13:05Z 冻结后首控制器在第 4 例验证阶段退出；数据库和连接池账本均已 applied，未重注入或重做修复。新隐藏后台控制器在核对完全相同的冻结源码后，只为第 4 例使用新 verification logical ID 完成独立观察，再运行尚未开始的 14 例，总故障注入仍严格为 18。原 unfinished journal 与中断记录保留，原 HTTP 基线记录因只在退出进程内存中而缺失，没有补造；该例标 controller_continuation=true、uninterrupted_cohort=false，不混入连续案例耗时中位数。权威任期按实际启动顺序从 13 递增至 31，其中 17 用于控制器续验；共享数据库账本历史 unknown 记录仍保留。

| E1-b 方法 | 完整 IFC 文本字节中位数 | 信息字节中位数 | 额外应用状态观察 | 后续工作秒中位数 |
|---|---:|---:|---:|---:|
| from_scratch | 1084 | 325 | 1 | 30.531 |
| full_history | 4594 | 3835 | 0 | 30.390 |
| resume_package | 5223 | 2388 | 0 | 30.375 |

ResumePackage 的信息比完整对话少约 37.7%，但兼容字段让 package 同时出现在 args.resume_package 和 handover.package，实际完整 IFC 反而大约 13.7%；不能声称传输、模型 tokens 或恢复时延优势。后续工作计时从数据库接管返回并核对 hash 后开始，包含池修复、30 秒验证、旧 token probe 和事件读取，排除故障检测及接管。替补查找/fence/resume 中位数分别为 0.406/0.219/0.219 秒，也不包含故障检测。确定性 continuation 只消费有效 revision 并完成固定剩余流程，不证明任意任务图理解。

原件位于 `eval/results/local/E1-native-20261017/`，独立分析、逐例数据、SHA 索引与图在其 `analysis/`。团队仓库提供[筛选后的完整报告](../evidence/eval/results/local/E1-native-20261017/analysis/report.md)。默认接管 5 项、新交接 7 项、网关 28 项相关测试作为实现验证；分析独立核对原生 wire/hash、TTL 时间界限、域 MCP 次数、业务窗口、旧令牌拒绝及实际任期顺序，18/18 通过、问题 0。图使用既有 report 环境补绘，项目环境缺 matplotlib 的绘图失败记录保留，未重跑实验或分析检查。正式平台 ADP 自动接管仍需独立验收。

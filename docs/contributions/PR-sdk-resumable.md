# 为 AIP 群组增加可接续任务支持与可选 access 记录，并防止迟到 TaskResult 回退状态

群组任务在发送方重启、执行方中断或结果延迟时，需要保留任务尝试、判断资源是否已经
修改，并用新 fence 接续。该补丁通过可选组合适配增加持久化任务历史、操作账本与接管
流程，同时修复真实 AMQPS 中迟到 working 覆盖 awaiting-completion 的问题。

目标仓库：AIP-PUB/ACPs-community；基线提交：
`3985c1330209f075c124669cc9d31f0e75448140`；SDK 版本：2.2.0。
这是 PR 正文草稿，尚未创建远端分支或提交 PR。

本地审阅补丁已从冻结的 `incident-v0.2.0-20261017T045307Z` SDK 导出，限 SDK 内
12 个文件（10 个新增、2 个修改；1535 行新增、9 行删除），共 91116 字节。
补丁 SHA256 为 `2df10ba1c1e0552003c514cdc30a1eff6f343886a96cd1ebad34e10f450c64b9`。
它已在该基线 SDK 的临时副本上通过 `git apply --check`，实际应用后每个改动文件的
SHA256 均与所审阅源码一致；原 SDK 与冻结基线未修改。本包未重复运行已有测试。
文件、来源及验证记录见 `sdk-review-20261017/{acps-sdk-high-score.patch,manifest.json,validation.json}`。

## 主要改动

| 范围 | 最终行为 |
| --- | --- |
| aip/_task_order.py 与 GroupLeader 结果处理 | 按同一 session/task/sender 的状态时间合并投影，保留终态；原始结果仍通知 listener。较新 Continue 可以回 working |
| aip/resumable/journal.py | 发送前记录 intent，持久化 attempt、原始状态事件与产物摘要；进程重启可查询未完成任务；协调任期持久递增 |
| aip/resumable/ledger.py | operation_id、参数摘要和本域 fence 约束副作用；applied 重放返回缓存；不确定结果先要求资源核验 |
| aip/resumable/takeover.py | 接入官方 DiscoveryRequest、能力确认、真实成员就绪检查、新 fence 与 resume package；可通过认证域端点远程推进 fence |
| aip/resumable/partner.py | 以 policy 提供的风险分类包装写动作，要求 operation_id / fence，复用原生结果发送接口 |
| amp/group_access.py 与 Group clients | 可选 AccessEmitter 注入；按首次 Start 记录每个任务尝试；Complete / Get / 重投仍正常处理，完整 message 边事件保留 |

不增加原生 AIP command 枚举。resume 是 Start 携带的业务 payload；现有默认格式可由
`resume_payload_factory` 适配为业务 schema。未注入 access emitter 时，不新增 access
文件；已有 MessageEmitter 的数据仍由官方 emitter 产生。

## 副作用与接管约束

操作账本采用 SQLite，修改同一资源域的主备必须共享同一个账本文件与 domain 名称。
writer 锁覆盖 fence 检查和受控动作；新 fence 激活等待当前动作完成，旧 fence 即使
重放已 applied 操作也会拒绝。operation_id 与不同参数绑定时拒绝第二次效果。

executing / unknown 等不确定状态默认不重试。只有 inspect 明确证明 expected_after
才可对账为已生效；重试还需要显式开启并证明 expected_before，调用方负责确认旧效果
不会迟到。账本不承诺任意外部工具恰好执行一次，也不能取消绕过其锁的外部进程。

协调方可以通过 `advance_fence` 认证回调访问本域网关，不需要资源凭据或本域账本文件。
`TakeoverManager` 必须确认远程 fence 成功和替补成员已加入，才派发接续任务；发送
status 命令成功本身不能作为执行方存活证明。

## 测试与实际证据

| 验证 | 本轮结果与范围 |
| --- | --- |
| tests/test_task_ordering.py | 3 项通过：迟到 working、较新 working、持久历史/终态保护 |
| acps-sdk/tests/resumable/test_resumable.py | 25 项通过：持久化、旧 fence、参数冲突、并发、真实子进程崩溃、原生 Group listener/access/重放等 |
| 真实本地 F15 三点 | observation 后、修改前、修改后分别崩溃；每点真实 PG MCP 修改调用 1 次、重复 0 次、旧 fence 拒绝，业务观察窗口通过 |
| 本地 access 对账 | 33 次原生 Start，对照发送/处理两侧合计 66 条 access，无缺失、多计 |
| 正式 AMQPS 原始缺陷 | 只读 describe 的真实 journal 记录 accepted→awaiting-completion→更早时间的 working；该失败原样保留 |
| 修复后正式 AMQPS 复验 | 三个正式身份经 ADP 与 describe 确认、完整任务生命周期、实际 PostgreSQL MCP 返回 read_only=false；结果 completed |
| 后续本地 E1-a / E1-b | 用户授权后完成 18 例最终业务验证；17 例连续、1 例控制器中断后仅续验；MCP 修复共 18 次、重复 0、旧 fence 18/18 拒绝；正式平台接管仍未验收 |

上述 3+25 项通过来自本轮开发验证记录。F15 使用本地 AIP stdio 与本地进程目录，不能
称为正式 ADP 自动接管验收。access 对账也不证明平台 Monitor 入库。正式 AMQPS 的缺陷
记录是修复依据；修复后成功结果单独保存在
`eval/results/platform/container-postgres-mcp-20261017-order-fix-v2/`，并有原始发送与回执。
该正式复验是已有身份的只读流程，不代替新主备的正式平台故障接续验收。
旧本地 F15 是每断点一次，共三次，与后续 E1 数据分开。SDK 审阅快照导出时的“等待授权”
是当时状态；后续本地 E1-a 为 8 连续、1 续验，E1-b 三策略各 3 连续，原控制器中断记录
保留，不能称一个进程连续完成 18 次。正式平台 E1-a / E1-b 仍未完成。本次补丁导出自身
没有启动模型、数据库工具或平台任务；后续资源实验见 `docs/resume_evaluation.md`。

从本项目根目录可运行：

```powershell
python -m unittest discover -s tests -p test_task_ordering.py -v
python -m unittest discover -s vendor/ACPs-community/acps-sdk/tests/resumable -p test_resumable.py -v
python vendor/ACPs-community/acps-sdk/examples/resumable_group_demo.py --output output/sdk-resumable-demo
```

移入上游时，应将独立的 `tests/test_task_ordering.py` 纳入 acps-sdk/tests，并调整示例命令的
仓库相对路径。示例使用官方 Group clients 配合进程内递送，展示 applied、缓存重放、
stale 拒绝；不把它当作真实 Broker / ADP 验收。

## 提交范围

源码为 `acps-sdk/acps_sdk/aip/{aip_group_leader.py,aip_group_partner.py,_task_order.py}`、
`aip/resumable/{__init__.py,journal.py,ledger.py,partner.py,takeover.py,README.md}`、
`amp/group_access.py`，以及 `acps-sdk/tests/resumable/test_resumable.py`、
`acps-sdk/examples/resumable_group_demo.py` 和乱序回归测试。

运行输出、SQLite、AMP 日志、证书、EAB、项目业务配置不进入上游补丁。改动可按状态修复、
可接续模块、可选统计三个独立提交审阅；现有协议模型与业务授权边界保持由相应层负责。

审阅补丁路径目前以项目根目录为准，使用 `git -c core.autocrlf=false apply --check`；
若从上游 ACPs-community 根目录检查同一补丁，使用 `git -c core.autocrlf=false apply -p3 --check`。
SDK 外的三项乱序回归 `tests/test_task_ordering.py` 被来源清单引用，不在这份仅 SDK
补丁中；正式提交前仍须移入上游测试目录并调整导入路径。

请重点审阅时间相同时的合并策略、终态保护、SQLite 在外部副作用期间持锁的取舍、
远程 fence 回调的契约，以及“首次尝试结果”是否适合作为 access 的可选口径。

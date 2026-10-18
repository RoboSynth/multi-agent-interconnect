# NEW7 正式 E1：已完成的源码与接续边界

正式 E1 当前处于源码实施与离线验证阶段。新增数据库工作者复用现有 Bridge、Policy、OperationLedger、BridgeGroupRuntime 和 AmpRuntime；它为正式 AMQPS 链路补充精确中断点和实际 MCP 修改调用计数。尚未运行正式 E1，本文不把离线回调退出称为真实进程退出、自动接管或业务恢复。

## 数据库工作者

`eval/platform_database_worker.py` 默认只检查文件；启动工作者需显式 `--serve`、匹配的实验编号、角色文件及冻结 bundle SHA。`eval/prepare_platform_e1_worker.py` 只准备新目录内的配置和 overlay，默认主库未 armed，备用库始终不能 armed。

| 中断点 | 退出码 | 已验证的顺序 |
| --- | --- | --- |
| `after_observation` | 81 | 指定只读观察成功后、AIP 产物提交前 |
| `before_modification` | 82 | 原策略与审批通过、原账本 `record_received` 已持久化后，尚无修改调用 |
| `after_applied` | 83 | 原 Bridge/账本已持久化 `applied`，尚未构造或提交 AIP 产物 |

钩子同时绑定实验编号、事故编号、主库 AIC、工具、角色及 armed 状态。观察点仅允许 `db.read_only_status`，两个修改点仅允许 `db.restore_writes`。备用、未 armed、错误事故或错误调用者不会触发退出；旧 fence 和已 applied 的重放沿用原拒绝、跳过语义。

## 隔离部署与计数

overlay 仅覆盖主、备数据库域的实验入口，新增只读 `/experiment` 挂载；保留原 `/srv` 业务与 SDK 源码、各自 `/domain` 身份及共同的 `/state/operations.sqlite` 账本。只有主库设置 `restart: "no"`。真实控制器必须先核对自己拥有的旧消费者，再切换入口，避免同 AIC 双 Inbox。

当前另有 8877 持续巡检使用原协调身份。真实 E1 开始前应先在空闲边界正常停止该巡检并核对群组关闭，不应并行启动同 AIC 的第二协调者；本批没有执行这一步或开展正式故障实验。

主、备各自记录按 operation 和 executor 绑定的修改 MCP 预调用事件与返回；正式标签为 `wutong-amqps`。预调用事件先于 AMP emit 和底层 MCP 调用，匹配返回可证明调用已返回；没有返回的事件不能单独证明已经发送、执行或产生物理副作用。旧本地工作者的默认标签保持 `local-aip-stdio`。额外三份实验源码及两个角色文件均由 bundle manifest 绑定，工作者启动前还检查实际 import 路径。

## 正式接续接口与单次计划

正式 Wutong 传输补充可选的交接信息工厂，仅允许替换 `args` 内的信息表达；operation、logical task、fence、审批、预算等控制字段仍受原约束。正式历史读取按 IFC 内事故编号关联任务和产物，在接管开始时固定历史字节边界，适配 AIP 群组会话与事故编号不同的情况。原本地默认接口保持兼容。

`eval/platform_resume_experiment.py` 是单次 `E1-a/after_applied` 的薄 runner。默认只检查文件，执行入口要求与精确计划 SHA 对应的明确授权；私密计划和 armed bundle 的文件准备不等于允许故障执行。计划拟验证主库在 durable applied 后真实退出 83、备用通过正式发现接续同一 operation 并跳过重复修改，最后正常关闭群组、复原域入口并独立验证业务；这些实际结果目前尚未产生。其它两个中断点仅完成工作者支持，不能据此称正式 E1-b/c 已验收。

当前具体计划已做只读未来 Compose 配置与镜像绑定检查；它没有执行 stop/up、注入或平台实验。前两次检查器失败保留：一次是辅助程序强制 UTF-8 解码 stderr 失败，同命令原字节诊断成功；另一次是两条配置渲染命令实际成功，但默认 profile 范围缺少六域而被守卫拒绝。修订后的[第三次只读预检](../evidence/new7-e1-implementation-20261018/future-compose-readonly.json)通过。详见[安全审阅入口](../evidence/new7-e1-implementation-20261018/README.md)、[具体计划投影](../evidence/new7-e1-implementation-20261018/execution-plan.json)及仍为 false 的[授权模板](../evidence/new7-e1-implementation-20261018/authorization-template.json)。私密配置、证书、资源 env 和真实授权文件不随该审阅包发布。

## 离线证据与下一步

[工作者离线检查](../evidence/new7-e1-implementation-20261018/worker-offline-checks.json)包含 12 项有效检查：9 项已通过结果复用，修正 SDK TaskCommand 测试必填字段后补跑 3 项。保留首次测试夹具错误和受限测试辅助进程等待记录。检查只使用 fake MCP/AIP、临时 SQLite 和退出回调。

[接续接口检查](../evidence/new7-e1-implementation-20261018/interfaces-offline-checks.json)与[runner 检查](../evidence/new7-e1-implementation-20261018/runner-offline-checks.json)分别保留新增、复用及失败历史，不将三组检查直接相加为全部不同检查。AMP 修复部署后的[独立健康窗口](../evidence/amp-fixed-runtime-20261018/healthy-amqps.json)和[巡检首轮](../evidence/new7-inspect-session-20261018/first-cycle.json)属于其它窗口，不是 E1 故障接管结果。真实 E1 仍需要对应的明确授权、固定目标、原始退出/trace、正常群组关闭和独立 H00。后续实施任务见[正式 E1 接续方案](new7_e1_adaptation_20261018.md)和[协作任务清单](协作任务清单_20261018.md)。

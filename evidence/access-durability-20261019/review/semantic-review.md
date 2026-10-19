# T05 接收端 access 崩溃恢复的协议语义审阅

基线为 canonical `[canonical]`，本次实际读取 HEAD `d8ae1958aef411c61742f57ddb96e0de453ec885`。本报告只读本地规范、SDK 与既有归因材料，另查 SQLite 官方锁文档；未读凭据、启动资源或改产品代码，没有检查 `group_access.py` 的完整实现。

建议采用**本地持久化接收事实 → 形成一份不可变 access 记录 → 原样重投**。不能预写成功，也不能用相同 `logId` 把已发表的 received/pending 记录改成成功。收到消息、处理器返回、AIP 完成、业务操作已应用、日志已落盘、Monitor 已入库，是不同事实。

## 直接可用的官方依据

| 问题 | 本地原文定位 | 可确认的语义 |
| --- | --- | --- |
| 同一事件能否稳定 ID 重试 | [AMP §5.1.3](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-specs/09-ACPs-spec-AMP/ACPs-spec-AMP.md#L445>)，尤其 447–457 行 | 链路按 at-least-once 设计；同一物理事件重投的键保持稳定，源端只生成一次，流经下游不可重生成。无显式 ID 时按不可变源内容做 JCS 哈希兜底，不能掺入管线观测时间。 |
| 同一 ID 能否更新 body/status | 同上 449–457 行；[签名范围](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-specs/09-ACPs-spec-AMP/ACPs-spec-AMP.md#L285>) | 这里定义单事件去重，不是更新同一 endpoint 的状态文档。没有同 ID 改 body 的 upsert 合同；如果签名，timestamp、logId、关联字段及整个 body 都参与签名。不能据此实现 received→success 的公开覆盖。 |
| access 是否要求成功状态或耗时 | [AccessBody](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-specs/09-ACPs-spec-AMP/ACPs-spec-AMP.md#L658>)，669–754 行；[SDK 模型](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-sdk/acps_sdk/amp/models.py#L305>)，305–352 行 | response、statusCode、durationMs 均可省略。没有 received、pending、phase 等 access 生命周期字段。未观测到回复时可以不填 response；没记录结束时刻就不填“总耗时”。 |
| 错误怎样影响平台统计 | [AMP Access 查询口径](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-specs/09-ACPs-spec-AMP/ACPs-spec-AMP.md#L2126>)，2130–2131 行 | statusCode≥500 或 error.code 非空计为错误。聚合 aic 是日志发射方，不能把 caller/callee 两个端点当成同一条日志的两个发射方。 |
| 签名是否为 access 必需条件 | [AMP §5.4.1](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-specs/09-ACPs-spec-AMP/ACPs-spec-AMP.md#L757>)；[SDK AccessEmitter](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-sdk/acps_sdk/amp/access_emitter.py#L1>) | access 通常不需要签名，现 AccessEmitter 不签名。audit 必须签名是另一要求，见 AMP 1014、1030–1035 行；不应为此次 access 恢复引入读取私钥的前置步骤。 |
| 接收消息是否就是处理成功 | [AMP Message 语义](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-specs/09-ACPs-spec-AMP/ACPs-spec-AMP.md#L782>)；[receive body 构造](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-sdk/acps_sdk/amp/_message_tap.py#L41>) | send、receive、ack 等是独立边事件，各有独立 logId，用消息/业务关联键串联。receive 不是成功或业务副作用的证明。已有 MessageEmitter receive 可说明收到了消息，不能替代 callee access 的业务结束结果。 |

AMP 规范 1465 行的 `op: upsert | delete` 属于 heartbeat 存活同步增量模型，不能移植成 access 写入合同。规范 1054 行明确 AMP HTTP API 提供稳定读模型查询，不接收 Agent 直接上报；本地副本缺少 `monitor-server`，也未找到本地 AMP-Design / Writer 具体去重实现。因此可依赖上述规范要求，不能声称已实证官方部署的去重窗口、冲突策略或更新行为。

## 当前发射器能复用什么，不能证明什么

[AccessEmitter.emit_sync](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-sdk/acps_sdk/amp/access_emitter.py#L38>) 在 50–63 行每次新建 logId 和 timestamp，公开参数不能传入一份已冻结记录或指定原 ID。65–67 行异步入口用 `asyncio.to_thread`；69–80 行追加文件时捕获所有写异常，仅 warning。它没有 `flush+fsync` 的显式持久化确认，也没有“写成功/失败”的返回区分。

直接重复 `emit(body)` 会产生新 ID、新时间，不能当成同一事件原样重试。其返回的 logId 只说明创建过 ID，不能当作落盘收据；[官方单元测试](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-sdk/tests/amp/test_amp_access_emitter.py#L73>) 还明确构造磁盘失败，仍预期返回 logId。这里是源码与既有测试的静态结论，本次没有运行测试。

可复用 `AccessBody`、`AccessRequest`、`AccessParticipant`、`ErrorInfo` 与 `AccessLogRecord` 的数据结构、追踪字段及序列化习惯；持久化发布部分需具备严格失败信号，并能重放已保存的完整记录。不要把旧的 best-effort emit 返回当成 durable outbox 的“已发送”。若采用追加文件，进程在“追加后、标记已发送前”退出仍可能重放相同行；应保留相同 ID、相同源字节，并在本地对账中单独呈现重投与按 ID 去重后的 endpoint 数。

此次读取的 `access_emitter.py`、`models.py`、`access_status.py` 与既有官方快照完全同字节；[来源归因](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/evidence/sdk-attribution-20261019/frozen-baseline-comparison.json>) 记录它们相对上游 `3985c133...` 仅有换行差异。群组客户端已有项目修改，本报告把其行为称为 canonical 当前行为，不冒称全部是原版官方实现。

## AIP 与本地 outbox 生命周期必须分开

[AIP TaskState](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-specs/07-ACPs-spec-AIP/ACPs-spec-AIP.md#L402>) 仅定义 accepted、working、awaiting-input、awaiting-completion、completed、canceled、failed、rejected。475–491 行规定终态不可逆，Start 对已存在的相同 TaskID 应忽略；Complete 仅适用于 awaiting-completion。没有 received 或 pending 这个 AIP 状态。

本地存储可以定义 received、processing、ready、emitted 等内部状态，但不得把它们写成 AIP TaskResult，也不能把 AIP 已完成或已应用操作倒回 pending。若“received→pending”仅表示本地日志等待发布，需要明确命名与原已提交事实；已形成不可变记录后只能重投该记录，不能重新计算状态或时间。日志去重也不能代替 AIP 层决定是否执行处理器。

当前 [Partner.send_task_result](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_partner.py#L1131>) 在 1149 行保存任务状态；[Leader.dissolve_group_session](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_leader.py#L2370>) 会移出 session、广播 shutdown、删除 ACL，随后调用群组资源清理。恢复日志应独立于旧 session 内存与旧 MQ 队列存活，不应重新建群、重发 Start 或复活任务来制造一条 access。

项目现有 [OperationLedger](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-sdk/acps_sdk/aip/resumable/ledger.py#L59>)、[TaskJournal](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/vendor/ACPs-community/acps-sdk/acps_sdk/aip/resumable/journal.py#L22>) 已有 SQLite WAL 与先提交再执行的可复用习惯；它们是本项目接续扩展，不能称作官方 access 恢复标准。ledger 的 received/executing/applied 是资源操作阶段，也不能与 access 或 AIP 状态混为一谈。

## 建议的最小恢复约定

1. 在接收端真实收到、且即将进入处理器时，先提交本地接收事实：原发射方 AIC、group/session/task ID、端点方向、请求方法/route、请求摘要、接收时刻，以及唯一进程实例标识。随机 logId 在源端生成一次并持久保存；本地 endpoint 唯一键用于防重，不能替代 AMP 对 logId 不碰撞的要求。相同逻辑键若请求摘要不同应报冲突，不能覆盖旧事实。
2. 正常路径在实际返回/异常后，只生成一份最终 access。只填真实观测到的状态、错误、响应字节和耗时。公开的 access 形成前，本地 pending 行可更新；公开之后记录保持不可变。若需要实时“已收到”，继续使用独立的 message.receive 事实，避免每个 endpoint 先后发两条 access 而悄悄改变原 T05 计数。
3. 启动恢复只处理已证明属于失效旧进程的未结束行，不能只因记录够旧就判定崩溃；活进程、SIGSTOP 后可复活的原进程必须排除。对没有真实结果的行，可按 schema 生成“结果未知、处理被中断”的 access，省略 response/statusCode 和未观测的总耗时。`ErrorInfo.code` 可承载项目明确命名的日志恢复原因，注明它会进入错误统计；不要编造 HTTP 500、任务 failed、业务未执行或业务已成功。该 convention 是本项目建议，规范未专门规定 hard-exit access 状态。
4. 恢复者只能恢复其拥有的真实发射端记录。caller 的发送记录不能证明 callee 接收，备用身份也不能凭自己的运行状态伪造主身份 access；若跨进程代投，需有可验证的原接收端持久原件、明确身份授权与原 AIC 绑定。缺这些证据就保留缺端或 unknown。
5. 严格落盘后才确认日志已发表。若发布失败或确认未知，原样重放同一个不可变记录与 ID。它是日志重投，不重跑业务、重发 AIP Start，也不改变原故障任务或原历史实验判定。

可用无业务的临时进程验证三处边界：本地接收提交后硬退出，只恢复一次未知结果；文件已追加但 outbox 未确认时退出，重放相同 ID/内容且能显式看到投递重复；暂停的活进程不被恢复者抢占。再核对磁盘写失败保留待发、日志恢复不触发处理器、组清理后仍能回放本域持久记录。这里只列必要验证对象，没有执行或宣称通过。

## 对根代理拟实现方向的并发复核

新增 `DurableAccessEmitter`、保持旧 best-effort 默认、独立 SQLite journal、回调前仅持久化元数据、正常后冻结完整记录、恢复为 `OutcomeUnconfirmed` 且省略 response/duration，这一方向与以上语义兼容。它是方案审阅，还不是已运行的产品行为。需要落实以下条件：

- **取得锁再恢复。** 应使用持续的 `PRAGMA locking_mode=EXCLUSIVE`，实际取得独占锁后才开始扫描旧 inflight，而不是仅设置选项或只用一次 `BEGIN EXCLUSIVE`。NORMAL 连接在事务结束会释放文件锁，EXCLUSIVE 连接在首次写时取得并持续保留；关闭连接会释放。见 [SQLite locking_mode 官方文档](https://www.sqlite.org/pragma.html#pragma_locking_mode)。WAL 的 EXCLUSIVE 模式及第二连接 BUSY 行为见 [SQLite WAL 官方说明](https://www.sqlite.org/wal.html#use_of_wal_without_shared_memory)。这只排斥遵循同一数据库锁的使用者。
- **单连接仍需线程串行。** 文件锁不能让同一 connection 的线程池调用变成一个原子 scan→append→fsync→ack；应有同步互斥保护这条序列和 close。`asyncio.to_thread` 取消等待也不代表工作线程已经结束。旧 callback 仍可能 finalize 时，不能先释放所有权让新 owner 宣称其已失效；close 与活动回调需要明确的拒绝/等待约定。
- **锁与目标文件一一绑定。** 同一个 canonical JSONL 必须使用同一个 canonical journal；journal 内核对发射 AIC 与目标日志路径绑定。两个不同 journal 各自独占，仍可能同时扫描/追加同一个 JSONL。不能允许仅通过配置另一 journal 路径绕过互斥，也不应混入另一个 AIC 的恢复记录。
- **已看见完整行后也要确保持久。** 若崩溃点是 append 后、fsync 前，恢复扫描能读到完整匹配行也可能只是读到缓存。标记 emitted 前，应对同一个目标文件完成 fsync；完全相同 ID/内容可确认而不重写，不同内容同 ID 则拒绝。半行/坏行保留并 fail closed 符合不覆盖原证据的方向。append 与 SQLite 确认是两个存储边界，不要只因看见一行就跳过持久化确认。
- **恢复时间不能冒充原请求时间。** timestamp 用恢复观察时刻时，ErrorInfo 应明确是“恢复时发现结果未确认”；它不表示原接收时刻或实际崩溃时刻。原 received_at 保留在 journal，必要时以明确命名的 error.data 元数据带出，便于按原窗口关联。`OutcomeUnconfirmed` 会计入平台错误率，不能被解释为真实 HTTP 500、AIP failed 或业务没有应用。

若验证仅覆盖临时进程 `os._exit` 与本地写失败，结果应称“进程退出后恢复与本地持久化边界验证”，不能扩大为机器掉电或官方 Monitor 入库验收。

原 [T05 18 条缺端诊断](<https://github.com/RoboSynth/multi-agent-interconnect/blob/d8ae1958aef411c61742f57ddb96e0de453ec885/docs/access_accounting_20261019.md#L3>) 的严格双端对账结果保持。此审阅能确定兼容的实现边界，不能据此把历史缺端补成真实成功，也不能声称 Monitor 已入库。

## 关键本地来源字节绑定

下列 SHA-256 绑定此次实际读取的 canonical 文件；它们不表示执行过相关路径。SQLite 外部依据为 2026-10-19 查询的官方文档链接。

| canonical 相对路径 | SHA-256 |
| --- | --- |
| `vendor/ACPs-community/acps-specs/09-ACPs-spec-AMP/ACPs-spec-AMP.md` | `b79c53789b10b56b120eb1f67c0ea67252d261f660d0d8655d773b7b386da4de` |
| `vendor/ACPs-community/acps-specs/07-ACPs-spec-AIP/ACPs-spec-AIP.md` | `69669716eea914b71da43ea979dbe752b89ec778ccbaa673ca5276a7aa06db0e` |
| `vendor/ACPs-community/acps-sdk/acps_sdk/amp/access_emitter.py` | `79faa279e78c0d3adc00bc3a12a79d5269fabee7bbbd1f6e9b569f5e21c85158` |
| `vendor/ACPs-community/acps-sdk/acps_sdk/amp/models.py` | `b32d9766d1df46ee156f3150107f7ede34ce24a9d705c4f3c569b4b3d8651840` |
| `vendor/ACPs-community/acps-sdk/acps_sdk/aip/access_status.py` | `c520a8215ba42d75007402d3aa4bcdc2dc8185c0c7105a90f44e544a6f266132` |
| `vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_leader.py` | `2e57f1dc5d1cefc444fef245e9aa4a12512c15aa04be17845626a6916dc530df` |
| `vendor/ACPs-community/acps-sdk/acps_sdk/aip/aip_group_partner.py` | `4b1302a1dbe9867a2fe16b9f8c33143774e678af5240ec6721a34f17ed98729f` |
| `vendor/ACPs-community/acps-sdk/tests/amp/test_amp_access_emitter.py` | `fe2cb60e8838ce62c1b85d40e2d4aa27428328837d027a6a04f4051d9190ce21` |

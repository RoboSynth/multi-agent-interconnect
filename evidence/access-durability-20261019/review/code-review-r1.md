# Durable access 独立源码审阅

审阅对象为 `p0-access-durability-20261019/checkout` 中根代理正在实现的新模块及接入，基于文末字节快照。这里只读源码并推导控制流，没有执行测试、临时进程、资源或平台操作，也没有修改产品代码。

结论：独占所有权、正常/崩溃记录分离、不可变 ready、JSONL fsync 与 active callback 关闭保护已按设计落实。发现 1 项需要修复的 middleware 接入缺口，另有一个失败恢复范围需要在实现或说明中明确。

## [P2] live middleware 的 seen 快速路径绕过持久元数据冲突检查

位置：[group_access.py:56](<../../../vendor/ACPs-community/acps-sdk/acps_sdk/amp/group_access.py#L56>)，56–58 行先根据 `_seen` 直接运行 callback；只有之后 59–70 行才构造 durable intent、调用 `begin_sync`。而 [durable_access.py:170](<../../../vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py#L170>) 才检查旧 intent 的 body/trace 是否相同。

无需资源的确定控制流：同一个 middleware 先处理 `(session S, task T, receive)`、route A；首次结束后该 key 在 `_seen`。再传入同 key 但 route B（或不同 caller/callee），当前会直接再次调用 callback，不执行已实现的 durable 元数据冲突检查；access 仍只有 route A 的原记录。新进程或 `_seen` 淘汰之后却会进入 begin_sync 并拒绝同样的冲突，导致行为依赖缓存命中。

必要修改：durable 路径先构造 intent、执行 begin_sync；得到重复/已结束后可以照旧调用协议 callback，但不能跳过元数据一致性校验。旧 emitter 的 `_seen` 快速路径可保留。这样日志层仍不代替 AIP 决定是否执行任务，只保证 durable key 绑定的原始元数据一致。

必要验证：同一 live middleware 的相同 key/相同 metadata 重投继续执行 callback 且不增加 access；相同 key/改变 route 或 caller/callee 要在第二 callback 前报冲突，且原记录原字节不变。此处给出源码可达序列，本次未实际执行。

## 需要明确的边界：ready 形成前的瞬时失败仅在下次 start 恢复

[finish_sync](<../../../vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py#L179>) 的 finally 会在 `_record` 或 SQLite ready 提交失败时也移除 `_active`。此时已提交的 intent 仍在，但 record 为 NULL；[periodic flush](<../../../vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py#L138>) 只处理 ready 的 written=0 行，close 同样仅 flush ready。该遗留行因此要等下一次 start_sync 才物化为 OutcomeUnconfirmed，持续运行的当前 owner 不会自行补齐。

这是“重启后仍保留真实接收事实”的有效恢复，并非 intent 丢失；但不能宣称所有瞬时错误都能由 periodic 自愈。若本轮要求持续运行时也补齐，应保留可重试的完整结果或明确处理已不在 `_active` 的遗留 intent；不能覆盖已有 ready，更不能抢占仍活跃的 callback。ready 已成功提交、随后 JSONL append 失败的路径会被 periodic 重试，不受此边界影响。

## 已落实的关键不变量

- [start_sync:58](<../../../vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py#L58>) 为 canonical JSONL 唯一派生 journal，核对 AIC/完整目标路径，拒绝已知 symlink journal 与 hardlink 文件。EXCLUSIVE 模式之后实际 UPDATE owner，再保留同一连接；不是仅设置一项 pragma 就宣称拥有所有权。
- 全部 journal/scan/append/close 操作通过同一 RLock；group begin/finish 和 periodic 是同步小事务，没有 `to_thread` 被取消后又重新打开连接的路径。[close_sync:230](<../../../vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py#L230>) 在 active 非空时拒绝关闭，先前回调尚未完成时不会正常释放所有权。
- begin 先提交无结果 intent，明确拒绝 response、duration 与 error；正常 finish 只从 NULL record 形成不可变 ready，后续调用不重新计算 timestamp/结果。旧进程 NULL intent 在取得独占锁后恢复为 OutcomeUnconfirmed，保留原 logId，不断言响应或耗时。
- [_scan_existing:102](<../../../vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py#L102>) 拒绝半行、坏 JSON、错误发射 AIC 与同 ID 不同内容；同 owner 存续期间检查替换/截断。发现同 ID 的完整匹配行时，[flush:146](<../../../vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py#L146>) 会再次 fsync 后才提交 written，覆盖 append 后确认前崩溃的缓存可见窗口；缺行时先 append+flush+fsync，再确认。
- [AmpRuntime](<../../../incident/amp_setup.py#L56>) 选择新 emitter、启动时恢复并周期 flush、关闭前结束周期任务；旧 AccessEmitter 文件没有本轮改动。能否实际安全关闭仍需根代理的 active callback 集成验证，以上是控制流核对。

这些保障依赖该 canonical JSONL 的 sole-writer 使用约定；SQLite journal 锁不会阻止另一个完全绕过该模块的旧 writer 直接打开 JSONL。当前接入把同一 AmpRuntime 的 access 全部选为 durable，未发现模块内部能通过另一自选 journal 绕过该绑定的公开入口。

## 审阅快照 SHA-256

| 文件（相对 checkout） | SHA-256 |
| --- | --- |
| `vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py` | `fab9c27c2ad7fb1201aecece8caea7b45f994048fa44ab2bdbef245c92840a03` |
| `vendor/ACPs-community/acps-sdk/acps_sdk/amp/group_access.py` | `d21ab7c2ed3de192ab071185f914f399516f6cc5e514a28ea30488fd4bd6d2c5` |
| `incident/amp_setup.py` | `c0a408b84ce953f12a9556d61084815f6209886b79373c97eefcdca3852858eb` |
| `vendor/ACPs-community/acps-sdk/acps_sdk/amp/__init__.py` | `bf0a524474bcf2df493db341d61c200fa022e9c66a1134766fe3215afdc248b1` |

根代理后续修改或测试不自动视为本次已复核；应按新字节只复核受影响部分。原 22/12 例数据与统计不在本次修改范围内。

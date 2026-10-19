# Durable access 独立源码审阅（revision 2）

审阅时间：2026-10-19T06:46:26.648589+00:00。本次复核根代理修正后的真实源码；初审内容与当时 SHA 保留在 [code-review-r1.md](code-review-r1.md)。只读检查，未执行测试、临时进程、业务或平台操作。

**当前源码审阅无未解决的确定正确性问题。** 初审发现的 live `_seen` 绕过 durable 元数据核验和 ready 形成前失败只能等重启恢复，两处控制流均已修正。这里确认的是实现路径，测试执行结果由根代理另附真实记录。

| 初审发现 | 修正后的源码事实 | 静态复核结果 |
| --- | --- | --- |
| 同 key 的 live 缓存重投绕过 request metadata 检查 | [group_access.py:56](<../../../vendor/ACPs-community/acps-sdk/acps_sdk/amp/group_access.py#L56>) 先判断 durable；只有旧 emitter 才走 `_seen` 快速分支。durable 每次都构造 intent 并调用 begin_sync，冲突在 callback 前抛出。 | 已修正；正常相同 metadata 重投仍调用协议 callback，不额外 access，不以日志去重代替 AIP 调度。 |
| finish ready 冻结失败后 NULL intent 在本进程内不恢复 | [durable_access.py:129](<../../../vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py#L129>) 将 NULL record 的物化移入 flush；排除仍在 `_active` 的 key，其他行形成真实 OutcomeUnconfirmed，原 ID 不变。 | 已修正；startup、periodic、close 共用此路径，未结束 callback 受保护。 |
| access owner 关闭失败时仍记录 process_stopped | [amp_setup.py:70](<../../../incident/amp_setup.py#L70>) 在 close_sync 抛错时记录 process_stop_failed 并重新抛出，只有成功后才发 process_stopped。 | 源码行为一致；不把未关闭所有权记成进程已停止。 |

以下关键不变量仍保持：

- canonical JSONL 唯一派生 journal，AIC/完整路径持久绑定；初次开启拒绝 journal symlink 与已有 hardlink 文件。
- `locking_mode=EXCLUSIVE` 后执行真实 owner UPDATE 并保留连接；同一 RLock 覆盖 journal、scan、append、fsync、ack 和 close。begin/finish/periodic 都用同步小事务，没有取消的线程稍后重新打开 owner 的路径。
- begin 先提交无结果 metadata；active 存续时 close 明确拒绝。finish 从 NULL 形成一次 ready，已有 ready 不覆盖；active 只在当前 finalization 结束时移除。
- 恢复 NULL intent 只写 OutcomeUnconfirmed，不填 response 或 duration，timestamp 表示恢复观察时刻。它不改写 AIP 状态或业务账本，不虚构 HTTP 响应或业务成功。
- JSONL 新行 append+flush+fsync 后才写 written；重放发现完整匹配行也先 fsync 再 ack，不额外写同一行；同 ID 不同内容、半行/坏 JSON 拒绝并保留原件。

已静态查看对应新增测试：同 live middleware 改 caller 在第二 callback 前拒绝；原结果冻结故障后不重启即可 flush 出 unknown；未结束 active 的 flush 不提前生成结果。这些方法覆盖本次两处修正的关键行为，但本审阅未运行它们。

独占 journal 只保护使用同一绑定的 writer，不能阻止完全绕过该模块的旧 writer 直接打开 JSONL；使用约定仍是该目标文件的 sole writer。文件扫描的替换/截断保护针对当前 owner 存续期间。此源码审阅与临时进程测试都不能自行证明真实平台入库或把旧 22/12 例缺端统计改判。

## 复核字节 SHA-256

| 相对 checkout 文件 | SHA-256 |
| --- | --- |
| `vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py` | `af78150a67b2112175bfb32235c1a210cd8aed85ae3b34b9c18ea9d77963c52a` |
| `vendor/ACPs-community/acps-sdk/acps_sdk/amp/group_access.py` | `caa31611e69bcb4858808ba73b2d076f894c60bf944a5204bf5f0331ffe1de60` |
| `incident/amp_setup.py` | `724a6da15aead22212eab320e4cc7b544ba1b8ce60f0da72c77405ce2bafcbdd` |
| `vendor/ACPs-community/acps-sdk/acps_sdk/amp/__init__.py` | `bf0a524474bcf2df493db341d61c200fa022e9c66a1134766fe3215afdc248b1` |
| `vendor/ACPs-community/acps-sdk/tests/amp/test_durable_access.py` | `1fe69465e43700c5b92b7fd44ebd0d9cc0c8f518a97bb82be28d65b875404b69` |

初审原件 SHA-256：`bd211694fcc5801d42be21843c216f6a0a84b118b77d3030a4170cac006144e4`。后续修改需按受影响部分继续复核。

# E1-b full_history-r1 运行取证补充（revision 2）

原结论保持 **failed / TimeoutError / runner exit 1**。本次只读补取了这一用例的主、备 worker trace；首次诊断和原实验输出均保留。

主端 trace 共 4 行，依次为启动、一次修改 MCP 调用、该调用非错误返回、`experiment_worker_crash`。最后一行记录 `after_applied`、`ledger_state=applied`、`exit_code=83`、`AIP_product_submitted=false`。这证实主端走到了持久化退出钩子；冻结源码随后调用默认的 `os._exit(83)`。它不等于 Docker 独立记录的实际退出码，也不单独证明物理副作用次数。

备用 trace 只有 1 行启动，修改调用与返回均为 0。协调端原有记录仍是恢复请求 0、备用消息 0、备用 journal attempt 0；接管在重新进行官方 ADP 数据库发现时发生 `ConnectError`，尚未发送 resume，因此没有备用 Bridge 接受或拒绝的证据。

本次先按冻结 target 的精确项目与 backup service 选择容器，核实项目标签、镜像 `sha256:f7e91b059a7b50b52294a6a3ab09dfb1d072841817480bbc2ad2b870f440f6ea`，以及 `/state` 的项目共享卷标签。仅复制 `/state/experiments/revalidation-20261019-e1b-full_history-r1/primary.jsonl` 和 `backup.jsonl`；两个启动事件中的 bundle manifest SHA 均与该用例准备包一致。

对原 primary 容器 `860ae4d752c3caf674087f20319be879c036c23ead24ccf3fbeb1fa847c719c7`，按原 `results.json` 的 UTC 起止时间 `2026-10-19T05:25:09.107548Z` 至 `2026-10-19T05:28:37.655780Z` 查询 daemon `die` 事件，命令退出 0，返回 **0 条**。历史事件可能不在保留缓存中，实际容器退出码仍为 **unknown**，不能把钩子记录中的 83 改称实际 daemon exit 83。

旧验收失败例已发送 full-history resume 并被备用以 `invalid handover conversation entry` 拒绝；本例没有进入该阶段。补取的主端钩子记录完善了故障阶段证据，但不能用本例证明平台 wire 修复已通过。

原资源恢复、群组收尾和独立最终 H00 的 30/30 请求、10 个完整订单流程通过仍保留；它们不改变接管失败判定。`ConnectError` 的底层原因仍未确定。Trace 无时间字段，本补充不推断准确退出时刻。

取证原始记录位于 [full-history-r1-runtime-capture](full-history-r1-runtime-capture/)，机器可读补充见 [full-history-r1-diagnosis-r2.json](full-history-r1-diagnosis-r2.json)。原始 trace 与命令日志的大小、SHA 和取证身份检查均列入机器可读补充。

# E1-c 开发与验证证据（2026-10-19）

基线 `43964616d63e1d4aed76ed4f4ef9d474cdfee999`；本轮补正式平台旧主暂停后由同一进程继续原请求的路径。

- [检查汇总](root-checks.json)：89 个不同离线方法，worker 21、Controller 15、runner 8、移除时序 3、原 runner 回归 42；复验不重复计数。
- [源码绑定](source-manifest.json)、[worker 收据](worker/source-ready.json)、[Controller 收据](controller/source-ready.json)。
- [集成审阅](worker/integration-review.json)及[终版只读审阅](review/e1c-contract-review-final.json)；初审和早期失败均保留。
- [真实 Linux 临时进程探针](review/process-probe/linux-result.json)及[Windows 监督结果](review/process-probe/supervisor-result.json)：当前 PROCESS_CODE 对自有子进程执行一次 pidfd SIGCONT，保持同 PID/start ticks，子进程正常退出 0 且确认终止。

SQLite、MCP、Docker 输出和 AIP 群组在离线方法中使用独立 fixture；Linux 探针只处理自有临时进程。没有启动本项目服务、业务故障或正式平台 E1-c，正式恢复和最终 H00 仍待新计划验收。旧本地 E1-c、旧批授权和历史结果不改写。操作入口见[正式 E1-c](../../docs/platform_e1c_20261019.md)。

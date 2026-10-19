# E1-b full_history-r1 复验失败定位

本例原结果保持 **failed / TimeoutError / runner exit 1**。失败发生在主数据库恢复请求等待结果、随后重新查询 ADP 的阶段；没有进入备用交接校验。

| UTC 时间 | 已保存事实 |
| --- | --- |
| 05:27:02.398691 | 发出第 4 个任务 `db.restore_writes`。 |
| 05:27:02.423636 / 05:27:02.448268 | 主数据库依次回复 accepted、working；此后没有 AwaitingCompletion 产品或终态。 |
| 约 05:27:22.640 | 等待 20 秒后开始接管；journal 仍为 working。 |
| 05:27:33.848881 | 官方 ADP 数据库发现记录 ConnectError。 |
| 05:27:33.850873 | 接管记录 takeover_unavailable；包装层保留原 TimeoutError。 |

51 行消息中有 9 个 start、0 个 resume，发往或来自备用身份的任务消息为 0。journal 只有一条 started 接管事件，replacement/fence 均空，也没有备用任务。冻结源码明确先执行 ADP 发现，再选择备用、生成交接表示并发送 resume。因此，当前范围没有备用 Bridge 接受或拒绝的实证。

旧正式批次同名失败例曾真实发出 full-history resume，备用明确拒绝 `invalid handover conversation entry`；历史条目的 `aip_session_id` 与旧 Bridge 白名单不匹配，随后 `operation=None` 又触发 AttributeError。当前复验在更早的 ADP 阶段结束，不能据此判定该修复在平台成功或仍失败。

本机可见原件尚无该例主/备 trace、实际 worker exit 或 MCP 计数，不能把计划中的 after_applied 退出写成已观察事实。ConnectError 也不足以确定网络根因。

33 条控制子进程记录均退出 0；关组 6 项检查全真，资源与 worker 恢复 completed。恢复后的独立 H00 为 30 秒、30/30 请求、10 个完整流程通过；该恢复检查不改写失败结论。

完整行号、时间、journal 摘要和输入原件 SHA 见 [诊断 JSON](full-history-r1-diagnosis.json)。本次只读检查没有修改运行输出、重试或访问 Docker/MQ/平台。

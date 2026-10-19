# 本批 18 条缺端诊断

本批原结论保持：289 条 Start，预期 578 条双端 access，实有 560 条，缺 18 条、额外 0 条；T05 严格双端对账仍为 false。

18 条全部缺接收端：17 条 database、1 条 verification。每条都可在原协调者发送、caller access 和目标 callee 的官方 MessageEmitter receive 中定位；诊断 JSON 仅保留键/请求哈希、角色、工具、时间和来源行哈希。

| 原证据分类 | 数量 | 能确认的原因 |
| --- | ---: | --- |
| 主库 exact crash marker 和实际 exit 81/82/83 一致 | 14 | 同一原请求在处理回调内硬退出；`os._exit` 不执行 access 中间件的 finally |
| full_history r1/r2/r3 | 3 | 数据库任务已 accepted/working，但 run 原件没有 primary trace 和实际 worker exit，结果为 TimeoutError；不能补推为计划硬退出 |
| 首个 after_observation r1 环境失败 | 1 | 缺的是 verification 的 incident.verification，不是数据库。已 accepted/working、没有 completed；保留 TimeoutError/ConnectError/ValueError，底层中断原因未由这些原件确认 |

E1-c 三例均有暂停、复活和旧请求拒绝标记，原主任务最终各写 1 条 access；原 AIP 生命周期却仍各有 1 条未完整。access 落盘与 AIP task-result 完整性必须分开。

## 源码与验收范围

- 当前项目补丁 `vendor/ACPs-community/acps-sdk/acps_sdk/amp/group_access.py:66–89`：callback 返回/抛异常后才在 finally 写 access。该文件是本项目新增群组钩子，不是上游已有的强持久性保证。
- `acps_mcp_bridge/experiment.py:140,170–177`：默认 exit callback 为 `os._exit`，先保存 crash trace，再退出。
- 官方 MessageEmitter 调用位置 `aip_group_partner.py:781–803` 在 handler 前写 receive；`aip_group_leader.py:860–880` 在 publish 后写 send。MessageEmitter 的 correlation_id 是 sessionId，关联本次命令须用 body.messageId；不能误用 access 的 sessionId/taskId 字段约定。
- `eval/reconcile_access.py:13–17` 对所有已捕获 Start 无条件期待 caller/callee 两条；是否 completed 在另一统计项中判断。因此 18 缺端是该严格口径下真实缺记录，没有发现键过滤、坏行或重复计算造成的这 18 条假缺失。
- 高分方案 T05 的原验收位于 `docs/高分方案_需求架构创新与任务_20261017.md:499`：跑一次 F10 做任务/access 对账。本批故意退出/环境失败任务的全量双端完整性是更强的观察范围，不能用它改判历史 F10，也不能据此把本批 false 改 true。

现有 access 是完成回调后的终态记录。若未来要求硬退出也必须可恢复记录，需要另定 admission/recovery 语义；提前记录 200 会伪造处理成功。本轮不修改产品、统计口径或原结果。

## 复现与收据

在同一保留原件的工作区，用项目 Python 执行 `diagnose_missing_access.py`。它只读取闭合文件，不导入产品控制器，不调用 Docker、WSL、平台、模型或业务；输出文件必须不存在，以免覆盖历史诊断。

`missing-access-diagnosis-final.json` 保存逐条安全投影与 151 个输入文件的哈希；`source-ready.json` 绑定最终脚本、结果和本说明。初次诊断的错误 AMP join 和“全部主库”假设导致 exit1，原脚本/结果保留为 revision1；最终脚本已纠正，原输入均未改。

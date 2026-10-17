# [Bug][SDK 2.2.0] 迟到的 TaskResult 会把 awaiting-completion 回退为 working

同一任务的 TaskResult 按到达顺序覆盖状态时，较早生成但较晚到达的 working 会覆盖
awaiting-completion。我们在正式 AMQPS 通信中观察到这一序列，协调者因此看不到已经
就绪的 Product，首次联调失败。

环境为 ACPs SDK `2.2.0`，基于提交
[`3985c1330209f075c124669cc9d31f0e75448140`](https://github.com/AIP-PUB/ACPs-community/tree/3985c1330209f075c124669cc9d31f0e75448140)。
使用官方 GroupLeader / GroupPartner、mTLS AMQPS，业务任务为只读 describe。

## 实际观察

2026-10-17 09:57 UTC 的同一 task，journal 按接收顺序保存了：

| event_id | state | status.stateChangedAt（UTC） |
| --- | --- | --- |
| 3 | accepted | 09:57:16.042798 |
| 4 | awaiting-completion | 09:57:16.092857 |
| 5 | working | 09:57:16.068235 |

event 4 含 products。event 5 的发送方状态时间比 event 4 早约 24.6ms，但到达更晚；
该次失败记录中 task_attempts.state 最后为 working。这里只证明应用收到的结果乱序，
没有据此判断是 Broker、并发发布还是消费调度造成了乱序。

基线的 `GroupLeader._handle_task_update` 对每条结果直接调用
`group_session.record_task_state`。TaskJournal 是我们新增的持久化适配；其初版沿用
同样覆盖方式，也记录了状态回退。原生内存状态与新增持久化投影都需要防护。

## 最小复现

下面脚本不需要 Broker；它向真实 GroupLeader 的结果处理入口注入同一任务的三条官方
TaskResult。基线最后状态是 working；修复后应为 awaiting-completion。

```python
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock
from acps_sdk.aip import TaskResult, TaskState
from acps_sdk.aip.aip_group_leader import GroupLeader

async def main():
    leader = object.__new__(GroupLeader)
    leader._task_listeners, leader._last_task_results = [], {}
    session = SimpleNamespace(session_id="session", record_task_state=Mock())
    for state, second in [("accepted", 1), ("awaiting-completion", 3), ("working", 2)]:
        at = f"2026-10-17T09:57:{second:02d}+00:00"
        task = TaskResult(groupId="group", id=f"r-{second}", senderId="partner",
            senderRole="partner", sentAt=at, sessionId="session", taskId="task",
            status={"state": state, "stateChangedAt": at})
        await leader._handle_task_update(session, task)
    assert session.record_task_state.call_args.kwargs["state"] == TaskState.AwaitingCompletion

asyncio.run(main())
```

## 预期与建议

按 `(sessionId, taskId, senderId)` 合并有效状态；较早的发送方状态时间不覆盖较新投影。
所有原始结果仍可进入事件历史，便于审计。进入终态后，不允许迟到的非终态结果复活任务。

不能简单把状态排成固定大小：较新的 Continue 合法地允许 awaiting-completion 回到
working。我们当前补丁优先比较 `status.stateChangedAt`，缺失时回退 `sentAt`，并保护终态；
同一发送方的序列号若有协议支持，也适合用于排序。这组验证尚未覆盖不可信或损坏时间戳
的所有策略。

本地已添加三项回归：迟到 working、真正较新的 working、持久化事件保留与终态保护。
随后在 2026-10-17 10:07:47–10:08:02 UTC 完成修复后的正式平台复验：经官方 ADP
选出容器中的应用、数据库、验证三个正式身份，完成 describe 与任务生命周期，并通过
实际 PostgreSQL MCP 返回 read_only=false，复验状态 completed。原始 TaskCommand 与
TaskResult 已归档。这验证了修复后该只读接入流程，不是新身份接管或故障恢复验收。

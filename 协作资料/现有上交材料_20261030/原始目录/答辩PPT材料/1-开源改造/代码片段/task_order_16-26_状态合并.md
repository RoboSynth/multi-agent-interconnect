# task_order_16-26_状态合并

源文件：`vendor/ACPs-community/acps-sdk/acps_sdk/aip/_task_order.py`，第 16–26 行。

保留终态，按发送方状态时间阻止迟到结果回退状态。

```python
def accepts_task_update(candidate, previous):
    if previous is None:
        return True
    old_state = previous.get("status", {}).get("state")
    new_state = candidate.get("status", {}).get("state")
    if old_state in TERMINAL_STATES and new_state != old_state:
        return False
    before, after = result_time(previous), result_time(candidate)
    if before is not None:
        return after is not None and after >= before
    return True
```

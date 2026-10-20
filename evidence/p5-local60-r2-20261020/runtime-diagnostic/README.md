# 第二批本地矩阵：验证产品序列化诊断

本诊断只读分析正在运行的矩阵，并离线校验已捕获消息；没有修改调度算法、冻结源码、运行资源或原始结果。

## 已证实的根因

首个无效产品来自首轮 F01 / M0 的 `inc-f71dcc3d0be546df`，时间为 `2026-10-20T05:15:26.829614+00:00`。

- 原始记录为 `matrix/transport/messages.jsonl` 第 82 行，完整行（含末尾换行）SHA256：`e5af360e34224db138247efd48fd6df94b24b1cbab0267fbdf8a331304836dae`。
- 原始行逐字节保存在 [first-invalid-message.json](first-invalid-message.json)。
- `TaskProduct.model_validate` 精确报错：`facts.6.value: Field required`。
- 该事实为 `carried_symptom_intents`，有 `key/source/observed_at`，缺少 `value`。

生成路径为：

1. `incident/partners.py:193` 在没有遗留快速复查请求时生成 `value=None` 的事实。M0 正常就会进入此分支。
2. `incident/contracts.py:58` 中 `Fact.value: Any` 允许显式 `None`，但该字段仍然必填。
3. `incident/local_worker.py:224` 将产品 `model_dump(exclude_none=True)`，递归省掉这个事实的 `value`。
4. `incident/local_transport.py:274` 在收到 `awaiting-completion` 时重新校验产品，因必填字段消失而失败。

离线复现同时证实：补回 `value=None` 后初次校验成功；再次执行与 worker 相同的序列化后，`value` 消失且重新校验失败。只在内存副本中移除这条不适用的事实后，产品校验通过。详细结果见 [validation-reproduction.json](validation-reproduction.json)，复现入口为 [reproduce_product_validation.py](reproduce_product_validation.py)。

## 后续影响

这不是一次业务观察失败。`incident/local_transport.py:293` 捕获校验错误后将验证 worker 的通道标为 `failed`，设置所有该 worker 在途任务的异常，然后结束唯一的 stdout 读取协程。进程仍可存活、继续写心跳，stderr 也可以为空；这些现象不能证明 AIP 任务通道可用。

`incident/local_transport.py:321` 会拒绝向非 ready worker 发布后续任务；`eval/run.py:199` 至 `:214` 只在整个矩阵开始时建立一次 transport，之后每格复用。所以首个无效产品之后的验证任务会持续因同一失效通道失败，不会在下一格自动恢复。

本次取样已观察到 21 个终态格，其中首个无效产品所在格及之后共 20 格，后续出现 `selected local domain worker is unavailable` 等错误。此数字只是诊断快照，不是最终矩阵计数。消息与结果文件取样时的字节数及 SHA 已记录。原始各格终态、tasks、planning_history 必须保留；这些通道失败不能写成调度算法未修复业务的证据，异常短耗时也不能拿来比较加速。

## 建议修复（未应用）

最小局部修复：没有遗留请求时，直接不生成 `carried_symptom_intents` 这条事实；有遗留请求时仍保持原有汇总结构和收敛判定。不要放宽 `Fact.value` 的必填约束来掩盖缺失，也不必为此修改调度、预算或排序。

补充一个覆盖缺口的离线测试：让没有 symptom state 的 `VerificationPartner` 完成验证，将产品走过 `TaskProduct.model_validate(...).model_dump(exclude_none=True)`，再重新 `TaskProduct.model_validate(...)`；应成功。再保留有遗留请求分支的同样往返测试。直接调用 partner 的测试不会触及这次序列化缺口。

修复后应由代码负责人确认，再冻结为新的执行版本和独立批次。当前批次不能中途修改源码、恢复通道后接着填满并当作一个完整同版本矩阵。

# [Feature] 为群组任务增加可选 AMP access 适配，按首次 Start 统计任务尝试

建议在 GroupLeaderMqClient / GroupPartnerMqClient 增加可选 AccessEmitter 注入。
群组任务包含 Start、Complete、Get 和重投等多个消息边事件，业务访问统计需要一个明确
的任务尝试口径，便于与 sessionId / taskId 对账。

这是基于 ACPs SDK `2.2.0`、提交 `3985c1330209f075c124669cc9d31f0e75448140` 的功能建议。
基线已有官方 AMP AccessEmitter 与 MessageEmitter；本建议补群组接入钩子，不是声称
上游原生已经存在一个错误的首次 Start 计数器。

## 建议的统计语义

对每个 `(sessionId, taskId, direction)`，在每个 client / middleware 实例及其 LRU 缓存生命周期内，只记录收到或发送的第一次 Start。
Complete、Get、Continue 及同 TaskId 的 Start 重投不新增 access，但仍照常执行协议处理。
重试若是新的任务尝试，使用新的 TaskId，新增一条记录。

Leader 发送记录的 202 表示成功发布；Partner 处理记录根据 handler 结果统计成功或失败。
它们都是 AMP access 状态码，不改变原生 AIP TaskResult 状态。
原有 MessageEmitter 继续记录完整 send/receive/ack 边事件。

| 输入序列 | 预期 handler / publish 次数 | 每一侧预期 access 条数 |
| --- | --- | --- |
| Start(t1), Complete(t1), Start(t1) 重投 | 3 | 1 |
| 再发 Start(t2) | 再执行 1 次 | 再增加 1 条 |
| 首次 Start(t1) 抛异常，重投随后成功 | 2 | 1，保留首次失败结果 |
| Partner 未被 mentions 定向 | 0 次业务处理 | 0 |

## 已实现的原型与复现

当前本地原型提供 `access_emitter=AccessEmitter(path, aic)`，未注入时沿用原行为。
`GroupAccessMiddleware` 可从 StructuredDataItem.data、JSON 文本或 commandParams 提取
skill/tool 路由，并写入 caller/callee、耗时、trace_id=sessionId、correlation_id=taskId。
业务 handler 返回 rejected / tool_error 时记录失败，异常详情只保存类型。

可在补丁树运行：

```powershell
python -m unittest discover -s acps-sdk/tests/resumable -p test_resumable.py -k OfficialGroupIntegrationTests -v
```

其中 `test_partner_start_complete_redelivery_counts_one_structured_route` 与
`test_leader_start_complete_redelivery_counts_one_access` 直接使用官方群组客户端，
分别检查三次调用仍只有一条 access；测试还覆盖结构化路由、业务失败、首次异常重投。
这些测试无需真实 Broker。

另一次本地真实 AIP stdio 调度验收捕获 33 次原生 Start，对照双方 AMP 文件为 66 条
access，缺失 0、多计 0。这是本地对账结果，未据此声称平台 Monitor 已入库。

2026-10-18 又对一个已经正常关闭的正式 Wutong AMQPS 健康窗口做了独立对账：
12 个不同 Start，协调端 12 条、六个参与资源域合计 12 条 access，共 24 条；缺失、
多余及不完整生命周期均为 0。长运行日志中另有 481 条无关 access，按该窗口捕获的
taskId 排除。该窗口与上面的本地 33/66 分开记录，仍不证明 Monitor 入库、访问排行
或正式故障接管；access 也不等于物理消息数、MCP 调用数或资源修改次数。

## 范围与接口讨论

去重缓存默认是每个 middleware 实例内的 8192 项 LRU，可配置上限。实例重建或条目被淘汰后可能重新计数，
因此它不是跨进程永久去重保证。需要跨进程统计时，可在汇总端按相同键做 distinct。
也希望维护者确认此“首次尝试结果”口径是否适合作为可选默认，或应提供策略参数。

应用适配器必须把真实业务结果返回给统计层。我们在项目桥接器发现过 handler 发布
Product 后未 return 的接法，已在项目层修正；这不是 SDK 原生处理器的缺陷。

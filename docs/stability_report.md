# AMP稳定性统计口径

`python -m eval.stability_report <AMP目录> --output <新结果.json>`读取指定目录中的`amp_*.jsonl`。默认心跳周期15秒，可用`--heartbeat-interval-seconds`明确调整。修订输出使用新目录，既有冻结报告保持原字节和原算法来源。

## 可选固定窗口与期望身份

固定窗口修订的应用状态为 已应用11个源码/测试/部署文件并完成本地验收：6项fresh导入/CLI均exit0，native start实际exit0、公共入口v2，产品验证器30.031秒/30次全成功/10流程通过，证据为 [固定窗口离线证明](../evidence/development-candidates-20261018/offline-stability-window.json)。其新增 `--window-start`、`--window-end` 与可重复的 `--expected-aic`，起止必须成对带时区并统一输出UTC，窗口为 `[start,end)`。未提供新参数时保留原默认输出；不能将后续可选模式的证明倒用于既有冻结报告。

固定窗口以起点为锚，按显式心跳周期分槽，总槽数为 `ceil(window_seconds/interval)`，样本以 `floor((timestamp-start)/interval)` 归位，每槽最多记一次；最后不足一个周期仍算一个槽。期望身份即使完全缺席仍保留完整分母。窗口内有效包先过滤再去重，窗口外包不会补窗内样本；没有期望清单时不推断谁应出现。

`heartbeat_sampling_window.coverage_percent` 是采样槽完整度；旧首末样本内部覆盖保留为次值。窗口边界抖动和末尾短槽会影响数值，既不是TTL存活占比，也不能据缺样直接认定宕机。21个不同离线检查为8旧+12新项目测试+1完整输出artifact对照；修订后13项受影响检查复跑、8项复用，不相加成34，也不证明任何真实24小时运行。

记录先验证非空log_id、类型、AIC和带时区时间戳，再按log_id去重；无效行单独计数，不占用后续有效行的ID。access正文必须为对象。时延仅接受有限、非负的数字，布尔值、NaN、无穷和负值另计，不进入分位数。

每个AIC只使用第一个至最后一个已观察心跳之间的区间。同一时间戳只提供一个心跳样本，原始记录数和重复时间戳数分别保留。相邻样本间隔除以周期，按最近整数估计经过的周期数，容许半个周期的调度偏移；例如周期15秒时，29.9秒间隔估计缺一个心跳。该值属于心跳节奏估计，不能证明在线率。单个时刻没有可测区间，覆盖率输出null。

访问时延p95采用nearest-rank，即排序后第`ceil(0.95*n)`个值。callee等于该记录AIC、caller为另一AIC的access另列为参与者处理耗时。发送侧耗时与处理耗时均不能替代协调者的真实任务往返耗时。

默认模式仍只衡量首末已见心跳之间的采样，不能测量边界外的在线时长或完全缺席身份；可选固定窗口与期望集合补齐的是采样分母，不把缺样推算成真实停机。本地文件不能证明密码学签名有效、Monitor/Kafka入库、巡检成功、连续24小时或7×24可用；这些结论仍需对应运行窗口、身份清单及平台证据。方法与验证边界见[本批结果说明](free_tools_matrix_20261018.md)。

## 巡检、演练与真实任务耗时组合报告

`eval/stability_bundle.py` 是薄报告入口，直接复用上面的 `summarize`；原函数、原CLI与JSON语义保持不变。它只读取显式指定的已记录文件，不连接工作台、平台、模型或业务资源。示例：

```powershell
python eval/stability_bundle.py <AMP目录> --output <不存在的新目录> `
  --window-start 2026-10-18T06:55:21Z --window-end 2026-10-18T07:25:21Z `
  --expected-aic <身份1> --expected-aic <身份2> `
  --scheduler <原生events.jsonl> --coordinator <最终incident.json>
```

两类输入都可重复指定。scheduler只接受`ops/schedule.py`原生JSONL：`at/event`，用`run_id`关联`job_started(kind,incident_id)`与`job_finished(status,seconds)`。只处理窗口内事件；缺端、冲突、不同事故身份或结束早于开始均保留unknown。未观察到演练不等于演练关闭或通过，未提供期望周期时不推算调度完成率。`seconds`是工作台报告的事故耗时，不是事件墙钟相减，也不是独立业务恢复验收。

coordinator接受`IncidentCoordinator`保存的最终事故JSON（`id/tasks`），仅提取任务的`logical_task_id/kind/status/started_at/elapsed_ms`。按任务开始时间选入`[start,end)`；最终结果可能在窗口结束后返回，不声称窗口内均已完成。有效失败/unknown效果任务的实测耗时也保留。缺失、待派发、待审批或非法耗时不补零；不同最终快照对同一任务给出冲突时不选择较快值。

任务`elapsed_ms`来自协调者monotonic计时，可能包括审批等待、传输、参与者处理和结果校验，不能叫纯网络RTT、AMP处理耗时或故障到恢复总时长。AMP两种耗时与协调者任务耗时分别作图，p95沿用nearest-rank。原AMP摘要没有有效耗时样本数，该项写unknown，不从access条数反推。

输出是`summary.json`、四个CSV（心跳、调度任务、协调者任务、不同口径时延）、PNG/SVG静态图及产物SHA清单。缺失CSV数值写`unknown`；图上身份别名与`heartbeats.csv`对应。摘要保留原AMP字段与身份，发布前须按项目材料规则审核。manifest只记录输入顺序ID、字节数与SHA，不泄露原始路径、任务参数或产品正文。输出目录必须不存在；图形依赖沿用已有Matplotlib/Agg，不自动安装软件。

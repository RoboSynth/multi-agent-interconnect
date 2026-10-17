# 本地模型调度实验

记录 9/9 项；协调完成且持续业务恢复 9 项；证据诊断精确匹配 9 项。

耗时是协调与域验证总耗时；恢复为 1 rps 采样估计。表格保留失败计数，未完成矩阵不作完整实验结论。

| 场景 | 方法 | 完成/记录 | 诊断正确 | 探测中位数 | 总耗时秒 | 成功恢复估计秒 | token中位数 | 回退/模型失败 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F06 | M0 | 3/3 | 3 | 6 | 31.578 | 5.328 | 0 | 0/0 |
| F06 | M1 | 3/3 | 3 | 6 | 33.344 | 7.125 | 3664 | 0/0 |
| F06 | M2 | 3/3 | 3 | 6 | 57.203 | 25.766 | 7522 | 0/0 |

- Local native-process/AIP-stdio evidence; not formal platform AMQPS/ADP.
- M1 freely selects observations and shares evidence-based repair rules.
- Recovery time is a 1rps observation estimate; total coordination time includes 30s domain verification.
- Raw recovery_confirmed_seconds is the later observer-stop time; analysis-rows derives earliest 30s/10-flow confirmation from original requests and injection timestamps.
- Held-out instances vary workload seeds and resource revisions/PIDs within the same fault families.
- Recovery medians use only completed, continuously confirmed cells; failure counts and every raw row remain visible.

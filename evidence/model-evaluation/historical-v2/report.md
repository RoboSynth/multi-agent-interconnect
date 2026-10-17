# 本地模型调度实验

记录 45/45 项；协调完成且持续业务恢复 36 项；证据诊断精确匹配 45 项。

耗时是协调与域验证总耗时；恢复为 1 rps 采样估计。表格保留失败计数，未完成矩阵不作完整实验结论。

| 场景 | 方法 | 完成/记录 | 诊断正确 | 探测中位数 | 总耗时秒 | 成功恢复估计秒 | token中位数 | 回退/模型失败 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F01 | M0 | 3/3 | 3 | 7 | 35.703 | 7.844 | 0 | 0/0 |
| F01 | M1 | 3/3 | 3 | 6 | 36.547 | 6.109 | 3042 | 0/0 |
| F01 | M2 | 3/3 | 3 | 6 | 70.25 | 10.469 | 7279 | 0/0 |
| F02 | M0 | 3/3 | 3 | 6 | 31.375 | 5.156 | 0 | 0/0 |
| F02 | M1 | 3/3 | 3 | 6 | 34.093 | 6.25 | 3025 | 0/0 |
| F02 | M2 | 3/3 | 3 | 6 | 70.203 | 15.265 | 7388 | 0/0 |
| F06 | M0 | 0/3 | 3 | 5 | 1.188 | None | 0 | 0/0 |
| F06 | M1 | 0/3 | 3 | 6 | 48.766 | None | 3169 | 0/0 |
| F06 | M2 | 0/3 | 3 | 6 | 86.172 | None | 8348 | 0/0 |
| F07 | M0 | 3/3 | 3 | 8 | 32.375 | 5.406 | 0 | 0/0 |
| F07 | M1 | 3/3 | 3 | 7 | 33.625 | 7.547 | 4403 | 0/0 |
| F07 | M2 | 3/3 | 3 | 7 | 59.453 | 25.218 | 8582 | 0/0 |
| F10 | M0 | 3/3 | 3 | 9 | 33.39 | 8.985 | 0 | 0/0 |
| F10 | M1 | 3/3 | 3 | 8 | 36.782 | 9.562 | 5004 | 0/0 |
| F10 | M2 | 3/3 | 3 | 8 | 67.047 | 33.515 | 9931 | 0/0 |

- Local native-process/AIP-stdio evidence; not formal platform AMQPS/ADP.
- M1 freely selects observations and shares evidence-based repair rules.
- Recovery time is a 1rps observation estimate; total coordination time includes 30s domain verification.
- Raw recovery_confirmed_seconds is the later observer-stop time; analysis-rows derives earliest 30s/10-flow confirmation from original requests and injection timestamps.
- Held-out instances vary workload seeds and resource revisions/PIDs within the same fault families.
- Recovery medians use only completed, continuously confirmed cells; failure counts and every raw row remain visible.

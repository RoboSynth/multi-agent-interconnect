# PARTIAL：原本地实验中断（40/45终态）

原进程退出码未知，原最终H00缺失，中断原因未验证。33/40持续恢复；另有1格运行中、4格未启动，不补造终态。


记录 40/45 项；协调完成且持续业务恢复 33 项；证据诊断精确匹配 29 项。

故障恢复 33/40；健康对照 0/0，健康对照不计入恢复分母。

耗时是协调与域验证总耗时；恢复为 1 rps 采样估计。表格保留失败计数，未完成矩阵不作完整实验结论。

| 场景 | 方法 | 完成/记录 | 诊断正确 | 探测中位数 | 总耗时秒 | 成功恢复估计秒 | token中位数 | 回退/模型失败 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F01 | M0 | 3/3 | 3 | 7 | 39.687 | 11.531 | 0 | 0/0 |
| F01 | M1 | 3/3 | 3 | 1 | 37.329 | 7.406 | 8990 | 0/0 |
| F01 | M2 | 3/3 | 3 | 6 | 65.875 | 10.937 | 7257 | 0/0 |
| F02 | M0 | 3/3 | 3 | 6 | 33.703 | 8.125 | 0 | 0/0 |
| F02 | M1 | 2/3 | 0 | 2 | 37.157 | 13.055 | 8001 | 0/0 |
| F02 | M2 | 3/3 | 3 | 6 | 71.547 | 17.078 | 7465 | 0/0 |
| F06 | M0 | 3/3 | 3 | 6 | 32.531 | 5.672 | 0 | 0/0 |
| F06 | M1 | 0/3 | 0 | 1 | 104.5 | None | 15011 | 0/3 |
| F06 | M2 | 3/3 | 3 | 6 | 69.39 | 28.437 | 7955 | 0/0 |
| F07 | M0 | 3/3 | 3 | 8 | 33.031 | 7.296 | 0 | 0/0 |
| F07 | M1 | 1/3 | 0 | 1 | 69.609 | 45.125 | 14564 | 0/2 |
| F07 | M2 | 3/3 | 3 | 7 | 64.656 | 29.563 | 9218 | 0/0 |
| F10 | M0 | 1/1 | 1 | 9 | 36.031 | 9.86 | 0 | 0/0 |
| F10 | M1 | 1/2 | 0 | 1.0 | 55.578 | 14.547 | 18483.5 | 0/1 |
| F10 | M2 | 1/1 | 1 | 8 | 69.437 | 33.829 | 9354 | 0/0 |

- Local native-process/AIP-stdio evidence; not formal platform AMQPS/ADP.
- M1 freely selects observations, guarded actions and verification; no rule fallback.
- Recovery time is a 1rps observation estimate; total coordination time includes 30s domain verification.
- Raw recovery_confirmed_seconds is the later observer-stop time; analysis-rows derives earliest 30s/10-flow confirmation from original requests and injection timestamps.
- Held-out instances vary workload seeds and resource revisions/PIDs within the same fault families.
- H00 is a separate healthy control: 30 seconds, 10 workflows, no failed/unknown/pending requests or attempted resource actions. It is excluded from recovery rates; legacy H00 rows without this proof are not counted as passed.
- Recovery medians use only completed, continuously confirmed cells; failure counts and every raw row remain visible.

# 分场景版本的真实本地模型对比

主对比 45 项，持续恢复 45 项，证据诊断匹配 45 项。原 F06 失败 9 项完整保留。

各场景内三方法使用相同版本/参数；此表不是单一源码冻结的45次运行。总耗时包含诊断与域验证，恢复为1rps采样估计。

| 场景 | 方法 | 版本 | 恢复/样本 | 探测中位数 | 修改中位数 | 总耗时秒 | 采样恢复秒 | 最早持续确认秒 | token中位数 | 错误阻塞目标调用 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F01 | M0 | v2 | 3/3 | 7 | 1 | 35.703 | 7.844 | 40.141 | 0 | 0 |
| F01 | M1 | v2 | 3/3 | 6 | 1 | 36.547 | 6.109 | 38.406 | 3042 | 0 |
| F01 | M2 | v2 | 3/3 | 6 | 1 | 70.25 | 10.469 | 42.781 | 7279 | 0 |
| F02 | M0 | v2 | 3/3 | 6 | 1 | 31.375 | 5.156 | 36.531 | 0 | 0 |
| F02 | M1 | v2 | 3/3 | 6 | 1 | 34.093 | 6.25 | 38.437 | 3025 | 0 |
| F02 | M2 | v2 | 3/3 | 6 | 1 | 70.203 | 15.265 | 46.593 | 7388 | 0 |
| F06 | M0 | F06-v3 | 3/3 | 6 | 1 | 31.578 | 5.328 | 36.75 | 0 | 0 |
| F06 | M1 | F06-v3 | 3/3 | 6 | 1 | 33.344 | 7.125 | 38.593 | 3664 | 0 |
| F06 | M2 | F06-v3 | 3/3 | 6 | 1 | 57.203 | 25.766 | 57.078 | 7522 | 0 |
| F07 | M0 | v2 | 3/3 | 8 | 2 | 32.375 | 5.406 | 36.766 | 0 | 0 |
| F07 | M1 | v2 | 3/3 | 7 | 2 | 33.625 | 7.547 | 38.844 | 4403 | 0 |
| F07 | M2 | v2 | 3/3 | 7 | 2 | 59.453 | 25.218 | 56.562 | 8582 | 0 |
| F10 | M0 | v2 | 3/3 | 9 | 3 | 33.39 | 8.985 | 40.297 | 0 | 0 |
| F10 | M1 | v2 | 3/3 | 8 | 3 | 36.782 | 9.562 | 40.875 | 5004 | 0 |
| F10 | M2 | v2 | 3/3 | 8 | 3 | 67.047 | 33.515 | 64.844 | 9931 | 0 |

修复范围：F06 injector uses orders_app rather than administrator; planner follows blocking_pids to roots, preserving SQL guards.

v2 used serial native transport with pre-AMQPS-ordering-fix SDK; F06-v3 uses current SDK. See each run's SDK snapshot addendum.

Per-scenario same-version comparisons; not one frozen 45-cell run. Same fault families with held-out workload/revision instances. Model output and usage are raw; stored context.local_hypotheses may reflect later list additions.

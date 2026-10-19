# 正式 E1-c：旧主同进程恢复

本轮从 `43964616d63e1d4aed76ed4f4ef9d474cdfee999` 继续，补齐正式平台 E1-c 的源码和离线验收路径。当前没有启动正式 E1-c、Docker 服务或新的业务故障；旧本地 stdio 实验与本轮证据分别保存。检查入口见[本轮证据](../evidence/p0-e1c-20261019/README.md)。

## 验收的实际行为

主数据库工作者先通过原策略和审批，将原操作持久保存为 `received`，随后对自己发送 `SIGSTOP`。备用仍通过原 ADP、能力确认、邀请、`resume` 和共享账本接管，在更高 fence 下完成一次 `db.restore_writes`。控制器核对暂停中的旧主，再通过 pidfd 向同一 Linux 进程发送 `SIGCONT`；旧主继续处理同一原请求，由正常 Bridge 和账本返回 `rejected_stale_fence`。

一次计划只统计 **1 个恢复后继续执行的原请求**，不生成额外 AIP 重放消息。必须同时观察到同一容器 ID、StartedAt、PID、Linux start ticks、原请求摘要及旧 fence；主方修改 MCP 调用为 0，备用为 1 且有匹配返回。MCP 调用次数不能代替物理副作用次数。

正常接管会先移除失联成员，关闭 AMQP channel 可能取消旧请求的处理。E1-c 专用适配器只延迟当前群组中已确认由备用接管的那个旧主的一次移除，直到取得精确的旧令牌拒绝记录，再调用原 SDK 移除。该实验时序写入计划 effects 和授权，普通 E1-a/E1-b 沿用原行为。

## 准备步骤

先按[自有账号配置](自有账号平台配置_20261018.md)和[开发测试环境](test_environment_20261019.md)准备独立身份、目标和当前源码镜像。Linux 目标需要支持 Python `os.pidfd_open`、`signal.pidfd_send_signal` 的内核。E1-c overlay 仅为主工作者增加 `init: true`，使 Python 不是命名空间 PID 1；备用保持原配置。

在当前项目根目录运行，所有示例身份和镜像 ID 都要换为本次实际值：

```powershell
$python = (Resolve-Path .\.venv-dev\Scripts\python.exe).Path
& $python .\eval\prepare_platform_e1_worker.py --prepare --arm-primary --suspend-primary `
  --output runtime/private/e1c-example/bundle `
  --experiment-id e1c-example --incident-id incident-e1c-example `
  --primary-aic YOUR_PRIMARY_AIC --backup-aic YOUR_BACKUP_AIC `
  --crash-point before_modification

& $python .\eval\platform_resume_experiment.py --prepare --case E1-c `
  --plan runtime/private/e1c-example/plan.json `
  --config runtime/private/YOUR_PROJECT/domains/coordinator/config.json `
  --target-config runtime/private/YOUR_PROJECT/target.json `
  --domain-profile runtime/private/YOUR_PROJECT `
  --bundle runtime/private/e1c-example/bundle `
  --image-id sha256:REPLACE_WITH_ACTUAL_64_HEX_IMAGE_ID `
  --output eval/results/platform/e1c-example

& $python .\eval\platform_resume_experiment.py --plan runtime/private/e1c-example/plan.json
```

以上只准备或检查文件，不启动工作者。准备产物须保留，不向旧 bundle、计划或结果目录覆盖写入。

## 执行绑定与产物

E1-c 使用 `platform-e1-plan/3`，仅支持 `before_modification`、`interruption_mode=suspend`、`replay_attempts=1`，没有 E1-b 的 method。授权采用 `platform-e1-authorization/3`，精确绑定计划 SHA、事故、实验、输出、case、中断点、mode、次数和 effects，以及 `authorized`、`exclusive_coordinator`、`no_other_identity_consumers`、`no_active_or_unknown_operations` 四个真实布尔确认。旧批授权和 `/1`、`/2` 授权不能用于本次执行。

明确批准本次具体运行范围后才执行：

```powershell
& $python .\eval\platform_resume_experiment.py `
  --plan runtime/private/e1c-example/plan.json --execute --approve-high `
  --authorization-file runtime/private/e1c-example/authorization.json
```

恢复前必须证明备用已完成该原操作、共享 fence 已前进、旧主确在 Linux `T/t` 停态，且原审批仍有效。审批过期、进程被替换、记录缺失或取消处理均判失败，不改原请求或续签审批来补成成功。

结果保留原始暂停前/恢复后 trace、进程探针、共享账本前后状态、`e1c-revival-metrics.json`、移出群结果和原始 journal。若旧主最后一条回报没有送达，原 journal 中的未确认尝试按独立证据分类，记录本身不被改写。正常关组后恢复同一目标及普通工作者，再独立检查公共 v2 连续 30 秒、至少 10 个完整订单流程；失败分别保留。

## 当前证据范围

本轮通过 89 个不同的离线测试方法，包含临时 SQLite 账本、真实 Bridge 与可控 MCP fixture、计划与授权、进程守门和失败清理；相关重复复验不累加。源收据与早期失败记录均保留。正式平台的暂停、接管、恢复和业务验收尚未运行，不能由这些离线检查推断已经通过。

另在本机 WSL Ubuntu 中运行了一个独立临时子进程，使用当前控制器的原始 `PROCESS_CODE` 实测 pidfd：暂停态 `T` 经一次 `SIGCONT` 恢复，PID 和 start ticks 保持一致，子进程正常退出 0 并确认终止。该探针不访问 Docker、平台或业务数据库，不能代替正式 E1-c；原始结果保存在本轮证据的 `review/process-probe/`。

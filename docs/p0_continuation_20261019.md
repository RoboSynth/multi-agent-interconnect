# P0 继续开发：正式接续与原键恢复

本轮从团队 `5267a3a4a47aeb0188df4894031cf18c240667ba` 继续，保留队友的 `deploy-check-record.md` 和旧实验结果。新代码在独立分支开发；协作时以 GitHub 最新提交为准，旧运行目录和冻结计划不会自动更新。

## 本轮变化

- 正式 E1 runner 支持三个中断点，分别核对退出码、账本标记、主备实际修改调用和原任务完成记录；接续后的修改使用已生效的 fence。
- E1-b 接入三种交接信息表达，读取真实故障前消息边界，核对实际发送的 IFC 字节及备用参与者确认的摘要。继续修复时只复用未过期事实，缺少连接池 revision 就重新观察。该确定性流程模型调用为 0。
- F12/E5 专用 runner 通过原订单键进入协调器与业务验证器，补足“已提交但回复丢失”的恢复路径。实现和运行边界见 [F12/E5 说明](f12_e5_20261019.md)。
- 新七身份部署配置显式携带 `reply_drop` 第四端口；旧三端口配置仍用于已有场景，F12 会拒绝缺少第四端口的配置。
- 补齐两份无凭据 ACS 测试样例，以及 [开发测试环境](test_environment_20261019.md) 所需依赖。历史部署反馈中的全仓时序、权限等失败仍保留，不能由本轮受影响检查推断全仓通过。

本轮证据是离线检查，索引见 [检查与源码记录](../evidence/p0-continuation-20261019/README.md)。尚未形成正式平台 E1/F12 的新运行结果。

## 正式 E1 的准备入口

先按 [环境与操作步骤](本地开发环境与操作_20261018.md) 和 [自有账号平台配置](自有账号平台配置_20261018.md) 准备自己的隔离项目、七个身份和镜像。下面路径是示例；证书、配置、bundle、计划及输出都必须属于当前 checkout。镜像 ID 必须来自实际部署的镜像。

从项目根运行，每个单例使用新事故、实验编号和新目录：

```powershell
$python = (Resolve-Path .\.venv-dev\Scripts\python.exe).Path
& $python .\eval\prepare_platform_e1_worker.py --prepare --arm-primary `
  --output runtime/private/e1-example/bundle `
  --experiment-id e1-example --incident-id incident-example `
  --primary-aic YOUR_PRIMARY_AIC --backup-aic YOUR_BACKUP_AIC `
  --crash-point after_observation
```

`after_observation`、`before_modification`、`after_applied` 对应 E1-a 三个单例；备用始终未 armed。准备 bundle 只写文件，不启动参与者。

```powershell
& $python .\eval\platform_resume_experiment.py --prepare `
  --plan runtime/private/e1-example/plan.json `
  --config runtime/private/YOUR_PROJECT/domains/coordinator/config.json `
  --target-config runtime/private/YOUR_PROJECT/target.json `
  --domain-profile runtime/private/YOUR_PROJECT `
  --bundle runtime/private/e1-example/bundle `
  --image-id sha256:REPLACE_WITH_ACTUAL_64_HEX_IMAGE_ID `
  --output eval/results/platform/e1-example --case E1-a

& $python .\eval\platform_resume_experiment.py --plan runtime/private/e1-example/plan.json
```

E1-b 仅使用 `after_applied` bundle，在准备计划时指定 `--case E1-b --method from_scratch`，或 `full_history`、`resume_package`。每种方法使用独立计划与结果目录，相同观察、审批、权限、修复及验收要求保持一致。单例通过并不构成三次重复的效果对比。

## 执行前的绑定

新计划采用 `platform-e1-plan/2`；旧 `/1` 仅保留原 E1-a/after_applied 语义，旧源码或配置变动仍会被拒绝。每次执行必须有与计划 SHA、事故、实验、输出、case、中断点和 effects 完全一致的授权 JSON；E1-b 还绑定 method。

授权 schema 为 `platform-e1-authorization/2`，必须明确确认 `authorized`、`exclusive_coordinator`、`no_other_identity_consumers` 和 `no_active_or_unknown_operations` 四个布尔值。不要从旧授权复制这些确认：本机文件锁只能防本机同协调身份重复启动，不能排除另一台机器消费相同 AIC。完整授权检查先于平台、容器和日志账本初始化。

获得本次明确运行范围后，才运行：

```powershell
& $python .\eval\platform_resume_experiment.py `
  --plan runtime/private/e1-example/plan.json --execute --approve-high `
  --authorization-file runtime/private/e1-example/authorization.json
```

控制器只切换本目标的主备数据库工作者，核对原容器、镜像、只读源码、共享账本及启动时间；失败仍尝试关闭自有群组、恢复正常入口并独立检查公共 v2 连续 30 秒、10 个完整订单流程。`results.json` 保留主流程、关闭与恢复的各自失败。修改调用计数不是物理副作用计数；正常关闭的本地状态和 SDK 返回也不是远端 broker ACL 库存证明。

## 尚需继续验收

正式 E1 的平台退出与接管、F12/E5 新运行、E1-c 同进程旧主复活、独立新机器部署、Kafka/Monitor 入库及长期巡检仍分别验收。旧 18 次、旧 45 次和新版 45 次授权已用于各自批次。本轮没有启动新的故障批次，也没有将旧失败、未知订单或历史材料改判为成功。

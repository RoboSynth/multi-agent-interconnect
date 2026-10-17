# 梧桐故障业务运行记录

四个正式业务身份通过审核、取得客户端证书，经官方 ADP 按技能发现三个参与者，通过梧桐 AMQPS 群组完成故障诊断与恢复。

| 项目 | 实际结果 |
|---|---|
| 身份 | 故障协作协调、应用、数据库、恢复分析，共四个正式身份 |
| 自动发现 | 官方 ADP 返回三个业务技能对应的 AIC 和 AMQPS 入口 |
| 进程 | 协调者及三个 Partner 分别运行；记录 Windows 启动器与实际运行进程 PID |
| 组合故障 | 地址错误＋数据库暂停，8 个平台任务，HTTP 503→200 |
| 恢复操作 | 修正应用连接地址一次，恢复数据库服务一次 |
| 业务耗时 | 组合故障 6.190 秒；正常状态 1.532 秒；含启动和收尾全程约 26.5 秒 |
| 正常状态 | 2 个平台任务，HTTP 200→200，零次恢复操作 |
| 订单 | 两种场景的数据保持相同 |
| 结束 | 退出码 0，三个 Partner 正常退出，实验服务端口关闭 |

[结果摘要](incident/RESULT.json) · [完整业务过程](incident/README.md) · [原始结果](artifacts/wutong-incident-20261017T0440Z/RESULT.json) · [平台任务消息](artifacts/wutong-incident-20261017T0440Z/messages.json) · [登记截图](../output/playwright/wutong-incident-approved.png)

## 发现问题与修正

平台默认发现查询只返回 `online`，本项目此前的身份为 `unknown`。线上接口将存活状态放在 `extFilter.alive`，发现请求显式包含 `online`、`offline`、`unknown` 后取得正式候选。业务运行按技能读取官方响应中的 AIC 与端点；[原始请求与响应](incident/discovery-root-cause.json)已保存。平台在线状态由 AMP 心跳链路更新。

## 运行范围

本轮采用现有规则诊断，HTTP/SQLite 业务服务和四个智能体程序均运行在本机。智能体任务经过梧桐消息服务。协调任务从本机命令入口发起，应用、数据库和恢复分析参与者通过 Inbox 接收邀请与任务。

# 此前双智能体交流

两个智能体通过梧桐审核，取得正式身份和客户端证书，完成双向任务交流，程序正常退出。

| 环节 | 实际结果 |
|---|---|
| 提供方 | 使用登录账号中的联系人姓名 |
| 任务协调智能体 | 审核通过，提供 AMQPS Inbox，同时发起和接收任务 |
| 消息回声智能体 | 审核通过，接收任务并回传原消息和任务状态 |
| 身份与证书 | 双方各有正式 AIC 和官方 clientAuth 证书 |
| 消息服务 | `amqps://wt.ioa.pub:5671/acps` |
| 群组服务 | `https://wt.ioa.pub:9007`，携带客户端证书访问 `/health` 返回 HTTP 200 |
| 协调者 → 回声者 | 返回原消息，任务完成 |
| 回声者 → 协调者 | 返回原消息，任务完成 |
| 程序退出 | 退出码 0，双方连接关闭 |
| ADP 目录 | 本轮按技能和 AIC 查询均返回 0 条，通信使用已获批 AIC 指定对方 |

每轮任务经历 accepted、working、awaiting-completion、completed 四个状态。双方使用独立证书，运行于本机同一 Python 进程，消息经梧桐 Broker 往返。

[结果摘要](two-agent/RESULT.json) · [完整任务消息](two-agent/live-bidirectional-fixed-20261017T035844Z.json) · [正式登记资料](two-agent/approved-registry-agents.json) · [群组服务响应](two-agent/group-service-authenticated-health.json)

## 运行

在 incident-pilot 目录执行：

```powershell
& '.\.venv\Scripts\python.exe' 'integration\wutong_smoke.py' --run --config 'integration\private\two-agent\config.json' --timeout 30 --output 'integration\two-agent\live-next.json'
```

运行程序打开两个收件箱，分别发起任务，接收回传结果，结束群组并关闭连接。每轮输出使用新的文件名。

## 实现

采用官方 ACPs SDK / CLI 2.2.0，固定源码提交 `3985c1330209f075c124669cc9d31f0e75448140`。项目代码为每个身份提供一个 Inbox 消费者，分派邀请及邀请反馈；逐群创建任务客户端处理消息。

首次平台运行已完成两轮任务，退出时出现关闭超时。原因是 SDK 在退群消息回调中关闭自身通道。项目侧将关闭动作移到独立生命周期任务，随后两轮平台任务和连接关闭均完成。首次记录保留在 [原始运行结果](two-agent/live-bidirectional-20261017T035145Z.json)。

## 历史资料

- [首次审核意见与原因](two-agent/rejection-analysis-v1.json)
- [获批状态](two-agent/resubmission-current-status.json)
- [ADP 技能查询](two-agent/approved-agent-discovery.json) · [ADP 身份查询](two-agent/approved-agent-discovery-by-aic.json)
- [此前本地故障协作测试](../artifacts/campaign-20261017-final-v2/REPORT.md)

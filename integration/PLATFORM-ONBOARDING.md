当前四身份故障业务已完成官方自动发现和平台运行。最新入口、配置及实际结果见 [故障业务说明](incident/README.md)和[运行记录](BUILD-VERIFICATION.md)。下文保留此前双智能体接入步骤与原始发现现象。

# 梧桐双智能体接入流程

采用 ACPs **v2.2.0**、协议 **02.02**，源码提交 `3985c1330209f075c124669cc9d31f0e75448140`，本地位于 `vendor/ACPs-community`。

## 任务与当前结果

| 本地设计 | ACS 文件 | 功能 |
|---|---|---|
| 任务协调智能体 | `two-agent/leader.resubmission.acs.json` | 创建群组、发送任务、接收邀请、回传消息、汇总结果 |
| 消息回声智能体 | `two-agent/partner.resubmission.acs.json` | 接收 Inbox 邀请、加入群组、返回消息和任务状态 |

任务输入为 `{"operation":"read-only-probe","nonce":"随机值"}`；返回 JSON 包含同一 `nonce`、`partner_aic`、`observed_utc`、`result:"probe-received"` 和 `business_mutations:0`。

“任务协调智能体”和“消息回声智能体”均已通过审核，取得正式 AIC 和客户端证书。程序通过梧桐完成双方互发任务，返回原消息及四阶段任务状态，并正常关闭连接。[历史摘要](../docs/historical-baseline-evidence.md#two-agent)记录双向任务状态、退出和证据范围。首轮驳回意见见[协调者记录](two-agent/leader.rejection-observation.json)、[回声记录](two-agent/partner.rejection-observation.json)。

## 地址与交流流程

| 服务 | 地址 |
|---|---|
| 注册页面 | https://wt.ioa.pub/registry/ |
| Registry / CA / Discovery 根地址 | `https://wt.ioa.pub/registry-server` / `https://wt.ioa.pub/ca-server` / `https://wt.ioa.pub/discovery` |
| ADP 查询 | `https://wt.ioa.pub/discovery/acps-adp-v2/discover` |
| AMQP broker | `wt.ioa.pub:5671`，vhost `acps` |
| MQ Group API | `https://wt.ioa.pub:9007`，运行参数为 `mq_auth_url` |

回声端点为 `amqps://wt.ioa.pub:5671/acps?inbox=inbox_{AIC}`，transport 为 `AMQP`，security 为 `[{"mtls":[]}]`。Registry 审批后替换 `{AIC}`；AMP 日志另用 Kafka/TLS 端口 `wt.ioa.pub:19092`。

本次流程：登记双方 → 取得 AIC 与 clientAuth 证书 → 连接各自 Inbox → 按正式 AIC 创建群组并授权 → Inbox 邀请 → 下发任务 → 返回内容 → 确认完成 → 交换发起方再执行一轮。任务状态依次为 `accepted`、`working`、`awaiting-completion`、`completed`。本轮 ADP 查询未返回这两项记录，原始响应见 `two-agent/approved-agent-discovery.json`。

`wutong_smoke.py` 为双方分别建立一个 `InboundProbeLeader`，每个身份由一个 Inbox 消费者接收邀请和消息反馈。入站任务交给群组客户端处理，出站任务由该身份创建群组发起。`--run` 依次执行双方互发任务；`--serve --serve-seconds 600` 提供持续消息接收。两种运行方式分别使用同一套身份配置。

## 准备材料与登记

网页操作依次为：进入“我的智能体” → 创建或编辑角色 → 填入 ACS → 独立实例选择“可派生/本体：否” → 保存 → 提交审核 → 在详情页读取审核意见及 AIC。

以下命令在 `incident-pilot` 根目录执行。

CLI 公共配置为 `integration/acps-cli.toml`，个人配置使用 `integration/acps-cli.local.toml`。OIDC 通过浏览器设备授权登录；local 模式在终端交互输入账号信息。

```powershell
$cli = '.\.venv\Scripts\acps-cli.exe'
$config = 'integration/acps-cli.local.toml'
& $cli --config $config auth login
```

用 CLI 登记时，对 `$role = 'leader'` 和 `$role = 'partner'` 分别运行；`$agentId` 取自保存结果：

```powershell
& $cli --config $config agent save --acs-file "integration/two-agent/$role.acs.json" --no-ontology --json
& $cli --config $config agent submit --agent-id $agentId --json
& $cli --config $config agent check --acs-file "integration/two-agent/$role.acs.json" --json
& $cli --config $config agent sync --acs-file "integration/two-agent/$role.acs.json" --json
```

## 获取证书并运行任务

从双方详情页复制 AIC，赋给 `$leaderAic`、`$partnerAic`；材料存入 `integration/private/two-agent/`：

```powershell
foreach ($role in @('leader', 'partner')) {
  $agentAic = if ($role -eq 'leader') { $leaderAic } else { $partnerAic }
  & $cli --config $config cert eab fetch --aic $agentAic --output "integration/private/two-agent/$role-eab.json"
  & $cli --config $config cert issue --aic $agentAic --eab-file "integration/private/two-agent/$role-eab.json" --usage clientAuth --key-path "integration/private/two-agent/$role.key" --cert-path "integration/private/two-agent/$role-chain.pem" --trust-bundle-path 'integration/private/two-agent/trust-bundle.pem'
  & $cli --config $config cert status --aic $agentAic --cert-path "integration/private/two-agent/$role-chain.pem"
}
```

EAB 包含 `keyId`、`macKey`、`aic`。CLI 生成私钥、CSR、ACME account 和证书。AMQPS 出站连接使用 `clientAuth`；HTTPS/mTLS 服务按服务域名配置 `serverAuth` 证书。

按[运行配置](two-agent/runtime-config.example.json)填写 `integration/private/two-agent/config.json`，包括双方 AIC、Partner 端点及 `mq_auth_url`。证书与私钥路径填写同目录的 `leader-chain.pem`、`leader.key`、`partner-chain.pem`、`partner.key`，trust bundle 填写 `trust-bundle.pem`。

```powershell
& '.\.venv\Scripts\python.exe' '.\integration\wutong_smoke.py' --run --config '.\integration\private\two-agent\config.json' --timeout 30 --output '.\integration\two-agent\live-run-01.json'
```

每轮使用新的结果文件名，输出保存群组 ID、任务 ID、消息、状态、随机值和返回内容。

## 接入故障协作角色

双智能体消息任务完成后，将回声处理器替换为应用故障信息采集，再加入数据库和恢复分析 Partner。对应 ACS 位于 `acs/application.draft.json`、`acs/database.local-draft.json`、`acs/verification.local-draft.json`、`acs/leader.local-draft.json`。

```powershell
.\.venv\Scripts\python.exe integration\build_registration.py --mq-endpoint 'amqps://wt.ioa.pub:5671/acps?inbox=inbox_{AIC}' --provider-file integration\verified-provider.json --require-official-schema
& $cli --config $config discover query --request-file integration/discovery-application.request.json
& $cli --config $config discover query '查找可以采集实验应用故障证据的智能体' --limit 5
```

CLI 在 Discovery 根地址后拼 `/acps-adp-v2`；Demo 简化客户端拼 `/discover`。公开请求采用 `and` 过滤，MQ 能力采用 `amqp:0.9.1`；线上 `rabbitmq:>=4.2` 内容以 ADP 原始字典读取。

## 来源与资料

- [梧桐文档](https://wt.ioa.pub/docs.html) · [官方代码](https://github.com/AIP-PUB/ACPs-community/tree/v2.2.0) · [构建记录](BUILD-VERIFICATION.md)
- [平台接口记录](artifacts/platform-probe-20261017-105722-a83fe7/REPORT.md) · [Group API 地址资料](two-agent/acl-probe-20261017-route-research/REPORT.md) · [运行接口说明](two-agent/smoke-readiness-notes.md) · [配置清单](platform-missing-fields.json)
- 官方源码：`acps-specs/03-ACPs-spec-ACS/ACPs-spec-ACS.md` §3.5；`registry-server/app/agent/{acsSchema.json,service_acs.py,service_provider.py}`；`acps-sdk/acps_sdk/aip/{aip_group_partner.py,aip_group_leader.py,aip_group_auth.py}`；`acps-cli/acps_cli/ca/{commands.py,config.py}`。

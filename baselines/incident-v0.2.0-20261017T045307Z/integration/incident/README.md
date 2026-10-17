# 梧桐故障诊断与恢复

协调者由本机命令发起业务，通过官方 ADP 按能力查找三个参与者，然后通过梧桐 AMQPS 群组发送任务。应用、数据库和恢复分析参与者分别使用独立正式身份、客户端证书和进程。

## 实际运行结果

四个业务身份全部审核通过并取得客户端证书，三个参与者已通过官方 ADP 按技能发现。两种业务场景经梧桐完成，共十个任务，程序退出码 0。

| 场景 | HTTP 前→后 | 平台业务任务 | 恢复操作 | 业务耗时 |
|---|---|---:|---:|---:|
| 地址错误＋数据库暂停 | 503→200 | 8 | 2 | 6.190 秒 |
| 正常状态 | 200→200 | 2 | 0 | 1.532 秒 |

两种场景的订单数据均保持相同。三个参与者分别正常退出；本轮实验网站和数据库端口已关闭。耗时记录从诊断开始到业务结果返回，整个程序包含启动、发现、组队和收尾，共运行约 26.5 秒。

[结果摘要](RESULT.json) · [本轮完整结果](../artifacts/wutong-incident-20261017T0440Z/RESULT.json) · [完整任务消息](../artifacts/wutong-incident-20261017T0440Z/messages.json) · [平台登记截图](../../output/playwright/wutong-incident-approved.png)

首次启动受到本机沙箱 AMQPS 访问限制，随后改用本机权限运行；Windows 启动器 PID 与实际 Python 进程 PID 已分别记录。首次失败结果保存在 [原始记录](../artifacts/wutong-incident-20261017T0439Z/RESULT.json)。

## 业务过程

实验同时把订单网站的数据库地址改错、将实验数据库设为暂停状态。协调者读取应用故障信息，向数据库参与者查询实际地址和运行状态，安排应用修正连接地址，再安排数据库恢复服务。恢复分析参与者通过网站读取 SQLite 中的订单并返回业务结果。

组合故障共需八个业务任务：

1. 应用读取故障和配置。
2. 数据库返回实际地址和暂停状态。
3. 应用修正连接地址。
4. 应用读取当前访问结果。
5. 数据库返回当前状态。
6. 数据库恢复服务。
7. 应用返回订单访问结果。
8. 恢复分析参与者查询订单并返回结果。

诊断沿用现有规则；业务服务为本机 HTTP/SQLite。实验中的暂停通过服务状态模拟，恢复动作修改本轮实验配置和服务状态。

## 自动发现

入口：`https://wt.ioa.pub/discovery/acps-adp-v2/discover`。

查询使用官方 SDK 的 `DiscoveryRequest` 生成 ACS 条件，并补充线上新增的 `extFilter.alive`。平台默认查询只返回 `online`；未向平台上报监控状态的新身份为 `unknown`。本程序显式查询 `online`、`offline`、`unknown` 候选，从响应中读取正式 AIC 与 AMQPS 入口，再邀请本轮三个参与者。

这一步使用官方目录。原始问题、请求和响应见 [发现原因](discovery-root-cause.json)；已完成的回声技能发现见 [实际响应](echo-official-discovery.json)。`online` 状态由平台 AMP 心跳链路更新。

## 运行

四身份配置位于本机 `integration/private/incident/config.json`，包含各身份的证书路径。证书、私钥及 EAB 保存在该目录。

```powershell
& 'D:\AI + 开源\incident-pilot\.venv\Scripts\python.exe' 'D:\AI + 开源\incident-pilot\integration\wutong_incident.py' --run --config 'D:\AI + 开源\incident-pilot\integration\private\incident\config.json' --scenarios combined,healthy
```

程序自动启动实验数据库、网站和三个参与者，生成独立运行目录。`RESULT.json` 保存业务结果、身份、任务与进程信息，`messages.json` 保存平台任务消息，`events.jsonl` 和各参与者记录保存发现、决策、动作和返回内容。

## 登记与本地运行资料

- [四身份草稿](draft-agents.json)
- [提交记录](submitted-agents.json)
- [当前审核状态](registration-status.json)
- [审核历史](review-history.jsonl)
- [协调者入口说明](leader-cli-entry-update.json)
- [本地业务回调试验](../artifacts/incident-offline-8c472eca/RESULT.json)

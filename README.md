> 当前目录是私有团队开发快照，不是最终比赛交付包。先看 [协作快速开始](COLLABORATION.md)。
> 当前高分分支使用真实 PostgreSQL 订单、MCP→AIP 网关和接续 SDK；下面保留 v0.2.0 的历史 README 主体。
> [高分方案](docs/高分方案_需求架构创新与任务_20261017.md) · [P0审计](docs/P0完成审计_20261017.md) · [部署](deploy/README.md)

# 跨系统故障诊断与协同恢复

高分方案的本地开发版本已新增 PostgreSQL 订单业务、MCP→AIP 网关、可接续 SDK、证据调度与审批工作台。使用 PowerShell7 在项目根运行：

```powershell
pwsh -NoProfile -File deploy/local-up.ps1
# 首次准备依赖时加 -Install。
```

新工作台：[http://127.0.0.1:8766](http://127.0.0.1:8766)。[开发进度](docs/开发进度_高分方案.md)与[本地验收记录](docs/本地开发验收.md)区分实际本地结果和后续平台验收；下文保留 v0.2.0 基线说明。

订单网站发生故障后，协调智能体收集应用和数据库的信息，安排恢复操作，再由恢复分析智能体访问网站、读取订单并汇总结果。当前诊断逻辑采用规则。

梧桐运行结构：Leader → 官方 ADP → 应用、数据库、恢复分析 Partner。四个正式身份分别运行，通过官方 ACPs SDK 的 AMQPS 群组交换任务和结果；应用通过 HTTP 访问 SQLite 数据服务。

## 梧桐故障业务运行

四个业务智能体全部审核通过并取得客户端证书，官方目录已按技能发现三个参与者。组合故障经八个正式平台任务恢复，订单接口由 503 变为 200，完成两次恢复操作，用时 6.190 秒；正常状态经两个任务返回结果，执行零次恢复操作。所有参与者正常退出。

```powershell
& 'D:\AI + 开源\incident-pilot\.venv\Scripts\python.exe' 'D:\AI + 开源\incident-pilot\integration\wutong_incident.py' --run --config 'D:\AI + 开源\incident-pilot\integration\private\incident\config.json' --scenarios combined,healthy
```

程序自动启动实验服务和三个独立 Partner，生成新的运行目录。[业务过程与运行记录](integration/incident/README.md)包括官方发现响应、平台任务消息、业务产物和登记截图。诊断沿用现有规则，业务服务运行在本机。

## 本地对照实验

在本目录打开 PowerShell：

```powershell
& '.\.venv\Scripts\python.exe' '.\run_pilot.py'
```

实验覆盖网站正常、数据库连接地址错误、数据库暂停、组合故障、未知业务故障和智能体替换。固定地址与动态发现各运行两次，使用相同诊断逻辑。

每次生成 `artifacts/<时间-随机ID>/`，保存 `REPORT.md`、`results.json`、`events.jsonl`、子进程日志和实验数据库。`LATEST.txt` 指向最新目录；退出时停止本次启动的进程。

## 梧桐双智能体交流

任务协调智能体和消息回声智能体分别接收 Inbox 邀请、加入群组、执行消息任务。运行程序先由协调者向回声者发任务，再由回声者向协调者发任务，双方返回原消息和任务状态。

双方已通过梧桐审核并取得正式 AIC 和客户端证书。两轮平台消息任务均已完成，程序正常退出；结果见 [运行记录](integration/two-agent/RESULT.json)。收件箱采用每个身份一个消费者，接收邀请和任务反馈。

[接入流程](integration/PLATFORM-ONBOARDING.md)包含平台地址、登记步骤、证书命令和任务输入输出。

## 扩展测试与资料

```powershell
& '.\.venv\Scripts\python.exe' '.\protocol_stress.py' --iterations 8 --label manual
& '.\.venv\Scripts\python.exe' '.\consistency_stress.py' --seed 20261017 --label manual
& '.\.venv\Scripts\python.exe' '.\resilience_stress.py' --repeats 12 --seed 20261017
```

本地测试覆盖消息与终态、并发恢复、重复执行、配置版本、组合故障和智能体替换。[最终测试报告](artifacts/campaign-20261017-final-v2/REPORT.md)记录最终一轮的 425 项场景与断言。

官方源码位于 `vendor/ACPs-community`，版本 **v2.2.0**，提交 `3985c1330209f075c124669cc9d31f0e75448140`；Python 环境位于 `.venv`。

- [官方代码](https://github.com/AIP-PUB/ACPs-community) · [梧桐文档](https://wt.ioa.pub/docs.html)
- [构建记录](integration/BUILD-VERIFICATION.md) · [平台审核结果](integration/two-agent/rejection-analysis-v1.json)

> 当前目录是私有团队开发快照，不是最终比赛交付包。先看 [开发者接手指南](docs/开发者接手指南_20261018.md) 和 [协作任务清单](docs/协作任务清单_20261018.md)；[历次协作记录](COLLABORATION.md) 保留批次证据。
> 当前高分分支使用真实 PostgreSQL 订单、MCP→AIP 网关和接续 SDK；下面保留 v0.2.0 的历史 README 主体。
> [高分方案](docs/高分方案_需求架构创新与任务_20261017.md) · [P0审计](docs/P0完成审计_20261017.md) · [部署](deploy/README.md)

# 跨系统故障诊断与协同恢复

高分方案的本地开发版本已新增 PostgreSQL 订单业务、MCP→AIP 网关、可接续 SDK、证据调度与审批工作台。使用 PowerShell7 在项目根运行：

```powershell
pwsh -NoProfile -File deploy/local-up.ps1
# 首次准备依赖时加 -Install。
```

新工作台：[http://127.0.0.1:8766](http://127.0.0.1:8766)。[开发进度](docs/开发进度_高分方案.md)与[本地验收记录](docs/本地开发验收.md)区分实际本地结果和后续平台验收；下文保留 v0.2.0 基线说明。

## 本地模型工作台（2026-10-18）

本地 Qwen 采用显式启用，普通重跑保留已选配置。已在既有开发机通过真实工作台健康验收：模型调用 6 次、输出校验通过 6 次、7098 tokens，零修改任务；独立业务观察 30.015 秒、10 个完整流程通过。桌面、手机和两组合成异常展示分别核验，见[启用方法与证据边界](docs/local_model_workbench_20261018.md)。

七个新版角色证书与 ADP 只读身份核对已通过；独立 NEW7 项目现已实际部署，六域经正式 AMQPS 完成 6 项 describe 和 6 项正常任务，独立业务窗口 30.003 秒、30 次成功请求、10 个完整流程，正常关闭本次自有群组。模型调用、act 和故障注入均为 0；本次健康运行不覆盖故障恢复或接管；后续正式E3闭合结果见下方。见[新版平台部署与健康验收](docs/new7_platform_20261018.md)。本次平台健康结果与前述本地模型验收、下方旧平台基线分别记录。

正式NEW7 E3已闭合：[45格结果与限制](docs/new7_e3_20261018.md)记录37格持续恢复确认、8格未确认（均M1），M0/M2各15/15、M1为7/15，实际exit1保留失败。M2耗时和模型成本单列，7个旧未决阶段与独立新H00分开；T62日志解析限制及路由换行复原均如实保留。

后续独立版本已将AMP日志追加修复部署至六域，新健康窗口12任务完成、30.003秒/30成功请求/10流程；该窗口[T05双端访问对账](evidence/new7-runtime-followup-20261018/access-reconciliation.json)为12任务/24条access，缺失、多余和未完成生命周期均0。8877巡检已自然完成[三轮](evidence/new7-inspect-session-20261018/cycle3.json)，各30.002秒/10流程，[实时UI26项检查与六张截图](evidence/new7-runtime-followup-20261018/ui-results.json)通过。七身份固定30分钟[心跳采样](evidence/new7-runtime-followup-20261018/heartbeat-window.json)为840/840；采样完整不等于连续在线、24小时/7天或Monitor入库。新证据不重跑或解除原45格失败、旧未决和坏行；正式[E1源码与计划](docs/new7_e1_implementation_20261018.md)仍未执行，具体故障实验待对应授权。[当前上游审阅包](docs/contributions/upstream-review-20261018/README.md)已整理为两个独立PR与四条Issue草稿；针对已核实的官方94077d1完成补丁适配与相关验证，尚未外发。

完整工具M1的[本地分段结果](docs/free_tools_matrix_20261018.md)：原批40终态、第41格中断，独立后续四格4/4恢复；两阶段为44终态、37确认、7未确认、1中断覆盖原45计划，独立HTTP H00为30.328秒/30次全成功/10流程。原进程退出码未知，不能称完整45格单批；旧M1/旧18例、新版梧桐及长期验收分别保留，下文继续为v0.2.0基线记录。

订单网站发生故障后，协调智能体收集应用和数据库的信息，安排恢复操作，再由恢复分析智能体访问网站、读取订单并汇总结果。当前诊断逻辑采用规则。

梧桐运行结构：Leader → 官方 ADP → 应用、数据库、恢复分析 Partner。四个正式身份分别运行，通过官方 ACPs SDK 的 AMQPS 群组交换任务和结果；应用通过 HTTP 访问 SQLite 数据服务。

## 梧桐故障业务运行

四个业务智能体全部审核通过并取得客户端证书，官方目录已按技能发现三个参与者。组合故障经八个正式平台任务恢复，订单接口由 503 变为 200，完成两次恢复操作，用时 6.190 秒；正常状态经两个任务返回结果，执行零次恢复操作。所有参与者正常退出。

```powershell
& '.\.venv\Scripts\python.exe' '.\integration\wutong_incident.py' --run --config '.\integration\private\incident\config.json' --scenarios combined,healthy
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

双方已通过梧桐审核并取得正式 AIC 和客户端证书。两轮平台消息任务均已完成，程序正常退出；结果见 [历史摘要](docs/historical-baseline-evidence.md#two-agent)。收件箱采用每个身份一个消费者，接收邀请和任务反馈。

[接入流程](integration/PLATFORM-ONBOARDING.md)包含平台地址、登记步骤、证书命令和任务输入输出。

## 扩展测试与资料

```powershell
& '.\.venv\Scripts\python.exe' '.\protocol_stress.py' --iterations 8 --label manual
& '.\.venv\Scripts\python.exe' '.\consistency_stress.py' --seed 20261017 --label manual
& '.\.venv\Scripts\python.exe' '.\resilience_stress.py' --repeats 12 --seed 20261017
```

本地测试覆盖消息与终态、并发恢复、重复执行、配置版本、组合故障和智能体替换。[历史摘要](docs/historical-baseline-evidence.md#campaign-425)记录最终一轮的 425 项场景与断言。

官方源码位于 `vendor/ACPs-community`，版本 **v2.2.0**，提交 `3985c1330209f075c124669cc9d31f0e75448140`；Python 环境位于 `.venv`。

- [官方代码](https://github.com/AIP-PUB/ACPs-community) · [梧桐文档](https://wt.ioa.pub/docs.html)
- [构建记录](integration/BUILD-VERIFICATION.md) · [驳回原因说明](docs/historical-baseline-evidence.md#first-rejection)


---

**[团队资料导航](docs/资料导航.md)** · [协作快速开始](COLLABORATION.md) · [E1 闭合报告](evidence/eval/results/local/E1-native-20261017/analysis/report.md) · [技术报告开发稿PDF](deliverables/development-report-20261017/technical-report-development.pdf)

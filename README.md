> **2026-10-19 当前审查入口：** [完整进度、真实结果与高分缺口](docs/当前进度审查入口_20261019.md)。SDK最终公开提交与147文件vendor来源已[精确绑定](evidence/sdk-final-binding-20261019/README.md)；原605套件源码字节未变。[Windows同机完整启停](evidence/native-lifecycle-20261019/README.md)通过，57个观察进程实际退出；[稳定性汇总与图表](evidence/t63-stability-report-20261019/README.md)已实现，31个不同相关方法有通过记录。
> [最新四例批次](evidence/access-validation-results-20261019/README.md)已获授权，实际尝试3项：1通过、2因平台连接失败，最后1项未执行；两个E1未到预设中断点，三次最终H00通过，自有10容器已停止。[后续清理收据](evidence/access-validation-results-20261019/group-cleanup/README.md)确认队列和交换机不存在，ACL仍未确认。旧22例18通过/4失败、修复12例11通过/1失败及历史访问缺口保持原判。[15页报告修订3](deliverables/development-report-20261019-revision3/technical-report-development.pdf)仍截止613ecbf；新机器、Kafka/Monitor与长期验收未闭合。下文为历次截面。
> [上游贡献状态](evidence/upstream-status-20261019/recheck-1651/README.md)于北京时间16:51核验：PR13/14仍为开放草稿，无审阅、评论或自动检查记录；Issue15–18仍开放、无评论。

> **完整源码包已更新：** [2018文件的固定版本与复现方法](docs/development_archive.md)，源码冻结 `3760b21`；逐文件与Git对象核验通过，含当前SDK检查入口和接手说明。新机器、平台入库与长期运行仍待独立验收。

> **2026-10-19 后续补证：** [E2-c逐条策略审计](docs/gateway_policy_evaluation_20261019.md)已完成14拒绝＋1合法正控及落盘验签；[18条访问缺端诊断](docs/access_accounting_20261019.md)保留原T05=false及4条原因未定。[8页技术报告开发稿](deliverables/development-report-20261019/technical-report-development.pdf)已更新并逐页检查，证据截止634c46d；本轮新E2-c结果另见链接。平台复验、新机、Kafka/Monitor和长期验收继续单列。

> **2026-10-19 最新正式验收：** [22项逐例结果与剩余P0](docs/platform_acceptance_results_20261019.md)。本批准备22项，实际尝试22项：通过18、失败4；未尝试0。失败照原结果保留，发布不要求全部通过。 接手见[开发者指南](docs/开发者接手指南_20261018.md)。
> **尚未闭合：** T05仍未通过：18例各少1条access，共18条缺端，原因待追踪；full_history独立修复仅离线39方法通过，仍待正式平台复验。
> 下文10-18记录、准备阶段和旧“尚未运行”表述均为历史截面；本批以最新结果、独立恢复与停机收据为准。

> **队友接手入口：** [开发者接手指南](docs/开发者接手指南_20261018.md) → [环境安装、启动、验证与停止](docs/本地开发环境与操作_20261018.md) → 按需配置[自己的模型与平台身份](docs/自有账号平台配置_20261018.md)。用自己的 GitHub 账号即可开发，本地开发不需要原开发者的平台账号。
> 原开发机项目服务已于 2026-10-18 20:47（北京时间）全部停止，数据保留。下方运行状态、PID、巡检和实验均为历史记录；在自己机器上重新生成环境。新文档已吸收队友的[部署反馈](deploy-check-record.md)，其中未解决的测试失败仍保留。
> 当前目录是私有团队开发快照，不是最终比赛交付包。[协作任务清单](docs/协作任务清单_20261018.md)列后续工作；[历次协作记录](COLLABORATION.md)保留批次证据。
> 当前高分分支使用真实 PostgreSQL 订单、MCP→AIP 网关和接续 SDK；下面保留 v0.2.0 的历史 README 主体。
> [高分方案](docs/高分方案_需求架构创新与任务_20261017.md) · [P0审计](docs/P0完成审计_20261017.md) · [部署](deploy/README.md)

# 跨系统故障诊断与协同恢复

2026-10-19 继续开发：[正式 E1 三中断点及交接信息、F12/E5 原键恢复](docs/p0_continuation_20261019.md)，测试安装见[开发环境补充](docs/test_environment_20261019.md)。本轮源码与离线证据按新批次保存；旧运行计划和实验结果保留。

同日新增[正式 E1-c 旧主同进程恢复](docs/platform_e1c_20261019.md)：共享账本接管后恢复原 PID、拒绝旧请求，计划与授权单独绑定；正式故障实验尚待运行。

[正式验收准备](docs/acceptance_preparation_20261019.md)已生成独立镜像、七身份配置及 22 个新计划，并修复 F12 镜像绑定与旧依赖下载阻断；计划尚未执行。

本轮完成[原请求回执正确性修复](docs/original_receipt_correctness_20261018.md)：HTTP200与v2标记不足以解除未知请求，共享校验要求原键、committed和一致的合法订单UUID及快照。两个旧缺陷经模拟HTTP复现，21个不同方法通过；[证据](evidence/original-receipt-correctness-20261018/summary.json)保留失败与适用范围。新修订未部署到现有运行进程，未新增真实F12/E5或改判旧未决。原204冻结不变；旧E1公开集合157、保留原源树动态158、本修订动态159，正式E1须新revision绑定，不能直接复用旧plan。按用户要求，本轮上传后暂停。

新增[独立部署入口](deploy/ISOLATED.md)：manifest绑定项目、端口、环境及路由，准备默认只写新目录，四业务与七身份模式分开。[业务验收工具](evidence/deployment-verifier-20261018/summary.json)支持URL或manifest并检查公共v2和30秒/10完整流程；原8088验收与[新580xx部署实跑](evidence/isolated-deployment-runtime-20261018/summary.json)分别留证，后者30.016秒/30成功/10流程，原30容器元数据保持，自有4容器正常停止并保留。两次监督检查误判退出1保留，最终H00/stop为0，没有第三次up。六份接手文档同步当前NEW7状态；[场景缺口审阅](docs/scenario_gaps_20261018.md)列出待实施的回执判据和F12显式目标缺口。本轮是同机缓存验收，正式E1、新机器T96、Kafka/Monitor及24小时仍待。

本轮新增[七源真实卷stdout采集](evidence/t06-real-volume-stdout-20261018/README.md)：只读挂载七角色日志，75.005秒取得32,069条唯一记录、42类组合及42个offset数据库，采集器正常退出，原29容器保持。Kafka显式集合模式与Linux配置入口已实现；[官方配置说明](docs/kafka_monitor_20261018.md)区分规划端点与可用连接资料，官方Kafka/Monitor尚未验收。[8766受控更新](evidence/workbench-8766-update-20261018/summary.json)保留历史事故，修复乱序加载导致默认事故过旧的问题；[第九次巡检观察](evidence/new7-runtime-followup-20261018/inspect-ninth-cycle.json)核最新周期30秒/10完整流程。正式E1和24小时验收仍待。

本轮新增[T50工作台验收](evidence/t50-workbench-development-20261018/summary.json)：计划依赖、假设预测、审批状态与历史已接入；访问对账随所选事故切换，完整、缺端、坏行和未采集分别显示。浏览器使用合成记录与真实更新后的GET接口，闭合健康记录分两事故各6任务/12访问复核。[T06本地七源采集](evidence/t06-seven-source-local-20261018/README.md)在隔离fixture通过252条逐字段对账、42个offset数据库、三轮host/collector正常退出；只覆盖固定追加、新稳定文件发现与重启续读，原console竞态失败及84条归档重放保留。实际七域卷、rename/copytruncate、Kafka/Monitor、正式E1与24小时仍待验收。

2026-10-18同机隔离[Compose H00实测](evidence/isolated-compose-h00-20261018/README.md)已闭合：固定5b7745新检出使用原Windows→WSL入口，四个业务容器、新数据库卷和独立v2路由实际启动，公共ready前后v2，30.016秒/30成功请求/10流程，失败、未知和未决0。仅正常停止本轮四容器，原25容器及原三端口PID保持，卷与网络保留；这是已有镜像/缓存的同机验收，不是新机器冷部署。[部署说明](deploy/README.md)补Linux宿主机依赖；原入口未改，新增[3项fake-WSL检查](evidence/isolated-compose-h00-20261018/offline-entry-checks.json)通过。10:10Z[第七次自然巡检快照](evidence/new7-runtime-followup-20261018/inspect-seventh-cycle.json)仅核最新周期，30.003秒/10流程、act/模型0，不代表七轮逐件审阅或24小时；正式E1仍未执行。

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

本机新检出目录已完成[开发接手验证](docs/本地接手验证_20261018.md)：固定659b4b5的依赖安装、pip check和23项指定离线检查通过，44包/11模块来自新venv；随后别名隔离4项及启动器15项检查单独通过。两个阶段不混称同一版本的全链路运行，未启动真实数据库/业务、未完成完整local-up或新机器冷部署，正式E1与Kafka/Monitor仍待验收。共享[配置参考和安装/离线日志](docs/team-runtime-reference-20261018/README.md)保留可复现参数，凭据由各自填写。

后续独立版本已将AMP日志追加修复部署至六域，新健康窗口12任务完成、30.003秒/30成功请求/10流程；该窗口[T05双端访问对账](evidence/new7-runtime-followup-20261018/access-reconciliation.json)为12任务/24条access，缺失、多余和未完成生命周期均0。8877巡检已自然完成[三轮](evidence/new7-inspect-session-20261018/cycle3.json)，各30.002秒/10流程，[实时UI26项检查与六张截图](evidence/new7-runtime-followup-20261018/ui-results.json)通过。七身份固定30分钟[心跳采样](evidence/new7-runtime-followup-20261018/heartbeat-window.json)为840/840；采样完整不等于连续在线、24小时/7天或Monitor入库。新证据不重跑或解除原45格失败、旧未决和坏行；正式[E1源码与计划](docs/new7_e1_implementation_20261018.md)仍未执行，具体故障实验待对应授权。[当前上游审阅包](docs/contributions/upstream-review-20261018/README.md)已通过公开GitHub fork提交[接续PR #13](https://github.com/AIP-PUB/ACPs-community/pull/13)与[日志PR #14](https://github.com/AIP-PUB/ACPs-community/pull/14)，两者均为draft、尚未合并，四条Issue #15–18已发布且六项GET核验一致；见[真实提交记录](evidence/upstream-public-submission-20261018/submission.json)。AtomGit和正式E1/24小时验收仍未完成，未执行上游CI。

2026-10-18 UTC09:16补证：现有两draft PR已追加测试可移植性修正，当前14/3文件；完整本地SDK suite分别581/581与558/558通过，共享用例不相加、未执行上游CI，首次失败与警告保留。见[完整测试与复现说明](docs/contributions/full-suite-20261018/README.md)及[PR后续状态](evidence/upstream-public-submission-20261018/followup.json)。[T06本机采集准备](deploy/fluent-bit/README.md)已通过13个不同Python离线检查和PowerShell解析；未启动真实转发器，Kafka/Monitor尚未验收。[第五次自然巡检](evidence/new7-runtime-followup-20261018/inspect-fifth-cycle.json)在09:24Z快照中已完成，最新业务30.002秒/10流程、act/模型0；这是一时点观察，不代表持续在线或24小时。正式NEW7 E1和24小时仍未完成。


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

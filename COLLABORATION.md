# 团队协作快速开始

这是私有团队的开发快照，保留当前源码、改造后的完整 ACPs SDK、必要官方 CLI、方案、测试和脱敏完成结果。它不是最终比赛交付包。

## Windows 本地启动

需要 Python 3.12、PowerShell 7.4+；首次启动需网络下载 Python 依赖及官方 PostgreSQL/Nginx portable binaries。
在本目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install "./vendor/ACPs-community/acps-sdk[amp-sign]"
pwsh -NoProfile -File deploy/local-up.ps1 -Install
```

本地工作台为 http://127.0.0.1:8766，订单入口为 http://127.0.0.1:8088。启动器会在本机生成随机私密配置和数据库。
先确认 8081/8082/8088/55432/8766 端口空闲；当前开发者原项目仍运行时，不要同时启动本副本。
该默认路径是 local AIP stdio，不能称为正式 AMQPS/mTLS 平台运行。Docker/WSL 路径见 [部署说明](deploy/README.md)，业务可独立启动；正式代理需每域自有配置。

## 私有配置与协作

- `runtime/private/`、`integration/private/`、实际 `.env`、EAB/访问令牌、证书私钥、数据库、账本和任期库均不在副本中。各人在本机生成，不互相提交。
- 正式平台需注册身份、自有证书及公开端点配置；禁止同 AIC 启动多个 Inbox 消费者。当前既有三身份的证书不会通过仓库分发。
- 如需官方 CLI，可运行 `.\.venv\Scripts\python.exe -m pip install ./vendor/ACPs-community/acps-cli`；先执行 `Copy-Item integration/acps-cli.example.toml integration/acps-cli.toml` 生成证书 helper 所需的本地配置，再按自己的身份填写。模板仅含公开端点和私有路径，不含凭据。
- 同一资源的多个协调者必须共享持久权威任期源；数据库主备必须共享资源域操作账本。新的隔离资源可使用独立命名空间，不能因新输出目录重置既有资源的 term。
- 克隆团队仓库后，先从独立分支修改，自测后提交审阅并合并。不要提交运行环境、模型或未冻结评测目录。

## 当前证据与未完成项

订单真实 PG 事务、六类原生故障恢复、浏览器 F10、两个真实上游 MCP、独立 Docker H00/F12、旧主同 PID 复活拦截已有证据。
三旧身份 application/verification/database 的容器版已通过真实 ADP、describe、完整 AIP 生命周期和 Postgres MCP 只读调用；属于旧身份新契约兼容，不能称新版 ACS 已发布。
修复前乱序失败与修复后成功均保留在 `evidence/`，脱敏副本附原件哈希；未复制原始数据库和完整私密日志。

新备/运维身份及新版 ACS 审核、平台高风险恢复/接管、三种交接对比、长期平台数据、新机器冷启动、最终报告/视频和公开 Issue/PR 仍按 [P0 审计](docs/P0完成审计_20261017.md) 推进。

[高分方案](docs/高分方案_需求架构创新与任务_20261017.md) · [本地验收](docs/本地开发验收.md) · [开发进度](docs/开发进度_高分方案.md) · [上游贡献草稿](docs/contributions/README.md)

`baselines/` 是过滤后的复现源码视图，原 ZIP 含运行数据库而未分发；查看 `TEAM-SOURCE-MANIFEST.json`。
官方来源与许可见 [THIRD_PARTY.md](THIRD_PARTY.md)。`SNAPSHOT-MANIFEST.json` 列本副本每个文件的哈希及相对原清单的增补/修改。

## 首快照后的闭合补证

原 v2 为 45 格、36 次恢复确认、F06 九次失败，完整保留在 [historical-v2](evidence/model-evaluation/historical-v2/summary.json)，其图仅展示 v2。修复后的 F06 v3 九项均恢复确认，另存 [F06-v3](evidence/model-evaluation/F06-v3/summary.json)。[逐场景 comparison](evidence/model-evaluation/comparison-by-scenario/report.md) 使用 F01/F02/F07/F10 的 v2 与 F06 的 v3，属于不同源码批次的选择合并，不能称同源码单次 45。以上均为本地 stdio/原生资源证据。

[团队副本冷部署](evidence/team-snapshot-cold-20261017/results.json)通过：同机新项目、新卷、镜像缓存复用，30.002 秒/30 请求/10 完整流程；不是新机器 15 分钟验收。原始消息、账本、私密配置和源码冻结档案留本地，仓库只含脱敏闭合汇总及原件哈希索引。

首快照提交为 800607c50a29b3527ff0713bd476a2efacfafd12；清单保留其 manifest 哈希与本次逐文件旧/新哈希。.gitattributes 使用 * -text 保留克隆字节，便于按清单复核。

本地模型实际响应另附 [v2 的 209 条](evidence/model-evaluation/historical-v2/model-response-evidence.jsonl) 与 [F06 v3 的 39 条](evidence/model-evaluation/F06-v3/model-response-evidence.jsonl)，保留 content/usage/采样参数/HTTP 状态，不含上下文、认证或环境信息。它们是闭合调用的精简派生证据，不替代原始运行记录。

## F12 产品输入与 E1c 独立补证

[F12 单元检查](evidence/product/F12-original-intent-20261017/unit-results.json)和[真实 UI 验收](evidence/product/F12-original-intent-20261017/live-ui-results.json)分别归档。两轮在隔离容器 28082/28088 上各完成 30 秒、30 请求、10 个新订单流程；缺失原请求键或原键回执 404 时仍显示 needs_attention、原业务未知并需人工处理，没有创建替代原订单。工作台使用 local AIP stdio，未测试正式平台 AMQPS。截图只含本地测试身份及测试键。

[E1c 三次证据汇总](evidence/eval/results/local/E1c-summary-20261017/summary.json)包含历史 retry 一次与之后两次复核，不是新冻结的同批三次实验。三次均复活同一旧主 PID，旧 fence 被共享资源域 SQLite OperationLedger 拦截，旧主实际 MCP 修改为 0、备侧修改一次，随后通过 30 秒/10 流程观察；这不是 PostgreSQL 原生 fence，也未验证平台 ADP 接管。历史原结果保持原位置，不重复复制。

本批基于模型提交 56b6a4595a745ef7faccaea2e4f6b927458ddced，仅同步已验收 F12 白名单、F06 测试对齐及闭合 E1c 补证。后续自由工具基线、正式公平交接和 Bridge 可选 handover 仍另批验收。

## 资料、SDK 审阅与本轮闭合证据

**[团队资料导航](docs/资料导航.md)**：官方赛题原件、项目方案、研究资料和证据入口。

本批增加 [SDK 独立审阅补丁](docs/contributions/sdk-review-20261017/README.md)，限12个SDK文件，已在冻结v0.2临时副本验证应用及哈希；尚未向上游公开提交。引用已有3项排序和25项接续测试，本次导出未重跑。

[E1准备包](evidence/preparation/E1-20261017/preparation.json)保留当时审批阻止状态；用户随后明确授权。[E1闭合报告](evidence/eval/results/local/E1-native-20261017/analysis/report.md)包含18例最终业务验证：17连续、1控制器中断后仅续验，实际注入18、DB MCP修复18、重复0、旧fence18/18拒绝、实际模型0。ResumePackage信息比完整对话少37.7%，兼容重复字段却令完整IFC大13.7%；不能声称wire或模型token优势。本批只收筛选后的闭合数据/图/来源hash，不含私有源码冻结、原始日志或数据库，未验证正式ADP自动接管。

M1新增自由选择observe/act/verify的可选控制器路径，仍共用安全审批/工具/预算，无规则fallback。[模型schema烟测](evidence/model-evaluation/free-tool-model-schema-20261017/results.json)为一次合成健康上下文请求（1031tokens、0资源调用）；[engine行为证据](evidence/model-evaluation/free-tool-engine-20261017/results.json)为离线/fixture结果，不是新的真实模型资源矩阵。历史M1-observe数据及负面延迟结论保持原界限。后续正在运行的M1资源实验不在本批。

共享路由前置守卫是E1闭合后的修复，[33项Gateway离线/stdio测试证据](evidence/product/route-precondition-20261017/results.json)单独记录；E1来源hash仍指向实验时旧Bridge，不能把E1结果当作新守卫验收。

[13页技术报告开发稿](deliverables/development-report-20261017/technical-report-development.pdf)为匿名、非最终提交版，证据截至2026-10-17 11:41:43 UTC；不含之后的完整工具M1 pilot。相邻目录保留编排源与最终检查记录。

[公开来源标识分类](evidence/audit/public-source-token-classification-20261017.json)仅按既有13份官方HTML的完整文件hash及标识指纹保留公开前端配置/HTML属性；项目16项已知私密值仍全部阻止，未来未知值不在例外内。

## 完整工具M1开发验收与T07巡检增量

[两批M1对照](evidence/model-evaluation/M1-free-tools-analysis-20261017/comparison.md)分别保留首批2/3与共享路由守卫修复后3/3，每批只有F01三方法各一次，不是新版45项矩阵。首批M1为真实MCP调用1次/error1次但ok修改0次，并有必要窗口中2条Nginx reload信号和7条health499；不把信号当重载完成证明，health收敛失败归因为日志与源码支持的推断，未补造MCP错误正文。v2 M1最终恢复但仍多1次不必要high和1次ok修改。模型证据只公开真实响应、usage和参数，历史M1-observe保持原统计边界。

[T07筛选后公开证据](evidence/T07-partial3-20261017/README.md)记录三旧域正式AMQPS健康once与30分钟inspect循环启动。once同一事故30.003秒、30请求、10完整流程全成功，unknown/pending/审批均0；原失败、包装器exit120和同事故续接保留。可信AIC筛选及候选describe截止时间有针对测试。循环keep-awake请求成功、drills/high自动审批关闭，当前不代表24小时或7天在线。详见[最新进度](docs/开发进度_高分方案.md)和[审计](docs/P0完成审计_20261017.md)。13页PDF仍保持11:41:43Z旧证据截止，不因本批重生成。

## 新七身份准备、E3入口与第二次正式巡检

[新七角色隔离部署](deploy/NEW7.md)使用独立incident-pilot-new7项目、380xx端口、路由与卷；[公开审核状态](evidence/platform/new7-registry-20261017/approved-public-aics.json)为七身份通过/五个详情AIC核实，证书办理按用户要求暂缓，尚未启动新版身份。

[E3正式平台入口](docs/e3_evaluation.md)复用原方法、预算和订单流，仅接受local/native或Wutong/明确Docker目标。组前核验六域、目标端口/挂载/卷、公开身份与固定源码摘要；组后selected与ops三scope再次绑定。源码digest仅在container/image/StartedAt稳定时复用，公开配置每次重读。旧配置、旧镜像、域重启或错资源会拒绝。代码验证为15项本轮离线测试及复用此前13项原生评测兼容结果，[证据](evidence/eval/e3-platform-runner-20261017/results.json)明确实际执行与复用范围。真实E3矩阵未运行，fixture不替代平台结果。

[域隔离与事实映射](evidence/product/docker-scope-offline-20261017/results.json)、[身份/平台入口契约](evidence/platform/wutong-new-profile-contract-20261017/final-results.json)和[部署准备](evidence/deployment/new7-container-plan-20261017/unit-results.json)分别保留各suite与版本，未相加宣称唯一测试总数。

[T07第二周期](evidence/T07-partial3-cycle2-20261017/README.md)是旧三身份/旧180xx目标的真实自然调度：业务30.002秒、30请求、10完整流程成功，4任务/24生命周期关联投影，无unknown/pending/act/审批；首段快照保留。它不证明新版身份已上线或24小时/七天稳定。13页PDF仍保持11:41:43Z证据截止。

[新镜像隔离验证](evidence/new7-image-build-20261017/image-proof.json)实际build/probe均exit0；仅构建incident-pilot-agent:new7，并在network-none、只读根目录、无资源/证书挂载的临时容器中验证导入、官方ACS schema及12个固定源码SHA和实际模块路径。旧服务未重建，新身份/消费者未启动。integration仅10个顶层Python源；构建参数不兼容exit125及首probe漏stdin未执行的早期失败保留，不计为验证成功。该镜像证明不替代正式平台启动或E3矩阵。

## 答辩与演示开发稿

[答辩内容开发稿](deliverables/defense-content-development-20261017/README.md)提供内容、讲者备注、数据和JS生成源。官方技能运行时缺失，PPTX/PDF生成未执行；内容稿不能作为已交付演示文件。[4分30秒演示开发稿](deliverables/demo-script-development-20261017/README.md)提供旁白、分镜、逐秒索引与录制清单，尚未录制视频或音频。两份材料保留平台高风险恢复、接管、新七身份与后台统计的待验收项，没有新增实验。

稿内原件locator和SHA指向原开发项目根目录，不保证团队仓库同路径存在；已上传公开派生请从[资料导航](docs/资料导航.md)进入。历史M1负例、修后额外high、E1本地stdio/零模型用量、17连续加1续验，以及旧身份巡检与新身份准备的区别均保留。13页技术PDF与先前实验快照维持原版本。

## 健康对照、统计修复与匿名佐证开发稿

[H00 健康对照说明与失败/修复实测](evidence/eval/H00-public-health-20261017/README.md)保留第一次31次请求后遗留一个未闭环流程的真实失败，以及安全停止修复后30次成功请求、10个完整流程、30.235秒健康窗口的通过结果。这是公共HTTP业务观察；完整评测还要求所有资源act尝试为零。健康对照单列，不进入故障恢复率分母。[相关离线证据](evidence/eval/H00-control-offline-20261017/results.json)明确16项受影响检查重新运行、20项未受影响检查复用，没有重跑历史矩阵。

[AMP心跳统计修复](docs/stability_report.md)仅对[18个既有AMP文件的闭合快照重算](evidence/eval/stability-report-v2-20261017/closed-snapshot-comparison.json)，不增加持续运行时长。[材料扫描](docs/material_anonymity.md)对[8个指定开发材料完成有界检查](evidence/audit/material-anonymity-review-20261017/results.json)，并不等同于最终匿名性验收。

[12页匿名佐证开发稿](deliverables/supporting-evidence-development-20261017/supporting-evidence-development.pdf)及[来源与使用说明](deliverables/supporting-evidence-development-20261017/README.md)按其原取证截止保存，不将后来H00测试写入旧证据。PPTX当前暂不需要；演示脚本仍不是已录制视频。F19仍显式Unsupported，T12全部场景和新full-M1正式公平矩阵尚未完成。证据中的原项目相对路径与SHA表示开发项目观察快照，团队公开文件以本快照清单及[资料导航](docs/资料导航.md)定位。

## 固定开发源码归档

[开发复现说明](docs/development_archive.md)绑定源码提交`69647cf29de96b50091c0a3e51ae2308115ad2fb`的1069个文件。[归档验证](evidence/deployment/development-archive-69647cf/verification.json)记录真实ZIP逐文件核对及解压目录Compose配置解析；这是开发复现归档，不是新机器T96验收。

## F19 参与者故障补证

[参与者失联诊断与专用F19入口](docs/participant_failure.md)补齐此前未支持的F19本地验收：本次新建运维worker自退出，按真实任务通道、管理Get和45秒心跳联合判定；订单健康与参与者人工处理分开记录。通用注入器在缺少进程所有权上下文时仍拒绝F19。

[真实实验精简证明](evidence/participant-failure/F19-owned-20261017/verification.json)、[复原后H00](evidence/participant-failure/F19-owned-20261017/post-restore-h00.json)及[工作台只读回放](evidence/participant-failure/F19-owned-ui-20261017/results.json)保留各自范围；这是本地stdio证据，不代表正式平台AMQPS失联或自动接管。既有PDF、研究材料和失败历史不变。开发ZIP仍固定69647cf、1069文件，不含本批新增内容。

## 2026-10-18 评测异常收尾与新矩阵

[评测口径](docs/evaluation.md)补充正常异常路径的复原保障：前置restore和观测器部分启动失败也进入清理，finish异常不跳过最终restore，错误上下文保留。[精简离线证明](evidence/evaluation-cleanup-20261018/results.json)记录16项相关测试及8种故障组合；它们使用mock，不代表已执行真实资源复原。

新45格已获用户明确授权，2026-10-18 01:05:53 UTC实际启动矩阵子进程，153份公开源码已冻结；当前尚未闭合，不报告45项通过。历史观察选择M1的v2/v3组合和F01 pilot各自保留，本批为完整free-tools-v1的本地stdio/native实验，不是正式平台E3。私有配置、启动器、授权回执及完整快照保留本机。开发ZIP仍固定69647cf、1069文件，不含随后增量；答辩PPTX与证书继续暂缓。

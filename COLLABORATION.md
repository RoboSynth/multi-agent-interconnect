# 团队协作快速开始

当前开发入口：[开发者接手指南](docs/开发者接手指南_20261018.md) · [本地环境及操作](docs/本地开发环境与操作_20261018.md) · [自有账号平台配置](docs/自有账号平台配置_20261018.md) · [协作任务清单](docs/协作任务清单_20261018.md)。

2026-10-18 交接更新：`xiaomuxia` 已有仓库管理员权限，使用自己的 GitHub 登录克隆并建立分支。原开发机项目服务、模型和全部运行容器已停止，数据保留；本地开发及四业务部署使用各自新环境，不依赖原开发者账号。新增七身份[配置模板](integration/seven-identities.example.json)，正式联调由接手者在自己的平台账号登记并签发证书。已同步并保留队友 PR #1 的 [Windows 部署验收记录](deploy-check-record.md)，补充其暴露的依赖、端口与排错信息；原失败不改判。本轮只更新文档和示例，不重启项目。

以下是按批次保留的历史记录。旧“仍运行”“待证书”“尚未提交”等描述对应当时状态；当前启动方法、完成情况与剩余工作以以上接手入口为准。

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

## Windows登录巡检准备

[T02/T07登录巡检说明](docs/windows_startup.md)补齐本地配置准备：默认只生成XML/摘要，显式Register/Unregister支持WhatIf；当前用户、隐藏窗口、固定项目Python/配置，任务IgnoreNew与状态目录进程锁共同防重复。演练和high自动审批关闭；残留待办演练留给人工，不由inspect续派或复原。

[精简离线证明](evidence/windows-startup-20261018/results.json)记录8个不同检查的当前适用通过记录，含真实进程锁竞争及释放后取得；7/6/2分轮运行按影响复用，不相加。两个PowerShell脚本WindowsPowerShell5.1解析通过，最终配置实际生成；任务服务和进程启动在配置测试中被拒绝桩隔离。本轮未注册/注销真实任务、启动巡检或底层服务，也未验收登录/重启及24小时/7天在线。SID/XML和私有启动计划留在开发机。

本批不改动正在运行的新45格的153份冻结源码，不追加矩阵完成结论；F19、旧18例与历史失败分别保留。开发ZIP继续绑定69647cf/1069文件，答辩PPTX与证书按用户安排暂缓。

## 原40中断、独立四格与修订验收

[原40格证据](evidence/model-evaluation/local-free-tools-matrix-20261018/)保留40个唯一终态、33次持续恢复、7次未确认，以及第41格运行中和其余4格未启动的原覆盖表；原进程退出码未知、原最终H00缺失，原因未验证。[独立四格](evidence/evaluation-continuation-four-20261018/)另记原授权内4个未启动键，4/4恢复、真实进程exit0及30.328秒/10流程健康检查。两段合计44终态、37确认、7未确认、1中断覆盖45计划，不称原单批完整45，也不重跑或自动解除第41格未知意图。

[分段结果与口径](docs/free_tools_matrix_20261018.md)说明模型选错与版本验证缺口、HTTP400上下文失败、usage缺失和背景请求unknown/pending。[修订与验收证明](evidence/development-candidates-20261018/)对应已应用11个代码/测试/部署文件、6项fresh导入/CLI、native start真实exit0以及修订产品验证器30.031秒/30次全成功/10流程；15/21/14项离线检查按组复用，不相加为唯一总数。旧结果仍绑定原153份冻结源码，后续修订不回写实验来源。

原失败、旧PDF/研究资料与历史证据保留。开发ZIP继续绑定69647cf/1069文件，不含本增量；证书与答辩PPTX按当前安排暂缓，未补报正式平台或长时在线验收。

## 本地模型工作台与七角色证书（2026-10-18）

[本地模型工作台](docs/local_model_workbench_20261018.md)已在既有开发机完成一次真实健康验收：持久配置与进程身份核对，5个参与者连接，本地Qwen 6次调用及6次输出校验通过、7098 tokens、零修改任务；独立订单观察30.015秒、30次成功请求、10个完整流程，failed/unknown/pending均为0。[真实与合成展示证据](evidence/local-model-workbench-20261018/)分别保留14项真实浏览器检查与10项合成展示检查，含桌面和手机图片；合成回退与缺失统计不作为真实故障结果。

本轮13份代码/测试/界面文件补齐显式本地模型配置、陈旧实例拒绝、venv直接子进程身份核验、连接后才报告启动成功、已有数据库缺身份时写前失败、保留运行路径及验证后提升下载缓存。[离线准备检查](evidence/local-startup-preparation-20261018/)按模型配置12、启动器12、数据库/下载9分别记录，重叠分轮检查复用，不相加为唯一总数；未作新机器冷部署或完整local-up重跑。

[七角色签证摘要](evidence/platform-certificates-20261018/summary.json)与七份单件证据记录官方CLI签发真实exit0、身份和有效期、clientAuth及私钥匹配检查。另一次[七个精确AIC的官方ADP只读元数据与端点查询](evidence/platform-certificates-20261018/adp-identity-observation.json)真实exit0；查询成功不等于端点可达或任务通道通过。[新版接入准备](docs/新版平台接入准备.md)仍把新版AMQPS群组任务和恢复验收留为后续项。EAB、账户及身份私钥、原始CLI日志与本地配置均不进入团队快照。

[历史基线材料摘要](docs/historical-baseline-evidence.md)修复旧导航，保留旧双智能体、425项本地场景/断言与驳回过程的来源边界。原40终态、第41格中断及独立四格证据保持各自来源；开发ZIP仍绑定旧69647cf/1069文件，未自动重打包。登录任务、24小时/7天和正式新版平台结果不作补报，答辩PPTX继续暂缓。


### 2026-10-18 NEW7 正常健康互联与模型容量

独立NEW7项目已实际构建并启动。六域完成12项正常任务（6 describe、5 observe、1 verify），30.003秒内30请求、10个完整订单流程全部成功，failed/unknown/pending/unresolved为0。本次健康运行model/act/fault均为0；自己的群组正常关闭，六项本地关闭检查通过。

24条账本快照含12条旧awaiting-completion和12条后续completed；12个有效最新任务均completed。运行期配置及捕获流量的63值凭据扫描独立通过。应用镜像构建的首次WSL调用失败和离线辅助进程终止均保留。容器StartedAt晚于初次up的原因未确定；两个后续快照相同，不据此声称7×24稳定。

生产新增显式模型上下文参数，默认8192保持；独立容量验证见[上下文证据](evidence/new7-platform-runtime-20261018/model-context-capacity.json)。它与健康运行的model=0分别计量。本批证明正常健康互联，不证明新故障恢复、备用接管或完整冷部署。

证据：[健康与关闭](evidence/new7-platform-runtime-20261018/healthy-amqps.json)、[任务对账](evidence/new7-platform-runtime-20261018/task-reconciliation.json)、[运行期凭据扫描](evidence/new7-platform-runtime-20261018/credential-scan.json)。

开发协作入口：[接手指南](docs/开发者接手指南_20261018.md)、[协作任务清单](docs/协作任务清单_20261018.md)。实验准备包用于审阅和分工，实际故障实验需另行授权。


### 2026-10-18 后续协作实施资料

[正式E1源码缺口与最小适配](docs/new7_e1_adaptation_20261018.md)、[NEW7持续巡检启动边界](docs/new7_inspect_preparation_20261018.md)和[E3后续三项优先工作](docs/post_e3_priorities_20261018.md)提供具体源码入口、依赖、实施顺序和必要验收，供开发者接手。这三份是待实施或待验收方案，不是新的运行结果。

本批NEW7正式45格E3实验已获授权并在进行中，结果将在真实结束后独立整理；本资料增量不发布实时结果或预写成功。E1参与者退出、暂停/复活、接管与持续巡检须按各自运行范围和窗口推进，不能沿用E3故障范围。现有[协作任务清单](docs/协作任务清单_20261018.md)保留原正文并新增上述具体接手入口。


### 2026-10-18 NEW7正式E3闭合结果

上段进行中的正式45格现已真实结束：37格持续恢复确认、8格needs_attention全部属于M1，M0/M2各15/15、M1为7/15；矩阵与外层监督实际exit1，失败完整保留。M2在五场景的总协调耗时中位数均高于M0，且有模型成本，不宣称全面性能领先。已发送模型调用277次、648020 tokens且usage完整，8次POST前预算拒绝另列。

原7个未完成意图阶段为5create/2cancel，1个cancel尚未发送；独立7次原键回执GET均404，不能消解旧流程。独立新H00为30.016秒、30成功请求/10流程且失败未知未决待决0。运行期T62原文/可解析字段命中0，但AMP有11/4509行解析失败，overall=false。首次路由字节检查失败仅CRLF/LF差异，随后1次文件写恢复精确初始LF；stderr有1行broker cancel，四类cleanup事件0不表示全部warning0。

[当前摘要](docs/new7_e3_20261018.md)、[完整公开说明](evidence/new7-e3-45-20261018-first/README.md)、[独立审阅](evidence/new7-e3-45-20261018-first/independent-review.json)、[旧未决观察](evidence/new7-e3-45-20261018-first/pending-intents.json)、[运行期扫描限制](evidence/new7-e3-45-20261018-first/credential-scan.json)和[收尾澄清](evidence/new7-e3-45-20261018-first/postcheck.json)分别保留来源。本批绑定旧冻结源码；结束后的SDK修复另计，不冒称本45格重验。正式E1接管、持续巡检和最终ZIP仍待各自验收。


### 2026-10-18 E3后SDK日志并发追加窄修

独立源码修订固定MessageEmitter构造时的实际sink，并按规范化路径共享进程内RLock，持锁直至追加句柄关闭。原SDK合成复现三轮400条分别坏4/8/11、丢9/13/18；单实例锁400条完整而双实例各自锁200条仍丢1，因此覆盖同进程多实例同路径写入。5项新增检查与3项既有检查共8项离线通过、actual exit0，真实网络/模型/资源调用0。

[版本边界](docs/new7_e3_20261018.md#e3结束后的sdk日志追加修复独立版本)、[SDK修复说明](evidence/amp-jsonl-concurrency-20261018/README.md)、[负面复现](evidence/amp-jsonl-concurrency-20261018/negative-reproduction.json)与[离线证据](evidence/amp-jsonl-concurrency-20261018/offline-checks.json)独立发布。当前域镜像和运行实例仍为实验冻结版本，修复未部署、45格未重跑；原16件E3证据逐字保留，原7未决/11坏行/T62 false不因此解除。跨进程写入安全不在本修复承诺内。


### 2026-10-18 E1源码接续与AMP修复后独立健康窗口

正式E1新增源码/离线准备：[工作者与接续状态](docs/new7_e1_implementation_20261018.md)。复用原Bridge/Policy/Ledger/AmpRuntime；只有明确实验主身份可在指定点退出，backup永不armed，overlay保留原业务逻辑和共享账本。修改计数区分wrapper预调用事件、匹配返回与未知返回，不能推算物理副作用。正式E1未执行，纯文件计划/armed bundle的准备不提供新故障授权；实际E1前须在空闲边界停止当前同AIC巡检并核对关闭。

AMP修复后六域已独立部署；首次部署辅助exit1保留、stop/up各0，v3契约21项通过。新正式健康窗口12任务/六域、30.003秒/30成功请求/10流程，Popen.wait0、close六门真、stderr0。新窗口8文件/63值凭据检查命中0、解析/解码错误0；捕获表示重叠不合计独特流量。[部署](evidence/amp-fixed-runtime-20261018/deployment.json)、[健康](evidence/amp-fixed-runtime-20261018/healthy-amqps.json)、[日志审计](evidence/amp-fixed-runtime-20261018/credential-integrity.json)独立于旧45格证据。

8877inspect已观察首轮完成；原launcher启动后编码读取失败exit1与仍运行服务分开记录，只读observer实际0且无重复启动，见[首轮记录](evidence/new7-inspect-session-20261018/first-cycle.json)。尚未24小时/7天验收。旧45格16件证据逐字保留；旧7未决/11坏行/T62 false不因此解除。


### 2026-10-18 只读运行补证：T05、固定窗心跳与巡检UI

fixed-SDK健康窗口按12个captured Start逐taskId核对两端AMP access：coordinator12、六域合计12，共24条，缺失/多余/未完成生命周期0；长运行域日志481条无关access排除，不将access视作物理消息或MCP调用数。固定UTC[06:55:21,07:25:21)七身份心跳采样为840/840，完整raw输入解析错误0；捕获字节和尾部不裁剪，有限前缀复读一致。它不证明连续在线、24小时/7天或Monitor入库。见[访问对账](evidence/new7-runtime-followup-20261018/access-reconciliation.json)和[心跳窗口](evidence/new7-runtime-followup-20261018/heartbeat-window.json)。

8877自然第二周期独立15项检查通过，业务30.002秒/30成功请求/10流程；raw17条awaiting为历史，effective in-flight0。观察器首次KeyError exit1与更早首周期检查器错误各自保留，均不是产品故障；[第二周期](evidence/new7-runtime-followup-20261018/inspect-cycle2.json)不将两轮称长期验收。真实浏览器只读GET验收26distinct=24复用+2纠正schema后delta，六PNG已逐张目视通过、浏览器正常关闭，没有停止持续巡检；首false保留，不把执行轮次相加。见[UI结果](evidence/new7-runtime-followup-20261018/ui-results.json)与[范围和截图清单](evidence/new7-runtime-followup-20261018/ui-inventory.json)。

本次不改生产代码、E1授权模板/计划/输出或原16件E3证据。正式E1未执行且未有新故障授权，旧7未决/11坏行/T62 false不解除。README和进度仅更新当前段；赛方确认表仅把七身份实际完成状态补正，数量上限仍待赛方答复。


### 2026-10-18 当前上游审阅包与第三周期

[当前贡献入口](docs/contributions/upstream-review-20261018/README.md)提供两个独立PR草稿、四条Issue草稿及精确补丁。目标是已核实的官方94077d10b336bfdb9a7d68e4859390bf44a67a27；所选129个SDK源文件与3985基线换行归一后相同，非整个仓库兼容承诺。仅派生LF补丁后，在各自隔离树实际apply-check/apply并逐件核对；接续包3项迁移排序检查通过，未变25项组件检查复用历史记录；并发包在当前未修复SDK上2个负例失败，修复后5项通过，不与项目3项集成检查相加。原CRLF应用失败、EOF警告及历史辅助工具失败保留；旧3985包、原16件E3与8件E1证据不变。当前只在团队内审阅，外部fork、PR及Issue尚未创建或提交，正式NEW7 E1仍待授权执行。

[8877自然第三周期](evidence/new7-inspect-session-20261018/cycle3.json)业务30.002秒、30成功请求、10流程，observe5/verify1且act/审批/模型均0。原23条awaiting快照是历史，当前effective in-flight为0；本次是第三周期和进程句柄/HTTP的时点观察，不等于24小时、7天或未来退出保证。原E3未决、坏行和此前启动/检查器失败不由该证据消解。


### 2026-10-18 GitHub公开贡献已提交

用户明确授权后，公开[fork](https://github.com/RoboSynth/ACPs-community)已创建，两个独立分支已push并远端核对。[接续PR #13](https://github.com/AIP-PUB/ACPs-community/pull/13)对应incident-ext/30f8840785a1b02a661e0fbb335a8dcd9bb038d0、13文件，[MessageEmitter PR #14](https://github.com/AIP-PUB/ACPs-community/pull/14)对应fix/message-emitter-append/ddf2094ef2ea7b687a8966e43302ab07d23b9950、2文件；两者为draft、未合并。四条Issue已发布：[乱序 #15](https://github.com/AIP-PUB/ACPs-community/issues/15)、[MQ文档 #16](https://github.com/AIP-PUB/ACPs-community/issues/16)、[access #17](https://github.com/AIP-PUB/ACPs-community/issues/17)、[发现语义 #18](https://github.com/AIP-PUB/ACPs-community/issues/18)。六项均创建HTTP201、立即GET200，标题/正文逐件一致，实际提交进程exit0。

[安全提交快照](evidence/upstream-public-submission-20261018/submission.json)保留实际公开URL、正文、body SHA与分支提交，仅反映提交当时状态；原始md/payload和补丁包保持原字节，贡献入口加日期前缀完整保留此前未提交阶段文字。本次没有重跑行为测试；排序3/并发5与历史25组件证据保持原范围。已核实的官方94077树中未找到CI配置，未执行上游CI，未声明合并或CI成功。AtomGit未做，正式NEW7 E1待授权执行、24小时验收未完成；原E3失败/旧未决/坏行、E1准备与3985历史包均不变。


### 2026-10-18 完整SDK本地suite与T06准备

现有draft PR #13/#14追加同一测试可移植性修正，当前head09fe13b/72a994b、14/3文件；完整官方SDK本地suite581/581与558/558通过，真实退出均0。首次各1失败因原测试假定根路径不可写，提升权限Windows可写；新测试以临时普通文件阻塞父路径，保留原告警断言，无mock产品/跳过用例。收集节点前后相同，setup/call/teardown全部通过，两套共享上游用例不相加，历史3/5检查不再加总。每套1条PytestAssertRewriteWarning保留；权限/TLS探测只终止持句柄的自有两进程，保留未闭合诊断，未停止项目服务；初次clone包装失败和ambient依赖警告分别保留。

两PR正文PATCH200及随后GET200一致，仍draft、未合并，没有新PR/Issue/评论；[后续公开状态](evidence/upstream-public-submission-20261018/followup.json)与[完整测试及审阅代码](docs/contributions/full-suite-20261018/README.md)新增，原[六项提交快照](evidence/upstream-public-submission-20261018/submission.json)、旧3985/94077包、16件E3及8件E1证据逐字保留。测试在两个父提交加精确一测试修正的隔离树运行，公开新提交源字节一致，提交后未重复跑相同输入。

T06[本机采集准备](deploy/fluent-bit/README.md)补只读预检、固定源归属和隔离state，13个不同Python离线检查（12新增+1既有）与PS解析0错；最终1项局部重验和12项复用不另加总，早期GBK测试夹具错误保留。未启动真实采集器，Kafka/Monitor未配置或验收。09:24Z[第五周期快照](evidence/new7-runtime-followup-20261018/inspect-fifth-cycle.json)核实原host与第五次自然巡检完成，最新30.002秒/30成功/10流程、act/模型0；35条历史awaiting与effective in-flight0分别记录，时点观察不当连续在线。计划中的verify会写合成订单，零act不等于零业务写入。本批不重跑既有测试、不改变E1授权模板/冻结输入或原科学结论；正式NEW7 E1待独立授权，AtomGit/上游CI/24小时验收仍未完成。


### 2026-10-19 正式历史交接契约修复

正式历史中的可选 aip_session_id 现在由 Bridge 接受并校验；拒绝响应的 operation=None 保留原 reason，unknown 接续仍不重发。两产品源与一个回归测试文件为独立修复版本，39 个不同离线方法通过，详见 [修复证据](evidence/handover-wire-fix-20261019/verification-summary.json)及[独立审阅](evidence/handover-wire-fix-20261019/peer-review.json)。原22项验收使用冻结镜像，修复未部署或平台复验；原失败保留。


2026-10-19 正式验收补证：准备22项、尝试22、通过18、失败4、未尝试0。见[本批结果](docs/platform_acceptance_results_20261019.md)；首环境失败、独立恢复/关组warning与资源absent分别保留。独立handover wire修复仅39个离线方法通过，未部署或重验原批；T05/T62按实际findings发布，旧E3和旧未知请求未改判。


### 2026-10-19 策略审计、访问缺端诊断与报告更新

新增可独立运行E2-c：真实MCP stdio与项目fixture的15例中14拒绝均签名audit落盘且转发0，合法正控3次MCP/1次fixture修改，16个独立探测另列；4项验证器检查通过，先前Windows初始化失败保留。新8页技术报告吸收634c46d闭合结果，已逐页目视；缺端诊断为14条确证硬退出、3条缺主进程证据、1条环境验证中断，不改T05=false。见[策略审计](docs/gateway_policy_evaluation_20261019.md)、[缺端诊断](docs/access_accounting_20261019.md)和[报告](deliverables/development-report-20261019/README.md)。本轮未启动真实业务、平台或长期巡检，后续源码复验与外部验收仍待各自证据。

# 当前 P0 缺口与下一动作（2026-10-19）

核对基线：`[canonical]`，clean HEAD `d8ae1958aef411c61742f57ddb96e0de453ec885`。下列源码、文档与证据路径均相对于该检出。任务范围取 `docs/高分方案_需求架构创新与任务_20261017.md` 第8节的40个P0；`docs/P0完成审计_20261017.md`只是历史截面，不作为当前完成状态。

本次只读核对源码、公开投影与已保存运行收据，未重跑测试、启动资源或查网络。没有给项目计算任意完成百分比。

## 优先推进的本机工作

| 顺序 | 任务 | 最新依据与实质缺口 | 下一具体动作与验收边界 |
| --- | --- | --- | --- |
| 1 | T30 | `vendor/ACPs-community/acps-sdk/tests/resumable/test_resumable.py:172`在同一进程重开TaskJournal；`:135`的真实进程死亡测试针对OperationLedger，不是协调者。所查范围未见“协调fixture被杀→全新进程列出在途任务”的收据。 | 新增独立临时协调fixture：经公开ResumableGroupLeader写入任务和多次尝试，持久提交后只杀本fixture；全新解释器经公开TaskJournal恢复任务、映射、事件和递增term。保留原同进程检查，不扩成P1 T33完整事故续跑。无需业务或平台。 |
| 2 | T11/T96 接手质量 | `docs/windows_database_mcp_20261019.md`：69包安装、7个launcher fixture已过，但完整live local-up未实跑；完整local-down未实现。`docs/windows_native_app_stop_20261019.md`的15项检查证明登记应用进程族停机，host、supervisor与业务底座仍分开管理。 | 复用nonce host关闭、supervisor停止、native stop，做精确归属的一键正常停机入口及失败保留登记测试；然后做独立同机真实启停验收。它改善接手，不替代T11/T96的新机器门。 |
| 3 | T01 | `docs/sdk_attribution_20261019.md`：vendor仍是普通文件副本，合并PR13产品改造与PR14写入修复；未绑定单一完整fork版本。本地vendor缺`tests/aip/test_task_ordering.py`、`tests/amp/test_message_emitter_concurrency.py`，MetricsEmitter可移植测试修正只在公开PR头。 | 在隔离检出整合精确runtime与测试树，固定来源修订与依赖绑定，跑适用官方suite并记录。AtomGit发布、上游CI与账号条件单列；不擅选项目总许可证。 |
| 4 | T61/T90/T93 | `eval/platform_resume_experiment.py:799,818`的remaining_workflow从handover完成后才计时；不是故障到接管的总耗时。新12例E1-b均未调用模型，tokens=0，不是模型省token对照。MCP wrapper调用/返回也不是物理修改次数。 | 从冻结结果生成分组CSV/图与字段口径：成功率、已有remaining_workflow、额外观察、完整IFC发送/确认字节、实际stale拒绝；失败缺值保留。缺少的接管总时长/物理效果指标只对未来新冻结源码补测，不反填旧批。 |
| 5 | T90/T93 | 12页修订二`deliverables/development-report-20261019-revision2/`仍截止`412f791`，未含刚结束的12例；旧佐证稿在`deliverables/supporting-evidence-development-20261017/`。 | 新增报告/佐证修订，纳入新11/1、T05=false、T62=true、原22独立18/4、E3局限与贡献来源；复用现有生成器，生成后渲染逐页检查。旧PDF与证据不改。 |
| 6 | T50/T92/T94/T95 | `deliverables/demo-script-development-20261017/`已有脚本分镜；所查deliverables范围未见最终MP4。完整连续F10+F15和后台数据未齐。已有`eval/material_scan.py`可查正文/属性/XMP及显式名称，但没有最终全材料验收。 | 先更新分镜、录制数据与最终材料清单、清洁导出/manifest及匿名检查输入；资源演示另定冻结范围。图像校徽/人物信息逐图检查，最终视频逐镜头检查。最终分享需不同账号验证。用户暂缓答辩PPTX，不新做。 |
| 7 | T10/T13/T61 旧未决项 | `docs/new7_e3_20261018.md`及`evidence/new7-e3-45-20261018-first/pending-intents.json`仍有7个旧未完成阶段：1个cancel未提交，其余6个有POST/unknown历史；原键GET均404，不证明未执行。 | 离线先整理原键/原库/原请求摘要与回执对账清单；仅在原服务恢复且归属明确后只读查询原键及原数据库回执。保留unknown/manual，不补单、不用新H00解除。 |

T05由根代理单独推进。本核对只保留当前失败事实，不提出提前计access或伪造终态来使计数通过。

## 40个P0逐项覆盖

“已有证据”只表示所列门已被当前材料覆盖，不表示依赖它的整条交付链完成。

| P0编号 | 当前状态与最新定位 | 剩余动作/条件 |
| --- | --- | --- |
| T00 | 待赛方答复。`docs/赛方确认.md`仍未取得统计口径、Kafka/TLS、Monitor权限、AIC匿名口径。 | 外部确认；不能以历史计划中写的端口猜生产端点。 |
| T01 | 部分完成：GitHub fork、PR已提交；来源/测试树/AtomGit/最终绑定未齐。`docs/sdk_attribution_20261019.md`。 | 上表3；本地整合与外部镜像分开。 |
| T02 | WSL/Docker/Compose与正式AMQPS已有运行；`deploy/HOST.md`记录主机。睡眠/开机自启及真实重启后恢复未有当前完整验收。 | 本机完善资源清单与自启方案；真实重启验证另安排。HOST中“新版平台主备接管待验收”是旧文字，应改为新结果入口。 |
| T03 | 七新版身份、证书及ADP核对已有证据；`evidence/p0-acceptance-prep-20261019/identity-readiness/summary-v2.json`与新12例。 | 保持身份独占；无本轮代码缺口。 |
| T04 | `incident/amp_setup.py`与新批六域36份日志快照已留证。 | 本地Emitter门已有证据；不等同T06入库。 |
| T05 | 未通过：`evidence/platform-revalidation-20261019/closed-access-credentials.json`，158Start/316预期/304实际/缺12/多余0/生命周期不全12。旧22缺18保留。 | 根代理负责持久性修复及行为验证。 |
| T06 | `deploy/fluent-bit/`已有模板；实际broker/TLS/CA通用性/Monitor地址与权限未齐。 | 外部参数后实际发送、平台可见与验签；已有查证见`evidence/platform-revalidation-20261019/official-config-check/`，本轮不再联网。 |
| T07 | `ops/schedule.py`与短时巡检证据存在；不足连续24小时/7×24。 | T05/T06后按固定窗口运行；需要实际经过时间及在线资源。 |
| T10 | `business/order_app/`、`business/receipts.py`及正式F12/E5已有证据；`docs/f12_e5_20261019.md`、原22汇总。 | 保持事务语义；7个旧未决阶段独立处理，不改为通过。 |
| T11 | `deploy/compose.yml`、`agents.yml`、准备器、跨平台入口与隔离部署/H00已有；未证明当前新机器15分钟。 | 上表2；独立新机器限时验收。 |
| T12 | `eval/inject.py`实现主故障与复原，F15/F19委托专用入口。五场景E3、正式E1与F12分别有结果。 | 不把通用F07当F15；F19的AMP调度属于P1 T43，不能用它强行扩成新的P0正式批次。 |
| T13 | `business/load.py`；新12例每例最终独立H00均≥30秒、30请求、10完整流程且无新未知。 | 已有当前范围证据；新健康窗口不解除历史旧键。 |
| T14 | `incident/contracts.py`、`incident/partners.py`、`tests/test_coordinator.py`与正式产物已有契约证据。 | 无本轮实质代码缺口。 |
| T20 | `acps_mcp_bridge/bridge.py`；正式群组经Postgres MCP返回结果已由E1/F12证明。 | 平台CA/Monitor签名验收另属T06；不重跑已足够的任务门。 |
| T21 | `acps_mcp_bridge/acs_mapper.py`、`tests/test_bridge_gateway.py`官方schema检查及正式身份技能。 | 已有当前范围证据；从零接入录屏T25是P1。 |
| T22 | `docs/gateway_policy_evaluation_20261019.md`：14拒绝+1正控，拒绝逐条签名落盘、0转发。 | 本地组件层已过；不宣称平台CA/Monitor验证。 |
| T23 | `domains/database/`；F06/F07 E3与正式主备接续已运行。 | 原失败/未知不抹去；其余门已有证据。 |
| T24 | `domains/ops/`；Docker MCP/路由MCP及F01/F02 E3已有结果。 | 无本轮实质代码缺口。 |
| T30 | 持久化源码已有；真实协调fixture被杀后新进程恢复查询门仍缺所查范围收据。 | 上表1。不要与P1 T33完整事故连续性混为一项。 |
| T31 | `acps_sdk/aip/resumable/ledger.py`及SDK测试覆盖接续规则/旧令牌；原22的E1-c三次真实旧主复活拒绝。 | 已有当前范围证据；MCP计数不替代物理副作用证据。 |
| T32 | 原22的三个F15点有独立结果；新after_observation3/3，full_history2/3。新r1在官方重新发现失败，0resume发送。 | 失败保持失败；可离线增强发现异常分类/可诊断性，不能未经新计划用盲重试覆盖冻结结果。 |
| T34 | SDK测试、示例、README与公开PR13已有；`docs/contributions/upstream_status_20261019.md`。 | “已提交”门满足；未合并不影响该门。集成测试树由T01补齐。 |
| T40 | `incident/coordinator/hypothesis.py`与`tests/test_coordinator.py`包含schema/回退及同症假设验证。 | E3 M2=15/15；不据此宣称更快。 |
| T41 | `incident/coordinator/planner.py`、`engine.py`；不同路径、选择/重规划测试及F10 E3已有。 | 已有当前范围证据。 |
| T42 | `incident/selection.py`、`tests/test_coordinator.py`资源范围测试与正式参与者选择。 | 已有当前范围证据。 |
| T44 | 工作台审批与Bridge/OperationLedger实际拒绝见E2-c14+1；`docs/gateway_policy_evaluation_20261019.md`。 | 组件门已有；完整连续演示另归T50/T92。 |
| T45 | M0/M1/M2实际矩阵已终态；`docs/new7_e3_20261018.md`：M0/M2各15/15，M1为7/15。 | M1其余8次是保守预算在新POST前拒绝；不改为模型服务器故障，不自动要求重跑矩阵。 |
| T50 | `demo-ui/`、`workbench_server.py`与`evidence/t50-workbench-development-20261018/`有浏览器/视图证据。 | 完整F10+F15全程界面展示仍需独立验收；平台后台统计待T06。 |
| T60 | `eval/run.py`已实际跑完45矩阵并汇总。 | 按真实字段整理可直接入报告图表；M2五场景中位总协调耗时均高于M0，不宣称整体速度优势。 |
| T61 | 新12与原22独立留证；指标未完全等价于4.1要求。`docs/platform_revalidation_results_20261019.md`、计时源码799/818。 | 上表4；三方法完整IFC比较已齐但package有双表示，不能宣称节省字节。模型tokens是无模型0。 |
| T62 | 新12闭合扫描133文件、73已知值，raw/decoded/解析错误均0、覆盖true。 | 仅该捕获范围通过；旧E3的11条AMP损坏行与旧检查不改。 |
| T63 | `eval/stability_report.py`及`docs/stability_report.md`有固定窗口/期望身份分母与离线测试。 | 缺真实24小时/7×24数据和平台证据；代码/30分钟采样不代替。 |
| T80 | 四条Issue15–18已提交，`docs/contributions/upstream_status_20261019.md`有时间快照。 | 提交门满足；维护者回复/合并不能由本机保证。 |
| T90 | 修订二12页、455975B，PDF SHA256`caf4f10f6920eb5482fea8a75702d1e164c04fe2fa2a0499f04bbe876e6ae123`；12页视觉/24自动检查已留证，截止412f791。 | 新修订吸收最新结果；外部与长窗口缺项真实标待验。当前不是最终T90。 |
| T91 | `deliverables/defense-content-development-20261017/`有开发内容；用户暂缓答辩PPTX。 | 当前不推进新答辩幻灯片；最终答辩PDF仍是原计划待办。 |
| T92 | 脚本/分镜/录制清单已有，所查deliverables未见最终MP4。 | 3–5分钟正式录制、≤300MB；后台数据依赖T06。 |
| T93 | 旧佐证开发PDF已有。 | 新合并佐证需加入当前平台、贡献、原数据摘要与来源绑定；缺后台/用户反馈则标待验。 |
| T94 | 当前团队仓库已可接手；历史冻结代码ZIP不等于当前最终交付包。 | 当前冻结源码清洁导出、数据/部署/视频manifest、规范命名；永久分享与他账号访问需外部验收。 |
| T95 | `eval/material_scan.py`及`docs/material_anonymity.md`已有有界扫描器；支持PDF正文/属性/XMP和文本，实际校名/教师/provider需显式词表。 | 最终全部材料清单+逐图逐镜头检查；AIC命名空间按T00答复处理，不能把有界0命中当整体匿名通过。 |
| T96 | 同机隔离部署、Windows新venv和队友旧基线记录均不能代替当前新机器F10。 | 独立机器/用户自有账号，按当前文档冷启动一次通过并留时间/版本/输出。 |

## 不能仅靠本机代码补齐的条件

| 类别 | 对应任务 | 需要的实际输入/运行 |
| --- | --- | --- |
| 赛方配置与权限 | T00/T06，牵连T07/T63/T92/T95 | 统计口径、确切Kafka/TLS/CA/认证说明、Monitor URL与查询权限、AIC匿名结论；需要真实入库/验签画面。 |
| 独立机器 | T11/T96 | 当前冻结版本在新机器限时部署并F10一次通过；已有同机fixture不替代。 |
| 实际经过时间 | T07/T63 | 连续24小时无人干预及更长窗口；明确期望身份、起止、巡检/演练与失败收据。 |
| 外部仓库/审阅 | T01/T34/T80 | AtomGit账号与发布、最终fork绑定和上游CI；PR/Issue已提交不承诺对方响应。 |
| 资源/录制与分享 | T50/T92/T94 | 完整连续F10+F15录制、后台数据与另账号分享检查；不因资料缺失拼接成一次成功运行。 |
| 用户暂缓 | T91 | 当前不生成新答辩PPTX。 |

本清单不新增P1门：T25、T33、T43、T70、T71、T81仍保持原优先级。新12为11/1，原22为18/4，两批不合并成功率；原7个未决阶段和旧T05缺端各保留原结论。

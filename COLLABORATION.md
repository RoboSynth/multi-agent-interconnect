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

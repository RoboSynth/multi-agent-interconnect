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
正在运行的 45 次模型评测整树未纳入本快照，不能从此副本宣称最终矩阵已完成。

[高分方案](docs/高分方案_需求架构创新与任务_20261017.md) · [本地验收](docs/本地开发验收.md) · [开发进度](docs/开发进度_高分方案.md) · [上游贡献草稿](docs/contributions/README.md)

`baselines/` 是过滤后的复现源码视图，原 ZIP 含运行数据库而未分发；查看 `TEAM-SOURCE-MANIFEST.json`。
官方来源与许可见 [THIRD_PARTY.md](THIRD_PARTY.md)。`SNAPSHOT-MANIFEST.json` 列本副本每个文件的哈希及相对原清单的增补/修改。

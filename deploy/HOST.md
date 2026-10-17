# 主机与运行边界

当前开发环境为 Windows，WSL2 Ubuntu-22.04 的 Docker 29.1.3 / Compose 2.40.3 已实际运行。
用户采用本地开发，没有提供 Linux 云主机。
本地 PostgreSQL / Nginx 使用官方可解压二进制，保存在 `tools/runtime/`；不安装系统服务、不改全局 PATH。
PostgreSQL 数据目录为项目 `runtime/pgdata`，仅监听 `127.0.0.1:55432`。

| 服务 | 本地地址 | 管理域 |
| --- | --- | --- |
| Nginx 订单入口 | `http://127.0.0.1:8088` | 运维域 |
| app-v1 | `http://127.0.0.1:8081` | 应用域 |
| app-v2 | `http://127.0.0.1:8082` | 应用域 |
| PostgreSQL 16 | `127.0.0.1:55432` | 数据库域 |
| F12 故障回复代理 | 临时 `127.0.0.1:8090` | 评测域 |
| Docker Nginx 独立入口 | `http://127.0.0.1:18088` | 容器运维域 |
| Docker app-v1 / app-v2 | `http://127.0.0.1:18081` / `18082` | 容器应用域 |
| Docker F12 回复代理 | 临时 `127.0.0.1:18090` | 容器评测域 |

`native-runtime.json` 记录项目内二进制路径、端口和托管进程 PID，不含凭据。
`runtime/private/*.env` 为本域私密配置，不能交给协调方或包含进演示交付包。
本机原生业务验收、Docker 部署验收、梧桐 AIP 验收与云端连续在线是不同结果，分别记录。
独立容器项目 `incident-pilot-container` 使用独立数据库卷，PostgreSQL 不公开主机端口。
容器业务 H00、第三方 Docker MCP 和 F12 已实跑通过；常驻应用/验证/数据库三容器使用旧正式身份做新版契约兼容验证。
数据库备、运维新 AIC、全部新版 ACS、完整平台接续、冷启动与连续运行仍分别验收。

后续 Linux 可使用 compose；需独立确认 Docker compose、出站 443/5671/19092、平台证书及各角色身份。
本机容器内到 wt.ioa.pub:5671 / 9007 的三域 TLS 检查通过，原始证据为
`eval/results/platform/container-old-contract-20261017/tls.json`。19092 Kafka/Monitor 另验。
无须新增云主机才能继续 P0；当前机器规格、禁睡眠/开机自启和新环境冷启动耗时仍须按实际配置记录。

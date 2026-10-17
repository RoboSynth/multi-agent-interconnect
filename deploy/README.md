# 业务底座部署

## Windows 本地开发

官方 PostgreSQL 16 Windows binaries 解压到项目 `tools/runtime/pgsql/`；官方 Nginx Windows ZIP 解压到 `tools/runtime/nginx-<版本>/`。
PostgreSQL 数据目录、`orders` 数据库、`orders_app` 最小权限账号由本项目初始化步骤创建。
数据库管理员在 `orders` 库运行 `business/order_app/schema.sql`，然后授权：

```sql
GRANT CONNECT ON DATABASE orders TO orders_app;
GRANT USAGE ON SCHEMA public TO orders_app;
GRANT SELECT, INSERT, UPDATE ON orders TO orders_app;
GRANT SELECT, INSERT ON operation_receipts TO orders_app;
```

私密环境保存在本机 `runtime/private/application.env`（PG* 和 APP_ADMIN_TOKEN）与
`runtime/private/postgres-superuser.env`（PGADMINPASSWORD 或管理员 PGPASSWORD）。
密码由初始化过程随机生成，不在代码或运行报告内保存。

使用 PowerShell 7.4+：

```powershell
pwsh -NoProfile -File deploy/native.ps1 start
pwsh -NoProfile -File deploy/native.ps1 status
.\.venv\Scripts\python.exe business/load.py --duration 30 --output eval/results/local/h00.json
# 完成本机演示后需要关闭时：
pwsh -NoProfile -File deploy/native.ps1 stop
```

`-EnvFile` 可指定其他应用域环境文件；`-RuntimeFile` 可指定已有运行配置。
中文项目路径下，Windows Nginx 使用运行配置记录的 `native_drive`（当前 P:）临时映射，
映射仍指向项目目录，没有复制数据库或修改系统 PATH。受限会话每次启动时重建本会话映射。
Nginx 重载需等待公共 `/health` 返回预期版本，信号命令成功不能直接认定新路由已生效。
脚本仅管理其记录且命令行匹配本项目的应用进程，以及指定数据目录的 PostgreSQL / Nginx。
停止命令会停止本项目数据库与网关，请在需要保留在线演示时保持运行。

## 真实故障注入

```powershell
.\.venv\Scripts\python.exe eval/inject.py F07 apply --backend native
.\.venv\Scripts\python.exe eval/inject.py F07 restore --backend native
```

| 场景 | 实际资源变化 | 复原 |
| --- | --- | --- |
| H00 | 无修改 | 无修改 |
| F01 | 停止实际 app-v2 进程 / 容器，入口变为 502 | 重启并等待数据库就绪 |
| F02 | 修改并重载实际 Nginx 上游到 v1，响应缺 v2 字段 | 上游回 v2 |
| F06 | 独立数据库事务持有 orders 的 SHARE 锁，读正常，写等待超时 | 结束实验持锁进程 / 容器，事务释放 |
| F07 | ALTER ROLE 设置真实默认只读，重建应用池使新会话生效 | 恢复角色读写，再重建池 |
| F10 | F02 + F07 | 恢复读写、连接及 v2 路由 |
| F12 | Nginx 转向实际回复代理；代理接收已提交成功响应后丢弃客户端回复 | 路由回 v2、停止代理 |

F15 的三个精确中断点、F19 的参与者进程 / 心跳实验由接续评测器提供。
本注入器对 F15 / F19 明确拒绝，不能用业务故障或任意杀进程冒充接续实验成功。
原因只追加到 `eval/results/private/injections.jsonl`；协调方输入应只带业务症状，不能读取此目录。
每个故障复原后运行 30 秒 `business/load.py` 记录 H00，而不是仅以管理接口成功认定业务恢复。

## Windows / WSL Docker 与 Linux Docker

本机 WSL2 Ubuntu-22.04 已有 Docker 29.1.3 / Compose 2.40.3。独立项目
`incident-pilot-container` 使用 18081、18082、18088 和独立 `orders-data` 卷，原生 808x 服务可同时运行。
`eval/results/local/docker-h00-20261017.json` 记录真实 30 秒、30 次请求、10 个完整流程通过。

Windows 从项目目录执行；本机有 Docker CLI 时直接使用，否则启动器调用指定 WSL 发行版：

```powershell
pwsh -NoProfile -File deploy/up.ps1 -EnvFile runtime/private/container.env -ProjectName incident-pilot-container
.\.venv\Scripts\python.exe business/load.py --url http://127.0.0.1:18088 --duration 30 --output eval/results/local/docker-h00-new.json
```

环境文件必须设置三个随机凭据 `POSTGRES_PASSWORD`、`ORDERS_DB_PASSWORD`、`APP_ADMIN_TOKEN`；
独立演练另外设置 `APP_V1_PORT=18081`、`APP_V2_PORT=18082`、`ORDER_PORT=18088`、`REPLY_DROP_PORT=18090`。
启动器把文件路径交给 Compose，不把其凭据加载到协调者环境。保留历史结果时使用新的输出文件名。

```sh
cp deploy/.env.example deploy/.env
# 在资源主机填入三个独立随机凭据，并限制文件权限。
chmod 600 deploy/.env
sh deploy/up.sh
python business/load.py --duration 30 --output eval/results/h00.json
python eval/inject.py F10 apply --backend docker
python eval/inject.py F10 restore --backend docker
```

Compose 包含 PostgreSQL16、两个版本应用、Nginx 与按需启用的真实故障辅助容器，
统一使用 `incident-pilot=true` 标签。数据库不向主机公开端口，应用管理端仅绑定回环，
公共入口默认也绑定回环。修改 `ORDER_BIND` 时应按实际部署需求设置入口访问范围。
数据卷保留订单；更新已有数据库时管理员显式执行迁移，不删除卷重新初始化。

两种启动器调用同一 `compose.yml`，Linux 可用 `INCIDENT_ENV_FILE` 与 `INCIDENT_PROJECT_NAME` 指定相同隔离配置。

### 正式参与者容器

`Dockerfile.agent` 复用已有 `incident/platform_worker.py` 和 `python -m acps_mcp_bridge`；
网关使用 MCP v1，Postgres MCP 与 Docker MCP 分别位于 `/opt/postgres-mcp`、`/opt/docker-mcp`，避免 v1/v2 依赖冲突。
`agents.yml` 为应用、验证、数据库主/备、运维各挂载一个域目录；只有运维域可访问 Docker socket。
数据库主备共享 `/state/operations.sqlite` 所在的一个持久卷，AMP 使用各自子目录。协调者留在用户本机工作台，
不挂数据库、应用或运维的私密卷。

先用 `domains/setup_platform.py` 准备正式配置，再只在本地生成每域挂载；此步骤复制本域证书引用，
不会注册、启动或邀请任何身份。缺 AIC 的备/运维身份记入 `readiness.json`，不能伪造为已就绪。

```powershell
.\.venv\Scripts\python.exe deploy/prepare_agents.py --source runtime/platform-preparation-<时间> --business-env runtime/private/container.env
# 独立 Docker 数据库已有数据卷时，显式应用现有最小权限 bootstrap；不删除卷。
.\.venv\Scripts\python.exe deploy/prepare_agents.py --business-env runtime/private/container.env --provision-db-only --wsl Ubuntu-22.04
# 仅在本批正式身份已注册、证书有效、且同 AIC 原进程已退出后启动；勿与本机正式 runner 重复消费 Inbox。
pwsh -NoProfile -File deploy/up.ps1 -EnvFile runtime/private/container.env -ProjectName incident-pilot-container -Agents
```

生成的应用配置仅显式允许固定服务名 `app-v2`，不会接受任务提供的任意管理地址。数据库上游使用
`bridge_operator` 的域内 `DATABASE_URI`，应用管理 token 只出现在应用挂载，数据库管理员密码不写入任何代理挂载。
首次空数据库若环境已有 `BRIDGE_DB_PASSWORD`，`postgres/init.sh` 会自动应用同一权限脚本；旧卷使用上面的显式迁移。
`up.ps1 -Agents` 要求五个域目录都已准备完成；缺身份时先构建镜像和离线检查，不能报正式参与者已运行。

独立容器资源可使用独立的持久任期库；若将工作台改为操作现有原生资源，必须与其复用同一个
`term_journal_path` 和 `term_namespace`，不得因输出目录更换而从 term=1 重置。正式身份和 AMP Kafka/Monitor 链路仍分别验收。

### 镜像下载与 F12

本机 Docker daemon 直连 Docker Hub 曾超时，而 Windows 既有代理可达。实际使用 Google 官方
`go-containerregistry` crane v0.22.1（官方 checksums.txt 校验）`crane pull --platform linux/amd64` 下载
`postgres:16-alpine`、`nginx:1.27-alpine`、`python:3.12-slim`、`docker:29-cli` 的 tar，再由 WSL `docker load -i` 导入。
没有修改 Mihomo、主机路由或 Docker daemon 代理。常规网络可达时不需要此补救。

F12 独立验收使用真实回复代理，仅在后端提交后丢回复：

```powershell
.\.venv\Scripts\python.exe eval/unknown_receipt_experiment.py --wsl Ubuntu-22.04 --env-file runtime/private/container.env
```

该 runner 核验原键回执、同键重试和 PostgreSQL 单据数为 1；缺原键时保留 unknown/人工状态，不创建新键冒充恢复。
随后停止隔离代理并进行 30 秒业务观察。它属于 F12，F19 在当前方案指运维参与者宕机。

技术依据：[asyncpg Pool API](https://magicstack.github.io/asyncpg/current/api/index.html#connection-pools)、
[PostgreSQL16 显式锁](https://www.postgresql.org/docs/16/explicit-locking.html)。

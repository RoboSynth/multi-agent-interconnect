# 可复用的独立部署准备

`prepare_deployment.py` 把项目名、端口、私密环境、路由挂载和六域配置绑定到一个 `deployment.json`。默认仅生成文件，不运行 Docker、身份注册或平台连接。输出必须是当前检出内的新空目录；既有环境、证书和路由不覆盖。Linux 的输出根和私密父目录为 700，业务环境、审批和协调者文件为 600；只有六个实际挂入 `/domain` 的子树设为目录 755 / 文件 644，使镜像 UID 65534 可读各自身份，宿主其他用户仍不能穿过 700 的输出父目录。Windows 应使用仅本账户可读的私密目录。

先按 [部署说明](README.md) 安装宿主 Python 3.12、项目 `.venv` 和依赖、Docker Engine / Compose v2。容器内依赖不代替宿主验收工具。Windows 使用 PowerShell 7.4+；WSL 模式需已安装并运行对应发行版和 Docker。准备器不安装或重启这些组件。

## 四个业务服务

在项目根目录执行；端口按自己机器选择，四个端口应各不相同且可用：

```powershell
.\.venv\Scripts\python.exe deploy/prepare_deployment.py --output runtime/private/my-deployment --project incident-pilot-my-deployment --app-v1-port 58081 --app-v2-port 58082 --order-port 58088 --reply-drop-port 58090 --wsl Ubuntu-22.04
pwsh -NoProfile -File deploy/up.ps1 -DeploymentFile runtime/private/my-deployment/deployment.json -ValidateOnly
# 确认项目、端口和资源归属后显式启动：
pwsh -NoProfile -File deploy/up.ps1 -DeploymentFile runtime/private/my-deployment/deployment.json
```

Windows 直接 Docker CLI 模式省略 `--wsl`。manifest 指定 WSL 时启动器始终使用该发行版，Windows 上另有 Docker CLI 不会改变选择。所有端口绑定回环，数据库不公开宿主端口，数据卷按 Compose project 隔离。`reply-drop` 仍是未启用的 faults profile；准备或业务启动不包含故障注入。

Linux 上运行同样的准备命令，使用 `.venv/bin/python` 且省略 `--wsl`：

```sh
.venv/bin/python deploy/prepare_deployment.py --output runtime/private/my-deployment --project incident-pilot-my-deployment --app-v1-port 58081 --app-v2-port 58082 --order-port 58088 --reply-drop-port 58090
INCIDENT_DEPLOYMENT_FILE=runtime/private/my-deployment/deployment.json INCIDENT_VALIDATE_ONLY=1 sh deploy/up.sh
INCIDENT_DEPLOYMENT_FILE=runtime/private/my-deployment/deployment.json sh deploy/up.sh
```

`INCIDENT_PYTHON` 可指定自己的宿主解释器，manifest 路径按项目根目录解析，两个启动入口可从其他当前目录调用。manifest 模式与旧的 env/project/agents 参数互斥；不把资源 env 导入宿主进程，并清除子进程继承的 `COMPOSE_*` 覆盖。代理设置保留。`ValidateOnly` / `INCIDENT_VALIDATE_ONLY=1` 仅执行 `config --quiet`，不初始化默认路由或启动服务。

四服务准备没有 `target.json`，因为当前显式故障评测器要求完整六域和业务服务。不能把它作为可注入目标。用同一个 manifest 验证公共 `/ready`、每个业务响应的 v2 版本，以及 30 秒、10 个订单创建/查询/取消流程；每次使用新的输出目录：

```powershell
.\.venv\Scripts\python.exe deploy/verify.py --deployment-file runtime/private/my-deployment/deployment.json --output artifacts/my-deployment-h00-first
```

Linux 使用 `.venv/bin/python` 调相同入口。Compose 启动成功不代替业务验收。七角色模式也可用该命令验证业务，但它不向平台提交任务。

## 六个参与域和独立协调者

七角色模式复用 `deploy/prepare_agents.py`，推荐直接使用 `--identity-file` 指定自己已有的注册身份 source.json，无需原生 PostgreSQL/MCP 的 setup_local 前置。身份文件格式与现有平台准备输入一致：公共 `discovery_url`、`mq_auth_url`、绝对 `trust_bundle`，以及 `agents.leader/application/verification/database/database_backup/ops/onboarding`，每项仅需非空 `aic`、无 URL 凭据的 `amqps` endpoint 和绝对 `cert` / `key` 文件路径。公共元数据 URL 必须为 HTTPS。

准备器在新目录内生成七份单身份中间配置，不复制完整身份映射到任何参与域；协调者只收到自己的私钥。它不申请证书或注册身份。

```powershell
.\.venv\Scripts\python.exe deploy/prepare_deployment.py --mode seven --identity-file integration/private/my-identities/source.json --output runtime/private/my-seven --project incident-pilot-my-seven --app-v1-port 58081 --app-v2-port 58082 --order-port 58088 --reply-drop-port 58090 --wsl Ubuntu-22.04
pwsh -NoProfile -File deploy/up.ps1 -DeploymentFile runtime/private/my-seven/deployment.json -ValidateOnly
```

已有 `domains/setup_platform.py` 输出仍可通过互斥的 `--source` 复用；该目录须含七个角色 JSON 及可读的材料引用，协调者的证书、私钥和信任链路径必须为本机绝对路径。旧 `setup_platform.py` 路线生成桥接域时仍要求既有 setup_local 配置；直接 `--identity-file` 路线绕过此依赖，不改动旧流程。

身份材料只做离线文件和七个 AIC 互异检查，不代替证书有效期、密钥匹配、注册审核或真实连接验证。**实际启动前排除这七个身份的并发 Inbox 消费者。** 使用自己的新身份或先正常结束同身份旧进程；生成新目录并不创造新身份。准备结果始终不宣称平台已就绪。

启动命令同上。它用基础 compose、agents 和生成的 overlay，显式启用六域 `isolated` profile；按项目名生成 agent 镜像 tag，先构建两个应用，再单独构建一次六域共享镜像，最后 `up --no-build --wait`。仍使用现有领域凭据隔离、主备共享数据库账本、ops 独占 socket、主数据库初选和独立任期 namespace；协调者配置留在宿主机 `domains/coordinator/config.json`，启动器不会自动运行协调者。

`target.json` 使用现有 `incident-evaluator-target/1.0`，与 manifest 的 project、WSL、Compose 文件、env、route 和三业务端口精确一致。故障评测必须显式传它；实际操作前现有注入器继续核验全部十个容器、只读域挂载、真实 AIC/源码、回环端口和独立数据卷，不放宽检查。准备本身不执行 F10，也不能算 T96 已通过。

env、overlay、target 和已准备域文件有 SHA 校验，变更后启动器拒绝使用旧 manifest；保留原目录并重新准备新目录。路由内容允许正常运行时变更，重跑会保留当前内容，由明确的故障复原步骤恢复 v2。生成的 env、approval、域配置和证书须留在私有目录，不能上传到仓库。

本入口减少手工步骤；它的离线测试与同机 Compose 配置渲染不代表新机器 15 分钟冷部署或正式平台 F10 验收。

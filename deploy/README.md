# 新机器 Windows 部署：10 步

队友用自己的 GitHub 账号克隆，用自己的七个梧桐身份做正式联调。本文主线使用 PowerShell 7.4+、Python 3.12、Windows Docker CLI 和 Linux 容器；只有 WSL Docker 的机器按 [ISOLATED.md](ISOLATED.md)给准备命令加 `--wsl <自己的发行版>`，后续启动、停止都沿用该 manifest。

每步把开始、结束、错误和处理填入[计时与试用反馈模板](新机器部署计时与反馈模板.md)。第 1–7 步完成四业务服务与 H00；第 8 步只准备七身份文件；**第 9–10 步等待用户确认实际项目、七身份独占和 F10 故障范围后执行。** T96 要另一台机器实际跑通 F10；业务 H00 通过时只记业务验收通过。

详细命令见[操作参考](操作参考.md)，当前能力和结果见[强基线说明](../docs/BASELINE.md)。

## 1. 检查工具并记开始时间

```powershell
(Get-Date).ToUniversalTime().ToString('o')
$PSVersionTable.PSVersion
py -3.12 --version
git --version
docker info --format '{{.OSType}}'
docker compose version
```

预期：Python 3.12、PowerShell 7.4+、Docker 返回 `linux`，Compose v2。常见错误：`docker` 不存在或 daemon 未启动，先安装/启动自己的 Docker 环境；Windows 容器模式改为 Linux 容器。工具安装时间和部署时间分别记录，原始总耗时保留。

## 2. 用自己的账号克隆并固定版本

```powershell
$G8Workspace = Join-Path $env:USERPROFILE 'source'
New-Item -ItemType Directory -Force $G8Workspace | Out-Null
git clone https://github.com/RoboSynth/multi-agent-interconnect.git (Join-Path $G8Workspace 'multi-agent-interconnect')
Set-Location (Join-Path $G8Workspace 'multi-agent-interconnect')
git rev-parse HEAD
```

预期：得到完整提交 SHA。常见错误：私有仓库 `404`/`403`，用自己的 GitHub 账号接受仓库邀请并重新认证；目标已存在时选择新检出目录。后续命令在本仓库根目录的同一个 PowerShell 窗口运行。

## 3. 建自己的 Python 环境

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-high-score.txt
.\.venv\Scripts\python.exe -m pip install './vendor/ACPs-community/acps-sdk[amp-sign]'
.\.venv\Scripts\python.exe -m pip check
```

预期：依赖安装退出 0，`pip check` 无损坏依赖。常见错误：解释器版本不符，使用第 1 步的 Python 3.12；下载失败保留错误，修复自己的网络后只续装未完成依赖。无需激活脚本、付费 API 或下载模型。

## 4. 准备独立四业务项目

```powershell
$G8Run = 'g8-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$G8Business = 'runtime/private/' + $G8Run + '-business'
$G8Seven = 'runtime/private/' + $G8Run + '-seven'
$G8BusinessProject = 'incident-pilot-' + $G8Run + '-business'
$G8SevenProject = 'incident-pilot-' + $G8Run + '-seven'
Get-NetTCPConnection -State Listen -LocalPort 58081,58082,58088,58090 -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe deploy/prepare_deployment.py --output $G8Business --project $G8BusinessProject --app-v1-port 58081 --app-v2-port 58082 --order-port 58088 --reply-drop-port 58090
```

预期：四端口无既有监听；输出 `prepared_only=true`、`resources_started=false`，生成 `deployment.json`。常见错误：端口占用就统一换四个空闲端口；输出非空就保留旧目录、重新设置新 `$G8Run`。准备器生成随机凭据，只写文件。

## 5. 检查并启动四业务

```powershell
pwsh -NoProfile -File deploy/up.ps1 -DeploymentFile "$G8Business/deployment.json" -ValidateOnly
pwsh -NoProfile -File deploy/up.ps1 -DeploymentFile "$G8Business/deployment.json"
```

预期：Compose 配置与构建/启动均退出 0。常见错误：镜像拉取失败，检查 Docker 自身的网络与错误日志；`prepared deployment input changed` 则保留原目录并重新准备，勿手改 manifest 的 SHA 或重置数据卷。

## 6. 跑 30 秒业务 H00

```powershell
.\.venv\Scripts\python.exe deploy/verify.py --deployment-file "$G8Business/deployment.json" --output "artifacts/$G8Run-business-h00"
```

预期：`result.json` 为 `passed`，30 次请求成功、10 个完整创建/查询/取消流程，前后 `/ready` 为 v2，失败/未知/待决为 0。常见错误：v1/502/数据库错误先保存 `readiness.json`、`h00.json` 与容器日志；输出目录已存在时用新目录，保留旧失败。这是业务验收，不是平台 F10。

## 7. 停止自己的四业务，保留数据

本段为 Windows 直接 Docker CLI 主线；WSL 模式使用[操作参考的 manifest 停止方法](操作参考.md#按同一-manifest-停止四业务或七角色)，传入本次四业务 manifest。

```powershell
$G8BusinessCompose = @('compose','-p',$G8BusinessProject,'--env-file',"$G8Business/compose.env",'-f','deploy/compose.yml','-f',"$G8Business/deployment.overlay.yml")
docker @G8BusinessCompose stop --timeout 30
docker @G8BusinessCompose ps --all
```

预期：本项目四个服务均停止。常见错误：命令失败或仍有运行服务时保留日志并查原因；不要删除卷、重建密码或停止其他项目。第 9 步复用这些端口前先确认监听已释放。

## 8. 准备自己的七身份与 target（只写本机文件）

先按[自有账号配置第 2–3 节](../docs/自有账号平台配置_20261018.md#2-在自己的梧桐账号下登记七个角色)完成注册、审核和证书，再把[身份模板](../integration/seven-identities.example.json)填入自己的 `integration/private/<自己目录>/source.json`；七角色为协调、应用、主数据库、备用数据库、运维、业务验证、接入体检，各自证书/私钥/信任链使用本机绝对路径。缺身份时停在此处，先交第 6 步结果。

```powershell
$G8Identities = 'integration/private/自己的目录/source.json' # 改为自己的实际文件
.\.venv\Scripts\python.exe deploy/prepare_deployment.py --mode seven --identity-file $G8Identities --output $G8Seven --project $G8SevenProject --app-v1-port 58081 --app-v2-port 58082 --order-port 58088 --reply-drop-port 58090
pwsh -NoProfile -File deploy/up.ps1 -DeploymentFile "$G8Seven/deployment.json" -ValidateOnly
```

预期：生成同项目的 `deployment.json`、`target.json`、`domains/coordinator/config.json`，准备输出 `platform_ready=false`；尚未连接平台。常见错误：文件不存在/七 AIC 重复/路径非绝对，按原错误修正输入并重新准备新目录；文件检查不代替证书有效期、clientAuth 和私钥匹配。

## 9. 确认范围后启动正式六域

**待用户确认：本项目及端口、七个具体 AIC 没有其他消费者；若原机巡检使用同身份，先正常停巡检并记停机时间。** 本步启动六个领域消费者，协调者由下一步 F10 runner 唯一启动；不用另开工作台或 scheduler。

```powershell
pwsh -NoProfile -File deploy/up.ps1 -DeploymentFile "$G8Seven/deployment.json"
.\.venv\Scripts\python.exe deploy/verify.py --deployment-file "$G8Seven/deployment.json" --output "artifacts/$G8Run-seven-h00-before"
```

预期：本项目十个容器启动、业务 H00 通过；正式发现/邀请是否成功由第 10 步逐项记录。常见错误：证书、TLS、DNS/ACL 连接问题保留原阶段与错误，检查自己的配置和平台状态；不反复注册、领取 EAB 或启动同 AIC 第二消费者。

## 10. 确认后只跑 1 次 F10/M0，验收并停止

**待用户确认范围：一次旧路由＋数据库只读＋连接池故障及受控恢复，M0、模型 0 调用、显式七身份 `target.json`，包含本例正常 SDK 关组；结束核验 30 秒/10 流程并停止自有项目。** 将项目名、七 AIC、端口和这段范围交用户确认后才执行下列命令；旧实验授权与准备文件不能代替本次确认。

```powershell
.\.venv\Scripts\python.exe eval/run.py --transport wutong-amqps --backend docker --target-config "$G8Seven/target.json" --config "$G8Seven/domains/coordinator/config.json" --scenarios F10 --methods M0 --repeats 1 --approve-high --output "artifacts/$G8Run-f10"
$G8F10Exit = $LASTEXITCODE
.\.venv\Scripts\python.exe deploy/verify.py --deployment-file "$G8Seven/deployment.json" --output "artifacts/$G8Run-seven-h00-after"
$G8FinalH00Exit = $LASTEXITCODE
$G8SevenCompose = @('compose','-p',$G8SevenProject,'--env-file',"$G8Seven/compose.env",'-f','deploy/compose.yml','-f','deploy/agents.yml','-f',"$G8Seven/deployment.overlay.yml",'--profile','isolated')
docker @G8SevenCompose stop --timeout 30 application-agent verification-agent onboarding-agent database-agent database-backup-agent ops-agent
docker @G8SevenCompose stop --timeout 30 nginx app-v1 app-v2 postgres
docker @G8SevenCompose ps --all
(Get-Date).ToUniversalTime().ToString('o')
```

预期：F10 退出 0，单行结果为 `completed` 且 `continuous_recovery_confirmed=true`；最终 H00 退出 0，本项目十个服务停止，提交完整计时与试用反馈。常见错误：任意失败都保留原输出，不重复同一计划；F10 未成功、SDK 关组未完成、停止未完成分别记录，最终 H00 通过不消除原失败。WSL 停止改用第 7 步所链接的 manifest 方法。T96 与 15 分钟目标只按这台新机器的真实记录判定。

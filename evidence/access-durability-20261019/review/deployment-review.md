# d8ae195：队友本地部署与停机审阅

基线：`d8ae1958aef411c61742f57ddb96e0de453ec885`，本轮核对目录为 `[canonical]`。这是只读代码/资料审阅与下一次实际验收范围，不是新的启动、H00、停机或新机器验收结果。本轮未启动容器、数据库、应用、平台身份、模型或故障。

## 1. 最先处理的真实缺口

| 优先级 | 位置 | 当前实际行为与影响 | 最小后续动作 |
| --- | --- | --- | --- |
| P0 | `deploy/native.ps1:93-98` | 应用族停止检查了退出码；Nginx `-s quit` 与 `pg_ctl stop` 均不检查退出码，随后无条件保存并 `exit 0`。外部命令报错时，PowerShell的`ErrorActionPreference=Stop`不会自动把普通native非零退出改为异常。静态可确定存在“总停机exit0但PG/网关未确认停止”的路径；本轮没有制造这个失败。 | 分别检查两条控制命令的真实退出码，随后核验本批Nginx/PG身份及结束状态；已停止应通过明确状态核验实现幂等，不能通过忽略错误实现。保存逐组件结果，不以总exit0代替结束证明。 |
| P0验收缺口 | `docs/windows_native_app_stop_20261019.md:11-15`；`evidence/native-app-stop-20261019/source-ready.json` | 15方法包括真实自定义venv启动器+休眠孩子的harmless fixture。该fixture没有监听应用端口、没有真实数据库/Nginx，也没有完整业务启动/停止。现在还不能称真实订单应用的子进程与端口释放已随该补丁验证。 | 在独立新资源里跑下述native业务真实启动→H00→正常stop，保存实际app父子PID、监听者、PG/网关和退出证据。既有fixture结果复用，不重跑整套离线测试冒充实测。 |
| P1 | `deploy/local-up.ps1:38-53`；`docs/本地开发环境与操作_20261018.md:272-319` | `local-up`还会准备MCP、启动supervisor和workbench。收尾要先nonce关闭workbench、等正常finished，再核对并终止独立8093 supervisor，最后native stop；没有对应完整`local-down`入口。文档已经明确这点。 | 后续复用现有host控制协议和已登记进程身份，补一个按顺序工作的停止入口。supervisor目前没有优雅关闭API，不能把TerminateProcess称为它的正常协议关闭。 |
| P1 | `deploy/prepare_deployment.py:310-354`；`deploy/up.ps1`；`deploy/up.sh` | manifest已覆盖准备/校验/启动，但没有对等的manifest停止CLI。指南140-181行要求人工重构同project/env/compose scope，WSL还要自己保持daemon与路径一致。它能操作，但不是一条统一停止命令。 | 最小扩展是让现有manifest入口支持正常stop，继续复用`load_deployment`和`compose_command`。本轮验收可先用第3节明确命令，不另造部署框架。 |
| P1 | `tools/prepare_native_database.py:52-53,77,100-103,137` | 初始化器固定读取`deploy/native-runtime.json`，生成env、启动/就绪探测和summary都写死55432。`native.ps1 -RuntimeFile`虽然可读自定义pgport和配置文件，初始化器没有对应参数。不能把“传另一个RuntimeFile”当作全链路端口隔离方案。 | 首次真实native验收使用全新checkout/数据目录且先确认55432空闲；如需要与其他PG并行，再小范围参数化初始化器。不得把新cluster初始化到旧目录或把旧服务的ready当作新cluster成功。 |

另一个需要留证的现有行为：`native.ps1 start`在启动PG/应用后若Nginx配置或ready失败，finally只恢复父进程环境；`local-up`后段失败也不会回滚此前已启动的业务。文档267行已提示可能留下业务。验收失败应保留runtime登记及原日志，按已核实归属正常停止本次资源，不能盲目整条重跑。

## 2. 账号和本机准备状态

账号本身不是本地业务阻塞：独立四业务、native订单底座与local-aip-stdio不需要原开发者GitHub/梧桐账号；自己的GitHub只用于取得仓库。正式七角色另需自己的注册身份与证书，不能把本次只跑业务的结果当作正式平台接入。指南15-24行的区别与代码主线一致。

本次只读查到：canonical checkout没有`.venv/Scripts/python.exe`、项目内PostgreSQL及Nginx二进制，符合源码仓库不带本机运行环境的状态；原开发目录`incident-pilot/tools/runtime`保留PostgreSQL与Nginx本地文件。已存在开发解释器为CPython3.12.14 AMD64/64，能定位httpx、asyncpg、fastapi、uvicorn模块。该解释器可用于后续同机warm验证，不证明队友新机器已安装。PATH能找到pwsh与wsl，未找到docker.exe；未检查WSL内daemon可用性，也未确认候选端口当前空闲。

## 3. 最小实际验收A：先验证独立四业务主线

这是最简单的队友自有账号路径；复用已有isolated business模式。准备独立的新源码目录，记录其HEAD；不要修改正式12例的冻结checkout、计划、数据卷或结果。项目名建议`incident-pilot-deploy-local-20261019`，端口`61081/61082/61088/61090`；最后一个只预留给未启用的reply-drop，不启动faults或agents profile。数据库不暴露宿主端口。

以下是后续执行命令，当前未执行。`$Root`必须是本批独立checkout，已有对应Python依赖；前置核对四端口空闲、同名项目不存在、所选Docker daemon可用。WSL版只能从Windows checkout启动；直接Docker CLI版省略`--wsl`。

```powershell
$Root = '[workspace]/incident-pilot/artifacts/deploy-local-acceptance-20261019/checkout'
Set-Location -LiteralPath $Root
$Py = Join-Path $Root '.venv/Scripts/python.exe'
$Manifest = Join-Path $Root 'runtime/private/deploy-local-20261019/deployment.json'
& $Py (Join-Path $Root 'deploy/prepare_deployment.py') --mode business --output runtime/private/deploy-local-20261019 --project incident-pilot-deploy-local-20261019 --app-v1-port 61081 --app-v2-port 61082 --order-port 61088 --reply-drop-port 61090 --wsl Ubuntu-22.04
if ($LASTEXITCODE) { throw 'Preparation failed; preserve this attempt.' }
$env:INCIDENT_PYTHON = $Py
pwsh -NoProfile -File (Join-Path $Root 'deploy/up.ps1') -DeploymentFile $Manifest -ValidateOnly
if ($LASTEXITCODE) { throw 'Configuration failed.' }
pwsh -NoProfile -File (Join-Path $Root 'deploy/up.ps1') -DeploymentFile $Manifest
if ($LASTEXITCODE) { throw 'Startup failed; inspect ownership and stop only this attempt.' }
& $Py (Join-Path $Root 'deploy/verify.py') --deployment-file $Manifest --output artifacts/deploy-local-h00-001
$H00Exit = $LASTEXITCODE
# Stop scope comes from the same manifest, including its WSL daemon and all files.
$CommandJson = & $Py -c 'import json,sys; from deploy.prepare_deployment import load_deployment,compose_command; print(json.dumps(compose_command(load_deployment(sys.argv[1]),sanitized=True)))' $Manifest
if ($LASTEXITCODE) { throw 'Cannot validate the original deployment scope.' }
$CommandParts = @($CommandJson | ConvertFrom-Json)
$Executable = $CommandParts[0]
$Prefix = @($CommandParts | Select-Object -Skip 1)
& $Executable @Prefix ps --all
# Verify that the listed four containers belong to this exact project before stop.
& $Executable @Prefix stop --timeout 15 nginx app-v1 app-v2 postgres
$StopExit = $LASTEXITCODE
& $Executable @Prefix ps --all
```

Linux对应启动入口只需把同一新manifest交给`INCIDENT_DEPLOYMENT_FILE=... sh deploy/up.sh`；验证使用`.venv/bin/python deploy/verify.py --deployment-file ... --output ...`。Windows/WSL的一次通过不能宣称Linux宿主的up.sh实跑通过，后者应在已有Linux宿主Python3.12与依赖可用后独立记录。

实际完成判据：prepare/validate/up均有真实terminal exit；四服务ID/project/image/端口与新scope一致；H00前后公共ready为v2，30秒、30成功请求、10个完整创建/查询/取消流程，failed/unknown/unresolved/pending全0；正常stop实际exit0且四容器均非running、宿主三个业务端口释放；原容器ID/数据卷保留且本批之前的其他容器/服务不变。H00或stop任何一项失败都保留原件，不能以另一项成功补判。这里的业务请求会写入本批自己的订单数据，不是只读探测，但不触碰共享/旧业务。

## 4. 最小实际验收B：关闭native真实业务缺口

必须另用新checkout和全新`runtime/pgdata`、private env、Nginx prefix以及自身`.venv`，不能复用原开发者的既有数据库或正式验收挂载。使用已保存且验证过的portable归档/本地文件准备本批自己的`tools/runtime/pgsql`和Nginx；不要把pgdata指向旧目录。`business/native_postgres.py:14-15`要求解析后的二进制及数据路径属于当前checkout，不能简单把runtime的路径改到原开发目录来绕过独立资源。

为最小复现，先使用默认`8081/8082/8088/55432`；四端口须在执行前重新确认空闲，已有监听则停止准备，不按端口杀进程。8093、8766、8089和8090均不启动；本范围只验证真实订单底座，不运行MCP、supervisor、workbench、模型或平台身份。

```powershell
$Root = '[workspace]/incident-pilot/artifacts/native-business-acceptance-20261019/checkout'
Set-Location -LiteralPath $Root
$Py = Join-Path $Root '.venv/Scripts/python.exe'
# Prerequisite: this checkout owns its fresh .venv and portable runtime files.
& $Py (Join-Path $Root 'tools/prepare_native_database.py')
if ($LASTEXITCODE) { throw 'Fresh database preparation failed; retain its own files.' }
$RuntimeFile = Join-Path $Root 'deploy/native-runtime.json'
$PreparedRuntime = Get-Content -LiteralPath $RuntimeFile -Raw | ConvertFrom-Json
# Normal setup stop allows the next native start to exercise its DB startup branch.
& (Join-Path $PreparedRuntime.postgres_bin 'pg_ctl.exe') stop -D $PreparedRuntime.pgdata -m fast
if ($LASTEXITCODE) { throw 'Owned setup database did not stop.' }
pwsh -NoProfile -File (Join-Path $Root 'deploy/native.ps1') start -RuntimeFile $RuntimeFile
if ($LASTEXITCODE) { throw 'Native start failed; preserve partial-start ownership metadata.' }
$Running = Get-Content -LiteralPath $RuntimeFile -Raw | ConvertFrom-Json
foreach ($Version in 'v1','v2') {
    $AppPid = $Running.managed.$Version
    $AppPort = $Running.('app_' + $Version + '_port')
    & $Py (Join-Path $Root 'business/native_process.py') --pid $AppPid --script run_app.py --version $Version --port $AppPort --python-executable $Running.app_python --app-family
    if ($LASTEXITCODE) { throw 'Real app family identity did not verify.' }
}
& $Py (Join-Path $Root 'deploy/verify.py') --url http://127.0.0.1:8088 --output artifacts/native-business-h00-001
$H00Exit = $LASTEXITCODE
pwsh -NoProfile -File (Join-Path $Root 'deploy/native.ps1') stop -RuntimeFile $RuntimeFile
$NativeStopExit = $LASTEXITCODE
```

最后必须另行核实并保存：两个真实app父子PID都已退出，8081/8082/8088/55432全部无监听；自己的PG进程及Nginx主/子进程终态；`managed`登记按实际结果清理；数据库、env和日志保留。本轮发现native stop还会吞掉PG/Nginx控制失败，因此当前`$NativeStopExit=0`只能作为一项观测，不能单独作为正常stop通过证据。该P0代码缺口应先修或在真实验收中独立揭示，不能为了拿到通过而删除失败。

本次B若通过，只证明同机独立真实native订单业务与最新app-family停机路径；不证明完整`local-up`、五域正常关闭、8093 supervisor收尾、新机器15分钟、平台或长期稳定性。完整local-up还应另外在新资源中按现有nonce流程完成workbench正常finished与五个worker exit0，再按身份范围处理supervisor、停止底座。

## 5. 本轮证据与建议次序

实际只做了源码/资料读取、工具文件存在性和解释器模块可定位性检查。基线核对chunk`0227d7`；native当前代码与端口初始化范围chunk`d07114`；真实fixture边界chunk`e4a088`/`1b817a`；解释器只读检查chunk`5c06c8`。候选端口本轮未确认为空闲，不能据此直接启动。

建议先修`native.ps1 stop`的Nginx/PG真实退出核验，再做B填补当前补丁最直接的真实业务缺口；A可以作为队友推荐主线的独立正常部署证明。两者分别记录，不相加成新机T11/T96，不重跑已授权故障批次，不修改原22例、12例或旧失败。

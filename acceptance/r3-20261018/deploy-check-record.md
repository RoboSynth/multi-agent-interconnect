# 共享说明

本文件是第三轮本机验收记录的脱敏派生，只提交此 Markdown。个人绝对路径替换为占位符，LOCAL_EVIDENCE 为本机证据定位符，不是仓库内可下载附件。命令中的占位符仅用于审阅，不能原样复制执行；原始日志、截图、凭据、DB 和账本均未上传。

本机完整记录 SHA-256：`ebe48d34277c8390d824b0365b93d08e0559da8bc47bbcef85e17eb7655dac5e`；记录生成时刻与测量提交在正文明确绑定。

# 第三轮按文档独立部署验收记录

本次由 AI 按文档执行、用户在场观察。

本轮 A、B、C 三档均完成。三组测试并非全绿；默认受限执行通道需要环境补充与源码辅助排查，因此不能宣称只凭两份文档即可在本机无干预完成部署。原失败、原跳过均保留。

- 仓库 RoboSynth/multi-agent-interconnect；固定提交 **8a820e419cea55f14d4de0edec76c0e1bcf87904**；产品源码为 f8f3e6634af3b6f9433c599f97a77a94b551faff，8a820e4 仅合并已提交的 R2 报告。
- 实测分支 deploy-check-20261018；第三轮副本 incident-pilot-r3（`R3_PROJECT/.`）；证据 deploy-check-r3-20261018（`LOCAL_EVIDENCE/.`）。路径全部为英文。
- 两份操作入口仅 COLLABORATION.md 和 deploy/README.md；需要读源码补充的安装/权限/停机步骤均列文档缺失，链接文档不自动成为额外平台操作授权。
- 仅 local AIP stdio，模型关闭；未启动正式平台身份、未使用正式 AIC/证书/私钥、未连接 wt.ioa.pub Inbox。本机 local-* 是进程通道标识。
- 已有 GitHub 只读访问、项目便携软件/依赖、本机随机凭据生成沿用用户批准；matplotlib 安装和本轮 F10 另获明确批准。用户要求审批按钮由本人点击，实际照办。
- 用户澄清可以用自己的账号，不需要那两个文件：本机 A/B/C 不以两份 ACS JSON 为前提；只把读取缺失 JSON 的测试记为错误。未索取其他人的身份文件、未生成或伪造这两份文件。
- 无产品源码/测试/阈值/skip 条件修改；无系统代理/全局环境变量/电源/执行策略修改；未安装 Windows 服务。PYTHONIOENCODING、MPLCONFIGDIR 仅对命令进程生效。
- 根目录已有的 R2 deploy-check-record.md 保持原字节；第三轮写入 acceptance/r3-20261018/deploy-check-record.md。原始日志和私有资源只保留本机。

## 机器环境

| 项目 | 实测 |
| --- | --- |
| 系统 | Windows 11 22H2，build 22621.4037，64 位；注册表 ProductName 残留 Windows 10 Pro，Python platform 识别 Windows 11 |
| Python | 已有 3.12.10 AMD64；全新 .venv 与 .venv-mcp-postgres，不继承系统 site-packages，user_site=false |
| PowerShell | 7.6.5；部分原测试调用系统 Windows PowerShell 5.1，Restricted 执行策略保持不变 |
| Docker | 未检出可用 Docker；未安装、未启动容器或 WSL 正式部署 |
| 便携运行时 | PostgreSQL 16.15、Nginx 1.30.6，R3 tools/runtime 项目内安装 |
| 依赖 | 主 SDK[amp-sign]/requirements-high-score/lock；独立 postgres-mcp==0.3.0；获新批准的 matplotlib==3.11.2、约束后的 Pillow==12.3.0 |
| 执行上下文 | 默认受限非管理员通道；网络/临时目录/WMI/子进程限制下，依赖与工作台等采用获准完整上下文；PG 由非管理员路径初始化启动 |

版本证据 29-version-dependency-and-source-freeze.log（`LOCAL_EVIDENCE/29-version-dependency-and-source-freeze.log`）；主环境 29-main-pip-freeze.txt（`LOCAL_EVIDENCE/29-main-pip-freeze.txt`）；MCP 环境 29-mcp-pip-freeze.txt（`LOCAL_EVIDENCE/29-mcp-pip-freeze.txt`）。

软件来源：[EnterpriseDB 官方 PostgreSQL 分发](https://sbp.enterprisedb.com/getfile.jsp?fileid=1260623)、[Nginx 官方 ZIP](https://nginx.org/download/nginx-1.30.6.zip)、[PyPI matplotlib](https://pypi.org/project/matplotlib/3.11.2/) 和已检出的 vendored SDK。只复用校验后的软件 ZIP，不复制数据库、配置、账本。软件 SHA/CRC 校验见 05-verified-portable-software-cache.log（`LOCAL_EVIDENCE/05-verified-portable-software-cache.log`）。这是新 checkout/新环境并复用软件缓存，不是无缓存新机器冷部署。

## 三档结果与证据

| 档位 | 结果 | 本机证据 |
| --- | --- | --- |
| A | 通过：30.0 秒、30/30 请求、10 完整流程 | 24-cli-h00.json（`LOCAL_EVIDENCE/24-cli-h00.json`）；24-ready-before/after.json |
| B | 通过：工作台 http://127.0.0.1:8766 打开、五个本地参与者已连接 | 26-workbench-ready-top.jpg（`LOCAL_EVIDENCE/26-workbench-ready-top.jpg`）；30-local-scope-preflight.json（`LOCAL_EVIDENCE/30-local-scope-preflight.json`） |
| C | 通过：真实注入→人工批准→恢复→30.0 秒/30 请求/10 流程→复原→复原后 H00 | 31-f10-authorization.json（`LOCAL_EVIDENCE/31-f10-authorization.json`）；34-f10-result-summary.json（`LOCAL_EVIDENCE/34-f10-result-summary.json`）；34-f10-business-metrics.jpg（`LOCAL_EVIDENCE/34-f10-business-metrics.jpg`）；35-restoration-proof.json（`LOCAL_EVIDENCE/35-restoration-proof.json`）；36-post-restore-h00.json（`LOCAL_EVIDENCE/36-post-restore-h00.json`） |

所有窗口的 failed、unknown、unresolved_intents 均为 0。原请求未知选项未勾选，没有用新订单冒充既有原请求恢复。

新版 deploy/verify.py 本机入口另外完整执行：原受限通道失败 25-new-documented-strict-verifier.log（`LOCAL_EVIDENCE/25-new-documented-strict-verifier.log`） 保留；相同命令/判定在新目录成功，30.016 秒、30 请求、10 流程，每个响应检查 v2，前后 ready=v2。原结果 result.json（`LOCAL_EVIDENCE/27-native-verifier/result.json`）、h00.json（`LOCAL_EVIDENCE/27-native-verifier/h00.json`）。这是公共 H00 证明，不代表新机器冷启动、Docker、接管、正式平台或 Monitor 入库。

F10 时间线：

- 21:14:28–21:14:30：用户已同意本轮范围，F10 apply 成功；公共 ready=v1。31-fault-public-ready.json（`LOCAL_EVIDENCE/31-fault-public-ready.json`）
- 21:14:38：AI 仅通过 UI 输入“订单提交异常，请查明原因并恢复业务。”并开始，事故 inc-a13cfd6dbf0b49d2。协调器未读取 private/injections 原因日志。
- 2026-10-18T21:14:39.917375+08:00：请求 high db.restore_writes；此前普通 write ops.route_rollback 按产品流程自动执行。审批截图 32-approval-db-restore-writes.jpg（`LOCAL_EVIDENCE/32-approval-db-restore-writes.jpg`）。
- 2026-10-18T21:15:26.595599+08:00：用户本人点击批准，API status=approved；AI 没有点击或调用审批 API。
- 21:15:27–21:15:57：恢复写入、重建池后，真实公共订单验证 30 秒/30 请求/10 流程通过，产品 completed、business_recovered/service_recovered=true、manual_required=false。原始状态 34-f10-workbench-after-human-approval.json（`LOCAL_EVIDENCE/34-f10-workbench-after-human-approval.json`）。
- 2026-10-18T21:16:47.0169839+08:00：原始 restore 命令成功；route.conf 前后 SHA-256 同为 BEC7A77EA0A27FC544504BC5993D688885CC399EA48968061E78B9BAAE7E090B。
- 复原后 business/load.py 30.0 秒、30/30、10 完整流程再次通过。

## 三组测试与获准补测

| 组 | 原始结果 | 方法通过 | 失败方法 / error / skip | 原日志 |
| --- | --- | --- | --- | --- |
| tests | Ran 472 in 66.012s；FAILED (failures=4, errors=6, skipped=6) | 457 | 3 / 6 / 6 | 09-tests-root-original.log（`LOCAL_EVIDENCE/09-tests-root-original.log`） |
| resumable | Ran 25 in 3.06s；OK | 25 | 0 / 0 / 0 | 10-tests-sdk-resumable.log（`LOCAL_EVIDENCE/10-tests-sdk-resumable.log`） |
| bridge | Ran 52 in 4.471s；FAILED (errors=1) | 51 | 0 / 1 / 0 | 12-tests-bridge-original.log（`LOCAL_EVIDENCE/12-tests-bridge-original.log`） |
| report_integrity_supplement | Ran 9 in 0.857s；OK | 9 | 0 / 0 / 0 | 16-supplement-report-integrity.log（`LOCAL_EVIDENCE/16-supplement-report-integrity.log`） |
| figure_supplement | Ran 1 in 0.088s；OK | 1 | 0 / 0 / 0 | 17-supplement-previously-skipped-figure.log（`LOCAL_EVIDENCE/17-supplement-previously-skipped-figure.log`） |

前三行为用户指定三组；后两行为获准安装 matplotlib 后仅补跑原先不能执行的项目。根组原始 472 保持不变；1 个导入错误补成 9 个真实测试，另一个原始 skip 补跑 1 个，不伪造新的全组总数。一个 Windows startup 方法包含两个 what_if 子测试失败，因此失败方法=3、原文 failures=4。网关与根组重叠，不能相加。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p '*test*.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s vendor/ACPs-community/acps-sdk/tests/resumable -p 'test*.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_bridge*.py' -v
```

原始错误：缺 database.submission.acs.json（1 error）、application.approved.acs.json（4 errors）、matplotlib（1 导入 error）。失败：部署准备测试硬编码 /mnt/d/（本轮英文路径在 C:）、Fluent Bit 测试预期 Kafka 错误却先触发 AMP 目录检查、PowerShell 5.1 Restricted（1 方法含2子测试）。原始 6 skips 为5项显式 PG 集成前置条件未满足及1项缺图表依赖；未人为改变开关跳过。

新提交相关子集来自同一次 09 原日志：回执/v2 校验 21/21、独立部署验证器7/7、部署准备11/12、工作台访问核对与 host 17/17。只作覆盖索引，不是额外测试总数，也不替代真实 F12、Docker 或平台验收。new-feature-test-subsets.json（`LOCAL_EVIDENCE/new-feature-test-subsets.json`）、test-results.json（`LOCAL_EVIDENCE/test-results.json`）。

## 文档缺失、错误和建议

| 编号 | 本次观察 | 建议改法 |
| --- | --- | --- |
| D01 | SDK/requirements/独立 postgres-mcp 的安装顺序需从启动器补全，报告绘图依赖未在入口说明 | 列新环境、各 requirements 安装命令、pip check 与可选报告依赖；说明失败后须停，安装须获授权 |
| D02 | PG 需要非管理员，但本机受限通道 WMI/子进程/0700 临时目录不可用；需拆源码初始化再完整上下文启动工作台 | 给权限/目录/网络预检与明确分段 native init / local up；区分工具通道限制与普通 Windows 终端，不笼统要求管理员启动 PG |
| D03 | 端口表遗漏 supervisor 8093 | 补用途、回环绑定和归属核验；禁止随意杀占用端口的进程 |
| D04 | F10 只有 F07 命令和组合表，没有完整 UI 排查/人工审批/异常复原指南 | 写完整 F10 apply、症状输入、高风险审批、completed+业务字段及30秒10流程、finally restore、复原后 H00 |
| D05 | 三组测试命令、覆盖模式、依赖、fixture 与 skip 条件不清晰 | 给本记录三条 discover；*test*.py 覆盖 business_*_test.py，列安全本地 PG 前置条件与预期失败留存 |
| D06 | 两个 JSON 不影响本地启动，但旧测试硬编码读取快照中不存在的文件 | 维护者改用仓库内无凭据固定 fixture 或明确生成公共测试元数据的方法；不要求辅助开发索取他人 AIC/证书 |
| D07 | 新部署准备测试硬编码 /mnt/d/；本轮实际正确生成 /mnt/c/ 仍失败 | 用临时 fixture 实际盘符计算期望路径，或显式模拟 D: 路径映射；保留 C:/D: 与Unicode/空格用例 |
| D08 | Fluent Bit 测试预期 Explicit Kafka settings，却先触发 The coordinator AMP directory must exist inside this project | 给测试创建明确隔离 AMP fixture，并分别验证目录和 Kafka 前置条件；由维护者判断期望顺序，验收方不改断言 |
| D09 | native.ps1 stop 的 PG fast 停机超时仍返回0；旧 PG 55432 未释放 | 传播 pg_ctl 非零退出码、报告剩余 PID/端口；注明日志/DB保留与经归属核验的有界停机升级方案，不吞失败 |
| D10 | 工作台/五域/MCP/supervisor 完整停机缺入口；后台句柄可令外层工具会话保持 | 提供 local-down 的空闲检查、归属核验、停止顺序和端口验证；子进程句柄重定向，明确各组件主进程退出状态 |
| D11 | 新 verify.py 在受限通道新建0700目录后不能写 result；普通通道失败未预检 | 输出目录写权限预检与明确错误；保持0700安全目标，说明受限执行器适配，使用新目录保留原失败 |
| D12 | 缓存复用、软件版本/来源/校验和本机冷启动口径未在两入口完整列出 | 列官方版本/URL/SHA或CRC；区分新checkout/新venv/软件缓存复用和无缓存新机器验收 |

D01/D02/D09/D10 的补充安装/分段/停机涉及源码辅助，按用户要求记为文档缺失。D02/D11 为本机工具受限上下文观察，不推断每台 Windows 必败。未更改执行策略以让 startup 测试变绿，也未安装计划任务、Windows 服务、Docker、正式平台身份。

## 每一步的时间、命令、耗时、结果、报错和处理

按开始时间排序；并行安装不相加为总墙钟时间。所有重试使用独立编号/输出目录，原日志保留。00 为轮次初始快照；浏览器截图26/32/34作为 UI 证据，其文件时间保留。命令只是记录，不含随机密码/令牌。

00-round3-start.json（`LOCAL_EVIDENCE/00-round3-start.json`）：20:45:07 开始，旧 R2 六端口尚占用，因此先保存其已结束事故/进程归属证据，再维护停机；20步空闲后才启动 R3。未同时启动两份副本。

### 01-prepare-new-checkout

开始 2026-10-18T20:47:03.7325561+08:00；结束 2026-10-18T20:47:03.8468116+08:00；耗时 0.112 秒；退出码 0。

结果：创建纯英文路径第三轮副本；不覆盖前两轮文件。

是否需要问人：否。文档依据/补充：COLLABORATION.md 独立检出及用户纯英文路径要求；上一轮副本和原件保持原样。

命令：

```powershell
$ErrorActionPreference='Stop'
git init '<R3_PROJECT>'
if($LASTEXITCODE -ne 0){throw 'git init failed'}
git -C '<R3_PROJECT>' remote add origin https://github.com/RoboSynth/multi-agent-interconnect.git
if($LASTEXITCODE -ne 0){throw 'remote add failed'}
```

完整输出与报错原文：01-prepare-new-checkout.log（`LOCAL_EVIDENCE/01-prepare-new-checkout.log`）。对应命令另存 01-prepare-new-checkout.command.ps1（`LOCAL_EVIDENCE/01-prepare-new-checkout.command.ps1`）。

### 02-fetch-pinned-latest

开始 2026-10-18T20:47:25.1641998+08:00；结束 2026-10-18T20:47:30.3717381+08:00；耗时 5.205 秒；退出码 0。

结果：使用已授权的既有 GitHub 登录获取并固定 8a820e4；不追随验收中的新提交。

是否需要问人：否。文档依据/补充：已有 GitHub 登录只读 fetch 最新主分支完整 SHA；安装/网络执行上下文沿用既有授权。

命令：

```powershell
git fetch --no-tags --no-recurse-submodules origin 8a820e419cea55f14d4de0edec76c0e1bcf87904
if($LASTEXITCODE -ne 0){throw 'Pinned fetch failed'}
```

完整输出与报错原文：02-fetch-pinned-latest.log（`LOCAL_EVIDENCE/02-fetch-pinned-latest.log`）。对应命令另存 02-fetch-pinned-latest.command.ps1（`LOCAL_EVIDENCE/02-fetch-pinned-latest.command.ps1`）。

### 03-checkout-documents-and-dependency-scope

开始 2026-10-18T20:47:38.9485417+08:00；结束 2026-10-18T20:47:40.3721420+08:00；耗时 1.422 秒；退出码 0。

结果：独立分支 checkout 固定提交，读取两份入口文档，主代码与 R2 对比确定为 f8f3e66 产品源码。

是否需要问人：否。文档依据/补充：固定最新 SHA；只按 COLLABORATION.md 与 deploy/README.md 选本机入口；额外测试/源码检查作为文档缺失单列。

命令：

```powershell
$ErrorActionPreference='Stop'
git checkout -b deploy-check-20261018 8a820e419cea55f14d4de0edec76c0e1bcf87904
if($LASTEXITCODE -ne 0){throw 'Checkout failed'}
git rev-parse HEAD
git status --short --branch
$instructionFiles=@(rg --files -g AGENTS.md)
if($instructionFiles.Count){foreach($f in $instructionFiles){Write-Output ('INSTRUCTION='+$f);Get-Content -LiteralPath $f}}
else{Write-Output 'NO_REPOSITORY_AGENTS_MD'}
$global:LASTEXITCODE=0
Get-FileHash -LiteralPath COLLABORATION.md,deploy/README.md,requirements-high-score.txt,requirements-lock.txt,domains/database/requirements.txt -Algorithm SHA256
Write-Output 'DEPLOYMENT_DOC_RELEVANT_LINES'
rg -n '^#|verify.py|venv|local-up|native.ps1|8766|8093|F10|restore' COLLABORATION.md deploy/README.md
Write-Output 'PRIOR_FAILURE_FIXTURE_EXISTS'
foreach($f in @('integration/incident/database.submission.acs.json','integration/incident/application.approved.acs.json')){Write-Output ($f+'='+(Test-Path -LiteralPath $f))}
Write-Output 'PINNED_DEPENDENCY_DIFF'
git diff --name-only f689dae16ab292717c4b695d96ee29e5263b4895 HEAD -- requirements-high-score.txt requirements-lock.txt domains/database/requirements.txt vendor/ACPs-community/acps-sdk
$global:LASTEXITCODE=0
```

完整输出与报错原文：03-checkout-documents-and-dependency-scope.log（`LOCAL_EVIDENCE/03-checkout-documents-and-dependency-scope.log`）。对应命令另存 03-checkout-documents-and-dependency-scope.command.ps1（`LOCAL_EVIDENCE/03-checkout-documents-and-dependency-scope.command.ps1`）。

### 04-fresh-python312-environments

开始 2026-10-18T20:48:04.4600223+08:00；结束 2026-10-18T20:48:17.1548867+08:00；耗时 12.693 秒；退出码 0。

结果：新建 Python 3.12 主环境及独立 postgres-mcp 环境，没有继承系统 site-packages。

是否需要问人：否。文档依据/补充：COLLABORATION.md venv 原始命令；沿用上一轮已确认的受限临时目录问题，完整执行上下文是文档缺失的环境补充。

命令：

```powershell
$ErrorActionPreference='Stop'
if((Test-Path -LiteralPath '.venv') -or (Test-Path -LiteralPath '.venv-mcp-postgres')){throw 'Fresh environments already exist'}
py -3.12 -m venv .venv
if($LASTEXITCODE -ne 0){throw 'Main venv creation failed; do not install'}
py -3.12 -m venv .venv-mcp-postgres
if($LASTEXITCODE -ne 0){throw 'MCP venv creation failed; do not install'}
& .\.venv\Scripts\python.exe -c 'import sys,site,json;print(json.dumps({"version":sys.version,"prefix":sys.prefix,"base_prefix":sys.base_prefix,"user_site":site.ENABLE_USER_SITE}))'
if($LASTEXITCODE -ne 0){throw 'Fresh venv probe failed'}
Get-Content -LiteralPath .venv/pyvenv.cfg
Get-Content -LiteralPath .venv-mcp-postgres/pyvenv.cfg
```

完整输出与报错原文：04-fresh-python312-environments.log（`LOCAL_EVIDENCE/04-fresh-python312-environments.log`）。对应命令另存 04-fresh-python312-environments.command.ps1（`LOCAL_EVIDENCE/04-fresh-python312-environments.command.ps1`）。

### 05-verified-portable-software-cache

开始 2026-10-18T20:48:25.3061523+08:00；结束 2026-10-18T20:48:31.9428957+08:00；耗时 6.635 秒；退出码 0。

结果：只复制并校验 PostgreSQL/Nginx 软件 ZIP 缓存；没有复制私有配置、数据库或账本。

是否需要问人：否。文档依据/补充：沿用已批准 PostgreSQL 16.15/Nginx 1.30.6 来源；当前未改下载器校验 ZIP/解压；缓存复用区别于新机器冷下载。

命令：

```powershell
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath 'tools/runtime'){throw 'New runtime cache already exists'}
New-Item -ItemType Directory -Path 'tools/runtime' | Out-Null
$expected=@{'postgresql-16.15.zip'='43BB45F173A6F08CF1D29A97A6D8DEB119E8E8093A24C00D2D1001A0CCAA8281';'nginx-1.30.6.zip'='C6EE35EDB0A861063323F709192AE50D1EEFAF2EA7D00678BD2B22D8542DC61E'}
foreach($name in $expected.Keys){
 $from=Join-Path '<R2_PROJECT>\tools\runtime' $name
 $hash=(Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash
 if($hash -ne $expected[$name]){throw ('Approved ZIP hash changed: '+$name)}
 Copy-Item -LiteralPath $from -Destination (Join-Path 'tools/runtime' $name)
 Write-Output ($name+' SHA256='+$hash)
}
py -3.12 tools/download_native_runtime.py
if($LASTEXITCODE -ne 0){throw 'Original runtime validator failed'}
Write-Output 'ONLY_APPROVED_SOFTWARE_ZIPS_REUSED; NO_PRIOR_DATABASE_CONFIG_OR_LEDGER_COPIED'
```

完整输出与报错原文：05-verified-portable-software-cache.log（`LOCAL_EVIDENCE/05-verified-portable-software-cache.log`）。对应命令另存 05-verified-portable-software-cache.command.ps1（`LOCAL_EVIDENCE/05-verified-portable-software-cache.command.ps1`）。

### 06-main-approved-install

开始 2026-10-18T20:48:51.5884957+08:00；结束 2026-10-18T20:49:38.7030723+08:00；耗时 47.113 秒；退出码 0。

结果：在新 .venv 安装已获授权的 SDK[amp-sign] 及主 requirements，pip check 通过。

是否需要问人：已获用户此前明确安装授权；没有新增软件类型。文档依据/补充：COLLABORATION.md SDK 命令和 deploy 本机依赖；相同锁文件与 SDK 已核对无变更。

命令：

```powershell
$ErrorActionPreference='Stop'
if(-not(Test-Path -LiteralPath '.venv/Scripts/python.exe')){throw 'Fresh venv missing'}
& .\.venv\Scripts\python.exe -m pip install "./vendor/ACPs-community/acps-sdk[amp-sign]"
if($LASTEXITCODE -ne 0){throw 'Approved SDK install failed'}
& .\.venv\Scripts\python.exe -m pip install -r requirements-high-score.txt
if($LASTEXITCODE -ne 0){throw 'Approved locked requirements install failed'}
& .\.venv\Scripts\python.exe -m pip check
if($LASTEXITCODE -ne 0){throw 'Main pip check failed'}
```

完整输出与报错原文：06-main-approved-install.log（`LOCAL_EVIDENCE/06-main-approved-install.log`）。对应命令另存 06-main-approved-install.command.ps1（`LOCAL_EVIDENCE/06-main-approved-install.command.ps1`）。

### 07-postgres-mcp-approved-install

开始 2026-10-18T20:48:52.9817434+08:00；结束 2026-10-18T20:50:04.2788017+08:00；耗时 71.295 秒；退出码 0。

结果：在独立新环境安装已获授权的 postgres-mcp==0.3.0，pip check 通过。

是否需要问人：已获用户此前明确安装授权；没有新增软件类型。文档依据/补充：沿用先前已批准的独立 postgres-mcp==0.3.0/mcp==1.30.0 环境，当前清单无变更；两份入口未列完整独立安装步骤，标记文档缺失。

命令：

```powershell
$ErrorActionPreference='Stop'
if(-not(Test-Path -LiteralPath '.venv-mcp-postgres/Scripts/python.exe')){throw 'Fresh MCP venv missing'}
& .\.venv-mcp-postgres\Scripts\python.exe -m pip install -r domains/database/requirements.txt
if($LASTEXITCODE -ne 0){throw 'Approved postgres-mcp install failed'}
& .\.venv-mcp-postgres\Scripts\python.exe -m pip check
if($LASTEXITCODE -ne 0){throw 'MCP pip check failed'}
```

完整输出与报错原文：07-postgres-mcp-approved-install.log（`LOCAL_EVIDENCE/07-postgres-mcp-approved-install.log`）。对应命令另存 07-postgres-mcp-approved-install.command.ps1（`LOCAL_EVIDENCE/07-postgres-mcp-approved-install.command.ps1`）。

### 08-new-test-and-local-shutdown-scope-review

开始 2026-10-18T20:49:21.8657937+08:00；结束 2026-10-18T20:49:22.1436091+08:00；耗时 0.276 秒；退出码 0。

结果：核对新增测试与上一轮停机范围；需要读源码补充的操作列为文档缺失。

是否需要问人：否。文档依据/补充：安全核对新增测试为离线/mock/自有进程；为补两份文档缺失的完整停机步骤读取源码，明确标记文档缺失。

命令：

```powershell
$ErrorActionPreference='Stop'
Write-Output 'NEW_OR_CHANGED_TESTS'
git diff --name-only f689dae16ab292717c4b695d96ee29e5263b4895 HEAD -- tests
Write-Output 'WORKBENCH_HOST_TEST_ACTUAL_SCOPE'
Get-Content -LiteralPath tests/test_workbench_host.py -Encoding utf8
Write-Output 'NEW_TEST_PROCESS_AND_NETWORK_BOUNDARIES'
rg -n 'patch|MockTransport|subprocess|Popen|create_subprocess|requests\.|httpx\.|socket|wt\.ioa\.pub|amqps|real|skip' tests/test_receipt_resolution.py tests/test_deployment_verify.py tests/test_deployment_preparation.py tests/test_workbench_access.py tests/test_fluent_bit_collection.py tests/test_fluent_bit_linux_collector.py tests/test_fluent_bit_preparation.py
Write-Output 'NATIVE_STOP_OWNERSHIP_IMPLEMENTATION'
rg -n -C 3 'Stop-|Process|stop|nginx|pg_ctl' deploy/native.ps1 | Select-Object -Last 110
$global:LASTEXITCODE=0
```

完整输出与报错原文：08-new-test-and-local-shutdown-scope-review.log（`LOCAL_EVIDENCE/08-new-test-and-local-shutdown-scope-review.log`）。对应命令另存 08-new-test-and-local-shutdown-scope-review.command.ps1（`LOCAL_EVIDENCE/08-new-test-and-local-shutdown-scope-review.command.ps1`）。

### 09-tests-root-original

开始 2026-10-18T20:51:08.7841623+08:00；结束 2026-10-18T20:52:18.2157759+08:00；耗时 69.43 秒；退出码 1。

结果：根组原始 472 方法：457 passed、3 failure 方法、6 errors、6 skips；原文 failures=4 包含两个 what_if 子测试。

是否需要问人：否。文档依据/补充：用户要求 tests/ 全组；*test*.py 同时覆盖 business_*_test.py；保留原失败/错误/条件跳过，离线 fixture 不启动正式身份。

命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p '*test*.py' -v
```

完整输出与报错原文：09-tests-root-original.log（`LOCAL_EVIDENCE/09-tests-root-original.log`）。对应命令另存 09-tests-root-original.command.ps1（`LOCAL_EVIDENCE/09-tests-root-original.command.ps1`）。

### 10-tests-sdk-resumable

开始 2026-10-18T20:51:11.0132459+08:00；结束 2026-10-18T20:51:15.2515392+08:00；耗时 4.237 秒；退出码 0。

结果：SDK resumable 原始 25/25 通过。

是否需要问人：否。文档依据/补充：用户要求独立 SDK resumable 测试组；新建 Python 3.12 环境，未改测试或判定。

命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s vendor/ACPs-community/acps-sdk/tests/resumable -p 'test*.py' -v
```

完整输出与报错原文：10-tests-sdk-resumable.log（`LOCAL_EVIDENCE/10-tests-sdk-resumable.log`）。对应命令另存 10-tests-sdk-resumable.command.ps1（`LOCAL_EVIDENCE/10-tests-sdk-resumable.command.ps1`）。

### 11-prior-idle-resource-ownership-check

开始 2026-10-18T20:52:03.6313650+08:00；结束 2026-10-18T20:52:21.4193583+08:00；耗时 17.786 秒；退出码 0。

结果：旧轮事故 completed 且无待审批；配置 SHA、PID、进程创建时间与归属核对后才准备维护停机。

是否需要问人：否。文档依据/补充：新副本启动前端口被上一轮占用；只读核对配置 SHA、事故已完成和本轮旧进程树。完整工作台停机未写在两入口，标记文档缺失。

命令：

```powershell
$ErrorActionPreference='Stop'
$s=Invoke-RestMethod 'http://127.0.0.1:8766/api/state' -TimeoutSec 5
$expected=(Get-FileHash -LiteralPath '<R2_PROJECT>\runtime\local-coordinator.json' -Algorithm SHA256).Hash.ToLowerInvariant()
if($s.mode -ne 'local-aip-stdio' -or -not $s.connected -or $s.config_sha256 -ne $expected -or $s.model_config.enabled){throw 'Prior workbench scope differs'}
if($s.incident.status -ne 'completed' -or @($s.incident.approvals|Where-Object {$_.status -eq 'pending'}).Count){throw 'Prior workbench has an active or pending incident'}
$raw=(Invoke-WebRequest 'http://127.0.0.1:8766/api/state').Content
$raw | Set-Content -LiteralPath '<LOCAL_EVIDENCE>\11-prior-workbench-idle-original.json' -Encoding utf8
$ports=@(8081,8082,8088,55432,8766,8093)
$listeners=@(Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -in $ports} | ForEach-Object {
 $p=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$_.OwningProcess)
 $owned=($p.CommandLine -like '*<R2_PROJECT>*' -or $p.ExecutablePath -like '<R2_PROJECT>\*')
 [pscustomobject]@{port=$_.LocalPort;address=$_.LocalAddress;pid=[int]$_.OwningProcess;owned_by_r2=$owned;creation_date=$p.CreationDate}
})
if(@($listeners|Where-Object {-not $_.owned_by_r2 -or $_.address -ne '127.0.0.1'}).Count){throw 'Listener belongs to another project or is not loopback'}
$roots=@([int]$s.pid,[int]($listeners|Where-Object {$_.port -eq 8093}).pid)
$nodes=[Collections.Generic.List[object]]::new()
$seen=[Collections.Generic.HashSet[int]]::new()
function Read-OwnedTree([int]$processId,[int]$depth){
 if(-not $seen.Add($processId)){return}
 $p=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$processId)
 if(-not $p){return}
 if($depth -eq 0 -and $p.CommandLine -notlike '*<R2_PROJECT>*'){throw 'Process root is not prior project'}
 $nodes.Add([pscustomobject]@{pid=[int]$p.ProcessId;parent_pid=[int]$p.ParentProcessId;name=$p.Name;depth=$depth;creation_date=$p.CreationDate;owned_by_r2_lineage=$true})
 foreach($child in @(Get-CimInstance Win32_Process -Filter ('ParentProcessId = '+$processId))){Read-OwnedTree ([int]$child.ProcessId) ($depth+1)}
}
foreach($rootId in $roots){Read-OwnedTree $rootId 0}
$proof=[ordered]@{checked_at=[DateTimeOffset]::Now.ToString('o');project_root='<R2_PROJECT>';mode=$s.mode;config_sha256=$expected;incident_status=$s.incident.status;roots=$roots;listeners=$listeners;control_process_tree=@($nodes);action='READ_ONLY_NO_STOP_YET';reason='Only prior idle project resources may be stopped for new independent checkout'}
$proof|ConvertTo-Json -Depth 8|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\11-prior-owned-processes.json' -Encoding utf8
$proof|ConvertTo-Json -Depth 8
```

完整输出与报错原文：11-prior-idle-resource-ownership-check.log（`LOCAL_EVIDENCE/11-prior-idle-resource-ownership-check.log`）。对应命令另存 11-prior-idle-resource-ownership-check.command.ps1（`LOCAL_EVIDENCE/11-prior-idle-resource-ownership-check.command.ps1`）。

### 12-tests-bridge-original

开始 2026-10-18T20:52:47.7685124+08:00；结束 2026-10-18T20:52:53.4755208+08:00；耗时 5.705 秒；退出码 1。

结果：网关原始 52 方法：51 passed、1 error；缺本地 JSON fixture，未补造身份材料。

是否需要问人：否。文档依据/补充：用户要求的网关 test_bridge* 原组；与根组有重叠，不相加；缺本地样例时保留原错误，不改测试。

命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_bridge*.py' -v
```

完整输出与报错原文：12-tests-bridge-original.log（`LOCAL_EVIDENCE/12-tests-bridge-original.log`）。对应命令另存 12-tests-bridge-original.command.ps1（`LOCAL_EVIDENCE/12-tests-bridge-original.command.ps1`）。

### 13-approved-optional-matplotlib-install

开始 2026-10-18T20:54:30.5627066+08:00；结束 2026-10-18T20:54:57.1036138+08:00；耗时 26.539 秒；退出码 0。

结果：用户明确批准后，只在 R3 .venv 安装 PyPI matplotlib==3.11.2 及必需依赖。

是否需要问人：用户明确同意仅安装到第三轮项目。文档依据/补充：requirements-report.txt 指定 matplotlib==3.11.2；用户本轮单独批准，初始缺依赖失败保持。PYTHONIOENCODING 仅本次子进程，不改全局环境。

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
Write-Output 'USER_APPROVED: matplotlib==3.11.2 and required dependencies, R3 venv only'
& .\.venv\Scripts\python.exe -m pip install matplotlib==3.11.2
if($LASTEXITCODE -ne 0){throw 'Approved optional dependency installation failed'}
& .\.venv\Scripts\python.exe -m pip check
if($LASTEXITCODE -ne 0){throw 'Dependency check failed'}
& .\.venv\Scripts\python.exe -c 'import matplotlib;print("matplotlib="+matplotlib.__version__)'
```

完整输出与报错原文：13-approved-optional-matplotlib-install.log（`LOCAL_EVIDENCE/13-approved-optional-matplotlib-install.log`）。对应命令另存 13-approved-optional-matplotlib-install.command.ps1（`LOCAL_EVIDENCE/13-approved-optional-matplotlib-install.command.ps1`）。

### 14-stop-only-prior-idle-local-services

开始 2026-10-18T20:55:39.3558257+08:00；结束 2026-10-18T20:56:58.0316103+08:00；耗时 78.674 秒；退出码 1。

结果：未通过：旧工作台/stdio 域/supervisor 已停，native stop 的 PostgreSQL fast 停机 60 秒超时；脚本却返回 0，包装器发现端口未释放并保留失败。

是否需要问人：用户要求接着做新版本机复测；只停止自己建立且事故已结束的上一轮本机服务；无正式平台，无 F10 注入。文档依据/补充：deploy/README.md native.ps1 stop；工作台/域/运维停机需自行补充（文档缺失），按配置/进程树/创建时间核对，仅为新版独立部署维护腾端口。

命令：

```powershell
$ErrorActionPreference='Stop'
$proof=Get-Content -LiteralPath '<LOCAL_EVIDENCE>\11-prior-owned-processes.json' -Raw|ConvertFrom-Json
$s=Invoke-RestMethod 'http://127.0.0.1:8766/api/state' -TimeoutSec 5
if($proof.project_root -ne (Get-Location).Path -or $s.config_sha256 -ne $proof.config_sha256 -or $s.mode -ne 'local-aip-stdio' -or [int]$s.pid -ne [int]$proof.roots[0] -or $s.incident.status -ne 'completed' -or @($s.incident.approvals|Where-Object {$_.status -eq 'pending'}).Count){throw 'Prior scope or idle status changed; no stop'}
$n=Get-Content -LiteralPath 'deploy/native-runtime.json' -Raw|ConvertFrom-Json
if($n.project_root -ne (Get-Location).Path -or $n.pgport -ne 55432 -or $n.order_port -ne 8088){throw 'Prior native scope differs'}
foreach($stem in @('21-documented-local-up-standard-context','27-documented-local-up-rerun')){Copy-Item -LiteralPath (Join-Path '<R2_EVIDENCE>' ($stem+'.log')) -Destination (Join-Path '<LOCAL_EVIDENCE>' ('14-prior-'+$stem+'-before-stop.log'))}
$terminated=[Collections.Generic.List[int]]::new()
function Stop-VerifiedPriorProcess([int]$processId){
 $record=@($proof.control_process_tree|Where-Object {$_.pid -eq $processId})
 if($record.Count -ne 1){throw 'Process not in verified prior tree'}
 $current=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$processId)
 if(-not $current){return}
 if(([DateTimeOffset]$current.CreationDate).UtcDateTime.Ticks -ne ([DateTimeOffset]$record[0].creation_date).UtcDateTime.Ticks){throw 'PID reused; will not stop'}
 if($record[0].depth -eq 0 -and $current.CommandLine -notlike '*<R2_PROJECT>*'){throw 'Root command no longer matches prior project'}
 Stop-Process -Id $processId -Force -ErrorAction Stop
 $terminated.Add($processId)
 Write-Output ('STOPPED_VERIFIED_R2_PID='+$processId)
}
foreach($rootId in $proof.roots){Stop-VerifiedPriorProcess ([int]$rootId)}
Start-Sleep -Seconds 5
foreach($node in @($proof.control_process_tree|Sort-Object depth -Descending)){Stop-VerifiedPriorProcess ([int]$node.pid)}
pwsh -NoProfile -File deploy/native.ps1 stop
if($LASTEXITCODE -ne 0){throw 'Documented prior native stop failed'}
Start-Sleep -Seconds 2
$remaining=@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()|Where-Object {$_.Port -in @(8081,8082,8088,55432,8766,8093)})
if($remaining.Count){throw 'Required ports not free after prior stop'}
$after=[ordered]@{finished_at=[DateTimeOffset]::Now.ToString('o');prior_root=(Get-Location).Path;only_verified_control_pids_stopped=$terminated.ToArray();required_listeners_remaining=$remaining.Count;database_and_private_files_preserved=$true;prior_record_sha256=(Get-FileHash -LiteralPath deploy-check-record.md -Algorithm SHA256).Hash;stop_type='Owned maintenance stop for round 3; not fault injection; forced control-root termination, no graceful-server-close claim'}
$after|ConvertTo-Json -Depth 6|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\14-prior-stop-result.json' -Encoding utf8
$after|ConvertTo-Json -Depth 6
$global:LASTEXITCODE=0
```

完整输出与报错原文：14-stop-only-prior-idle-local-services.log（`LOCAL_EVIDENCE/14-stop-only-prior-idle-local-services.log`）。对应命令另存 14-stop-only-prior-idle-local-services.command.ps1（`LOCAL_EVIDENCE/14-stop-only-prior-idle-local-services.command.ps1`）。

### 15-align-approved-report-dependency-constraints

开始 2026-10-18T20:56:26.0992355+08:00；结束 2026-10-18T20:56:31.5003681+08:00；耗时 5.399 秒；退出码 0。

结果：用仓库 requirements-report.txt 约束对齐 matplotlib 必需依赖 Pillow==12.3.0；pip check 通过，未安装无关报告软件。

是否需要问人：沿用用户刚批准的 matplotlib 及必要依赖范围。文档依据/补充：只对已批准 matplotlib 及其必需依赖应用 requirements-report.txt 版本约束；不安装 reportlab/ffmpeg，不改测试。

处理：pip 首次选择 Pillow 13.0.0；按仓库声明约束收敛到 12.3.0 后再补跑，全部安装记录保留

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
& .\.venv\Scripts\python.exe -m pip install -c requirements-report.txt matplotlib==3.11.2
if($LASTEXITCODE -ne 0){throw 'Approved dependency constraints alignment failed'}
& .\.venv\Scripts\python.exe -m pip check
if($LASTEXITCODE -ne 0){throw 'Pip check failed after constraints alignment'}
& .\.venv\Scripts\python.exe -c 'import matplotlib,PIL;print("matplotlib="+matplotlib.__version__);print("Pillow="+PIL.__version__)'
```

完整输出与报错原文：15-align-approved-report-dependency-constraints.log（`LOCAL_EVIDENCE/15-align-approved-report-dependency-constraints.log`）。对应命令另存 15-align-approved-report-dependency-constraints.command.ps1（`LOCAL_EVIDENCE/15-align-approved-report-dependency-constraints.command.ps1`）。

### 16-supplement-report-integrity

开始 2026-10-18T20:57:32.6525871+08:00；结束 2026-10-18T20:57:36.9920329+08:00；耗时 4.338 秒；退出码 0。

结果：只补跑此前 matplotlib 导入失败的报告完整性模块，9/9 通过；09 原失败不覆盖。

是否需要问人：否。文档依据/补充：用户已批准补齐 matplotlib；只补跑原先无法导入的模块或被原缺依赖条件跳过的一项；原全组结果不覆盖，不改断言，缓存/编码只影响本次进程。

命令：

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:MPLCONFIGDIR='<R3_PROJECT>\artifacts\acceptance-r3\matplotlib-cache'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_evaluation_report_integrity.py' -v
```

完整输出与报错原文：16-supplement-report-integrity.log（`LOCAL_EVIDENCE/16-supplement-report-integrity.log`）。对应命令另存 16-supplement-report-integrity.command.ps1（`LOCAL_EVIDENCE/16-supplement-report-integrity.command.ps1`）。

### 17-supplement-previously-skipped-figure

开始 2026-10-18T20:57:39.6841206+08:00；结束 2026-10-18T20:57:40.5464717+08:00；耗时 0.861 秒；退出码 0。

结果：只补跑此前因 matplotlib 缺失而跳过的一个图表用例，1/1 通过；不把原始 skip 改记通过。

是否需要问人：否。文档依据/补充：用户已批准补齐 matplotlib；只补跑原先无法导入的模块或被原缺依赖条件跳过的一项；原全组结果不覆盖，不改断言，缓存/编码只影响本次进程。

命令：

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:MPLCONFIGDIR='<R3_PROJECT>\artifacts\acceptance-r3\matplotlib-cache'
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_evaluation_reports.py' -k 'test_full_tool_scope_reaches_report_and_exported_figure' -v
```

完整输出与报错原文：17-supplement-previously-skipped-figure.log（`LOCAL_EVIDENCE/17-supplement-previously-skipped-figure.log`）。对应命令另存 17-supplement-previously-skipped-figure.command.ps1（`LOCAL_EVIDENCE/17-supplement-previously-skipped-figure.command.ps1`）。

### 18-prior-postgres-bounded-immediate-stop

开始 2026-10-18T20:59:29.2038367+08:00；结束 2026-10-18T20:59:29.5194652+08:00；耗时 0.314 秒；退出码 1。

结果：未通过：对核对归属的旧 PG 执行有界 immediate 停机，普通受限通道报 Operation not permitted；未更改 ACL/系统设置。

是否需要问人：否。文档依据/补充：原 native.ps1 fast stop 已失败，源码/官方便携 pg_ctl 停机补救；两份入口未写异常停机处理，标记文档缺失。仅已核对的旧本机数据库。

处理：保留原超时及 PG 日志；请求 immediate 停机，不删除数据，不能宣称正常优雅关闭

命令：

```powershell
$ErrorActionPreference='Stop'
$n=Get-Content -LiteralPath 'deploy/native-runtime.json' -Raw|ConvertFrom-Json
$expectedRoot='<R2_PROJECT>'
if($n.project_root -ne $expectedRoot -or $n.pgdata -ne (Join-Path $expectedRoot 'runtime/pgdata') -or $n.pgport -ne 55432){throw 'Prior database scope differs'}
$old=Get-Content -LiteralPath '<LOCAL_EVIDENCE>\11-prior-owned-processes.json' -Raw|ConvertFrom-Json
$expected=@($old.listeners|Where-Object {$_.port -eq 55432})[0]
$actualPid=[int](Get-Content -LiteralPath (Join-Path $n.pgdata 'postmaster.pid') -TotalCount 1)
if($actualPid -ne $expected.pid){throw 'Prior PostgreSQL PID changed'}
$p=Get-Process -Id $actualPid -ErrorAction Stop
$actualBinary=Join-Path $n.postgres_bin 'postgres.exe'
if($p.Path -ne $actualBinary){throw 'Prior database executable differs'}
if([Math]::Abs((([DateTimeOffset]$p.StartTime)-([DateTimeOffset]$expected.creation_date)).TotalMilliseconds) -gt 1){throw 'Prior database PID reused'}
Copy-Item -LiteralPath 'runtime/postgres.log' -Destination '<LOCAL_EVIDENCE>\18-prior-postgres-before-immediate.log'
Write-Output 'PRIOR_FAST_SHUTDOWN_REQUEST_ACCEPTED_BUT_TIMED_OUT; ORIGINAL LOG PRESERVED'
& (Join-Path $n.postgres_bin 'pg_ctl.exe') stop -D $n.pgdata -m immediate -w -t 15
$code=$LASTEXITCODE
Write-Output ('PG_CTL_IMMEDIATE_EXIT='+$code)
$remaining=@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()|Where-Object {$_.Port -eq 55432})
[pscustomobject]@{at=[DateTimeOffset]::Now.ToString('o');pgdata=$n.pgdata;prior_pid=$actualPid;immediate_exit=$code;remaining_listener_count=$remaining.Count;database_files_deleted=$false;note='Immediate stop requested only after fast stop timed out; preserve all files and failure; next start may require WAL recovery'}|ConvertTo-Json -Depth 5|Tee-Object -FilePath '<LOCAL_EVIDENCE>\18-prior-postgres-stop-result.json'
if($code -ne 0 -or $remaining.Count){throw 'Prior PostgreSQL immediate stop did not free listener'}
$global:LASTEXITCODE=0
```

完整输出与报错原文：18-prior-postgres-bounded-immediate-stop.log（`LOCAL_EVIDENCE/18-prior-postgres-bounded-immediate-stop.log`）。对应命令另存 18-prior-postgres-bounded-immediate-stop.command.ps1（`LOCAL_EVIDENCE/18-prior-postgres-bounded-immediate-stop.command.ps1`）。

### 19-prior-postgres-immediate-full-context

开始 2026-10-18T20:59:54.8590032+08:00；结束 2026-10-18T21:00:00.1005051+08:00；耗时 5.241 秒；退出码 0。

结果：同一有界 PG 停机在获准完整上下文成功；旧 DB 文件保留，下次启动可能需要 WAL 恢复，不称优雅关闭。

是否需要问人：否。文档依据/补充：同一项目/数据目录/PID/创建时间边界；默认受限上下文报 Operation not permitted，使用已有获准完整上下文，不修改任何系统权限设置。

处理：第 18 步默认上下文失败完整保留；本次使用新的 19 前缀证据文件，不覆盖原件

命令：

```powershell
$ErrorActionPreference='Stop'
$n=Get-Content -LiteralPath 'deploy/native-runtime.json' -Raw|ConvertFrom-Json
$expectedRoot='<R2_PROJECT>'
if($n.project_root -ne $expectedRoot -or $n.pgdata -ne (Join-Path $expectedRoot 'runtime/pgdata') -or $n.pgport -ne 55432){throw 'Prior database scope differs'}
$old=Get-Content -LiteralPath '<LOCAL_EVIDENCE>\11-prior-owned-processes.json' -Raw|ConvertFrom-Json
$expected=@($old.listeners|Where-Object {$_.port -eq 55432})[0]
$actualPid=[int](Get-Content -LiteralPath (Join-Path $n.pgdata 'postmaster.pid') -TotalCount 1)
if($actualPid -ne $expected.pid){throw 'Prior PostgreSQL PID changed'}
$p=Get-Process -Id $actualPid -ErrorAction Stop
$actualBinary=Join-Path $n.postgres_bin 'postgres.exe'
if($p.Path -ne $actualBinary){throw 'Prior database executable differs'}
if([Math]::Abs((([DateTimeOffset]$p.StartTime)-([DateTimeOffset]$expected.creation_date)).TotalMilliseconds) -gt 1){throw 'Prior database PID reused'}
Copy-Item -LiteralPath 'runtime/postgres.log' -Destination '<LOCAL_EVIDENCE>\19-prior-postgres-before-immediate.log'
Write-Output 'PRIOR_FAST_SHUTDOWN_REQUEST_ACCEPTED_BUT_TIMED_OUT; ORIGINAL LOG PRESERVED'
& (Join-Path $n.postgres_bin 'pg_ctl.exe') stop -D $n.pgdata -m immediate -w -t 15
$code=$LASTEXITCODE
Write-Output ('PG_CTL_IMMEDIATE_EXIT='+$code)
$remaining=@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()|Where-Object {$_.Port -eq 55432})
[pscustomobject]@{at=[DateTimeOffset]::Now.ToString('o');pgdata=$n.pgdata;prior_pid=$actualPid;immediate_exit=$code;remaining_listener_count=$remaining.Count;database_files_deleted=$false;note='Immediate stop requested only after fast stop timed out; preserve all files and failure; next start may require WAL recovery'}|ConvertTo-Json -Depth 5|Tee-Object -FilePath '<LOCAL_EVIDENCE>\19-prior-postgres-stop-result.json'
if($code -ne 0 -or $remaining.Count){throw 'Prior PostgreSQL immediate stop did not free listener'}
$global:LASTEXITCODE=0
```

完整输出与报错原文：19-prior-postgres-immediate-full-context.log（`LOCAL_EVIDENCE/19-prior-postgres-immediate-full-context.log`）。对应命令另存 19-prior-postgres-immediate-full-context.command.ps1（`LOCAL_EVIDENCE/19-prior-postgres-immediate-full-context.command.ps1`）。

### 20-all-required-ports-free-before-new-start

开始 2026-10-18T21:01:18.0510737+08:00；结束 2026-10-18T21:01:18.5575927+08:00；耗时 0.505 秒；退出码 0。

结果：实际启动前，8081/8082/8088/55432/8766/8093 的 IPv4/IPv6 独占绑定均空闲；前两轮报告哈希保持。

是否需要问人：否。文档依据/补充：用户要求新副本启动前先确认 8081/8082/8088/55432/8766 空闲，另含文档遗漏 8093；IPv4/IPv6 实际独占绑定验证。

命令：

```powershell
$ErrorActionPreference='Stop'
$ports=@(8081,8082,8088,55432,8766,8093)
$results=@()
foreach($port in $ports){foreach($address in @([Net.IPAddress]::Loopback,[Net.IPAddress]::IPv6Loopback)){
 $listener=[Net.Sockets.TcpListener]::new($address,$port)
 $listener.Server.ExclusiveAddressUse=$true
 try{$listener.Start();$results += [pscustomobject]@{address=$address.ToString();port=$port;free=$true}}
 finally{$listener.Stop()}
}}
$check=[ordered]@{checked_at=[DateTimeOffset]::Now.ToString('o');ports=$results;os=[Runtime.InteropServices.RuntimeInformation]::OSDescription;powershell=$PSVersionTable.PSVersion.ToString();docker_available=[bool](Get-Command docker -ErrorAction Ignore);old_r2_report_sha256=(Get-FileHash -LiteralPath '<R2_PROJECT>\deploy-check-record.md' -Algorithm SHA256).Hash;new_root=(Get-Location).Path;model_enabled=$false}
$check|ConvertTo-Json -Depth 6|Tee-Object -FilePath '<LOCAL_EVIDENCE>\20-before-start-port-proof.json'
py -3.12 --version
$global:LASTEXITCODE=0
```

完整输出与报错原文：20-all-required-ports-free-before-new-start.log（`LOCAL_EVIDENCE/20-all-required-ports-free-before-new-start.log`）。对应命令另存 20-all-required-ports-free-before-new-start.command.ps1（`LOCAL_EVIDENCE/20-all-required-ports-free-before-new-start.command.ps1`）。

### 21-fresh-native-database-and-business-start

开始 2026-10-18T21:01:38.5453917+08:00；结束 2026-10-18T21:01:49.2875179+08:00；耗时 10.74 秒；退出码 0。

结果：新 PG/业务底座成功启动；initdb 的受限令牌 87/3 警告原样保留。初始化从启动器拆出以保持 PG 非管理员，属于文档缺失。

是否需要问人：否。文档依据/补充：deploy/README.md native.ps1 start；初始化调用从 local-up.py/ps1 源码拆出以保持 PG 非管理员，属于两份文档缺失的受限环境分段步骤；仅新 R3 资源。

处理：用独立隐藏 pwsh 主进程和文件重定向取证退出码，避免后台输出句柄阻塞记录包装器；不改启动命令或产品判定

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
$busy=@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()|Where-Object {$_.Port -in @(8081,8082,8088,55432,8766,8093)})
if($busy.Count){throw 'Ports changed after preflight'}
& .\.venv\Scripts\python.exe tools/prepare_native_database.py
if($LASTEXITCODE -ne 0){throw 'New native database initialization failed'}
$stdout='<LOCAL_EVIDENCE>\21-native-start.stdout.log'
$stderr='<LOCAL_EVIDENCE>\21-native-start.stderr.log'
$p=Start-Process -FilePath (Join-Path $PSHOME 'pwsh.exe') -ArgumentList @('-NoProfile','-File','<R3_PROJECT>\deploy\native.ps1','start') -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
if(-not $p.WaitForExit(45000)){throw 'Documented native start process exceeded 45 seconds; preserve it and inspect'}
$p.Refresh()
Write-Output ('NATIVE_START_PROCESS_EXIT='+$p.ExitCode)
Get-Content -LiteralPath $stdout
Get-Content -LiteralPath $stderr
if($p.ExitCode -ne 0){throw 'Documented native start failed'}
$ready=(Invoke-WebRequest 'http://127.0.0.1:8088/ready' -TimeoutSec 5).Content
$ready|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\21-native-ready.json' -Encoding utf8
Write-Output $ready
```

完整输出与报错原文：21-fresh-native-database-and-business-start.log（`LOCAL_EVIDENCE/21-fresh-native-database-and-business-start.log`）。对应命令另存 21-fresh-native-database-and-business-start.command.ps1（`LOCAL_EVIDENCE/21-fresh-native-database-and-business-start.command.ps1`）。

### 22-parse-original-test-evidence

开始 2026-10-18T21:02:52.5041347+08:00；结束 2026-10-18T21:02:52.7589615+08:00；耗时 0.253 秒；退出码 0。

结果：只解析原日志，区分方法数与子测试失败数；新功能子集来自同一次原始运行，不重复相加。

是否需要问人：否。文档依据/补充：只解析原日志统计方法级/子测试级结果并保存完整错误摘录；新增功能子集来自同一次全组运行，不重复运行或相加。

命令：

```powershell
.\.venv\Scripts\python.exe '<LOCAL_EVIDENCE>\summarize_tests_r3.py'
```

完整输出与报错原文：22-parse-original-test-evidence.log（`LOCAL_EVIDENCE/22-parse-original-test-evidence.log`）。对应命令另存 22-parse-original-test-evidence.command.ps1（`LOCAL_EVIDENCE/22-parse-original-test-evidence.command.ps1`）。

### 23-documented-local-up-with-ready-check

开始 2026-10-18T21:03:51.2299931+08:00；结束 2026-10-18T21:04:10.1039919+08:00；耗时 18.872 秒；退出码 0。

结果：在获准完整上下文执行文档 local-up -Install，主进程退出 0；复用本轮已启动的非管理员 PG，五个本地参与者 ready。

是否需要问人：否。文档依据/补充：COLLABORATION.md/deploy/README.md 原始 local-up -Install；PG 已按普通路径启动，本步骤只复用新 R3 PG，完整上下文解决已知 WMI/子进程限制，记录为环境补充。

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
$stdout='<LOCAL_EVIDENCE>\23-local-up.stdout.log'
$stderr='<LOCAL_EVIDENCE>\23-local-up.stderr.log'
$p=Start-Process -FilePath (Join-Path $PSHOME 'pwsh.exe') -ArgumentList @('-NoProfile','-File','<R3_PROJECT>\deploy\local-up.ps1','-Install') -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
if(-not $p.WaitForExit(55000)){throw 'Documented local-up main process exceeded 55 seconds; preserve logs and inspect'}
$p.Refresh()
Write-Output ('LOCAL_UP_MAIN_PROCESS_EXIT='+$p.ExitCode)
Get-Content -LiteralPath $stdout
Get-Content -LiteralPath $stderr
if($p.ExitCode -ne 0){throw 'Documented local-up failed'}
$raw=(Invoke-WebRequest 'http://127.0.0.1:8766/api/state' -TimeoutSec 5).Content
$raw|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\23-workbench-state.json' -Encoding utf8
$s=$raw|ConvertFrom-Json
$sha=(Get-FileHash -LiteralPath runtime/local-coordinator.json -Algorithm SHA256).Hash.ToLowerInvariant()
[pscustomobject]@{mode=$s.mode;connected=$s.connected;config_sha256=$s.config_sha256;expected_sha256=$sha;participant_count=@($s.participants).Count;model_enabled=$s.model_config.enabled;coordinator_resource_credential_count=$s.resource_credential_count;pid=$s.pid}|ConvertTo-Json
if($s.mode -ne 'local-aip-stdio' -or -not $s.connected -or $s.config_sha256 -ne $sha -or @($s.participants).Count -ne 5 -or $s.model_config.enabled){throw 'New workbench does not meet local-only readiness'}
```

完整输出与报错原文：23-documented-local-up-with-ready-check.log（`LOCAL_EVIDENCE/23-documented-local-up-with-ready-check.log`）。对应命令另存 23-documented-local-up-with-ready-check.command.ps1（`LOCAL_EVIDENCE/23-documented-local-up-with-ready-check.command.ps1`）。

### 24-original-user-cli-h00

开始 2026-10-18T21:05:45.5301766+08:00；结束 2026-10-18T21:06:16.1226602+08:00；耗时 30.59 秒；退出码 0。

结果：原始 A 标准通过：30 秒、30 次请求全成功、10 个完整流程，失败/未知/未决均 0。

是否需要问人：否。文档依据/补充：用户原 A 档 business/load.py 30 秒、30 请求、10 完整订单流程；新 R3 资源和原始结果不混用旧轮数据。

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
$n=Get-Content -LiteralPath deploy/native-runtime.json -Raw|ConvertFrom-Json
if($n.project_root -ne (Get-Location).Path -or $n.order_port -ne 8088){throw 'New native scope differs'}
(Invoke-WebRequest 'http://127.0.0.1:8088/ready').Content|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\24-ready-before.json' -Encoding utf8
.\.venv\Scripts\python.exe business/load.py --duration 30 --output eval/results/local/deploy-check-r3-20261018-h00.json
$code=$LASTEXITCODE
Copy-Item -LiteralPath eval/results/local/deploy-check-r3-20261018-h00.json -Destination '<LOCAL_EVIDENCE>\24-cli-h00.json'
(Invoke-WebRequest 'http://127.0.0.1:8088/ready').Content|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\24-ready-after.json' -Encoding utf8
$j=Get-Content -LiteralPath '<LOCAL_EVIDENCE>\24-cli-h00.json' -Raw|ConvertFrom-Json
$j|Select-Object run_id,duration_seconds,requests,success,failed,unknown,completed_workflows,unresolved_intents,passed|ConvertTo-Json
if($code -ne 0 -or -not $j.passed -or $j.duration_seconds -lt 30 -or $j.requests -ne 30 -or $j.success -ne 30 -or $j.completed_workflows -ne 10 -or $j.failed -ne 0 -or $j.unknown -ne 0 -or $j.unresolved_intents -ne 0){throw 'Original user A-tier criteria did not pass'}
```

完整输出与报错原文：24-original-user-cli-h00.log（`LOCAL_EVIDENCE/24-original-user-cli-h00.log`）。对应命令另存 24-original-user-cli-h00.command.ps1（`LOCAL_EVIDENCE/24-original-user-cli-h00.command.ps1`）。

### 25-new-documented-strict-verifier

开始 2026-10-18T21:06:58.9711946+08:00；结束 2026-10-18T21:06:59.4614886+08:00；耗时 0.488 秒；退出码 1。

结果：未通过：新版 verify.py 在受限通道无法写 mode=0700 结果目录，尚未执行业务窗口；原错误和空目录保留。

是否需要问人：否。文档依据/补充：新版 deploy/README.md 本机验收原命令：deploy/verify.py --url；每响应 v2、前后 ready、30秒/30请求/10流程，输出新目录保留原失败。

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe deploy/verify.py --url http://127.0.0.1:8088 --output artifacts/acceptance-r3/h00-verifier
$code=$LASTEXITCODE
New-Item -ItemType Directory -Path '<LOCAL_EVIDENCE>\25-native-verifier' | Out-Null
Get-ChildItem -LiteralPath artifacts/acceptance-r3/h00-verifier -File|ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination '<LOCAL_EVIDENCE>\25-native-verifier'}
$j=Get-Content -LiteralPath artifacts/acceptance-r3/h00-verifier/result.json -Raw|ConvertFrom-Json
$j|Select-Object status,order_url,expected_api_version,started_at,completed_at,business,scope|ConvertTo-Json -Depth 6
if($code -ne 0 -or $j.status -ne 'passed'){throw 'New documented strict verifier failed'}
$global:LASTEXITCODE=0
```

完整输出与报错原文：25-new-documented-strict-verifier.log（`LOCAL_EVIDENCE/25-new-documented-strict-verifier.log`）。对应命令另存 25-new-documented-strict-verifier.command.ps1（`LOCAL_EVIDENCE/25-new-documented-strict-verifier.command.ps1`）。

### 27-new-strict-verifier-approved-context

开始 2026-10-18T21:07:57.1200841+08:00；结束 2026-10-18T21:08:27.9897201+08:00；耗时 30.868 秒；退出码 0。

结果：相同 verify.py 命令及判定在获准完整上下文、新目录完整执行通过：30.016 秒、30/30、10 流程，逐响应 v2。

是否需要问人：否。文档依据/补充：同一 deploy/README.md verify.py 原命令和相同业务判定；原 25 步 PermissionError 与空目录保持；新输出目录完整执行上下文不改 ACL/系统设置。

处理：受限通道无法写 mode=0700 新目录；不改权限、不覆盖原失败，使用获准完整上下文重跑并独立保存

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
$failed=@(Get-ChildItem -LiteralPath artifacts/acceptance-r3/h00-verifier -Force)
Write-Output ('ORIGINAL_RESTRICTED_OUTPUT_FILE_COUNT='+$failed.Count)
$failed|Select-Object Name,Length
.\.venv\Scripts\python.exe deploy/verify.py --url http://127.0.0.1:8088 --output artifacts/acceptance-r3/h00-verifier-approved-context
$code=$LASTEXITCODE
New-Item -ItemType Directory -Path '<LOCAL_EVIDENCE>\27-native-verifier' | Out-Null
Get-ChildItem -LiteralPath artifacts/acceptance-r3/h00-verifier-approved-context -File|ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination '<LOCAL_EVIDENCE>\27-native-verifier'}
$j=Get-Content -LiteralPath artifacts/acceptance-r3/h00-verifier-approved-context/result.json -Raw|ConvertFrom-Json
$j|Select-Object status,order_url,expected_api_version,started_at,completed_at,business,scope|ConvertTo-Json -Depth 6
if($code -ne 0 -or $j.status -ne 'passed'){throw 'New documented strict verifier failed in approved context'}
$global:LASTEXITCODE=0
```

完整输出与报错原文：27-new-strict-verifier-approved-context.log（`LOCAL_EVIDENCE/27-new-strict-verifier-approved-context.log`）。对应命令另存 27-new-strict-verifier-approved-context.command.ps1（`LOCAL_EVIDENCE/27-new-strict-verifier-approved-context.command.ps1`）。

### 29-version-dependency-and-source-freeze

开始 2026-10-18T21:09:00.0366636+08:00；结束 2026-10-18T21:09:01.6979446+08:00；耗时 1.659 秒；退出码 0。

结果：保存依赖冻结与 Python/源码信息；tracked 和 staged diff 均为空。

是否需要问人：否。文档依据/补充：交付所需版本、依赖、源码未修改及用户账号/两文件澄清取证；仅本机测试，不生成平台身份资料。

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
& .\.venv\Scripts\python.exe -m pip freeze|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\29-main-pip-freeze.txt' -Encoding utf8
if($LASTEXITCODE -ne 0){throw 'Main freeze failed'}
& .\.venv-mcp-postgres\Scripts\python.exe -m pip freeze|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\29-mcp-pip-freeze.txt' -Encoding utf8
if($LASTEXITCODE -ne 0){throw 'MCP freeze failed'}
& .\.venv\Scripts\python.exe -c 'import sys,site,platform,json;print(json.dumps({"version":sys.version,"executable":sys.executable,"user_site":site.ENABLE_USER_SITE,"platform":platform.platform()}))'
git rev-parse HEAD
git diff --exit-code
if($LASTEXITCODE -ne 0){throw 'Tracked source changed during acceptance'}
git diff --cached --exit-code
if($LASTEXITCODE -ne 0){throw 'Staged files found'}
git status --short --untracked-files=normal
Write-Output 'PREVIOUS_TWO_JSON_FILES_ARE_NOT_LOCAL_DEPLOYMENT_PREREQUISITES; TEST_FILE_READ_FAILURES_REMAIN_UNCHANGED'
$global:LASTEXITCODE=0
```

完整输出与报错原文：29-version-dependency-and-source-freeze.log（`LOCAL_EVIDENCE/29-version-dependency-and-source-freeze.log`）。对应命令另存 29-version-dependency-and-source-freeze.command.ps1（`LOCAL_EVIDENCE/29-version-dependency-and-source-freeze.command.ps1`）。

### 30-local-only-pre-injection-preflight

开始 2026-10-18T21:12:10.0877866+08:00；结束 2026-10-18T21:12:11.8679228+08:00；耗时 1.778 秒；退出码 0。

结果：只读确认本轮资源路径、六端口进程归属、loopback、local AIP stdio、模型关闭、协调器资源凭据数 0，并保存注入前路由原件。

是否需要问人：否。文档依据/补充：第三轮注入前只读安全范围核对；不注入，等待用户对本轮的独立确认。

命令：

```powershell
$ErrorActionPreference='Stop'
$root=(Get-Location).Path
$n=Get-Content -LiteralPath deploy/native-runtime.json -Raw|ConvertFrom-Json
$c=Get-Content -LiteralPath runtime/local-coordinator.json -Raw|ConvertFrom-Json
$raw=(Invoke-WebRequest 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5).Content
$s=$raw|ConvertFrom-Json
if($s.mode -ne 'local-aip-stdio' -or -not $s.connected -or $s.connection_error -or $s.resource_credential_count -ne 0 -or $s.model_config.enabled -or $c.mode -ne 'local-aip-stdio' -or $c.llm_enabled -ne $false){throw 'Local-only boundary failed'}
if($s.incident -or @($s.incidents).Count -gt 0){throw 'Unexpected incident before injection'}
$sha=(Get-FileHash -LiteralPath runtime/local-coordinator.json -Algorithm SHA256).Hash.ToLowerInvariant()
if($s.config_sha256 -ne $sha -or @($s.participants).Count -ne 5){throw 'Config or participants changed'}
foreach($path in @($n.project_root,$n.postgres_bin,$n.pgdata,$n.nginx_prefix,$n.nginx_bin,$n.app_python)){
 $full=[IO.Path]::GetFullPath($path)
 if($full -ne $root -and -not $full.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Native path escapes R3'}
}
if($n.pgport -ne 55432 -or $n.order_port -ne 8088 -or $n.app_v1_port -ne 8081 -or $n.app_v2_port -ne 8082){throw 'Resource ports changed'}
foreach($w in $c.workers){if($w.aic -notlike 'local-*'){throw 'Unexpected formal identity'}}
$connections=@(Get-NetTCPConnection -State Listen -ErrorAction Stop|Where-Object {$_.LocalPort -in @(8081,8082,8088,55432,8766,8093)})
$proof=@()
foreach($x in $connections){
 if($x.LocalAddress -notin @('127.0.0.1','::1')){throw 'Non-loopback listener'}
 $p=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$x.OwningProcess) -ErrorAction Stop
 if(-not ($p.ExecutablePath.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase) -or $p.CommandLine.Contains($root))){throw 'Listener owner is not R3'}
 $proof += [pscustomobject]@{address=$x.LocalAddress;port=$x.LocalPort;pid=$x.OwningProcess;name=$p.Name;executable=$p.ExecutablePath;creation=$p.CreationDate}
}
if(@($connections.LocalPort|Sort-Object -Unique).Count -ne 6){throw 'Expected service port absent'}
$ready=Invoke-RestMethod 'http://127.0.0.1:8088/ready' -NoProxy -TimeoutSec 5
if(-not $ready.ok -or $ready.api_version -ne 'v2'){throw 'Initial public readiness is not healthy v2'}
Copy-Item -LiteralPath runtime/nginx/conf/route.conf -Destination '<LOCAL_EVIDENCE>\30-route-before.conf'
$raw|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\30-workbench-state-before.json' -Encoding utf8
$result=[ordered]@{checked_at=[DateTimeOffset]::Now.ToString('o');revision='8a820e419cea55f14d4de0edec76c0e1bcf87904';project_root=$root;mode=$s.mode;connected=$s.connected;config_sha256=$sha;credential_count=$s.resource_credential_count;model_enabled=$s.model_config.enabled;participants=$s.participants;ready=$ready;resources=@{pgdata=$n.pgdata;nginx_prefix=$n.nginx_prefix;ports=@(8081,8082,8088,55432,8766,8093)};listeners=$proof;route_before_sha256=(Get-FileHash -LiteralPath runtime/nginx/conf/route.conf -Algorithm SHA256).Hash;incidents=0;formal_platform_started=$false;fault_injected=$false}
$result|ConvertTo-Json -Depth 12|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\30-local-scope-preflight.json' -Encoding utf8
$result|Select-Object checked_at,mode,connected,credential_count,model_enabled,route_before_sha256,listeners|ConvertTo-Json -Depth 5
$global:LASTEXITCODE=0
```

完整输出与报错原文：30-local-only-pre-injection-preflight.log（`LOCAL_EVIDENCE/30-local-only-pre-injection-preflight.log`）。对应命令另存 30-local-only-pre-injection-preflight.command.ps1（`LOCAL_EVIDENCE/30-local-only-pre-injection-preflight.command.ps1`）。

### 31-authorized-local-f10-apply

开始 2026-10-18T21:14:28.7050793+08:00；结束 2026-10-18T21:14:30.5507386+08:00；耗时 1.844 秒；退出码 0。

结果：获本轮明确同意后，执行原始 F10 apply；本机只读及 v1 路由真实注入，公共 ready=v1。

是否需要问人：已明确同意第三轮本机 F10；恢复审批按钮由用户本人点击。文档依据/补充：deploy/README.md F10=F02+F07；用户刚明确同意第三轮本机范围，人工点击恢复审批。

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
$pre=Get-Content -LiteralPath '<LOCAL_EVIDENCE>\30-local-scope-preflight.json' -Raw|ConvertFrom-Json
$n=Get-Content -LiteralPath deploy/native-runtime.json -Raw|ConvertFrom-Json
$s=Invoke-RestMethod 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5
$sha=(Get-FileHash -LiteralPath runtime/local-coordinator.json -Algorithm SHA256).Hash.ToLowerInvariant()
if($pre.project_root -ne (Get-Location).Path -or $n.project_root -ne $pre.project_root -or $n.pgport -ne 55432 -or $n.order_port -ne 8088 -or $s.mode -ne 'local-aip-stdio' -or -not $s.connected -or $s.resource_credential_count -ne 0 -or $s.config_sha256 -ne $sha -or $sha -ne $pre.config_sha256 -or $s.model_config.enabled -or $s.incident -or @($s.incidents).Count){throw 'Authorized R3 local scope changed before injection'}
if((Get-FileHash -LiteralPath runtime/nginx/conf/route.conf -Algorithm SHA256).Hash -ne $pre.route_before_sha256){throw 'Initial route changed'}
$a=[ordered]@{recorded_at=[DateTimeOffset]::Now.ToString('o');user_decision='同意第三轮本机 F10，审批我来点';project_root=(Get-Location).Path;revision='8a820e419cea55f14d4de0edec76c0e1bcf87904';scope='Only R3 native PostgreSQL 55432 and Nginx 8088; human UI approval';formal_platform=$false;state='authorized_before_injection';restore_command='.\.venv\Scripts\python.exe eval/inject.py F10 restore --backend native'}
$a|ConvertTo-Json -Depth 6|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\31-f10-authorization.json' -Encoding utf8
try {
 & .\.venv\Scripts\python.exe eval/inject.py F10 apply --backend native
 if($LASTEXITCODE -ne 0){throw 'Documented F10 apply failed'}
 $fault=Invoke-RestMethod 'http://127.0.0.1:8088/ready' -NoProxy -TimeoutSec 5
 $fault|ConvertTo-Json -Depth 6|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\31-fault-public-ready.json' -Encoding utf8
 $fault|ConvertTo-Json -Compress
 if($fault.api_version -ne 'v1'){throw 'Expected local v1 fault routing not observed'}
} catch {
 Write-Output 'APPLY_OR_PROOF_FAILED_ATTEMPTING_REQUIRED_LOCAL_RESTORE'
 & .\.venv\Scripts\python.exe eval/inject.py F10 restore --backend native
 Write-Output ('RESTORE_AFTER_APPLY_ERROR_EXIT='+$LASTEXITCODE)
 throw
}
$global:LASTEXITCODE=0
```

完整输出与报错原文：31-authorized-local-f10-apply.log（`LOCAL_EVIDENCE/31-authorized-local-f10-apply.log`）。对应命令另存 31-authorized-local-f10-apply.command.ps1（`LOCAL_EVIDENCE/31-authorized-local-f10-apply.command.ps1`）。

### 32-ui-start-and-wait-human-approval

开始 2026-10-18T21:14:53.6102699+08:00；结束 2026-10-18T21:14:53.7970613+08:00；耗时 0.185 秒；退出码 0。

结果：AI 通过 UI 输入普通业务症状并开始排查；只读等待 db.restore_writes 人工审批，AI 未点批准，也未 POST 审批。

是否需要问人：等待用户本人点击 db.restore_writes 审批。文档依据/补充：AI 通过本机 UI 输入一般业务症状并点击开始；只 GET 等待 high 审批，未读注入原因、未点击或 POST 审批。

命令：

```powershell
$ErrorActionPreference='Stop'
$deadline=[DateTimeOffset]::Now.AddSeconds(25)
do {
 $raw=(Invoke-WebRequest 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5).Content
 $s=$raw|ConvertFrom-Json
 $pending=@($s.incident.approvals|Where-Object {$_.status -eq 'pending'})
 if($pending.Count -or $s.incident.status -in @('completed','needs_attention','failed')){break}
 Start-Sleep -Seconds 2
}while([DateTimeOffset]::Now -lt $deadline)
$raw|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\32-f10-before-human-approval.json' -Encoding utf8
[pscustomobject]@{incident_id=$s.incident.id;status=$s.incident.status;mode=$s.mode;approvals=$s.incident.approvals;ui_symptom='订单提交异常，请查明原因并恢复业务。';ui_started_at_observed='2026-10-18T21:14:38+08:00';ai_clicked_approval=$false}|ConvertTo-Json -Depth 6
if($s.incident.id -ne 'inc-a13cfd6dbf0b49d2' -or $s.mode -ne 'local-aip-stdio' -or $pending.Count -ne 1){throw 'Expected single local human approval not observed; preserve state'}
$global:LASTEXITCODE=0
```

完整输出与报错原文：32-ui-start-and-wait-human-approval.log（`LOCAL_EVIDENCE/32-ui-start-and-wait-human-approval.log`）。对应命令另存 32-ui-start-and-wait-human-approval.command.ps1（`LOCAL_EVIDENCE/32-ui-start-and-wait-human-approval.command.ps1`）。

### 34-f10-human-approved-recovery-observation

开始 2026-10-18T21:15:53.9181799+08:00；结束 2026-10-18T21:15:58.1810520+08:00；耗时 4.261 秒；退出码 0。

结果：用户亲自批准后，产品 completed；实际恢复并完成 30 秒/30 请求/10 流程全成功。规则诊断，模型调用 0。

是否需要问人：用户回复已点击批准，并由 API approved/decided_at 交叉取证。文档依据/补充：用户本人已点击批准；只读保存原始产品 completed / recovery / order_observation 证据，不修改测试、判定或审批。

命令：

```powershell
$ErrorActionPreference='Stop'
$deadline=[DateTimeOffset]::Now.AddSeconds(50)
do {
 $raw=(Invoke-WebRequest 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5).Content
 $s=$raw|ConvertFrom-Json
 if($s.incident.id -ne 'inc-a13cfd6dbf0b49d2' -or $s.mode -ne 'local-aip-stdio'){throw 'Incident identity or local mode changed'}
 if($s.incident.status -in @('completed','failed','needs_attention')){break}
 Start-Sleep -Seconds 2
}while([DateTimeOffset]::Now -lt $deadline)
$raw|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\34-f10-workbench-after-human-approval.json' -Encoding utf8
$o=$s.incident.result.order_observation
$approval=@($s.incident.approvals|Where-Object {$_.id -eq 'approval-992860c49687'})[0]
$summary=[ordered]@{collected_at=[DateTimeOffset]::Now.ToString('o');incident_id=$s.incident.id;status_original=$s.incident.status;business_recovered=$s.incident.result.business_recovered;service_recovered=$s.incident.result.service_recovered;manual_required=$s.incident.result.manual_required;approval_status=$approval.status;approval_requested_at=$approval.requested_at;approval_decided_at=$approval.decided_at;duration_seconds=$o.duration_seconds;requests=$o.requests;success=$o.success;failed=$o.failed;unknown=$o.unknown;completed_workflows=$o.completed_workflows;unresolved_intents=$o.unresolved_intents;passed=$o.passed;model_source=$s.incident.model_source;tokens=$s.incident.tokens;user_reported_click='已点击批准';ai_clicked_approval=$false}
$summary|ConvertTo-Json -Depth 8|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\34-f10-result-summary.json' -Encoding utf8
$summary|ConvertTo-Json -Depth 8
if($s.incident.status -ne 'completed' -or -not $s.incident.result.business_recovered -or -not $s.incident.result.service_recovered -or $s.incident.result.manual_required -or $approval.status -ne 'approved' -or -not $o.passed -or $o.duration_seconds -lt 30 -or $o.requests -ne 30 -or $o.success -ne 30 -or $o.failed -ne 0 -or $o.unknown -ne 0 -or $o.completed_workflows -ne 10 -or $o.unresolved_intents -ne 0){throw 'Actual workbench F10 evidence does not yet satisfy original C criteria; preserve and restore'}
$global:LASTEXITCODE=0
```

完整输出与报错原文：34-f10-human-approved-recovery-observation.log（`LOCAL_EVIDENCE/34-f10-human-approved-recovery-observation.log`）。对应命令另存 34-f10-human-approved-recovery-observation.command.ps1（`LOCAL_EVIDENCE/34-f10-human-approved-recovery-observation.command.ps1`）。

### 35-documented-f10-restore

开始 2026-10-18T21:16:45.2634204+08:00；结束 2026-10-18T21:16:47.0322884+08:00；耗时 1.767 秒；退出码 0。

结果：文档 F10 restore 成功，公共 v2，路由 SHA 与注入前完全相同；未手工覆盖字节来通过。

是否需要问人：否。文档依据/补充：deploy/README.md F10 原始 restore；保存实际输出并核对与注入前 route.conf 字节 SHA256 相同。

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
$n=Get-Content -LiteralPath deploy/native-runtime.json -Raw|ConvertFrom-Json
$s=Invoke-RestMethod 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5
$pre=Get-Content -LiteralPath '<LOCAL_EVIDENCE>\30-local-scope-preflight.json' -Raw|ConvertFrom-Json
if((Get-Location).Path -ne $pre.project_root -or $n.project_root -ne $pre.project_root -or $n.pgport -ne 55432 -or $n.order_port -ne 8088 -or $s.mode -ne 'local-aip-stdio' -or $s.incident.id -ne 'inc-a13cfd6dbf0b49d2' -or $s.incident.status -ne 'completed' -or @($s.incident.approvals|Where-Object {$_.status -eq 'pending'}).Count){throw 'Restoration scope or terminal state changed'}
& .\.venv\Scripts\python.exe eval/inject.py F10 restore --backend native
if($LASTEXITCODE -ne 0){throw 'Original F10 restore failed'}
$ready=Invoke-RestMethod 'http://127.0.0.1:8088/ready' -NoProxy -TimeoutSec 5
Copy-Item -LiteralPath runtime/nginx/conf/route.conf -Destination '<LOCAL_EVIDENCE>\35-route-after-restore.conf'
$after=(Get-FileHash -LiteralPath runtime/nginx/conf/route.conf -Algorithm SHA256).Hash
$proof=[pscustomobject]@{at=[DateTimeOffset]::Now.ToString('o');project_root=(Get-Location).Path;ready=$ready;route_before_sha256=$pre.route_before_sha256;route_after_sha256=$after;identical=($after -eq $pre.route_before_sha256);restore_exit=0}
$proof|ConvertTo-Json -Depth 6|Tee-Object -FilePath '<LOCAL_EVIDENCE>\35-restoration-proof.json'
if(-not $ready.ok -or $ready.api_version -ne 'v2' -or -not $proof.identical){throw 'Restoration readiness or exact route bytes failed'}
$global:LASTEXITCODE=0
```

完整输出与报错原文：35-documented-f10-restore.log（`LOCAL_EVIDENCE/35-documented-f10-restore.log`）。对应命令另存 35-documented-f10-restore.command.ps1（`LOCAL_EVIDENCE/35-documented-f10-restore.command.ps1`）。

### 36-post-restore-documented-h00

开始 2026-10-18T21:16:56.3510458+08:00；结束 2026-10-18T21:17:26.8263289+08:00；耗时 30.473 秒；退出码 0。

结果：复原后文档 business/load.py 再次 30 秒、30/30 请求、10 完整流程通过。

是否需要问人：否。文档依据/补充：deploy/README.md 每个故障复原后 business/load.py 30 秒；用户原定 30 请求、10 流程标准保持。

命令：

```powershell
$ErrorActionPreference='Stop'
$env:PYTHONIOENCODING='utf-8'
(Invoke-WebRequest 'http://127.0.0.1:8088/ready' -NoProxy -TimeoutSec 5).Content|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\36-ready-before.json' -Encoding utf8
& .\.venv\Scripts\python.exe business/load.py --duration 30 --output eval/results/local/deploy-check-r3-20261018-post-restore-h00.json
$code=$LASTEXITCODE
Copy-Item -LiteralPath eval/results/local/deploy-check-r3-20261018-post-restore-h00.json -Destination '<LOCAL_EVIDENCE>\36-post-restore-h00.json'
(Invoke-WebRequest 'http://127.0.0.1:8088/ready' -NoProxy -TimeoutSec 5).Content|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\36-ready-after.json' -Encoding utf8
$j=Get-Content -LiteralPath '<LOCAL_EVIDENCE>\36-post-restore-h00.json' -Raw|ConvertFrom-Json
$j|Select-Object run_id,duration_seconds,requests,success,failed,unknown,completed_workflows,unresolved_intents,passed|ConvertTo-Json
if($code -ne 0 -or -not $j.passed -or $j.duration_seconds -lt 30 -or $j.requests -ne 30 -or $j.success -ne 30 -or $j.completed_workflows -ne 10 -or $j.failed -ne 0 -or $j.unknown -ne 0 -or $j.unresolved_intents -ne 0){throw 'Original post-restore H00 criteria failed'}
$global:LASTEXITCODE=0
```

完整输出与报错原文：36-post-restore-documented-h00.log（`LOCAL_EVIDENCE/36-post-restore-documented-h00.log`）。对应命令另存 36-post-restore-documented-h00.command.ps1（`LOCAL_EVIDENCE/36-post-restore-documented-h00.command.ps1`）。

### 37-final-services-and-source-evidence

开始 2026-10-18T21:19:59.4833996+08:00；结束 2026-10-18T21:20:00.8645274+08:00；耗时 1.379 秒；退出码 0。

结果：最终六端口仅监听回环且归属 R3；事故已结束，无 pending 审批；前两轮原报告哈希保持，产品源码未改。

是否需要问人：否。文档依据/补充：交付：只读记录本轮运行服务、回环/进程归属、原报告哈希与产品源码未修改；不停止服务。

命令：

```powershell
$ErrorActionPreference='Stop'
$root=(Get-Location).Path
$pre=Get-Content -LiteralPath '<LOCAL_EVIDENCE>\30-local-scope-preflight.json' -Raw|ConvertFrom-Json
$s=Invoke-RestMethod 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5
if($root -ne $pre.project_root -or $s.mode -ne 'local-aip-stdio' -or -not $s.connected -or $s.resource_credential_count -ne 0 -or $s.model_config.enabled -or $s.incident.id -ne 'inc-a13cfd6dbf0b49d2' -or $s.incident.status -ne 'completed' -or @($s.incident.approvals|Where-Object {$_.status -eq 'pending'}).Count){throw 'Final local state differs'}
$all=@(Get-CimInstance Win32_Process -ErrorAction Stop)
$connections=@(Get-NetTCPConnection -State Listen|Where-Object {$_.LocalPort -in @(8081,8082,8088,55432,8766,8093)})
$proof=@()
foreach($x in $connections){
 $p=@($all|Where-Object {$_.ProcessId -eq $x.OwningProcess})[0]
 if($x.LocalAddress -notin @('127.0.0.1','::1') -or -not ($p.ExecutablePath.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase) -or $p.CommandLine.Contains($root))){throw 'Final port owner or bind differs'}
 $proof += [pscustomobject]@{port=$x.LocalPort;address=$x.LocalAddress;pid=$x.OwningProcess;name=$p.Name;executable=$p.ExecutablePath;creation=$p.CreationDate}
}
if(@($proof.port|Sort-Object -Unique).Count -ne 6){throw 'Expected final port absent'}
$r1=(Get-FileHash -LiteralPath '<R1_PROJECT>\deploy-check-record.md' -Algorithm SHA256).Hash
$r2=(Get-FileHash -LiteralPath '<R2_PROJECT>\deploy-check-record.md' -Algorithm SHA256).Hash
if($r1 -ne 'B712840AD26FF50B5711621321663480C5318C65F2FA70AAE61FF3B7B4C9499D' -or $r2 -ne '6959448B696C948ACF02F838BED7CD7065D51BEB037FB0B545A2B06F5053032C'){throw 'Prior original report changed'}
git rev-parse HEAD
git branch --show-current
git diff --exit-code
if($LASTEXITCODE -ne 0){throw 'Tracked source changed'}
git diff --cached --exit-code
if($LASTEXITCODE -ne 0){throw 'Unexpected staged content'}
$blob=(git hash-object deploy-check-record.md)
$expected=(git rev-parse HEAD:deploy-check-record.md)
if($blob -ne $expected){throw 'Merged R2 record changed'}
git status --short --untracked-files=normal
$ready=Invoke-RestMethod 'http://127.0.0.1:8088/ready' -NoProxy -TimeoutSec 5
$owned=@($all|Where-Object {$_.CommandLine -and $_.CommandLine.Contains($root)}|Select-Object @{n='pid';e={$_.ProcessId}},@{n='parent_pid';e={$_.ParentProcessId}},Name,CreationDate,ExecutablePath)
$result=[pscustomobject]@{checked_at=[DateTimeOffset]::Now.ToString('o');project_root=$root;mode=$s.mode;connected=$s.connected;config_sha256=$s.config_sha256;model_enabled=$s.model_config.enabled;resource_credential_count=$s.resource_credential_count;incident_id=$s.incident.id;incident_status=$s.incident.status;ready=$ready;listeners=$proof;owned_processes=$owned;round1_original_report_sha256=$r1;round2_original_report_sha256=$r2;merged_round2_report_blob_unchanged=($blob -eq $expected);formal_platform_started=$false;services_stopped=$false}
$result|ConvertTo-Json -Depth 8|Set-Content -LiteralPath '<LOCAL_EVIDENCE>\37-final-owned-services.json' -Encoding utf8
$result|Select-Object checked_at,mode,connected,incident_status,ready,listeners,round1_original_report_sha256,round2_original_report_sha256,merged_round2_report_blob_unchanged|ConvertTo-Json -Depth 5
$global:LASTEXITCODE=0
```

完整输出与报错原文：37-final-services-and-source-evidence.log（`LOCAL_EVIDENCE/37-final-services-and-source-evidence.log`）。对应命令另存 37-final-services-and-source-evidence.command.ps1（`LOCAL_EVIDENCE/37-final-services-and-source-evidence.command.ps1`）。

## 原失败的脱敏派生及警告

本共享副本的 traceback 由本机原文仅替换个人路径，保留失败内容和原乱码；逐字原件与完整输出仍留本机，哈希见文件末尾。

### 09-tests-root-original
```text
======================================================================
ERROR: test_describe_inventory_and_acs_official_schema (test_bridge_gateway.BridgePolicyTests.test_describe_inventory_and_acs_official_schema)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<PYTHON312>\Lib\asyncio\runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\asyncio\base_events.py", line 691, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "<R3_PROJECT>\tests\test_bridge_gateway.py", line 303, in test_describe_inventory_and_acs_official_schema
    base = json.loads((ROOT / "integration/incident/database.submission.acs.json").read_text(encoding="utf-8"))
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '<R3_PROJECT>\\integration\\incident\\database.submission.acs.json'

======================================================================
ERROR: test_evaluation_report_integrity (unittest.loader._FailedTest.test_evaluation_report_integrity)
----------------------------------------------------------------------
ImportError: Failed to import test module: test_evaluation_report_integrity
Traceback (most recent call last):
  File "<PYTHON312>\Lib\unittest\loader.py", line 396, in _find_test_path
    module = self._get_module_from_name(name)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\unittest\loader.py", line 339, in _get_module_from_name
    __import__(name)
  File "<R3_PROJECT>\tests\test_evaluation_report_integrity.py", line 12, in <module>
    from eval.plot_results import plot
  File "<R3_PROJECT>\eval\plot_results.py", line 14, in <module>
    import matplotlib
ModuleNotFoundError: No module named 'matplotlib'


======================================================================
ERROR: test_approved_public_metadata_passes_official_schema (test_onboarding.OnboardingTests.test_approved_public_metadata_passes_official_schema)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<R3_PROJECT>\tests\test_onboarding.py", line 14, in setUp
    self.document = json.loads((ROOT / "integration/incident/application.approved.acs.json").read_text(encoding="utf-8"))
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '<R3_PROJECT>\\integration\\incident\\application.approved.acs.json'

======================================================================
ERROR: test_missing_identity_is_not_a_runtime_reachability_claim (test_onboarding.OnboardingTests.test_missing_identity_is_not_a_runtime_reachability_claim)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<R3_PROJECT>\tests\test_onboarding.py", line 14, in setUp
    self.document = json.loads((ROOT / "integration/incident/application.approved.acs.json").read_text(encoding="utf-8"))
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '<R3_PROJECT>\\integration\\incident\\application.approved.acs.json'

======================================================================
ERROR: test_unauthorized_and_active_probe_requests_never_contact_target (test_onboarding.OnboardingTests.test_unauthorized_and_active_probe_requests_never_contact_target)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<R3_PROJECT>\tests\test_onboarding.py", line 14, in setUp
    self.document = json.loads((ROOT / "integration/incident/application.approved.acs.json").read_text(encoding="utf-8"))
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '<R3_PROJECT>\\integration\\incident\\application.approved.acs.json'

======================================================================
ERROR: test_wrong_protocol_and_inbox_return_specific_advice (test_onboarding.OnboardingTests.test_wrong_protocol_and_inbox_return_specific_advice)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<R3_PROJECT>\tests\test_onboarding.py", line 14, in setUp
    self.document = json.loads((ROOT / "integration/incident/application.approved.acs.json").read_text(encoding="utf-8"))
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '<R3_PROJECT>\\integration\\incident\\application.approved.acs.json'

======================================================================
FAIL: test_wsl_target_and_launcher_use_identical_unicode_spaced_paths_and_distro (test_deployment_preparation.DeploymentPreparationTests.test_wsl_target_and_launcher_use_identical_unicode_spaced_paths_and_distro)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<R3_PROJECT>\tests\test_deployment_preparation.py", line 191, in test_wsl_target_and_launcher_use_identical_unicode_spaced_paths_and_distro
    self.assertIn("/mnt/d/", " ".join(command))
AssertionError: '/mnt/d/' not found in 'wsl.exe -d Ubuntu-22.04 --exec docker compose -p isolated-fixture --env-file /mnt/c/Users/xiao/.codex/visualizations/2026/10/18/01a14cbc-96d9-7a52-85a1-8ab00a9eddc1/incident-pilot-r3/artifacts/deployment-gap-audit-20261018/fixtures/���� ���� hvkgb8ct/output/compose.env -f /mnt/c/Users/xiao/.codex/visualizations/2026/10/18/01a14cbc-96d9-7a52-85a1-8ab00a9eddc1/incident-pilot-r3/deploy/compose.yml -f /mnt/c/Users/xiao/.codex/visualizations/2026/10/18/01a14cbc-96d9-7a52-85a1-8ab00a9eddc1/incident-pilot-r3/deploy/agents.yml -f /mnt/c/Users/xiao/.codex/visualizations/2026/10/18/01a14cbc-96d9-7a52-85a1-8ab00a9eddc1/incident-pilot-r3/artifacts/deployment-gap-audit-20261018/fixtures/���� ���� hvkgb8ct/output/deployment.overlay.yml --profile isolated'

======================================================================
FAIL: test_requires_explicit_pinned_image_and_kafka_mode (test_fluent_bit_linux_collector.LinuxCollectorPreparationTests.test_requires_explicit_pinned_image_and_kafka_mode)
----------------------------------------------------------------------
ValueError: The coordinator AMP directory must exist inside this project

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "<R3_PROJECT>\tests\test_fluent_bit_linux_collector.py", line 119, in test_requires_explicit_pinned_image_and_kafka_mode
    with self.assertRaisesRegex(ValueError, "Explicit Kafka settings"):
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: "Explicit Kafka settings" does not match "The coordinator AMP directory must exist inside this project"

======================================================================
FAIL: test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task (test_windows_startup.WindowsStartupConfigurationTests.test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task) (what_if=False)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<R3_PROJECT>\tests\test_windows_startup.py", line 89, in test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task
    self.assertEqual(result.returncode, 0, result.stderr)
AssertionError: 1 != 0 : & : File <R3_PROJECT>\ops\inst
all_startup.ps1 cannot be loaded because running scripts is disabled on this system. For more information, see about_Ex
ecution_Policies at https:/go.microsoft.com/fwlink/?LinkID=135170.
At line:5 char:3
+ & '<USER_PROFILE>\.codex\visualizations\2026\10\18\01a14cbc-96d9-7a52- ...
+   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : SecurityError: (:) [], PSSecurityException
    + FullyQualifiedErrorId : UnauthorizedAccess


======================================================================
FAIL: test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task (test_windows_startup.WindowsStartupConfigurationTests.test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task) (what_if=True)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<R3_PROJECT>\tests\test_windows_startup.py", line 89, in test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task
    self.assertEqual(result.returncode, 0, result.stderr)
AssertionError: 1 != 0 : & : File <R3_PROJECT>\ops\inst
all_startup.ps1 cannot be loaded because running scripts is disabled on this system. For more information, see about_Ex
ecution_Policies at https:/go.microsoft.com/fwlink/?LinkID=135170.
At line:5 char:3
+ & '<USER_PROFILE>\.codex\visualizations\2026\10\18\01a14cbc-96d9-7a52- ...
+   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : SecurityError: (:) [], PSSecurityException
    + FullyQualifiedErrorId : UnauthorizedAccess


----------------------------------------------------------------------
Ran 472 tests in 66.012s

FAILED (failures=4, errors=6, skipped=6)
```

### 12-tests-bridge-original
```text
======================================================================
ERROR: test_describe_inventory_and_acs_official_schema (test_bridge_gateway.BridgePolicyTests.test_describe_inventory_and_acs_official_schema)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "<PYTHON312>\Lib\asyncio\runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\asyncio\base_events.py", line 691, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "<R3_PROJECT>\tests\test_bridge_gateway.py", line 303, in test_describe_inventory_and_acs_official_schema
    base = json.loads((ROOT / "integration/incident/database.submission.acs.json").read_text(encoding="utf-8"))
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<PYTHON312>\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '<R3_PROJECT>\\integration\\incident\\database.submission.acs.json'

----------------------------------------------------------------------
Ran 52 tests in 4.471s

FAILED (errors=1)
```

### 14-stop-only-prior-idle-local-services
```text
STOPPED_VERIFIED_R2_PID=60648
STOPPED_VERIFIED_R2_PID=23676
waiting for server to shut down............................................................... failed
pg_ctl: server does not shut down
Exception: 
Line |
  27 |  … f($remaining.Count){throw 'Required ports not free after prior stop'}
     |                        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Required ports not free after prior stop
```

### 18-prior-postgres-bounded-immediate-stop
```text
PRIOR_FAST_SHUTDOWN_REQUEST_ACCEPTED_BUT_TIMED_OUT; ORIGINAL LOG PRESERVED
pg_ctl: could not send stop signal (PID: 56548): Operation not permitted
PG_CTL_IMMEDIATE_EXIT=1
{
  "at": "2026-10-18T20:59:29.4518212+08:00",
  "pgdata": "<R2_PROJECT>\\runtime\\pgdata",
  "prior_pid": 56548,
  "immediate_exit": 1,
  "remaining_listener_count": 1,
  "database_files_deleted": false,
  "note": "Immediate stop requested only after fast stop timed out; preserve all files and failure; next start may require WAL recovery"
}
Exception: 
Line |
  20 |  … ning.Count){throw 'Prior PostgreSQL immediate stop did not free liste …
     |                ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Prior PostgreSQL immediate stop did not free listener
```

### 25-new-documented-strict-verifier
```text
usage: verify.py [-h]
                 (--url URL | --target-config TARGET_CONFIG | --deployment-file DEPLOYMENT_FILE)
                 --output OUTPUT
verify.py: error: [Errno 13] Permission denied: 'artifacts\\acceptance-r3\\h00-verifier\\result.json'
Get-ChildItem: 
Line |
   6 |  Get-ChildItem -LiteralPath artifacts/acceptance-r3/h00-verifier -File …
     |  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Access to the path '<R3_PROJECT>\artifacts\acceptance-r3\h00-verifier' is denied.
```

### 21-fresh-native-database-and-business-start：警告片段
```text
initdb: error: could not create restricted token: error code 87
initdb: error: could not re-execute with restricted token: error code 3
The files belonging to this database system will be owned by user "xiao".
This user must also own the server process.

```

### 23-documented-local-up-with-ready-check：警告片段
```text
{"status": "CONFIGURATION_READY", "config": "<R3_PROJECT>\\runtime\\local-coordinator.json", "mode": "local-aip-stdio", "llm_enabled": false}
Workbench ready at http://127.0.0.1:8766; log: <R3_PROJECT>\artifacts\high-score-workbench
Local workbench: http://127.0.0.1:8766

[notice] A new release of pip is available: 25.0.1 -> 26.2.1
[notice] To update, run: <R3_PROJECT>\.venv\Scripts\python.exe -m pip install --upgrade pip
```

AI 辅助取证说明：30步终端摘要对 ordered dictionary 使用 Select-Object 显示 null，但落盘 JSON 的实测值完整有效，已只读复核；未重写原输出。整理时一次误读不存在的 failure 文件名后改读实际文件，未影响项目。初始大日志显示截断仅为工具输出限制，原盘文件未截断。以上不计为项目测试失败。

## 总耗时与完整文档时的估计

- 开始 2026-10-18T20:45:07+08:00；本记录生成 2026-10-18T21:20:01+08:00。本轮至记录生成墙钟 **34.9 分钟（2094.5 秒）**，含新副本/新环境、旧服务停机故障诊断、阅读、审批等待和记录整理。
- db.restore_writes 请求到人工批准等待 46.678 秒；其他沟通等待未扣除。安装、测试有并行，不能相加日志耗时。
- 若文档完整、权限/网络预检一次满足、软件与 PyPI 缓存可复用、用户及时审批，估计 A/B/C+三组测试+简要记录需15–25分钟。无缓存下载耗时另计。此为估计，不是新机器15分钟实测或全绿承诺。
- 报告之后的分享/PR上传时间单独记录提交回执，不混为业务启动或验证耗时。

## 仍在运行的服务

清单时间 2026-10-18T21:20:00.8460194+08:00；本轮 F10 已复原、复原后 H00 通过；六端口均仅绑定回环且归属 R3：

| 服务 | 端口 | PID |
| --- | --- | --- |
| 订单 app-v1 | 8081 | 37804 |
| 订单 app-v2 | 8082 | 1504 |
| Nginx订单入口 | 8088 | 66620 |
| 运维 supervisor | 8093 | 63244 |
| 本机工作台 | 8766 | 64912 |
| PostgreSQL | 55432 | 57100 |

五个本地 stdio 域及其 MCP 子进程随工作台保持运行。旧 R2 服务已停止；旧 DB 因 fast 停机失败后使用 immediate，文件保留，下一次可能需要 WAL recovery。R3未停机，按用户要求先列清单再询问是否关闭。

## 交付与提交边界

前两轮原记录字节/哈希保持；根目录合并进来的 R2 报告不覆盖。新记录与原日志留本机。若沿用用户“如果有用可以提交给他”的授权反馈，只发送脱敏 Markdown 到单独 deploy-check-<日期> 分支供审阅；原日志、截图、runtime、private、.env、数据库、账本、证书一律不上传；不推 main、不自动合并。实际提交/PR状态以本地 submission-receipt.json 和最终答复为准。

## 本机原件 SHA-256 索引

| 定位符 | SHA-256 |
| --- | --- |
| `LOCAL_EVIDENCE/09-tests-root-original.log` | `f0a0816fa167a2260c7c9e0fa279a3f072c9764f64318ae1f947a99f90153f20` |
| `LOCAL_EVIDENCE/09-tests-root-original.failure-original.txt` | `eef2b2fc845808537a309e6d01a9840555ccd4db5c52f5d5de5e30f5630fe04c` |
| `LOCAL_EVIDENCE/10-tests-sdk-resumable.log` | `14e6dae232671293b1aa17a2eef0ecc4d859e00d9182f8b4a7546816160765d5` |
| `LOCAL_EVIDENCE/12-tests-bridge-original.log` | `64f07ca70797fa7395fd7b10b99177b656e00880ca453f4a6984e516fb353abb` |
| `LOCAL_EVIDENCE/12-tests-bridge-original.failure-original.txt` | `23f44f1dd021ee3dd9097ab97c6bb22e9631fbd54bfef18f1099507cb627b508` |
| `LOCAL_EVIDENCE/16-supplement-report-integrity.log` | `8cfcc81abd2adca34d8136265da07f38474d3af315f3c7d4555f480122b82a25` |
| `LOCAL_EVIDENCE/17-supplement-previously-skipped-figure.log` | `d1450a44848e6caf68e863376ff7de1b47881839d36319579c2dfb040b89d310` |
| `LOCAL_EVIDENCE/20-before-start-port-proof.json` | `900fab1fe63d23efc805b98cdf9f967b1e3bbe15ec57c66833f255ceec454759` |
| `LOCAL_EVIDENCE/24-cli-h00.json` | `d5b01438050c56eaa845c208131e3633c64331300b796807346c5ad458729f6f` |
| `LOCAL_EVIDENCE/25-new-documented-strict-verifier.log` | `62346be2b3b077cd8659bb80a67bb1d4cd99dc898c26f79dbae6d446f3b07e7d` |
| `LOCAL_EVIDENCE/26-workbench-ready-top.jpg` | `ea33d158cf6a56f6295fd00961c57ed1c40f9a43ae9b1be6c089a81bd945cc69` |
| `LOCAL_EVIDENCE/27-native-verifier/result.json` | `120364e13de828aabbf324c39b362ca61c4b2dcdabe3a7f9ad7de80ab9e41e42` |
| `LOCAL_EVIDENCE/27-native-verifier/h00.json` | `28156cfbb2ddf5612d869420d79ee076711711f84045a5677653626c98925ad6` |
| `LOCAL_EVIDENCE/30-local-scope-preflight.json` | `1c7da34a7a365bcd53b2c15c7e8c774ea91ecae2ea26d05f49590653b43a6391` |
| `LOCAL_EVIDENCE/31-f10-authorization.json` | `0adff3d157c4165c91a8329048366d4aeee615c48a6192896b0cc8ae4b8a1639` |
| `LOCAL_EVIDENCE/31-fault-public-ready.json` | `b9dd54c2f1b47d610ca84183cd41b400bb0579162adf7242374616e62d47233f` |
| `LOCAL_EVIDENCE/32-approval-db-restore-writes.jpg` | `d4e5b93aae4cbe04ba1335f792bc7540916fd0d5f000fea38aa308825e33a76c` |
| `LOCAL_EVIDENCE/34-f10-workbench-after-human-approval.json` | `8c517eaf7fa4464e8daba968f547c882cd760aabcffa678a844a7b98ee2cdf8d` |
| `LOCAL_EVIDENCE/34-f10-result-summary.json` | `405f9ad2f34666f3203839ffc6cacc8fc8e2d6b491f725427631638f54226718` |
| `LOCAL_EVIDENCE/34-f10-business-metrics.jpg` | `928b4be73532b481fa30ab6167577e6a5a010ff832711549d3da48ee84b16822` |
| `LOCAL_EVIDENCE/35-restoration-proof.json` | `12e11de2a6e8cd477c95325187d3b521e92e796ba8d7701818a58c3aec4811ec` |
| `LOCAL_EVIDENCE/36-post-restore-h00.json` | `dc1d07577705863e93ccc03c250dbc7c30c4a9e096aaaedfd59ad2c8e073fbc9` |
| `LOCAL_EVIDENCE/37-final-owned-services.json` | `8b556ccd3a82417c395f87fc7d4110476cfe9b25f01d0359abcb9f94633ee6d4` |

---

# 验收冻结后的文档补充（只读核对）

第三轮实测固定在 8a820e419cea55f14d4de0edec76c0e1bcf87904；记录生成于 2026-10-18 21:20:01 +08:00，执行及记录耗时34.9分钟。

验收期间主分支新增文档提交 [5267a3a4a47aeb0188df4894031cf18c240667ba](https://github.com/RoboSynth/multi-agent-interconnect/commit/5267a3a4a47aeb0188df4894031cf18c240667ba)，标题 docs: add teammate setup with independent accounts and runtime steps。与8a对比只含文档、清单和示例，没有产品/测试源码改动。

只读审阅了更新后的 COLLABORATION.md 和 docs/本地开发环境与操作_20261018.md。新说明已补主依赖与独立 MCP 安装、六端口（含8093）、普通用户PG与受限终端区分、分段启动、受控host正常关闭/自有进程终止、三组测试命令及fixture/图表依赖/skip说明。D01/D02/D03/D05/D06/D10/D12的说明已部分补足，不再把这些旧快照问题都称为最新文档仍未说明。

新文档明确：自己的GitHub账号和本机新环境即可本地开发；无需正式平台身份/证书/云主机。那两个JSON是完整测试的公共fixture缺口，不是本机部署前提，不要求用户去索取其他人的账号材料。

本轮未切换工作台host、未按新路线重启服务，也未执行Docker或正式平台。新host的正常关闭流程尚无本轮实测；新增文档不能替代实际验收。D07（D盘假设）、D08（AMP/Kafka前置测试）、D09（PG停机超时仍退出0）、D11（受限通道结果目录写入）原失败保留；本次docs-only提交未修改这些代码。

本地完整记录与原错误保持原字节；此说明为额外版本区分，分享副本将一并注明。


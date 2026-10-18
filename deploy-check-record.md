# 供维护者审阅：Windows 本机按文档部署验收

本次由 AI 按文档执行、用户在场观察。验收固定源码为 f689dae16ab292717c4b695d96ee29e5263b4895。用户已授权把本记录提交给主开发者审阅；仅提交此 Markdown 文件，不包含运行目录、配置凭据、数据库、账本、证书、截图或原始日志。

功能结果：业务底座 H00、工作台、本机 F10 注入/人工审批/恢复/验证/复原均完成。文档自足性仍未通过，两组测试仍有原始失败；这份记录不表示所有测试通过，也不表示正式平台部署通过。

建议维护者优先处理：

1. 补齐离线测试使用的两个无凭据 ACS fixture：integration/incident/database.submission.acs.json、integration/incident/application.approved.acs.json；不要以实际平台身份或私钥替代测试 fixture。
2. 明确测试环境中的 matplotlib 等依赖与完整 discover 命令，说明原有 PG opt-in 跳过条件；保留 worker 启动错误和 deadline 约 5.6ms 的原失败，定位原因后再修复。
3. 补充 Windows 普通/受限终端的启动排错：PostgreSQL 非管理员启动、WMI/子进程权限、额外端口 8093、失败工作台的归属检查及安全重启。
4. 补完整本机 F10 工作台人工审批流程和全部本机组件的停机步骤。运行故障演练仍须单独确认；不得启动正式 Inbox 消费者。

测试方法统计（各组可能重叠，不相加）：

| 组别 | 通过 | 失败方法 | error | skip | 原始 unittest 结果 |
| --- | --- | --- | --- | --- | --- |
| tests/ | 391 | 2 | 7 | 6 | Ran 406；FAILED (failures=3, errors=7, skipped=6)，其中一个失败方法含两个子测试 failure |
| SDK resumable | 25 | 0 | 0 | 0 | Ran 25；OK |
| test_bridge* | 51 | 0 | 1 | 0 | Ran 52；FAILED (errors=1) |

下文保留验收结束时的过程快照。“未提交”描述是当时状态；本次提交已获用户后续授权。失败摘录仅替换本机路径，未改错误正文、判定条件或测试。

路径别名：$PROJECT_ROOT 为第二轮独立副本，$EVIDENCE_ROOT 为其旁侧本机证据目录，$ROUND1_ROOT 为首轮副本；$PYTHON312_HOME/$USER_TEMP/$CODEX_HOME 均为本机目录。证据路径是保管位置索引，其他机器无法直接访问；必要的错误摘录已附在本文。完整本机原件及下列 SHA-256 留作对应核验。

## 本机原件 SHA-256

| 原件 | SHA-256 |
| --- | --- |
| deploy-check-record.md | 6959448B696C948ACF02F838BED7CD7065D51BEB037FB0B545A2B06F5053032C |
| 20-tests-root-original.log | 3D10445D54A08AA52E9A142866CD626282C1B26289F38AFFACBC77F44C944578 |
| 25-tests-sdk-resumable.log | CD17DBE94E82E4AC2F677591074A8D00F5A94993E96AD1EF7E7669AD19BCBB47 |
| 28-tests-bridge-original.log | 36698B34EE52B03DB4C06504771CB9E87C1197038C51FD8A590B031CF925DDCE |
| 22-h00-original.json | 5EE8438CBF45650BA59BC989DC45D8803D84560063F2A6597B8526DC727BF787 |
| 34-f10-workbench-after-human-approval.json | 8B80192AE5FB53A66848E8E92B2C2E65F5E04632522413440F6F4C849CC48E07 |
| 37-restoration-proof.json | 1841BBBFE642AD2FE421561A8DB9176310926E1569F2977708091B1E63A977AF |
| 38-post-restore-h00.json | C709A8183AA3DF84F85454CEC5364F6C14CA72098C888176ECC6780FB8000C43 |

---

# 第二轮按文档独立部署验收记录

本次由 AI 按文档执行、用户在场观察。

本轮实际完成 **A、B、C 三档**。但“只靠两份入口文档即可独立完成”不能判为通过：本机受限执行环境与启动权限需要补充排查，两组测试仍未全通过。原失败、跳过与 AI 取证错误全部保留。

- 仓库 RoboSynth/multi-agent-interconnect；固定提交 **f689dae16ab292717c4b695d96ee29e5263b4895**；分支 **deploy-check-20261018**。

- 新副本：incident-pilot-r2（本机：$PROJECT_ROOT）；证据：deploy-check-r2-20261018（本机：$EVIDENCE_ROOT）。首轮 $ROUND1_ROOT 未覆盖；首轮报告 SHA-256 仍为 B712840AD26FF50B5711621321663480C5318C65F2FA70AAE61FF3B7B4C9499D。

- 开始约 2026-10-18T19:24:15+08:00；报告生成 2026-10-18T19:56:38+08:00；时区 Asia/Taipei（UTC+08:00）。

- 仅 local AIP stdio、规则诊断，模型关闭。五个 local-* 仅为本机进程通道标识；未加载正式 AIC/证书/私钥，未连接 wt.ioa.pub Inbox。随机本机数据库密码/令牌由已获授权的启动器生成并留在私有目录。

- 既有 GitHub 登录只读 clone/fetch、便携软件、项目 Python 依赖、独立 postgres-mcp 环境及随机本机凭据生成均已获用户明确同意；无新增权限或平台账户。

- 未 commit、未 push、未暂存文件。源码/测试/系统代理/全局环境/电源/执行策略均未修改，未安装 Windows 服务。文档建议只保存在本分支记录，任何提交仍须用户确认。

## 机器环境

| 项目 | 实测 |
| --- | --- |
| 系统 | Windows 11 22H2，build 22621.4037，64 位；注册表 ProductName 残留 Windows 10 Pro，Python platform 为 Windows-11-10.0.22621-SP0 |
| Python | 已有 3.12.10 AMD64；本轮新 .venv 和 .venv-mcp-postgres，均 include-system-site-packages=false、user_site=false |
| PowerShell | pwsh 7.6.5；部分原测试调用系统 PowerShell 5.1，受 Restricted 策略阻止，未更改策略 |
| Docker | 未检出可用 Docker 命令，先前常见路径/进程检查也未发现；本轮采用 Windows native，没有安装 Docker |
| 便携运行时 | PostgreSQL 16.15、Nginx 1.30.6，安装在新副本 tools/runtime，无 Windows 服务 |
| 执行上下文 | 默认非管理员受限通道；网络、临时目录和 WMI/子进程受限。安装与工作台重跑用获准完整上下文；首次 PG 实际经非管理员路径启动 |


环境证据 05-documents-and-environment.log（本机：$EVIDENCE_ROOT/05-documents-and-environment.log）、33-environment-and-unchanged-source-evidence.log（本机：$EVIDENCE_ROOT/33-environment-and-unchanged-source-evidence.log）；依赖清单 33-main-pip-freeze.txt（本机：$EVIDENCE_ROOT/33-main-pip-freeze.txt）、33-postgres-mcp-pip-freeze.txt（本机：$EVIDENCE_ROOT/33-postgres-mcp-pip-freeze.txt）。

软件来源：[EnterpriseDB PostgreSQL 官方分发](https://sbp.enterprisedb.com/getfile.jsp?fileid=1260623)、[Nginx 官方 ZIP](https://nginx.org/download/nginx-1.30.6.zip)、PyPI，以及固定提交内 vendored SDK。仅复用首轮软件 ZIP，核对 SHA-256 后通过当前下载器的 CRC/可执行文件检查；没有复制数据库、私密配置、账本。准确哈希见 09-reuse-verified-portable-download-cache.log（本机：$EVIDENCE_ROOT/09-reuse-verified-portable-download-cache.log）。这是新 checkout/新 Python 环境/软件缓存复用，不能称无缓存新机器冷下载验收。

## 三档结果和证据

| 档位 | 结果 | 证据 |
| --- | --- | --- |
| A | 通过，30.016 秒，30/30 请求成功、10 完整流程 | 22-h00-original.json（本机：$EVIDENCE_ROOT/22-h00-original.json），22-ready-before/after.json 均 v2 |
| B | 通过，浏览器能打开工作台、五域 ready | 30-workbench-ready.jpg（本机：$EVIDENCE_ROOT/30-workbench-ready.jpg）、29-local-scope-preflight.json（本机：$EVIDENCE_ROOT/29-local-scope-preflight.json） |
| C | 通过，真实注入→人工批准→恢复→30.015 秒/30 请求/10 流程→复原→复原后 H00 | 35-f10-result-summary.json（本机：$EVIDENCE_ROOT/35-f10-result-summary.json）、35-f10-business-recovered.jpg（本机：$EVIDENCE_ROOT/35-f10-business-recovered.jpg）、37-restoration-proof.json（本机：$EVIDENCE_ROOT/37-restoration-proof.json）、38-post-restore-h00.json（本机：$EVIDENCE_ROOT/38-post-restore-h00.json） |


A/C 所有观察的 failed、unknown、unresolved_intents 均 0。CLI 版本另以前后 /ready=v2 留证，工作台内部按公共 v2 产品路径验证。本轮没有结果未知的原请求，UI 未勾选该选项。

F10 实际时间线：

- 19:43:26–19:43:27：获用户明确同意后执行 eval/inject.py F10 apply --backend native，返回 applied，公共 ready=v1。授权与故障原件：31-f10-authorization.json（本机：$EVIDENCE_ROOT/31-f10-authorization.json）、31-fault-public-ready.json（本机：$EVIDENCE_ROOT/31-fault-public-ready.json）。

- 19:45:48：AI 只填写业务症状并点击开始排查，事故 inc-50f68322a0b44f88；未把注入器原因日志作为协调器输入。

- 19:45:49：产品自动执行普通 write 的 ops.route_rollback；19:45:50 请求 high 风险 db.restore_writes 审批。AI 没有点击或调用审批 API。

- 2026-10-18T11:47:48.893955+00:00：用户本人点击批准；状态 approved，随后恢复数据库写入和重建应用连接池。审批截图 32-approval-db-restore-writes.jpg（本机：$EVIDENCE_ROOT/32-approval-db-restore-writes.jpg）。

- 19:47:50–19:48:20：工作台 30.015 秒、30 请求全成功、10 完整流程；产品原始状态 completed，business_recovered/service_recovered=true、manual_required=false；规则诊断、模型调用 0。完整原始状态：34-f10-workbench-after-human-approval.json（本机：$EVIDENCE_ROOT/34-f10-workbench-after-human-approval.json）。

- 19:49:39–19:49:41：实际执行文档 F10 restore，公共 v2；route.conf 前后 SHA-256 均 BEC7A77EA0A27FC544504BC5993D688885CC399EA48968061E78B9BAAE7E090B，未手工覆盖字节来通过判定。

- 19:49:51–19:50:22：文档要求的复原后 H00，30.015 秒、30/30 请求、10 流程，全通过。


两条 AI 取证错误单独保留：34 步错猜状态枚举；36 步错猜配置字段，且在任何 restore 前退出。35 步只读取同一份产品原始结果，未改测试/业务判定、未重跑掩盖失败；37 步才实际完成复原。

## 三组测试：新 Python 3.12 环境

| 组 | 原始 unittest 结果 | 方法通过 | 失败方法 / error / skip | 原日志 |
| --- | --- | --- | --- | --- |
| tests | Ran 406 in 68.003s；FAILED (failures=3, errors=7, skipped=6) | 391 | 2 / 7 / 6 | 20-tests-root-original.log（本机：$EVIDENCE_ROOT/20-tests-root-original.log） |
| resumable | Ran 25 in 2.854s；OK | 25 | 0 / 0 / 0 | 25-tests-sdk-resumable.log（本机：$EVIDENCE_ROOT/25-tests-sdk-resumable.log） |
| bridge | Ran 52 in 4.442s；FAILED (errors=1) | 51 | 0 / 1 / 0 | 28-tests-bridge-original.log（本机：$EVIDENCE_ROOT/28-tests-bridge-original.log） |


实际命令：
```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p '*test*.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s vendor/ACPs-community/acps-sdk/tests/resumable -p 'test*.py' -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_bridge*.py' -v
```

根组一个失败方法含两条 what_if 子测试失败，另一个方法失败一次，所以原文 failures=3，失败方法为 2，406−2−7−6=391。网关组与 tests/ 组重叠，不相加。六条 skip 均为原条件：五个 PG 集成用例要求 BUSINESS_TEST_DATABASE，一个图表测试缺 matplotlib；未人为设置 skip、未将 skip 算通过。另有 matplotlib 模块导入 error，test_evaluation_report_integrity 内用例未能收集，不能称已执行。

根组错误：缺 database.submission.acs.json（1）、application.approved.acs.json（4）、matplotlib（1 导入错误）、本地接续 worker RuntimeError（1）；失败为 deadline 早于目标约 5.6ms（1 方法）及 PowerShell 5.1 Restricted（1 方法、2 子测试）。均未解决/未改阈值。没有额外安装 matplotlib、补造身份材料或修改执行策略。逐项方法结果 test-results.json（本机：$EVIDENCE_ROOT/test-results.json）；完整 traceback 在后文及各 failure-original.txt。

## 文档缺失、错误及建议

| 编号 | 本次发现 | 建议改法 |
| --- | --- | --- |
| D01 | Windows 前置条件未覆盖受限工具通道代理连通、临时目录 PermissionError，新 venv 无法直接建立 | 补项目目录/临时目录/网络只读预检与失败即停；区别普通交互终端与受限执行器，给不改系统代理的批准下载方式 |
| D02 | PG 与工作台权限需求不同：非管理员 PG 成功，工作台子进程/WMI 失败，需读源码定位 | 补分段安装/启动及自有进程安全重启步骤；PG 保持非管理员，已初始化后核对目录再复用；就绪必须同时检查 connected、mode、配置 SHA |
| D03 | 两入口未列完整依赖/两个隔离环境/排错顺序，需从启动器源码补全 | 给 SDK、主 requirements、独立 postgres-mcp 安装和 pip check 命令；环境创建失败不能继续安装 |
| D04 | 端口表遗漏 ops supervisor 8093 | 补 8093、端口用途和 loopback 绑定，附只读占用检查，不允许停止他人进程 |
| D05 | 有 F07 命令和 F10 表格，没有完整 F10 工作台操作流程 | 补症状输入、用户 high 审批、普通 write 自动执行、completed/业务恢复字段、30 秒/10 流程与异常 finally restore 的步骤和证据路径 |
| D06 | 无三组测试完整命令/覆盖模式/可选依赖/跳过条件说明 | 补本记录三条 discover；说明 *test*.py 覆盖 business_*_test.py，列 matplotlib 和安全的 BUSINESS_TEST_DATABASE 配置，失败原文须留存 |
| D07 | 固定快照缺测试所需两个公共 ACS JSON；这不要求真实证书 | 维护者提供无凭据的固定公共 fixture 并对齐路径，或明确列快照预期错误；不要让辅助开发索取别人的 AIC/私钥 |
| D08 | native.ps1 stop 只描述业务底座，无工作台/五域/MCP/supervisor 完整停机文档 | 补 local-down：事故空闲→保存日志→核对归属→停自有组件→核对端口；明确保留在线演示选项 |
| D09 | 精确软件版本/来源 URL 需读下载器源码，缓存与冷下载口径不完整 | README 列官方 URL、版本和 SHA/CRC 校验；区分新 checkout/新 venv/缓存复用与无缓存新机器 |
| D10 | 局部启动失败仍遗留服务，后台句柄导致启动包装器无 END/退出码 | 明确重定向/关闭子进程标准句柄、输出每组件终态与定界清理命令，失败时禁止盲目启动重复实例 |


这些是记录内建议，未修改两份入口文档或源码。D01/D02 为本机执行环境实测，不能推断所有普通 Windows 终端必败。时序失败/worker RuntimeError 尚未定位，不把推测写成确定根因。读源码补部署/排查的 05/16/17/24/26/29 等步骤均明确记录，不能包装为纯文档自足验收。

## 每一步时间、命令、耗时、结果及处理

按实际开始时间排序；部分安装和只读检查并行，不能相加为总耗时。每次重试均使用新编号，原日志未覆盖。

初始约 2026-10-18T19:24:15+08:00 已核对六端口空闲、默认非管理员上下文、已有 Python/PowerShell 和首轮报告哈希；00-round2-start.json（本机：$EVIDENCE_ROOT/00-round2-start.json）。UI 开始 19:45:48、审批请求 19:45:50、用户批准 19:47:48；UI 截图见 26/30/32/35 前缀 JPG。

### 01-clone-standard-user

开始 2026-10-18T19:25:22.1037991+08:00；结束 2026-10-18T19:25:24.4989385+08:00；耗时 2.393 秒；退出码 128。

结果/处理：默认通道 clone 失败：不能连接本机代理。未修改代理；已授权的 GitHub 只读 fetch 在获准网络通道完成。

是否需要问人：已有 GitHub 登录及第二轮基线已获用户授权。依据：用户授权第二轮；纯英文新目录和默认本机通道；已有 GitHub HTTPS 只读登录。

命令：

```powershell
$ErrorActionPreference='Stop'
$target='$PROJECT_ROOT'
if(Test-Path -LiteralPath $target){throw 'R2 clone target already exists; do not overwrite.'}
$repoUrl='https://github.com/RoboSynth/multi-agent-interconnect.git'
$effective=(& git ls-remote --get-url $repoUrl | Out-String).Trim()
if($LASTEXITCODE -ne 0){throw 'Cannot resolve Git URL.'}
$uri=[Uri]$effective
if($uri.Scheme -ne 'https' -or $uri.Host -ne 'github.com' -or $uri.UserInfo){throw 'Unexpected Git URL rewrite; stop without credentials or keys.'}
$env:GIT_TERMINAL_PROMPT='0'
$env:GCM_INTERACTIVE='Never'
$env:GIT_ASKPASS=''
$env:SSH_ASKPASS=''
git -c credential.interactive=never -c credential.guiPrompt=false clone --no-checkout --no-recurse-submodules $repoUrl $target
```

结果和报错原文：01-clone-standard-user.log（本机：$EVIDENCE_ROOT/01-clone-standard-user.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 02-prepare-standard-user-checkout

开始 2026-10-18T19:26:29.6307476+08:00；结束 2026-10-18T19:26:30.3214686+08:00；耗时 0.688 秒；退出码 0。

结果/处理：新纯英文目录初始化仓库，保留首轮副本，不改全局 Git 配置。

后续处理：失败 clone 保持原日志；以 git init + fetch 完成等价克隆，不载入旧 runtime/private

是否需要问人：否。依据：环境补充／文档缺失：普通权限通道代理不可达，初始化同一空目标以分离网络读取与业务运行；不改变系统配置。

命令：

```powershell
$ErrorActionPreference='Stop'
$target='$PROJECT_ROOT'
if(Test-Path -LiteralPath (Join-Path $target '.git')){throw 'Existing Git metadata after failed clone; preserve and inspect before reuse.'}
if(Test-Path -LiteralPath $target){$items=@(Get-ChildItem -LiteralPath $target -Force); if($items.Count){throw 'Failed clone left files; preserve target without overwriting.'}}
git init $target
if($LASTEXITCODE -ne 0){throw 'Repository initialization failed.'}
git -C $target remote add origin 'https://github.com/RoboSynth/multi-agent-interconnect.git'
if($LASTEXITCODE -ne 0){throw 'Origin setup failed.'}
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
Write-Output ('IS_ADMIN='+$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))
Get-Acl -LiteralPath $target,(Join-Path $target '.git') | Select-Object Path,Owner | ConvertTo-Json -Compress
```

结果和报错原文：02-prepare-standard-user-checkout.log（本机：$EVIDENCE_ROOT/02-prepare-standard-user-checkout.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 03-fetch-confirmed-revision

开始 2026-10-18T19:26:33.6143763+08:00；结束 2026-10-18T19:26:38.6095870+08:00；耗时 4.992 秒；退出码 0。

结果/处理：只读 fetch 用户指定完整提交，现有登录可用，无新 GitHub 权限请求。

是否需要问人：使用先前已授权的 GitHub HTTPS 登录与获准网络通道。依据：用户已确认新固定提交；仅网络读取 Git 对象，无业务进程。

命令：

```powershell
$ErrorActionPreference='Stop'
$repo='$PROJECT_ROOT'
$url='https://github.com/RoboSynth/multi-agent-interconnect.git'
$effective=(& git -C $repo ls-remote --get-url $url | Out-String).Trim()
if($LASTEXITCODE -ne 0){throw 'Cannot resolve Git URL.'}
$uri=[Uri]$effective
if($uri.Scheme -ne 'https' -or $uri.Host -ne 'github.com' -or $uri.UserInfo){throw 'Unexpected URL rewrite; stop without credentials or keys.'}
$env:GIT_TERMINAL_PROMPT='0'
$env:GCM_INTERACTIVE='Never'
$env:GIT_ASKPASS=''
$env:SSH_ASKPASS=''
git -C $repo -c credential.interactive=never -c credential.guiPrompt=false fetch --no-tags --no-recurse-submodules origin 'f689dae16ab292717c4b695d96ee29e5263b4895'
if($LASTEXITCODE -ne 0){throw 'Fetch failed; stop without changing authentication.'}
```

结果和报错原文：03-fetch-confirmed-revision.log（本机：$EVIDENCE_ROOT/03-fetch-confirmed-revision.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 04-checkout-pinned-r2

开始 2026-10-18T19:27:05.3659710+08:00；结束 2026-10-18T19:27:06.6873452+08:00；耗时 1.32 秒；退出码 0。

结果/处理：checkout 固定 f689dae，新副本使用单独 deploy-check-20261018 分支。

是否需要问人：否。依据：用户确认 f689dae 第二轮；新仓库独立分支，不改原仓库。

命令：

```powershell
$ErrorActionPreference='Stop'
git checkout -b deploy-check-20261018 'f689dae16ab292717c4b695d96ee29e5263b4895'
if($LASTEXITCODE -ne 0){throw 'Pinned checkout failed; preserve failure.'}
$head=(& git rev-parse HEAD | Out-String).Trim()
if($head -ne 'f689dae16ab292717c4b695d96ee29e5263b4895'){throw 'R2 HEAD mismatch.'}
Write-Output ('PINNED_HEAD='+$head)
git status --short --branch
git ls-files '*AGENTS.md'
```

结果和报错原文：04-checkout-pinned-r2.log（本机：$EVIDENCE_ROOT/04-checkout-pinned-r2.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 05-documents-and-environment

开始 2026-10-18T19:27:07.1359266+08:00；结束 2026-10-18T19:27:07.8474211+08:00；耗时 0.71 秒；退出码 0。

结果/处理：核对两份指定文档、系统、版本与已批准来源；从源码核对下载 URL 的补充列为文档缺失。

是否需要问人：否。依据：仅读取指定部署文档；为已有安装授权核对下载来源与包清单，源码辅助内容标明文档缺失。

命令：

```powershell
$ErrorActionPreference='Stop'
Write-Output ('TIME='+[DateTimeOffset]::Now.ToString('o'))
Write-Output ('PS='+$PSVersionTable.PSVersion.ToString())
Write-Output ('OS='+[Runtime.InteropServices.RuntimeInformation]::OSDescription)
Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' | Select-Object ProductName,DisplayVersion,CurrentBuild,UBR | ConvertTo-Json -Compress
py -3.12 --version
foreach($name in @('docker','gh')){$found=Get-Command $name -ErrorAction Ignore;Write-Output ($name+'='+$(if($found){$found.Source}else{'NOT_FOUND'}))}
foreach($path in @('COLLABORATION.md','deploy\README.md','requirements-high-score.txt','requirements-lock.txt','domains\database\requirements.txt')){Write-Output ('DOCUMENT='+$path);Get-Content -LiteralPath $path}
Write-Output 'SOURCE_DOWNLOAD_URLS_FOR_ALREADY_APPROVED_SOFTWARE'
rg -n 'https?://' tools/download_native_runtime.py
Write-Output 'SENSITIVE_ENVIRONMENT_NAMES_ONLY'
$names=@(Get-ChildItem Env: | Where-Object {$_.Name -match '(^ACPS|^AIC|^AMP_|^AIP_|^PG|CERT|PRIVATE_KEY|DATABASE_URI|DATABASE_URL|APP_ADMIN_TOKEN|POSTGRES_PASSWORD|ORDERS_DB_PASSWORD|INCIDENT_APPROVAL_SECRET|OPS_SUPERVISOR_TOKEN)'} | Select-Object -ExpandProperty Name)
Write-Output ('NAME_COUNT='+$names.Count)
$names | ConvertTo-Json -Compress
$global:LASTEXITCODE=0
```

结果和报错原文：05-documents-and-environment.log（本机：$EVIDENCE_ROOT/05-documents-and-environment.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 06-create-fresh-python312-environments

开始 2026-10-18T19:27:40.8566071+08:00；结束 2026-10-18T19:27:41.4615327+08:00；耗时 0.603 秒；退出码 1。

结果/处理：新 venv 的 ensurepip 报 PermissionError，失败保留。

是否需要问人：否。依据：COLLABORATION.md 新建 .venv；MCP 环境原由 setup_local 创建，因网络/运行权限分离而提前准备，记为环境补充步骤。

命令：

```powershell
$ErrorActionPreference='Stop'
foreach($path in @('.venv','.venv-mcp-postgres')){if(Test-Path -LiteralPath $path){throw ('Fresh environment path exists: '+$path)}}
py -3.12 -m venv .venv
if($LASTEXITCODE -ne 0){throw 'Main venv creation failed.'}
py -3.12 -m venv .venv-mcp-postgres
if($LASTEXITCODE -ne 0){throw 'PostgreSQL MCP venv creation failed.'}
Get-Content -LiteralPath '.venv\pyvenv.cfg'
.\.venv\Scripts\python.exe -c "import sys,site,json; print(json.dumps({'python':sys.version,'executable':sys.executable,'prefix':sys.prefix,'base_prefix':sys.base_prefix,'user_site':site.ENABLE_USER_SITE})); assert sys.version_info[:2]==(3,12); assert sys.prefix!=sys.base_prefix; assert site.ENABLE_USER_SITE is False"
```

结果和报错原文：06-create-fresh-python312-environments.log（本机：$EVIDENCE_ROOT/06-create-fresh-python312-environments.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 09-reuse-verified-portable-download-cache

开始 2026-10-18T19:27:41.9192591+08:00；结束 2026-10-18T19:27:48.5861069+08:00；耗时 6.665 秒；退出码 0。

结果/处理：只复用首轮软件 ZIP，核对 SHA-256 并由当前下载器做 ZIP CRC/可执行文件检查，未复制数据库/私密配置。

是否需要问人：否。依据：部署文档要求的便携程序；只复用第一轮官方 ZIP 并验证旧实测哈希，由新版原下载器校验解压；不是无缓存新机器冷下载。

命令：

```powershell
$ErrorActionPreference='Stop'
$runtime='tools\runtime'
if(Test-Path -LiteralPath $runtime){throw 'R2 runtime directory already exists; preserve it.'}
New-Item -ItemType Directory -Path $runtime | Out-Null
$expected=@{'postgresql-16.15.zip'='43BB45F173A6F08CF1D29A97A6D8DEB119E8E8093A24C00D2D1001A0CCAA8281';'nginx-1.30.6.zip'='C6EE35EDB0A861063323F709192AE50D1EEFAF2EA7D00678BD2B22D8542DC61E'}
foreach($name in $expected.Keys){$from=Join-Path '$ROUND1_ROOT\tools\runtime' $name;$hash=(Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash;if($hash -ne $expected[$name]){throw ('Original downloaded ZIP changed: '+$name)};Copy-Item -LiteralPath $from -Destination (Join-Path $runtime $name)}
py -3.12 tools/download_native_runtime.py
if($LASTEXITCODE -ne 0){throw 'Approved runtime cache validation or extraction failed.'}
Write-Output 'Reused only first-round approved portable ZIPs; no runtime/private/database/ledger/config copied.'
```

结果和报错原文：09-reuse-verified-portable-download-cache.log（本机：$EVIDENCE_ROOT/09-reuse-verified-portable-download-cache.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 07-install-main-approved-dependencies

开始 2026-10-18T19:27:44.6323104+08:00；结束 2026-10-18T19:27:44.9470556+08:00；耗时 0.313 秒；退出码 1。

结果/处理：AI 调度错误：环境未创建成功仍执行安装，报 No module named pip；后续先确认新环境成功。

是否需要问人：沿用已批准的软件清单和 PyPI 来源；无新增软件类型。依据：COLLABORATION.md SDK 安装及 local-up -Install 内部主依赖命令；仅提前完成网络步骤，不启动资源。

命令：

```powershell
$ErrorActionPreference='Stop'
.\.venv\Scripts\python.exe -m pip install "./vendor/ACPs-community/acps-sdk[amp-sign]"
if($LASTEXITCODE -ne 0){throw 'Vendor SDK installation failed; preserve raw output.'}
.\.venv\Scripts\python.exe -m pip install -r requirements-high-score.txt --cache-dir .cache/pip
if($LASTEXITCODE -ne 0){throw 'Documented main dependencies installation failed.'}
.\.venv\Scripts\python.exe -m pip check
```

结果和报错原文：07-install-main-approved-dependencies.log（本机：$EVIDENCE_ROOT/07-install-main-approved-dependencies.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 08-install-approved-postgres-mcp

开始 2026-10-18T19:27:45.7168532+08:00；结束 2026-10-18T19:27:45.9353757+08:00；耗时 0.217 秒；退出码 1。

结果/处理：同一 AI 调度错误，独立环境解释器尚不存在，失败保留。

是否需要问人：postgres-mcp==0.3.0 和独立环境已在此前获准。依据：local-up 调用 setup_local 的已批准独立 PostgreSQL MCP 安装，提前完成网络步骤；无配置或业务动作。

命令：

```powershell
.\.venv-mcp-postgres\Scripts\python.exe -m pip install -r domains/database/requirements.txt
```

结果和报错原文：08-install-approved-postgres-mcp.log（本机：$EVIDENCE_ROOT/08-install-approved-postgres-mcp.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 10-ensurepip-failure-diagnostic

开始 2026-10-18T19:28:15.5799975+08:00；结束 2026-10-18T19:28:15.9891616+08:00；耗时 0.407 秒；退出码 1。

结果/处理：只读诊断临时目录 PermissionError；未修改系统安全策略。

后续处理：07/08 是环境未成功建立后的连带错误，原样保留；在安装前先恢复并验证环境

是否需要问人：否。依据：环境补充：venv 内置 ensurepip 失败后保留原始报错并显示详细原因；不下载软件、不改系统配置。

命令：

```powershell
$ErrorActionPreference='Stop'
Write-Output 'FAILED_VENV_METADATA'
Get-Content -LiteralPath '.venv\pyvenv.cfg'
.\.venv\Scripts\python.exe -c "import os,sys,tempfile,json; p=tempfile.gettempdir(); print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,'temp_directory':p,'version':sys.version})); f=tempfile.NamedTemporaryFile(prefix='deploy-r2-temp-',delete=True); print('TEMP_CREATE_OK'); f.close()"
if($LASTEXITCODE -ne 0){throw 'Failed environment diagnostic failed.'}
.\.venv\Scripts\python.exe -m ensurepip --upgrade --default-pip -v
```

结果和报错原文：10-ensurepip-failure-diagnostic.log（本机：$EVIDENCE_ROOT/10-ensurepip-failure-diagnostic.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 11-venv-with-project-local-temp

开始 2026-10-18T19:28:52.9035820+08:00；结束 2026-10-18T19:28:53.4184945+08:00；耗时 0.513 秒；退出码 1。

结果/处理：仅本进程使用项目内 TEMP/TMP 仍失败；未改全局变量。

后续处理：保留06/07/08/10原失败；使用项目可写临时目录恢复全新虚拟环境

是否需要问人：否。依据：环境补充／文档缺失：执行器对系统临时子目录拒绝写入；仅本次进程 TEMP/TMP 指向项目 .cache，不改用户或系统环境变量。

命令：

```powershell
$ErrorActionPreference='Stop'
$processTemp=Join-Path (Get-Location).Path '.cache\process-temp'
New-Item -ItemType Directory -Path $processTemp -Force | Out-Null
$env:TEMP=$processTemp
$env:TMP=$processTemp
Write-Output ('PROCESS_ONLY_TEMP='+$processTemp)
py -3.12 -m venv .venv
if($LASTEXITCODE -ne 0){throw 'Main venv recovery failed; do not start installation.'}
py -3.12 -m venv .venv-mcp-postgres
if($LASTEXITCODE -ne 0){throw 'Independent PostgreSQL MCP environment creation failed.'}
.\.venv\Scripts\python.exe -m pip --version
if($LASTEXITCODE -ne 0){throw 'Fresh environment pip verification failed.'}
.\.venv\Scripts\python.exe -c "import sys,site,json,tempfile; print(json.dumps({'python':sys.version,'prefix':sys.prefix,'base_prefix':sys.base_prefix,'user_site':site.ENABLE_USER_SITE,'temp_directory':tempfile.gettempdir()})); assert sys.version_info[:2]==(3,12); assert sys.prefix!=sys.base_prefix; assert site.ENABLE_USER_SITE is False"
Get-Content -LiteralPath '.venv\pyvenv.cfg'
```

结果和报错原文：11-venv-with-project-local-temp.log（本机：$EVIDENCE_ROOT/11-venv-with-project-local-temp.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 12-standard-user-process-capability

开始 2026-10-18T19:29:51.8573681+08:00；结束 2026-10-18T19:29:52.2808104+08:00；耗时 0.422 秒；退出码 1。

结果/处理：只读查询 linked token 返回 1312；没有获得密码、切换账户或变更权限。

是否需要问人：否。依据：只读核实当前登录是否已有非管理员关联令牌；不请求密码、不创建账户、不修改权限或策略。

命令：

```powershell
$ErrorActionPreference='Stop'
& '$ROUND1_ROOT\.venv\Scripts\python.exe' -c "import json,win32api,win32security,win32con; token=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32con.TOKEN_QUERY); result={'elevation_type':win32security.GetTokenInformation(token,win32security.TokenElevationType),'has_linked_token_constant':hasattr(win32security,'TokenLinkedToken'),'create_process_with_token_available':hasattr(__import__('win32process'),'CreateProcessWithTokenW')}; print(json.dumps(result)); linked=win32security.GetTokenInformation(token,win32security.TokenLinkedToken); print('LINKED_STANDARD_TOKEN_AVAILABLE='+str(bool(linked)))"
```

结果和报错原文：12-standard-user-process-capability.log（本机：$EVIDENCE_ROOT/12-standard-user-process-capability.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 13-recover-fresh-environments

开始 2026-10-18T19:30:49.9184734+08:00；结束 2026-10-18T19:31:03.3580643+08:00；耗时 13.437 秒；退出码 0。

结果/处理：获准完整执行上下文中创建两个全新 Python 3.12 隔离环境。

后续处理：06/07/08/10/11失败不删除；12只读检查确认没有现成关联登录，不尝试账户或密码

是否需要问人：否。依据：文档创建全新 venv；执行器受限临时目录失败后改用已有获准安装通道，未改变全局环境或策略。

命令：

```powershell
$ErrorActionPreference='Stop'
py -3.12 -m venv .venv
if($LASTEXITCODE -ne 0){throw 'Main environment creation still failed; do not install.'}
py -3.12 -m venv .venv-mcp-postgres
if($LASTEXITCODE -ne 0){throw 'PostgreSQL MCP environment creation failed.'}
.\.venv\Scripts\python.exe -m pip --version
if($LASTEXITCODE -ne 0){throw 'Main pip unavailable.'}
.\.venv-mcp-postgres\Scripts\python.exe -m pip --version
if($LASTEXITCODE -ne 0){throw 'MCP pip unavailable.'}
Get-Content -LiteralPath '.venv\pyvenv.cfg'
.\.venv\Scripts\python.exe -c "import sys,site,json; print(json.dumps({'python':sys.version,'prefix':sys.prefix,'base_prefix':sys.base_prefix,'user_site':site.ENABLE_USER_SITE})); assert sys.version_info[:2]==(3,12); assert sys.prefix!=sys.base_prefix; assert site.ENABLE_USER_SITE is False"
```

结果和报错原文：13-recover-fresh-environments.log（本机：$EVIDENCE_ROOT/13-recover-fresh-environments.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 16-local-launch-and-test-boundaries

开始 2026-10-18T19:31:15.4935544+08:00；结束 2026-10-18T19:31:15.7585377+08:00；耗时 0.263 秒；退出码 0。

结果/处理：为确认默认入口及测试不访问正式平台而读源码，所需补步骤标记文档缺失。

是否需要问人：否。依据：为用户仅本地通道边界读取源码；测试命令/skip 与原始三组范围未在指定文档完整说明，登记缺失；不执行任何平台操作。

命令：

```powershell
$ErrorActionPreference='Stop'
Write-Output 'DOCUMENTED_LOCAL_LAUNCH_CHAIN'
Get-Content -LiteralPath 'deploy\local-up.ps1'
Write-Output 'LOCAL_COORDINATOR_MODE_AND_MODEL_BOUNDARY'
rg -n 'mode|llm_enabled|local-aip|wutong|amqps|endpoint|workers|approval' tools/configure_local_coordinator.py
Write-Output 'SOURCE_TEST_SKIP_MARKERS'
rg -n 'unittest\.skip|skipTest\(' tests vendor/ACPs-community/acps-sdk/tests/resumable
$global:LASTEXITCODE=0
```

结果和报错原文：16-local-launch-and-test-boundaries.log（本机：$EVIDENCE_ROOT/16-local-launch-and-test-boundaries.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 14-install-main-approved-dependencies

开始 2026-10-18T19:31:29.9001792+08:00；结束 2026-10-18T19:32:32.2866958+08:00；耗时 62.383 秒；退出码 0。

结果/处理：已批准的 SDK[amp-sign]、requirements-high-score/lock 安装成功；pip check 无冲突。

是否需要问人：沿用已批准的相同软件及 PyPI 来源。依据：COLLABORATION.md SDK 与 local-up -Install 主依赖；提前完成已授权网络安装，不启动资源。

命令：

```powershell
$ErrorActionPreference='Stop'
.\.venv\Scripts\python.exe -m pip install "./vendor/ACPs-community/acps-sdk[amp-sign]"
if($LASTEXITCODE -ne 0){throw 'Vendor SDK installation failed.'}
.\.venv\Scripts\python.exe -m pip install -r requirements-high-score.txt --cache-dir .cache/pip
if($LASTEXITCODE -ne 0){throw 'Main requirements installation failed.'}
.\.venv\Scripts\python.exe -m pip check
```

结果和报错原文：14-install-main-approved-dependencies.log（本机：$EVIDENCE_ROOT/14-install-main-approved-dependencies.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 15-install-approved-postgres-mcp

开始 2026-10-18T19:31:30.6482446+08:00；结束 2026-10-18T19:33:17.0783713+08:00；耗时 106.425 秒；退出码 0。

结果/处理：独立环境安装已批准 postgres-mcp==0.3.0 及传递依赖成功，未启用模型。

是否需要问人：已批准 postgres-mcp==0.3.0 及其依赖。依据：local-up 内部已授权 postgres-mcp 独立安装，提前完成网络步骤；不使用正式平台配置。

命令：

```powershell
$ErrorActionPreference='Stop'
.\.venv-mcp-postgres\Scripts\python.exe -m pip install -r domains/database/requirements.txt
```

结果和报错原文：15-install-approved-postgres-mcp.log（本机：$EVIDENCE_ROOT/15-install-approved-postgres-mcp.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 17-native-and-observation-source-review

开始 2026-10-18T19:31:58.1325622+08:00；结束 2026-10-18T19:31:58.3476594+08:00；耗时 0.213 秒；退出码 0。

结果/处理：核对 native/观察源码与资源作用域，所需补步骤标记文档缺失。

是否需要问人：否。依据：文档缺失／环境诊断：核实 PostgreSQL 默认启动方式和本机 supervisor；只读取源码，不改变实现或判定条件。

命令：

```powershell
$ErrorActionPreference='Stop'
Write-Output 'NATIVE_PREPARATION_STARTUP_CHAIN'
$lines=Get-Content -LiteralPath 'tools\prepare_native_database.py'
$lines | Select-Object -Skip 64 -First 71
Write-Output 'OWNED_PROCESS_HELPER'
Get-Content -LiteralPath 'business\native_postgres.py'
Write-Output 'LOCAL_SETUP_PACKAGE_AND_PORT_REQUIREMENTS'
rg -n 'pip|venv|8093|native_supervisor|CREATE_NO_WINDOW|127\.0\.0\.1|DATABASE_URI|provision' domains/setup_local.py
Write-Output 'PUBLIC_HTTP_H00_DEFAULT_AND_OUTPUT'
rg -n 'ArgumentParser|duration|--url|--output|expected_api_version|passed' business/load.py
$global:LASTEXITCODE=0
```

结果和报错原文：17-native-and-observation-source-review.log（本机：$EVIDENCE_ROOT/17-native-and-observation-source-review.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 18-pre-start-port-bindings

开始 2026-10-18T19:33:02.7125186+08:00；结束 2026-10-18T19:33:02.8909841+08:00；耗时 0.177 秒；退出码 0。

结果/处理：8081/8082/8088/55432/8766/8093 在 IPv4/IPv6 均可绑定；实际启动前再次无占用。

是否需要问人：否。依据：COLLABORATION.md 指定端口；8093 为源码发现的额外本机服务端口，启动前全部复查。

命令：

```powershell
$ErrorActionPreference='Stop'
$ports=@(8081,8082,8088,55432,8766,8093)
$hits=@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object {$_.Port -in $ports})
if($hits.Count){$hits | ForEach-Object {Write-Output ('OCCUPIED='+$_.ToString())};throw 'Required local startup port occupied.'}
foreach($port in $ports){foreach($address in @([Net.IPAddress]::Loopback,[Net.IPAddress]::IPv6Loopback)){$listener=[Net.Sockets.TcpListener]::new($address,$port);try{$listener.Server.ExclusiveAddressUse=$true;$listener.Start();Write-Output ('BIND_OK='+$address.ToString()+':'+$port)}finally{$listener.Stop()}}}
$principal=[Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
Write-Output ('STANDARD_EXECUTION_IS_ADMIN='+$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))
```

结果和报错原文：18-pre-start-port-bindings.log（本机：$EVIDENCE_ROOT/18-pre-start-port-bindings.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 19-new-tests-offline-boundary-review

开始 2026-10-18T19:33:37.3305571+08:00；结束 2026-10-18T19:33:37.4976522+08:00；耗时 0.165 秒；退出码 0。

结果/处理：核对新增测试使用本地 fixture/mock；完整 discover 使用 *test*.py 覆盖 business_*_test.py。

是否需要问人：否。依据：用户三组测试原样执行前检查新增测试使用原有离线 fixtures/mocks；不修改或跳过用例，不载入正式凭据。

命令：

```powershell
$ErrorActionPreference='Stop'
rg -n 'subprocess\.(run|Popen)|create_subprocess|connect_robust|requests\.(get|post)|httpx\.(get|post)|Register-ScheduledTask|Get-ScheduledTask|patch\(' tests/test_formal_handover.py tests/test_platform_e1_worker.py tests/test_platform_resume_experiment.py tests/test_compose_entry.py tests/test_local_launcher.py
Write-Output 'NO_REAL_PLATFORM_ENVIRONMENT_OR_CERTIFICATES_PREPARED'
$global:LASTEXITCODE=0
```

结果和报错原文：19-new-tests-offline-boundary-review.log（本机：$EVIDENCE_ROOT/19-new-tests-offline-boundary-review.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 20-tests-root-original

开始 2026-10-18T19:33:40.3320575+08:00；结束 2026-10-18T19:34:51.5815176+08:00；耗时 71.246 秒；退出码 1。

结果/处理：未通过：406 个方法，391 通过、2 个失败方法（3 条 failure 记录）、7 error、6 skip；未修改测试/断言/跳过开关。

是否需要问人：否。依据：用户要求 tests/；完整 *test*.py 测试模块原样执行，包含 business_*_test.py，不运行独立真实注入脚本；命令口径为文档补充。

命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p '*test*.py' -v
```

结果和报错原文：20-tests-root-original.log（本机：$EVIDENCE_ROOT/20-tests-root-original.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 21-documented-local-up-standard-context

开始 2026-10-18T19:34:03.4644563+08:00；包装会话未结束，报告时已观察 1354.8 秒；完整命令耗时和退出码未知。

结果/处理：部分启动：业务底座成功，initdb 受限令牌警告保留；工作台 PermissionError、启动器 WMI 拒绝访问。包装会话尚未闭合。

后续处理：后台服务继承输出句柄，包装会话尚未闭合；不能虚构退出码

是否需要问人：沿用已有安装/本机运行授权；第 27 步获准完整执行上下文。依据：COLLABORATION.md 与 deploy/README.md 原样 local-up -Install；当前普通执行上下文，无模型开关。

命令：

```powershell
$ErrorActionPreference='Stop'
$ports=@(8081,8082,8088,55432,8766,8093)
$hits=@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object {$_.Port -in $ports})
if($hits.Count){$hits | ForEach-Object {Write-Output $_.ToString()};throw 'Port collision before startup.'}
Write-Output 'STARTUP_PORTS_RECHECKED_FREE'
pwsh -NoProfile -File deploy/local-up.ps1 -Install
```

结果和报错原文：21-documented-local-up-standard-context.log（本机：$EVIDENCE_ROOT/21-documented-local-up-standard-context.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 22-h00-original

开始 2026-10-18T19:35:09.5841574+08:00；结束 2026-10-18T19:35:40.1279890+08:00；耗时 30.541 秒；退出码 0。

结果/处理：A 通过：30.016 秒，30 请求全成功、10 完整流程，failed/unknown/unresolved 全 0。

是否需要问人：否。依据：deploy/README.md H00 原CLI 30秒；另按文档核实公共ready为v2，保留新文件，不改判定。

命令：

```powershell
$ErrorActionPreference='Stop'
$output='eval/results/local/deploy-check-r2-20261018-h00.json'
if(Test-Path -LiteralPath $output){throw 'R2 H00 output exists; do not overwrite.'}
$ready=Invoke-RestMethod -Uri 'http://127.0.0.1:8088/ready' -NoProxy -TimeoutSec 5
$ready | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath '$EVIDENCE_ROOT\22-ready-before.json' -Encoding utf8
$ready | ConvertTo-Json -Compress
if($ready.ok -ne $true -or $ready.api_version -ne 'v2'){throw 'Public readiness is not v2; preserve result before H00.'}
.\.venv\Scripts\python.exe business/load.py --duration 30 --output eval/results/local/deploy-check-r2-20261018-h00.json
$loadCode=$LASTEXITCODE
$after=Invoke-RestMethod -Uri 'http://127.0.0.1:8088/ready' -NoProxy -TimeoutSec 5
$after | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath '$EVIDENCE_ROOT\22-ready-after.json' -Encoding utf8
$after | ConvertTo-Json -Compress
Copy-Item -LiteralPath $output -Destination '$EVIDENCE_ROOT\22-h00-original.json'
$global:LASTEXITCODE=$loadCode
```

结果和报错原文：22-h00-original.log（本机：$EVIDENCE_ROOT/22-h00-original.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 23-workbench-start-diagnostics

开始 2026-10-18T19:36:46.2372562+08:00；结束 2026-10-18T19:36:46.4670024+08:00；耗时 0.228 秒；退出码 0。

结果/处理：只读定位工作台异常及存活组件，没有把网页 HTTP 200 当作已连接。

是否需要问人：否。依据：文档缺失／失败诊断：本机工作台已监听但显示unconfigured，保留原状态及启动器错误；不重配身份、不改源码。

命令：

```powershell
$ErrorActionPreference='Stop'
Write-Output 'WORKBENCH_LAUNCHER_SOURCE'
Get-Content -LiteralPath 'tools\start_workbench.ps1'
Write-Output 'WORKBENCH_PUBLIC_STATE_DIAGNOSTICS'
$state=Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5
Write-Output ('STATE_KEYS='+($state.PSObject.Properties.Name -join ','))
$state | Select-Object mode,status,error,startup_error,coordinator_error,configuration_error,connected | ConvertTo-Json -Depth 5
Write-Output 'WORKBENCH_STDERR_TAIL'
if(Test-Path -LiteralPath 'artifacts\high-score-workbench\server.stderr.log'){Get-Content -LiteralPath 'artifacts\high-score-workbench\server.stderr.log' -Tail 50}
Write-Output 'WORKBENCH_STDOUT_TAIL'
if(Test-Path -LiteralPath 'artifacts\high-score-workbench\server.stdout.log'){Get-Content -LiteralPath 'artifacts\high-score-workbench\server.stdout.log' -Tail 15}
```

结果和报错原文：23-workbench-start-diagnostics.log（本机：$EVIDENCE_ROOT/23-workbench-start-diagnostics.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 24-workbench-connection-error-original

开始 2026-10-18T19:37:31.5092433+08:00；结束 2026-10-18T19:37:31.8093065+08:00；耗时 0.298 秒；退出码 0。

结果/处理：保留原始 PermissionError 状态和自有日志，源码辅助定位列文档缺失。

是否需要问人：否。依据：保留工作台原公共诊断与实际启动日志路径，日志原件不动；源码仅诊断缺失步骤，不修改配置或源码。

命令：

```powershell
$ErrorActionPreference='Stop'
$state=Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5
$state | Select-Object connected,mode,pid,resource_credential_count,connection_error,config_sha256,participants,model_config | ConvertTo-Json -Depth 8
Write-Output 'OWNED_WORKBENCH_LOG_FILES'
$logs=@(Get-ChildItem -LiteralPath 'artifacts\high-score-workbench' -File -Filter 'server-*.log' | Sort-Object LastWriteTime)
$logs | Select-Object Name,Length,LastWriteTime | ConvertTo-Json -Compress
foreach($file in $logs){Write-Output ('LOG='+$file.FullName);Get-Content -LiteralPath $file.FullName -Tail 50 | ForEach-Object {$_ -replace '(?i)(postgres(?:ql)?://)[^@\s]+@','$1[REDACTED]@'}}
Write-Output 'ORIGINAL_LOGS_REMAIN_UNMODIFIED; EXCERPTS REDACT URL USERINFO IF PRESENT'
Write-Output 'STARTUP_CONNECTION_HANDLING_SOURCE'
rg -n 'connection_error|unconfigured|connect\(|TemporaryDirectory|config_sha256|startup|lifespan' workbench_server.py incident/local_transport.py incident/local_worker.py
```

结果和报错原文：24-workbench-connection-error-original.log（本机：$EVIDENCE_ROOT/24-workbench-connection-error-original.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 25-tests-sdk-resumable

开始 2026-10-18T19:37:35.0154789+08:00；结束 2026-10-18T19:37:39.0957931+08:00；耗时 4.078 秒；退出码 0。

结果/处理：SDK resumable 25/25，通过，零 error/failure/skip。

是否需要问人：否。依据：用户第二组原样 SDK resumable；使用新 Python 3.12 环境，不改变 skip、断言或用例。

命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s vendor/ACPs-community/acps-sdk/tests/resumable -p 'test*.py' -v
```

结果和报错原文：25-tests-sdk-resumable.log（本机：$EVIDENCE_ROOT/25-tests-sdk-resumable.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 26-preserve-and-stop-own-failed-workbench

开始 2026-10-18T19:39:40.9884507+08:00；结束 2026-10-18T19:39:41.5475450+08:00；耗时 0.557 秒；退出码 0。

结果/处理：保留原始失败截图与日志后，仅停止归属、配置哈希已核对的本轮失败工作台。

后续处理：文档未说明 WMI 权限要求；核实 PID、脚本、配置SHA和空任务后停止本轮失败工作台，准备按原命令重跑

是否需要问人：否。依据：原启动器要求明确重启无健康连接实例；只处理本次无事故的自有进程，原错误/配置/日志保留，不修改实现。

命令：

```powershell
$ErrorActionPreference='Stop'
$project=(Get-Location).Path
$state=Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5
if($state.connected -eq $true -or $state.incident -or @($state.incidents).Count -gt 0){throw 'Workbench is connected or has incidents; do not stop.'}
$expectedSha=(Get-FileHash -LiteralPath 'runtime\local-coordinator.json' -Algorithm SHA256).Hash.ToLowerInvariant()
if($state.config_sha256 -ne $expectedSha){throw 'Workbench configuration digest differs; do not stop.'}
$runtimePid=[int]$state.pid
$process=Get-CimInstance Win32_Process -Filter "ProcessId = $runtimePid" -ErrorAction Stop
$script=Join-Path $project 'workbench_server.py'
$config=Join-Path $project 'runtime\local-coordinator.json'
if(-not $process -or -not $process.CommandLine.Contains($script) -or -not $process.CommandLine.Contains($config) -or $process.CommandLine -notmatch '--port\s+8766'){throw 'Owned workbench process identity did not match; do not stop.'}
$state | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath '$EVIDENCE_ROOT\26-workbench-original-failed-state.json' -Encoding utf8
$process | Select-Object Name,ProcessId,ParentProcessId,ExecutablePath | ConvertTo-Json -Compress
Stop-Process -Id $runtimePid -ErrorAction Stop
Write-Output ('STOPPED_ONLY_OWN_UNCONFIGURED_WORKBENCH_PID='+$runtimePid)
for($attempt=0;$attempt -lt 20;$attempt++){$hits=@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object {$_.Port -eq 8766});if(-not $hits.Count){break};Start-Sleep -Milliseconds 100}
if($hits.Count){throw 'Workbench port remains occupied; do not restart.'}
Write-Output 'PORT_8766_RELEASED'
```

结果和报错原文：26-preserve-and-stop-own-failed-workbench.log（本机：$EVIDENCE_ROOT/26-preserve-and-stop-own-failed-workbench.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 27-documented-local-up-rerun

开始 2026-10-18T19:39:44.7338331+08:00；包装会话未结束，报告时已观察 1013.5 秒；完整命令耗时和退出码未知。

结果/处理：B 通过：文档普通重跑命令在获准完整上下文执行，五个本地参与者 ready；复用已有非管理员 PG。

后续处理：后台服务继承输出句柄，包装会话尚未闭合；不能虚构退出码

是否需要问人：沿用已有安装/本机运行授权；第 27 步获准完整执行上下文。依据：deploy/README.md 普通重跑原命令；保持配置和模型关闭；既有本轮 PG 已以非管理员运行，本步不改其启动身份。

命令：

```powershell
pwsh -NoProfile -File deploy/local-up.ps1
```

结果和报错原文：27-documented-local-up-rerun.log（本机：$EVIDENCE_ROOT/27-documented-local-up-rerun.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 28-tests-bridge-original

开始 2026-10-18T19:39:56.6054889+08:00；结束 2026-10-18T19:40:02.5040944+08:00；耗时 5.896 秒；退出码 1。

结果/处理：网关 52 项：51 passed、1 error，缺 database.submission.acs.json。

是否需要问人：否。依据：用户第三组网关 test_bridge* 原样独立运行；52项与根组重叠，不相加计唯一用例。

命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_bridge*.py' -v
```

结果和报错原文：28-tests-bridge-original.log（本机：$EVIDENCE_ROOT/28-tests-bridge-original.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 29-local-only-pre-injection-preflight

开始 2026-10-18T19:41:36.0992691+08:00；结束 2026-10-18T19:41:39.4614424+08:00；耗时 3.36 秒；退出码 0。

结果/处理：确认本机进程/端口/配置/零事故作用域，保存注入前 route.conf 原件。

是否需要问人：否。依据：用户要求只本机资源；F10前只读核实模式、进程归属、回环端口、运行路径及原路由；没有注入或审批操作。

命令：

```powershell
$ErrorActionPreference='Stop'
$root=(Get-Location).Path
$runtime=Get-Content -LiteralPath 'deploy\native-runtime.json' -Raw | ConvertFrom-Json
$coordinator=Get-Content -LiteralPath 'runtime\local-coordinator.json' -Raw | ConvertFrom-Json
$state=Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5
$ready=Invoke-RestMethod -Uri 'http://127.0.0.1:8088/ready' -NoProxy -TimeoutSec 5
if($coordinator.mode -ne 'local-aip-stdio' -or $coordinator.llm_enabled -ne $false -or $state.mode -ne 'local-aip-stdio' -or $state.connected -ne $true -or $state.connection_error){throw 'Local-only healthy coordinator boundary failed.'}
if($state.resource_credential_count -ne 0){throw 'Workbench reports resource credentials.'}
if($state.incident -or @($state.incidents).Count -gt 0){throw 'Unexpected existing incident; stop before injection.'}
foreach($path in @($runtime.project_root,$runtime.postgres_bin,$runtime.pgdata,$runtime.nginx_prefix,$runtime.nginx_bin,$runtime.app_python)){if(-not ([IO.Path]::GetFullPath($path).StartsWith($root,[StringComparison]::OrdinalIgnoreCase))){throw 'Native resource path escapes R2 project.'}}
if($runtime.pgport -ne 55432 -or $runtime.app_v1_port -ne 8081 -or $runtime.app_v2_port -ne 8082 -or $runtime.order_port -ne 8088){throw 'Unexpected local resource ports.'}
foreach($worker in $coordinator.workers){if($worker.aic -notlike 'local-*'){throw 'Unexpected non-local worker identity.'}}
$connections=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object {$_.LocalPort -in @(8081,8082,8088,55432,8766,8093)})
$proof=@()
foreach($connection in $connections){if($connection.LocalAddress -notin @('127.0.0.1','::1')){throw 'Project listener is not loopback-only.'};$process=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$connection.OwningProcess) -ErrorAction Stop;if(-not ($process.ExecutablePath.StartsWith($root,[StringComparison]::OrdinalIgnoreCase) -or $process.CommandLine.Contains($root))){throw 'Port listener is not owned by this project.'};$proof += [pscustomobject]@{address=$connection.LocalAddress;port=$connection.LocalPort;pid=$connection.OwningProcess;name=$process.Name;executable=$process.ExecutablePath}}
Copy-Item -LiteralPath 'runtime\nginx\conf\route.conf' -Destination '$EVIDENCE_ROOT\29-route-before.conf'
$routeHash=(Get-FileHash -LiteralPath 'runtime\nginx\conf\route.conf' -Algorithm SHA256).Hash
$result=[ordered]@{checked_at=[DateTimeOffset]::Now.ToString('o');revision='f689dae16ab292717c4b695d96ee29e5263b4895';project_root=$root;mode=$state.mode;connected=$state.connected;credential_count=$state.resource_credential_count;llm_enabled=$coordinator.llm_enabled;participants=$state.participants;ready=$ready;resources=@{pgdata=$runtime.pgdata;nginx_prefix=$runtime.nginx_prefix;ports=@(8081,8082,8088,55432,8766,8093)};listeners=$proof;route_before_sha256=$routeHash;incidents=0;formal_platform_started=$false;fault_injected=$false}
$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath '$EVIDENCE_ROOT\29-local-scope-preflight.json' -Encoding utf8
$result | ConvertTo-Json -Depth 8
Write-Output 'DOCUMENTED_NATIVE_STATUS'
pwsh -NoProfile -File deploy/native.ps1 status
Write-Output 'INJECTOR_DEFAULT_TARGET_SOURCE'
rg -n 'ROOT|native-runtime|postgres-superuser|application.env|F10|def apply|def restore|--backend' eval/inject.py
$global:LASTEXITCODE=0
```

结果和报错原文：29-local-only-pre-injection-preflight.log（本机：$EVIDENCE_ROOT/29-local-only-pre-injection-preflight.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 31-authorized-local-f10-apply

开始 2026-10-18T19:43:26.0341752+08:00；结束 2026-10-18T19:43:27.8314050+08:00；耗时 1.795 秒；退出码 0。

结果/处理：用户明确同意后执行 F10 apply；本机数据库只读及 v1 路由真实注入，公共 ready=v1。

是否需要问人：用户本轮已明确同意 F10 注入；后续工作台审批仍由用户点击。依据：deploy/README.md F10=F02+F07；沿原注入器native参数执行；人工确认已收到，失败时保留并尝试同项目复原。

命令：

```powershell
$ErrorActionPreference='Stop'
$state=Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/state' -NoProxy -TimeoutSec 5
if($state.connected -ne $true -or $state.mode -ne 'local-aip-stdio' -or $state.incident -or @($state.incidents).Count -gt 0){throw 'Workbench no longer matches authorized empty local scope.'}
$preflight=Get-Content -LiteralPath '$EVIDENCE_ROOT\29-local-scope-preflight.json' -Raw | ConvertFrom-Json
if($preflight.project_root -ne (Get-Location).Path){throw 'R2 resource scope changed.'}
$hash=(Get-FileHash -LiteralPath 'runtime\nginx\conf\route.conf' -Algorithm SHA256).Hash
if($hash -ne $preflight.route_before_sha256){throw 'Initial route changed before F10; stop.'}
$authorization=[ordered]@{recorded_at=[DateTimeOffset]::Now.ToString('o');user_decision='同意本机 F10 注入，审批按钮我来点';project_root=(Get-Location).Path;revision='f689dae16ab292717c4b695d96ee29e5263b4895';scope='Only R2 native PostgreSQL 55432 and Nginx 8088; human UI approvals';formal_platform=$false;state='authorized_before_injection';restore_command='.\.venv\Scripts\python.exe eval/inject.py F10 restore --backend native'}
$authorization | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath '$EVIDENCE_ROOT\31-f10-authorization.json' -Encoding utf8
.\.venv\Scripts\python.exe eval/inject.py F10 apply --backend native
$applyCode=$LASTEXITCODE
if($applyCode -ne 0){Write-Output 'APPLY_FAILED_ATTEMPTING_REQUIRED_LOCAL_RESTORE';.\.venv\Scripts\python.exe eval/inject.py F10 restore --backend native;Write-Output ('RESTORE_AFTER_FAILED_APPLY_EXIT='+$LASTEXITCODE);$global:LASTEXITCODE=$applyCode}else{$fault=Invoke-RestMethod -Uri 'http://127.0.0.1:8088/ready' -NoProxy -TimeoutSec 5;$fault | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath '$EVIDENCE_ROOT\31-fault-public-ready.json' -Encoding utf8;$fault | ConvertTo-Json -Compress;$global:LASTEXITCODE=0}
```

结果和报错原文：31-authorized-local-f10-apply.log（本机：$EVIDENCE_ROOT/31-authorized-local-f10-apply.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 32-human-ui-start-and-approval-observation

开始 2026-10-18T19:46:32.3682317+08:00；结束 2026-10-18T19:46:32.5597305+08:00；耗时 0.19 秒；退出码 0。

结果/处理：AI 在 UI 填业务症状并开始排查；db.restore_writes 等待用户本人审批。产品普通 write 路由恢复自动执行。

是否需要问人：用户本人须点击 db.restore_writes 批准按钮；AI 未提交审批。依据：工作台真实 UI 发起与只读状态取证；两份入口文档未列完整 F10 人工操作流程，标记文档缺失。

命令：

```powershell
$raw=(Invoke-WebRequest -Uri 'http://127.0.0.1:8766/api/state').Content
$raw | Set-Content -LiteralPath '$EVIDENCE_ROOT\32-workbench-awaiting-approval.json' -Encoding utf8
$s=$raw | ConvertFrom-Json
[pscustomobject]@{incident_id=$s.incident.id;status=$s.incident.status;mode=$s.mode;connected=$s.connected;approval=$s.incident.approvals;model_source=$s.incident.model_source;tokens=$s.incident.tokens} | ConvertTo-Json -Depth 8
if($s.mode -ne 'local-aip-stdio'){throw 'Unexpected mode'}
```

结果和报错原文：32-human-ui-start-and-approval-observation.log（本机：$EVIDENCE_ROOT/32-human-ui-start-and-approval-observation.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 33-environment-and-unchanged-source-evidence

开始 2026-10-18T19:47:50.3044560+08:00；结束 2026-10-18T19:47:52.4243087+08:00；耗时 2.118 秒；退出码 0。

结果/处理：保存新环境、pip freeze、固定 HEAD/分支、源码与暂存区无变化证据。

是否需要问人：否。依据：交付所需环境、版本、依赖和零源码修改取证；仅读取本轮隔离环境。

命令：

```powershell
$ErrorActionPreference='Stop'
& .\.venv\Scripts\python.exe -m pip freeze | Set-Content -LiteralPath '$EVIDENCE_ROOT\33-main-pip-freeze.txt' -Encoding utf8
if($LASTEXITCODE -ne 0){throw 'main freeze failed'}
& .\.venv-mcp-postgres\Scripts\python.exe -m pip freeze | Set-Content -LiteralPath '$EVIDENCE_ROOT\33-postgres-mcp-pip-freeze.txt' -Encoding utf8
if($LASTEXITCODE -ne 0){throw 'mcp freeze failed'}
& .\.venv\Scripts\python.exe -c 'import sys,site,platform,json;print(json.dumps({"python":sys.version,"executable":sys.executable,"prefix":sys.prefix,"base_prefix":sys.base_prefix,"user_site":site.ENABLE_USER_SITE,"platform":platform.platform()}))'
Get-Content -LiteralPath .venv\pyvenv.cfg
Get-Content -LiteralPath .venv-mcp-postgres\pyvenv.cfg
git rev-parse HEAD
git branch --show-current
git diff --exit-code
if($LASTEXITCODE -ne 0){throw 'Tracked checkout differs'}
git diff --cached --exit-code
if($LASTEXITCODE -ne 0){throw 'Staged files found'}
git status --short --untracked-files=normal
$global:LASTEXITCODE=0
```

结果和报错原文：33-environment-and-unchanged-source-evidence.log（本机：$EVIDENCE_ROOT/33-environment-and-unchanged-source-evidence.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 34-observe-human-approved-recovery

开始 2026-10-18T19:48:11.5400151+08:00；结束 2026-10-18T19:48:21.9674731+08:00；耗时 10.425 秒；退出码 1。

结果/处理：AI 采集器误判：产品 completed、business_recovered=true、30 秒观察通过，但采集器错期待 recovered 而 exit 1；原日志与 JSON 不改。

是否需要问人：用户已亲自在工作台批准；响应明确记录 19:47:48 操作获批。依据：C 档真实人工 UI 审批后只读观察工作台原生恢复与业务验证；无审批 API 写入。

命令：

```powershell
$ErrorActionPreference='Stop'
$deadline=[DateTimeOffset]::Now.AddSeconds(50)
do {
 $raw=(Invoke-WebRequest -Uri 'http://127.0.0.1:8766/api/state').Content
 $s=$raw | ConvertFrom-Json
 if($s.incident.id -ne 'inc-50f68322a0b44f88' -or $s.mode -ne 'local-aip-stdio'){throw 'Incident or local scope changed'}
 if($s.incident.status -in @('recovered','needs_attention','failed','completed','resolved')){break}
 if([DateTimeOffset]::Now -ge $deadline){break}
 Start-Sleep -Seconds 2
} while($true)
$raw | Set-Content -LiteralPath '$EVIDENCE_ROOT\34-f10-workbench-after-human-approval.json' -Encoding utf8
[pscustomobject]@{incident_id=$s.incident.id;status=$s.incident.status;approvals=$s.incident.approvals;result=$s.incident.result;error=$s.incident.error;model_source=$s.incident.model_source;tokens=$s.incident.tokens} | ConvertTo-Json -Depth 15
if($s.incident.status -ne 'recovered'){throw ('F10 workflow did not report recovered: '+$s.incident.status)}
```

结果和报错原文：34-observe-human-approved-recovery.log（本机：$EVIDENCE_ROOT/34-observe-human-approved-recovery.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 35-preserve-and-read-original-f10-evidence

开始 2026-10-18T19:49:05.8827815+08:00；结束 2026-10-18T19:49:06.0464058+08:00；耗时 0.162 秒；退出码 0。

结果/处理：读取同一份原始产品结果，按用户原定 30 秒/30 请求/10 流程核对；没有修改产品测试或重跑掩盖失败。

后续处理：产品原始状态 completed，UI 业务已恢复，business_recovered=true；原第 34 步错误日志不修改

是否需要问人：否。依据：读取产品原始业务结果与用户要求的 30 秒/30 请求/10 流程；第 34 步采集器误判单独保留，无仓库或原测试改动。

命令：

```powershell
$ErrorActionPreference='Stop'
$s=Get-Content -LiteralPath '$EVIDENCE_ROOT\34-f10-workbench-after-human-approval.json' -Raw | ConvertFrom-Json
$o=$s.incident.result.order_observation
$summary=[ordered]@{incident_id=$s.incident.id;status_original=$s.incident.status;business_recovered=$s.incident.result.business_recovered;service_recovered=$s.incident.result.service_recovered;manual_required=$s.incident.result.manual_required;approval_status=$s.incident.approvals[0].status;approval_decided_at=$s.incident.approvals[0].decided_at;duration_seconds=$o.duration_seconds;requests=$o.requests;success=$o.success;failed=$o.failed;unknown=$o.unknown;completed_workflows=$o.completed_workflows;unresolved_intents=$o.unresolved_intents;passed=$o.passed;model_source=$s.incident.model_source;tokens=$s.incident.tokens;collector_error='Step 34 incorrectly expected status recovered; original completed status and all original evidence remain unchanged'}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath '$EVIDENCE_ROOT\35-f10-result-summary.json' -Encoding utf8
$summary | ConvertTo-Json -Depth 8
if($s.incident.status -ne 'completed' -or -not $s.incident.result.business_recovered -or -not $s.incident.result.service_recovered -or $s.incident.result.manual_required -or $s.incident.approvals[0].status -ne 'approved' -or -not $o.passed -or $o.duration_seconds -lt 30 -or $o.requests -ne 30 -or $o.success -ne 30 -or $o.failed -ne 0 -or $o.unknown -ne 0 -or $o.completed_workflows -ne 10 -or $o.unresolved_intents -ne 0){throw 'Actual F10 acceptance evidence failed original criteria'}
```

结果和报错原文：35-preserve-and-read-original-f10-evidence.log（本机：$EVIDENCE_ROOT/35-preserve-and-read-original-f10-evidence.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 36-documented-f10-restore

开始 2026-10-18T19:49:19.4036130+08:00；结束 2026-10-18T19:49:19.7374356+08:00；耗时 0.332 秒；退出码 1。

结果/处理：AI 取证脚本误读 root 字段（真实为 project_root），作用域检查在 restore 之前退出，无资源修改。

是否需要问人：沿用用户已授权的本机演练及复原范围，无新增账户或凭据。依据：deploy/README.md F10 恢复读写、连接与 v2 路由；仅本轮已授权本机资源，恢复后核对注入前路由字节。

命令：

```powershell
$ErrorActionPreference='Stop'
$s=Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/state'
$n=Get-Content -LiteralPath 'deploy/native-runtime.json' -Raw | ConvertFrom-Json
$root=(Resolve-Path -LiteralPath '.').Path
if($root -ne '$PROJECT_ROOT' -or (Resolve-Path -LiteralPath $n.root).Path -ne $root -or $s.mode -ne 'local-aip-stdio'){throw 'Restoration scope changed'}
& .\.venv\Scripts\python.exe eval/inject.py F10 restore --backend native
if($LASTEXITCODE -ne 0){throw 'Original F10 restore command failed'}
$ready=(Invoke-WebRequest 'http://127.0.0.1:8088/ready').Content
$ready | Set-Content -LiteralPath '$EVIDENCE_ROOT\36-public-ready-after-restore.json' -Encoding utf8
Copy-Item -LiteralPath 'runtime/nginx/conf/route.conf' -Destination '$EVIDENCE_ROOT\36-route-after-restore.conf'
$before=(Get-FileHash -LiteralPath '$EVIDENCE_ROOT\29-route-before.conf' -Algorithm SHA256).Hash
$after=(Get-FileHash -LiteralPath 'runtime/nginx/conf/route.conf' -Algorithm SHA256).Hash
[pscustomobject]@{at=[DateTimeOffset]::Now.ToString('o');ready=($ready|ConvertFrom-Json);route_before_sha256=$before;route_after_sha256=$after;identical=($before -eq $after)} | ConvertTo-Json -Depth 6 | Tee-Object -FilePath '$EVIDENCE_ROOT\36-restoration-proof.json'
if($before -ne $after){throw 'Restored route bytes differ from pre-injection snapshot'}
$global:LASTEXITCODE=0
```

结果和报错原文：36-documented-f10-restore.log（本机：$EVIDENCE_ROOT/36-documented-f10-restore.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 37-documented-f10-restore-correct-scope-field

开始 2026-10-18T19:49:39.6255019+08:00；结束 2026-10-18T19:49:41.5449529+08:00；耗时 1.918 秒；退出码 0。

结果/处理：核对真实作用域后执行文档原始 F10 restore，公共 v2、路由文件 SHA 与注入前相同。

后续处理：第 36 步取证脚本误读 root 字段，在任何复原操作前已退出；本步使用真实配置字段，保留原失败

是否需要问人：否。依据：deploy/README.md 原始 F10 restore 命令；使用已读出的实际 project_root/pgport/order_port 字段核对本轮作用域。

命令：

```powershell
$ErrorActionPreference='Stop'
$s=Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/state'
$n=Get-Content -LiteralPath 'deploy/native-runtime.json' -Raw | ConvertFrom-Json
$root=(Get-Location).Path
if($root -ne '$PROJECT_ROOT' -or $n.project_root -ne $root -or $n.pgport -ne 55432 -or $n.order_port -ne 8088 -or $s.mode -ne 'local-aip-stdio'){throw 'Restoration scope changed'}
& .\.venv\Scripts\python.exe eval/inject.py F10 restore --backend native
if($LASTEXITCODE -ne 0){throw 'Original F10 restore command failed'}
$ready=(Invoke-WebRequest 'http://127.0.0.1:8088/ready').Content
$ready | Set-Content -LiteralPath '$EVIDENCE_ROOT\37-public-ready-after-restore.json' -Encoding utf8
Copy-Item -LiteralPath 'runtime/nginx/conf/route.conf' -Destination '$EVIDENCE_ROOT\37-route-after-restore.conf'
$before=(Get-FileHash -LiteralPath '$EVIDENCE_ROOT\29-route-before.conf' -Algorithm SHA256).Hash
$after=(Get-FileHash -LiteralPath 'runtime/nginx/conf/route.conf' -Algorithm SHA256).Hash
[pscustomobject]@{at=[DateTimeOffset]::Now.ToString('o');ready=($ready|ConvertFrom-Json);route_before_sha256=$before;route_after_sha256=$after;identical=($before -eq $after)} | ConvertTo-Json -Depth 6 | Tee-Object -FilePath '$EVIDENCE_ROOT\37-restoration-proof.json'
if($before -ne $after){throw 'Restored route bytes differ from pre-injection snapshot'}
$global:LASTEXITCODE=0
```

结果和报错原文：37-documented-f10-restore-correct-scope-field.log（本机：$EVIDENCE_ROOT/37-documented-f10-restore-correct-scope-field.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 38-post-restore-documented-h00

开始 2026-10-18T19:49:51.5671202+08:00；结束 2026-10-18T19:50:22.1074858+08:00；耗时 30.538 秒；退出码 0。

结果/处理：复原后 H00 通过：30.015 秒、30 次请求、10 完整流程、失败/未知/未决全 0。

是否需要问人：否。依据：deploy/README.md：每个故障复原后运行 30 秒 business/load.py；保存原 CLI 结果和前后公共 v2 就绪证据。

命令：

```powershell
$ErrorActionPreference='Stop'
$before=(Invoke-WebRequest 'http://127.0.0.1:8088/ready').Content
$before | Set-Content -LiteralPath '$EVIDENCE_ROOT\38-ready-before.json' -Encoding utf8
& .\.venv\Scripts\python.exe business/load.py --duration 30 --output eval/results/local/deploy-check-r2-20261018-post-restore-h00.json
$code=$LASTEXITCODE
Copy-Item -LiteralPath 'eval/results/local/deploy-check-r2-20261018-post-restore-h00.json' -Destination '$EVIDENCE_ROOT\38-post-restore-h00.json'
$after=(Invoke-WebRequest 'http://127.0.0.1:8088/ready').Content
$after | Set-Content -LiteralPath '$EVIDENCE_ROOT\38-ready-after.json' -Encoding utf8
$j=Get-Content -LiteralPath '$EVIDENCE_ROOT\38-post-restore-h00.json' -Raw | ConvertFrom-Json
$j | Select-Object run_id,duration_seconds,requests,success,failed,unknown,completed_workflows,unresolved_intents,passed | ConvertTo-Json
if($code -ne 0){throw ('Original load.py failed with exit '+$code)}
if(-not $j.passed -or $j.requests -ne 30 -or $j.completed_workflows -ne 10 -or $j.failed -ne 0 -or $j.unknown -ne 0 -or $j.unresolved_intents -ne 0){throw 'Original post-restore H00 criteria failed'}
$global:LASTEXITCODE=0
```

结果和报错原文：38-post-restore-documented-h00.log（本机：$EVIDENCE_ROOT/38-post-restore-documented-h00.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 39-final-running-services-and-scope

开始 2026-10-18T19:51:05.0404316+08:00；结束 2026-10-18T19:51:08.2968259+08:00；耗时 3.255 秒；退出码 0。

结果/处理：所有六端口均仅绑定 127.0.0.1、进程属于本轮；本地模式/模型关闭，首轮报告哈希不变。

是否需要问人：否。依据：交付服务清单及本机绑定、资源归属、模式和首轮原件哈希取证；native.ps1 status 为文档命令。

命令：

```powershell
$ErrorActionPreference='Stop'
$raw=(Invoke-WebRequest 'http://127.0.0.1:8766/api/state').Content
$raw | Set-Content -LiteralPath '$EVIDENCE_ROOT\39-final-workbench-state.json' -Encoding utf8
$s=$raw|ConvertFrom-Json
$ports=@(8081,8082,8088,55432,8766,8093)
$listeners=@(Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -in $ports} | ForEach-Object {
 $proc=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$_.OwningProcess)
 $owned=($proc.CommandLine -like '*$PROJECT_ROOT*' -or $proc.ExecutablePath -like '$PROJECT_ROOT\*')
 [pscustomobject]@{address=$_.LocalAddress;port=$_.LocalPort;pid=$_.OwningProcess;parent_pid=$proc.ParentProcessId;executable=$proc.ExecutablePath;owned_by_round2=$owned}
})
$proof=[ordered]@{checked_at=[DateTimeOffset]::Now.ToString('o');project_root=(Get-Location).Path;mode=$s.mode;connected=$s.connected;coordinator_resource_credential_count=$s.resource_credential_count;model_enabled=$s.model_config.enabled;incident_id=$s.incident.id;incident_status=$s.incident.status;business_recovered=$s.incident.result.business_recovered;listeners=$listeners;participants=@($s.participants|Select-Object name,role,aic,pid,status,transport,standby);original_round1_report_sha256=(Get-FileHash '$ROUND1_ROOT\deploy-check-record.md' -Algorithm SHA256).Hash;round2_head=(git rev-parse HEAD);round2_branch=(git branch --show-current)}
$proof | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath '$EVIDENCE_ROOT\39-final-services-and-scope.json' -Encoding utf8
$proof | ConvertTo-Json -Depth 8
if($s.mode -ne 'local-aip-stdio' -or -not $s.connected -or $s.model_config.enabled){throw 'Final workbench boundary differs'}
if(@($listeners|Where-Object {$_.address -ne '127.0.0.1' -or -not $_.owned_by_round2}).Count){throw 'Final listener binding or owner differs'}
pwsh -NoProfile -File deploy/native.ps1 status
```

结果和报错原文：39-final-running-services-and-scope.log（本机：$EVIDENCE_ROOT/39-final-running-services-and-scope.log）。错误全文见下文；成功步骤的警告也留在原日志。

### 40-report-and-evidence-review

开始 2026-10-18T19:56:15.8387976+08:00；结束 2026-10-18T19:56:16.2067752+08:00；耗时 0.366 秒；退出码 0。

结果/处理：交付核对通过：固定提交、无源码/暂存变更、仅未跟踪验收记录；证据链接存在，报告副本一致。

是否需要问人：否。依据：交付检查：记录归因、证据存在性、完整基线、未暂存/未提交与报告副本一致性。

命令：

```powershell
$ErrorActionPreference='Stop'
git diff --exit-code
if($LASTEXITCODE -ne 0){throw 'Tracked source changed'}
git diff --cached --exit-code
if($LASTEXITCODE -ne 0){throw 'Staged files found'}
git status --short --untracked-files=normal
$head=git rev-parse HEAD
if($head -ne 'f689dae16ab292717c4b695d96ee29e5263b4895'){throw 'Revision differs'}
$report='$PROJECT_ROOT\deploy-check-record.md'
$copy='$EVIDENCE_ROOT\deploy-check-record.md'
if((Get-FileHash $report).Hash -ne (Get-FileHash $copy).Hash){throw 'Report evidence copy differs'}
$doc=Get-Content -LiteralPath $report -Raw
$links=[regex]::Matches($doc,'\]\(<([^>]+)>\)')
$missing=@($links|ForEach-Object {$_.Groups[1].Value}|Sort-Object -Unique|Where-Object {-not(Test-Path -LiteralPath $_)})
if($missing.Count){$missing;throw 'Missing evidence link'}
if($doc -notmatch '本次由 AI 按文档执行、用户在场观察'){throw 'Required attribution missing'}
$required=@('00-round2-start.json','22-h00-original.json','30-workbench-ready.jpg','32-approval-db-restore-writes.jpg','34-f10-workbench-after-human-approval.json','35-f10-result-summary.json','37-restoration-proof.json','38-post-restore-h00.json','39-final-services-and-scope.json','test-results.json')
foreach($name in $required){if(-not(Test-Path -LiteralPath (Join-Path '$EVIDENCE_ROOT' $name))){throw ('Missing evidence '+$name)}}
Write-Output ('EVIDENCE_LINKS_CHECKED='+$links.Count)
Write-Output 'HEAD_PINNED; TRACKED_DIFF_EMPTY; STAGED_DIFF_EMPTY; REPORT_COPY_IDENTICAL'
$global:LASTEXITCODE=0
```

结果和报错原文：40-report-and-evidence-review.log（本机：$EVIDENCE_ROOT/40-report-and-evidence-review.log）。错误全文见下文；成功步骤的警告也留在原日志。

## 失败脱敏摘录与启动错误片段

以下是原日志 OUTPUT 的脱敏摘录，仅将本机目录替换为路径别名；错误正文、数字、行号和结果不变。未脱敏原日志及 failure-original.txt 全部保留本机，未上传。

### 01-clone-standard-user

```text
Cloning into '$PROJECT_ROOT'...
fatal: unable to access 'https://github.com/RoboSynth/multi-agent-interconnect.git/': Failed to connect to github.com:443 over proxy 127.0.0.1 after 2103 ms: Could not connect to server
```

### 06-create-fresh-python312-environments

```text
Error: Command '['$PROJECT_ROOT\\.venv\\Scripts\\python.exe', '-m', 'ensurepip', '--upgrade', '--default-pip']' returned non-zero exit status 1.
Exception: 
Line |
   4 |  if($LASTEXITCODE -ne 0){throw 'Main venv creation failed.'}
     |                          ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Main venv creation failed.
```

### 07-install-main-approved-dependencies

```text
$PROJECT_ROOT\.venv\Scripts\python.exe: No module named pip
Exception: 
Line |
   3 |  … CODE -ne 0){throw 'Vendor SDK installation failed; preserve raw outpu …
     |                ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Vendor SDK installation failed; preserve raw output.
```

### 08-install-approved-postgres-mcp

```text
.\.venv-mcp-postgres\Scripts\python.exe: The term '.\.venv-mcp-postgres\Scripts\python.exe' is not recognized as a name of a cmdlet, function, script file, or executable program.
Check the spelling of the name, or if a path was included, verify that the path is correct and try again.
```

### 10-ensurepip-failure-diagnostic

```text
FAILED_VENV_METADATA
home = $PYTHON312_HOME
include-system-site-packages = false
version = 3.12.10
executable = $PYTHON312_HOME\python.exe
command = $PYTHON312_HOME\python.exe -m venv $PROJECT_ROOT\.venv
{"executable": "$PROJECT_ROOT\\.venv\\Scripts\\python.exe", "prefix": "$PROJECT_ROOT\\.venv", "temp_directory": "$USER_TEMP", "version": "3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]"}
TEMP_CREATE_OK
Traceback (most recent call last):
  File "$PYTHON312_HOME\Lib\ensurepip\__init__.py", line 184, in _bootstrap
    with open(filename, "wb") as fp:
         ^^^^^^^^^^^^^^^^^^^^
PermissionError: [Errno 13] Permission denied: '$USER_TEMP\\tmp_62_3zq_\\pip-25.0.1-py3-none-any.whl'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "<frozen os>", line 366, in walk
PermissionError: [WinError 5] �ܾ����ʡ�: '$USER_TEMP\\tmp_62_3zq_'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "<frozen runpy>", line 198, in _run_module_as_main
  File "<frozen runpy>", line 88, in _run_code
  File "$PYTHON312_HOME\Lib\ensurepip\__main__.py", line 5, in <module>
    sys.exit(ensurepip._main())
             ^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\ensurepip\__init__.py", line 284, in _main
    return _bootstrap(
           ^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\ensurepip\__init__.py", line 167, in _bootstrap
    with tempfile.TemporaryDirectory() as tmpdir:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\tempfile.py", line 950, in __exit__
    self.cleanup()
  File "$PYTHON312_HOME\Lib\tempfile.py", line 954, in cleanup
    self._rmtree(self.name, ignore_errors=self._ignore_cleanup_errors)
  File "$PYTHON312_HOME\Lib\tempfile.py", line 934, in _rmtree
    _shutil.rmtree(name, onexc=onexc)
  File "$PYTHON312_HOME\Lib\shutil.py", line 781, in rmtree
    return _rmtree_unsafe(path, onexc)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\shutil.py", line 623, in _rmtree_unsafe
    for dirpath, dirnames, filenames in results:
                                        ^^^^^^^
  File "<frozen os>", line 369, in walk
  File "$PYTHON312_HOME\Lib\shutil.py", line 621, in onerror
    onexc(os.scandir, err.filename, err)
  File "$PYTHON312_HOME\Lib\tempfile.py", line 906, in onexc
    _resetperms(path)
  File "$PYTHON312_HOME\Lib\tempfile.py", line 286, in _resetperms
    _dont_follow_symlinks(_os.chmod, path, 0o700)
  File "$PYTHON312_HOME\Lib\tempfile.py", line 277, in _dont_follow_symlinks
    func(path, *args)
PermissionError: [WinError 5] �ܾ����ʡ�: '$USER_TEMP\\tmp_62_3zq_'
```

### 11-venv-with-project-local-temp

```text
PROCESS_ONLY_TEMP=$PROJECT_ROOT\.cache\process-temp
Error: Command '['$PROJECT_ROOT\\.venv\\Scripts\\python.exe', '-m', 'ensurepip', '--upgrade', '--default-pip']' returned non-zero exit status 1.
Exception: 
Line |
   8 |  … CODE -ne 0){throw 'Main venv recovery failed; do not start installati …
     |                ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Main venv recovery failed; do not start installation.
```

### 12-standard-user-process-capability

```text
Traceback (most recent call last):
{"elevation_type": 1, "has_linked_token_constant": true, "create_process_with_token_available": false}
  File "<string>", line 1, in <module>
pywintypes.error: (1312, 'GetTokenInformation', 'ָ���ĵ�¼�Ự�����ڡ������ѱ���ֹ��')
```

### 20-tests-root-original

```text
======================================================================
ERROR: test_describe_inventory_and_acs_official_schema (test_bridge_gateway.BridgePolicyTests.test_describe_inventory_and_acs_official_schema)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "$PYTHON312_HOME\Lib\asyncio\runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\asyncio\base_events.py", line 691, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "$PROJECT_ROOT\tests\test_bridge_gateway.py", line 303, in test_describe_inventory_and_acs_official_schema
    base = json.loads((ROOT / "integration/incident/database.submission.acs.json").read_text(encoding="utf-8"))
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '$PROJECT_ROOT\\integration\\incident\\database.submission.acs.json'

======================================================================
ERROR: test_evaluation_report_integrity (unittest.loader._FailedTest.test_evaluation_report_integrity)
----------------------------------------------------------------------
ImportError: Failed to import test module: test_evaluation_report_integrity
Traceback (most recent call last):
  File "$PYTHON312_HOME\Lib\unittest\loader.py", line 396, in _find_test_path
    module = self._get_module_from_name(name)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\unittest\loader.py", line 339, in _get_module_from_name
    __import__(name)
  File "$PROJECT_ROOT\tests\test_evaluation_report_integrity.py", line 12, in <module>
    from eval.plot_results import plot
  File "$PROJECT_ROOT\eval\plot_results.py", line 14, in <module>
    import matplotlib
ModuleNotFoundError: No module named 'matplotlib'


======================================================================
ERROR: test_approved_public_metadata_passes_official_schema (test_onboarding.OnboardingTests.test_approved_public_metadata_passes_official_schema)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "$PROJECT_ROOT\tests\test_onboarding.py", line 14, in setUp
    self.document = json.loads((ROOT / "integration/incident/application.approved.acs.json").read_text(encoding="utf-8"))
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '$PROJECT_ROOT\\integration\\incident\\application.approved.acs.json'

======================================================================
ERROR: test_missing_identity_is_not_a_runtime_reachability_claim (test_onboarding.OnboardingTests.test_missing_identity_is_not_a_runtime_reachability_claim)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "$PROJECT_ROOT\tests\test_onboarding.py", line 14, in setUp
    self.document = json.loads((ROOT / "integration/incident/application.approved.acs.json").read_text(encoding="utf-8"))
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '$PROJECT_ROOT\\integration\\incident\\application.approved.acs.json'

======================================================================
ERROR: test_unauthorized_and_active_probe_requests_never_contact_target (test_onboarding.OnboardingTests.test_unauthorized_and_active_probe_requests_never_contact_target)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "$PROJECT_ROOT\tests\test_onboarding.py", line 14, in setUp
    self.document = json.loads((ROOT / "integration/incident/application.approved.acs.json").read_text(encoding="utf-8"))
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '$PROJECT_ROOT\\integration\\incident\\application.approved.acs.json'

======================================================================
ERROR: test_wrong_protocol_and_inbox_return_specific_advice (test_onboarding.OnboardingTests.test_wrong_protocol_and_inbox_return_specific_advice)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "$PROJECT_ROOT\tests\test_onboarding.py", line 14, in setUp
    self.document = json.loads((ROOT / "integration/incident/application.approved.acs.json").read_text(encoding="utf-8"))
                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '$PROJECT_ROOT\\integration\\incident\\application.approved.acs.json'

======================================================================
ERROR: test_custom_information_crosses_native_aip_and_shared_ledger_skips_effect (test_resume_comparison.HandoverControlTests.test_custom_information_crosses_native_aip_and_shared_ledger_skips_effect)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "$PYTHON312_HOME\Lib\asyncio\runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\asyncio\base_events.py", line 691, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "$PROJECT_ROOT\tests\test_resume_comparison.py", line 84, in test_custom_information_crosses_native_aip_and_shared_ledger_skips_effect
    await transport.start()
  File "$PROJECT_ROOT\incident\local_transport.py", line 212, in start
    await asyncio.wait_for(asyncio.gather(*(w.ready for w in self.workers.values())),
  File "$PYTHON312_HOME\Lib\asyncio\tasks.py", line 520, in wait_for
    return await fut
           ^^^^^^^^^
RuntimeError: domain worker failed: RuntimeError

======================================================================
FAIL: test_local_deadline_is_recorded_from_actual_wait (test_participant_health_transport.ParticipantHealthTransportTests.test_local_deadline_is_recorded_from_actual_wait)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "$PYTHON312_HOME\Lib\asyncio\runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\asyncio\base_events.py", line 691, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "$PROJECT_ROOT\tests\test_participant_health_transport.py", line 127, in test_local_deadline_is_recorded_from_actual_wait
    self.assertGreaterEqual(saved["task"].observed_at, saved["task"].deadline)
AssertionError: 1792323259.2185686 not greater than or equal to 1792323259.2241447

======================================================================
FAIL: test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task (test_windows_startup.WindowsStartupConfigurationTests.test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task) (what_if=False)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "$PROJECT_ROOT\tests\test_windows_startup.py", line 89, in test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task
    self.assertEqual(result.returncode, 0, result.stderr)
AssertionError: 1 != 0 : & : File $PROJECT_ROOT\ops\inst
all_startup.ps1 cannot be loaded because running scripts is disabled on this system. For more information, see about_Ex
ecution_Policies at https:/go.microsoft.com/fwlink/?LinkID=135170.
At line:5 char:3
+ & '$CODEX_HOME\visualizations\2026\10\18\01a14cbc-96d9-7a52- ...
+   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : SecurityError: (:) [], PSSecurityException
    + FullyQualifiedErrorId : UnauthorizedAccess


======================================================================
FAIL: test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task (test_windows_startup.WindowsStartupConfigurationTests.test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task) (what_if=True)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "$PROJECT_ROOT\tests\test_windows_startup.py", line 89, in test_default_and_register_whatif_only_prepare_fixed_hidden_inspection_task
    self.assertEqual(result.returncode, 0, result.stderr)
AssertionError: 1 != 0 : & : File $PROJECT_ROOT\ops\inst
all_startup.ps1 cannot be loaded because running scripts is disabled on this system. For more information, see about_Ex
ecution_Policies at https:/go.microsoft.com/fwlink/?LinkID=135170.
At line:5 char:3
+ & '$CODEX_HOME\visualizations\2026\10\18\01a14cbc-96d9-7a52- ...
+   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : SecurityError: (:) [], PSSecurityException
    + FullyQualifiedErrorId : UnauthorizedAccess


----------------------------------------------------------------------
Ran 406 tests in 68.003s

FAILED (failures=3, errors=7, skipped=6)
```

### 28-tests-bridge-original

```text
======================================================================
ERROR: test_describe_inventory_and_acs_official_schema (test_bridge_gateway.BridgePolicyTests.test_describe_inventory_and_acs_official_schema)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "$PYTHON312_HOME\Lib\asyncio\runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\asyncio\base_events.py", line 691, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "$PROJECT_ROOT\tests\test_bridge_gateway.py", line 303, in test_describe_inventory_and_acs_official_schema
    base = json.loads((ROOT / "integration/incident/database.submission.acs.json").read_text(encoding="utf-8"))
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1027, in read_text
    with self.open(mode='r', encoding=encoding, errors=errors) as f:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$PYTHON312_HOME\Lib\pathlib.py", line 1013, in open
    return io.open(self, mode, buffering, encoding, errors, newline)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
FileNotFoundError: [Errno 2] No such file or directory: '$PROJECT_ROOT\\integration\\incident\\database.submission.acs.json'

----------------------------------------------------------------------
Ran 52 tests in 4.442s

FAILED (errors=1)
```

### 34-observe-human-approved-recovery

```text
Exception: 
Line |
  13 |  … recovered'){throw ('F10 workflow did not report recovered: '+$s.incid …
     |                ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | F10 workflow did not report recovered: completed
```

### 36-documented-f10-restore

```text
Resolve-Path: 
Line |
   5 |  … dc1\incident-pilot-r2' -or (Resolve-Path -LiteralPath $n.root).Path - …
     |                                                          ~~~~~~~
     | Cannot bind argument to parameter 'LiteralPath' because it is null.
```

### 21-documented-local-up-standard-context：启动错误/警告片段

```text
Requirement already satisfied: pycparser in $PROJECT_ROOT\.venv\lib\site-packages (from cffi>=2.0.0->cryptography>=3.4.0->pyjwt[crypto]>=2.10.1->mcp==1.30.0->-r $PROJECT_ROOT\requirements-high-score.txt (line 3)) (3.11)
WARNING: Failed to remove contents in a temporary directory '$USER_TEMP\pip-build-tracker-4kmv7y9g'.
You can safely remove it manually.
WARNING: Failed to remove contents in a temporary directory '$USER_TEMP\pip-unpack-osecr9fg'.
You can safely remove it manually.
WARNING: Failed to remove contents in a temporary directory '$USER_TEMP\pip-ephem-wheel-cache-qgeb0foo'.
You can safely remove it manually.
WARNING: Failed to remove contents in a temporary directory '$USER_TEMP\pip-install-06gem3_d'.
You can safely remove it manually.
initdb: error: could not create restricted token: error code 87
initdb: error: could not re-execute with restricted token: error code 3
The files belonging to this database system will be owned by user "xiao".
This user must also own the server process.

The database cluster will be initialized with locale "C".
Requirement already satisfied: mdurl~=0.1 in $PROJECT_ROOT\.venv-mcp-postgres\lib\site-packages (from markdown-it-py>=2.2.0->rich<15.0.0,>=13.7.0->instructor>=1.7.9->postgres-mcp==0.3.0->-r $PROJECT_ROOT\domains\database\requirements.txt (line 2)) (0.1.2)
WARNING: Failed to remove contents in a temporary directory '$USER_TEMP\pip-build-tracker-3x7wvsxu'.
You can safely remove it manually.
WARNING: Failed to remove contents in a temporary directory '$USER_TEMP\pip-unpack-e9sm47ht'.
You can safely remove it manually.
WARNING: Failed to remove contents in a temporary directory '$USER_TEMP\pip-ephem-wheel-cache-1hr9qyq6'.
You can safely remove it manually.
WARNING: Failed to remove contents in a temporary directory '$USER_TEMP\pip-install-iarf8ccr'.
You can safely remove it manually.
bridge_operator provisioned; domain-only environment written to runtime/private/database-bridge.env
Native ops supervisor started on 127.0.0.1:8093.
Local domain configs ready. Secrets were preserved/generated in runtime/private; no secret values printed.
{"status": "CONFIGURATION_READY", "config": "$PROJECT_ROOT\\runtime\\local-coordinator.json", "mode": "local-aip-stdio", "llm_enabled": false}
Get-CimInstance: $PROJECT_ROOT\tools\start_workbench.ps1:50
Line |
  50 |  …    $Process=Get-CimInstance -ClassName Win32_Process -Filter "Process …
     |                ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | 拒绝访问
```

### 24-workbench-connection-error-original：启动错误/警告片段

```text
  "resource_credential_count": 0,
  "connection_error": "PermissionError: [WinError 5] 拒绝访问。",
  "config_sha256": "1ce78442d8405f2982d8524247cff5ac7af74457033cd6f626051a6edc9e1cd2",
  "participants": [],
  "model_config": {
    "enabled": false,
workbench_server.py:44:    async def lifespan(app):
workbench_server.py:47:        app.state.connection_error = None
workbench_server.py:51:        app.state.config_sha256 = hashlib.sha256(config_bytes).hexdigest() if config_bytes is not None else None
workbench_server.py:67:                app.state.connection_error = f"{type(exc).__name__}: {exc}"
workbench_server.py:101:    app = FastAPI(title="跨域故障协同工作台", lifespan=lifespan, docs_url=None, redoc_url=None)
workbench_server.py:141:        return {"connected": active_transport is not None, "mode": getattr(active_transport, "mode", "unconfigured"),
workbench_server.py:144:                "connection_error": app.state.connection_error,
workbench_server.py:148:                "config_sha256": app.state.config_sha256,
```

报告生成工具首次提交代码在工具解析阶段报 SyntaxError: Unexpected identifier 'RoboSynth'，尚未执行文件或 shell 操作；换用无 Markdown 反引号的生成器后继续。该工具级错误不属于项目测试，也未抹除。

## 总耗时及文档完整时的估计

- 本轮执行至本报告生成墙钟总耗时约 **32.4 分钟**（1943.3 秒），含排查、依赖解析、UI 等待、失败保留和整理记录。

- 其中工作台等待用户恢复审批约 **118.9 秒**；其他沟通和阅读时间未扣除。

- 若文档完整、终端权限/网络预检一次满足、软件/PyPI 缓存可复用、用户及时审批，估计完成 A/B/C、三组测试和简要记录需 **15–25 分钟**。无缓存新机器还要额外下载时间，本轮无法据此承诺。此为估计，不是实测耗时或全绿保证。

## 仍在运行的服务与交付状态

清单时间 2026-10-18T19:51:07.3615280+08:00；F10 已 restore，复原后 H00 通过；以下监听均为 127.0.0.1 且归属本轮：

| 服务 | 端口 | PID |
| --- | --- | --- |
| 订单 app-v1 | 8081 | 14136 |
| 订单 app-v2 | 8082 | 60356 |
| Nginx 订单入口 | 8088 | 19696 |
| native ops supervisor | 8093 | 23676 |
| 本地工作台 | 8766 | 60648 |
| PostgreSQL orders | 55432 | 56548 |


五个 stdio 域（应用、数据库主、数据库备、运维、业务验证）及其自有 MCP 子进程随工作台保持运行。凭据、数据库、账本和原始日志保留在运行/私有目录，不提交。两个启动包装会话仍未闭合，不能把其存活时间当作启动耗时或宣称完整命令 exit 0。

未执行停机：按用户要求先列清单并询问是否关闭。用户同意后应仅停止本轮已核对归属的组件并复核端口。验收结束时报告为未提交 Markdown；用户随后授权仅将本记录提交给主开发者，未授权源码修改或正式部署。

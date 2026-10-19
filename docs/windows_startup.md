# Windows 登录后单实例巡检

P2 新增受管模式（2026-10-19）：[配置模板](../ops/longrun.example.json)、[三任务生成器](../ops/startup.py)、[受管工作台](../ops/longrun_host.py)和[身份租约](../ops/aic_lease.py)已完成本地实现，当前仍未注册、启动或进行重启验收。下方原 `install_startup.ps1` 继续支持“工作台已经就绪、仅启动 scheduler”的旧模式，并补充失败后每分钟重启、最多5次。

受管模式先沿[新机器部署](../deploy/README.md)准备自己的七身份 `deployment.json`、镜像和健康业务。复制 `ops/longrun.example.json` 填自己的 manifest、持久化调度目录和控制目录；保留原目录才能对账在途任务。初次迁移前让原工作台和六个参与者由原所有者正常关闭；新主机拒绝接管已有运行容器，不会停止队友或旧实例。

```powershell
$P2Sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
# 模板演示：只生成三个 XML，不验证示例 manifest，也不注册、启动。
.\.venv\Scripts\python.exe ops/startup.py --config ops/longrun.example.json --output runtime/private/startup-preview --user-sid $P2Sid --python .\.venv\Scripts\pythonw.exe --template-only
# 实际准备：将 config 换成自己的配置并去掉 --template-only；受管模式默认10分钟。
# 需要30分钟时再显式加 --inspect-minutes 30；源 schedule 配置不会被覆盖。
```

三个登录任务依次准备资源、60秒后工作台、90秒后巡检，每个均为当前用户 `InteractiveToken`、`IgnoreNew`、失败后每分钟重启最多5次；延迟以外还有真实健康检查，未就绪不会启动下一阶段。WSL资源任务持有自己的 keeper；`start_wsl_docker:true` 时才在指定发行版内启动 systemd 的 docker 服务，否则要求 Docker Desktop 或 WSL Docker 已配置好启动。资源任务只启动四个业务服务（保留 `unless-stopped`）；六个 Inbox 消费者由受管工作台在取得七身份租约后启动，使用 `restart:no` 和挂载的信号包装器，正常关闭 SDK/MCP 后退出码0才能交接。XML生成不调用任务计划服务，不改变自动登录、系统睡眠或代理；是否注册和选择常开电脑由用户决定，受管模式默认每10分钟巡检，旧 scheduler 示例仍保持每30分钟。

租约覆盖整段消费者存续期，不能每轮释放 scheduler 锁而让工作台仍消费 Inbox。新实验入口先用 `experiment_lease(..., control_directory=...)` 请求空闲暂停，工作台停止接新事故、等当前任务结束，关闭 transport 及自己启动的准确容器ID后才释放七身份；实验随后取得独占租约，在 `finally` 中登记资源恢复、30秒H00、消费者关闭和所有自有远端群组清理均成功，再恢复原配置。缺任何一项即留下 `.quarantine.json` 并阻止同套七身份继续运行；H00通过不能替代ACL、队列和交换机清理。隔离解除需先核实远端状态、保留恢复证据，再由所有者处理隔离记录，不自动到期或抢占。

旧冻结 `run_authorized.py` 和已有实验入口尚未改用交接协议，不能直接包上租约再嵌套原 `coordinator_lock`；新计划须采用一个共同的所有权入口。租约只约束同一台机器、同一 ownership 目录（默认复用旧协调锁目录），另一台电脑的七身份独占仍需双方确认；更换checkout时也必须显式复用同一租约目录。

状态脚本新增 `heartbeat_continuity`（七身份联合连续采样覆盖和缺口）、`planned_interruptions` 与本地 `local_task_pairing`；这些均来自提供的日志，不代表进程在线时长或平台入库。每日可用不同 `--output` 名保存快照，24小时验收仍需真实连续运行。

G1当前准备：NEW7轮换配置见`ops/schedule.new7.example.json`，显式绑定自己的`target_config`并固定seed；`drill_auto_approvals:[]`不自动批准高风险操作，演练仍须显式开启。轮换场景和索引保存在原状态目录，恢复失败保留active，恢复完成后才记录演练完成；真实注册与24小时运行另留收据。

只读状态：`python ops/longrun_status.py --schedule-directory <持久化调度目录> --amp-directory <七源AMP根目录> --window-start <带时区起点> --expected-aic <AIC>`；重复`--expected-aic`列出七身份，`--team-aic`列出全部本队身份后可统计外部体检调用，`--output`只接受新文件。状态输出区分观察窗口、日志采样和实际进程在线时长；没有access输入时不把外部调用数写成0。

对应高分方案 T02/T07。`ops/install_startup.ps1` 默认只校验项目 Python、巡检配置和本地工作台地址，生成当前用户登录触发的任务 XML 与摘要。当前交付只完成配置生成和离线验证，未注册真实任务、重启电脑或启动第二个巡检。

```powershell
# 只准备配置，默认不会接触任务计划服务或启动进程
./ops/install_startup.ps1 -ConfigPath ops/schedule.example.json

# 审阅显式注册动作，仍只生成配置
./ops/install_startup.ps1 -ConfigPath ops/schedule.example.json -Register -WhatIf
```

默认产物在 `runtime/startup/inspect-task.xml` 与 `startup-plan.json`。其中有本机绝对路径和当前用户 SID，留在本机。任务名称绑定项目、配置路径及用户，重复准备得到同一名称。

确认已有资源和正式工作台就绪后，可显式执行以下管理动作。注册仅安排以后的登录触发，不立即启动任务；注销不作为已运行进程已退出的证明。

```powershell
./ops/install_startup.ps1 -ConfigPath ops/schedule.example.json -Register
./ops/install_startup.ps1 -ConfigPath ops/schedule.example.json -Unregister -WhatIf
./ops/install_startup.ps1 -ConfigPath ops/schedule.example.json -Unregister
```

任务以当前用户的 `InteractiveToken`、普通权限运行，不存密码；登录时隐藏窗口调用 `ops/run_startup.ps1`，再使用固定项目 `.venv/Scripts/python.exe` 运行现有 `ops/schedule.py --config <配置>`。PowerShell使用仅对该子进程生效的`-ExecutionPolicy Bypass`，不修改系统执行策略；组织强制策略仍需按实际环境确认。没有故障演练或本地替代通道开关，巡检不会自动批准 high 动作。默认配置每30分钟巡检，演练保持关闭。启动包装器清除新任务进程继承的非系统环境变量，不读取资源凭据文件，不修改调用者或系统代理。

任务计划的 `IgnoreNew` 防止同一任务重叠；scheduler CLI 另按持久化状态目录持有非阻塞文件锁，手动启动与任务启动使用同一目录时，第二个进程以退出码2拒绝。锁由操作系统持有，正常退出或进程结束后释放；遗留 `scheduler.lock` 文件不是仍有进程运行的证据。升级前已经运行、未持新锁的旧进程不受此保护，切换前应核实其已退出。保持原状态目录可继续对账在途派发，不能通过换目录绕过未知结果。若残留待办演练，inspect仅记录需要人工处理，保留状态，不续派演练或自动复原。

任务不会启动 Docker、PostgreSQL、应用、模型、工作台或领取平台证书。工作台必须已连接且不含资源凭据；尚未就绪的巡检按既有 scheduler 记录失败，后续周期再检查。当前仅登录触发，用户注销期间不运行，也不等同于开机未登录时的服务。

每次启动保留独立的 `runtime/startup/logs/<时间>-<随机号>.json`、stdout、stderr。记录包含实际子进程退出码；配置生成、注册成功、任务被触发和业务巡检完成分别验收。24小时/7天连续运行、Monitor入库和重启后恢复仍需真实运行证据。

配置语义依据 Microsoft 的[登录触发器](https://learn.microsoft.com/en-us/windows/win32/taskschd/logontrigger)、[多实例策略](https://learn.microsoft.com/en-us/windows/win32/taskschd/taskschedulerschema-multipleinstancespolicy-settingstype-element)和[任务 XML schema](https://learn.microsoft.com/en-us/windows/win32/taskschd/task-scheduler-schema)。

# Windows 登录后单实例巡检

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

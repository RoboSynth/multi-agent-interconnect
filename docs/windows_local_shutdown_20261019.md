# Windows 本地一键停机（2026-10-19）

`deploy/local-down.ps1` 现在与 `local-up.ps1` 配套，按工作台、运维 supervisor、原生业务的顺序关闭当前检出的已登记资源。它保留数据、日志、身份配置及登记文件。此入口完成了本地停机编排；当前验证来自隔离 fixture，完整新机器的启动→H00→停机验收仍待执行。

在 PowerShell 7.4 或更新版本，从自己的检出运行：

```powershell
& .\deploy\local-down.ps1
```

工作台或 supervisor 等待正常退出默认各 120 秒，可以通过 `-TimeoutSeconds 300` 延长。工作台存在待审批或未完成任务时，正常停机请求会等待空闲；超时会返回失败，停机请求仍保留，不继续关闭后续依赖。

## 关闭范围与回执

1. **工作台：** 读取 `runtime/workbench-server.json`，核对本检出的控制目录、32 位 nonce 和 `started.json` 中的实际 PID。对登记的 Python 启动器及实际运行进程持有只读 Windows 句柄，核验绝对脚本路径、固定参数、解释器、真实父 PID 和创建时序，复用 `workbench_host` 的 `stop_when_idle` 请求。只有句柄实际退出且退出码为 0，`finished.json` 记录正常关闭、空闲检查为真、参与者退出码均为 0，才进入下一步。重复执行复用同一有效请求；已有正常关闭收据时仍核验进程并等待实际退出，仅没有存活的登记句柄时报告已关闭。
2. **运维 supervisor：** 读取 `runtime/ops-supervisor.pid`，用相同的句柄归属核验定位当前检出的 supervisor 及其 venv 子进程。通过本机私密配置的认证 token 查询 `/health`，要求返回的 PID、项目路径及服务名称匹配；随后调用新增的 `/shutdown`。该接口在运维重启进行中返回 409，成功响应仅表示接受请求。入口继续等待所有已核实进程实际退出且退出码为 0，才登记正常关闭。token 不写入停机回执。
3. **原生业务：** 先要求 `deploy/native-runtime.json` 的 backend 和 project_root 对应当前检出，PostgreSQL 数据/二进制与 Nginx 配置/二进制路径位于该检出或其登记的 ASCII alias 内；登记在停机期间发生变化时拒绝继续。再调用现有 `native.ps1 stop -RuntimeFile ...`，沿用已核实应用进程族的关闭、项目 Nginx quit、项目 PostgreSQL fast stop。该阶段的通过证据是现有停机入口实际返回 0。

每次执行将独立回执保存在 `runtime/local-down/<时间>-<随机值>.json`，包含阶段状态、登记内容的 SHA256、错误阶段及错误类型。已有登记文件保留；原生停机成功后仍按原有语义更新 managed 应用字段。没有某阶段登记时记录 `NO_REGISTRATION`，不会从进程名或端口猜测归属。

请在同一检出串行执行 `local-up` 和 `local-down`，不要在停机期间启动另一份服务。入口会检测阶段前后可见的登记变化；现有启动入口没有与停机共用的全局互斥锁。

任一阶段失败均停止后续步骤，返回非 0，并保留本轮回执和已有登记。工作台没有正常关闭证据、未知进程归属、认证失败、supervisor 正忙或等待退出超时，都需要根据保留记录处理后再运行。旧版 supervisor 不支持 `/shutdown` 时会在该阶段失败；更新源码后重新启动自己的服务即可使用新接口。

现有 `native.ps1` 对已停止的 PostgreSQL 仍可能返回非 0，因此一键入口不承诺对所有旧登记重复执行均成功。回执会准确保留这一失败。该入口也不管理未由 `local-up` 登记的模型、Docker 项目、平台群组或其他检出；它没有按进程名关闭和强制终止的回退路径。

## 当前验证

`tests/test_local_shutdown.py` 的 15 个独立方法通过，覆盖空检出、错误项目与越界路径拒绝、登记变化、工作台空闲请求/终态/超时、失败停序、登记保留、原生入口非 0 传播、PowerShell 入口，以及认证 supervisor 的正常关闭、未授权/忙拒绝和原有重启响应。补充的进程族用例检查错误命令、不完整父子关系和创建时间变化时，所有已打开句柄均关闭。独立审阅指出的“收据已写但进程尚在退出”和“接受关闭后响应断开”均已修正并补充隔离验证。

真实进程 fixture 只运行临时目录中的休眠脚本：基础 Python 单进程与 venv 启动器/真实子进程，分别持有 1 和 2 个归属句柄，写入 fixture 退出标记后均确认系统退出码为 0；错误脚本路径的查询被拒绝，进程继续存活至 fixture 自己退出。HTTP fixture 只使用自己的临时随机本机端口，原有业务重启函数被替身替换。

首轮保留的测试失败来自 fixture 把 venv 当作基础 Python、以及输出编码问题；修正测试解释器和 UTF-8 捕获后通过。这里没有启动工作台、平台身份、模型、订单服务或真实数据库/Nginx，没有验证完整业务启停，也不代表 T11/T96 整体完成。

复核隔离用例：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_local_shutdown.py -v
```

该测试使用自己的临时 HTTP 服务和休眠进程，用例结束关闭自己的句柄/服务并清理临时文件。Windows 沙箱需要允许本机 loopback；无需业务凭证或平台身份。

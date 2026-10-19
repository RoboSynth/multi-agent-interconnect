# Windows 原生订单应用停机修复（2026-10-19）

`deploy/native.ps1 stop` 现在显式关闭已登记的订单应用进程及其真实 Python 子进程。此前登记的是 Windows venv 启动器 PID，单独终止它可能遗留监听 8081/8082 的应用。

停机读取本检出 `native-runtime.json` 的 v1/v2 PID、配置端口和 `app_python` 绝对路径，使用新的 `managed_app_family` / `--app-family` 入口。每个候选进程都通过持有的同一个 Windows handle 核验：绝对 `business/run_app.py` 路径、独立的版本及端口参数、配置的 Python 启动器或其环境 `pyvenv.cfg` 指定的基础 Python、创建时间和真实父 PID。它支持默认 `.venv`、自定义 venv 和显式基础解释器；先结束应用子进程，再结束启动器，两者确认退出后才移除登记。

启动器不存在但匹配子进程仍在、子进程归属不明、查询/终止失败、未就绪启动器缺少真实子进程时，入口会失败并保留原登记文件。按[接手操作文档](本地开发环境与操作_20261018.md)核对实际 PID 和绝对脚本后处理，不扩大停止范围。对已经全部退出的登记可重复执行。

这是显式终止已核实进程；完整停机仍先正常关闭工作台，再处理 supervisor，最后运行 `native.ps1 stop`。Nginx/PostgreSQL 控制流程未改；`status`、运维重启和故障注入继续使用原单 PID API，不因此获得新的进程族或完整停机保证。

## 验证

`tests/test_native_app_stop.py` 的 15 个方法通过：进程归属、精确参数、配置解释器及其自有 venv 识别、子进程优先、无关进程保留、PID/父进程变化、查询和终止失败、重复停止，以及真实 PowerShell 入口的端口/解释器绑定和失败保留登记。

其中一项显式启用的真实 Windows fixture 只启动临时复制到自定义目录的 venv 启动器和休眠脚本，没有监听端口或访问业务/网络。实际按子进程、启动器的顺序关闭；同目录另一端口参数的独立 fixture 当时仍存活，随后单独清理。测试没有运行完整业务停机或平台验收。

普通检查默认跳过真实进程 fixture：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_native_app_stop.py -v
```

需要复核休眠 fixture 时，显式设置本终端的 `INCIDENT_NATIVE_STOP_FIXTURE=1` 后执行同一命令；临时文件位于检出目录旁的 `fixtures`，用例结束会清理自己的进程和目录。

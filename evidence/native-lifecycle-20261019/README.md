# Windows native 生命周期实测（2026-10-19）

固定源码 `3760b21c8a1ed62e8119925da6f24ebd8b851d14` 的独立 detached 检出在本机完成 `prepare_native_database.py → deploy/local-up.ps1 → 独立 H00 → deploy/local-down.ps1`，各入口退出 0。默认六端口在启动前空闲，项目配置、随机密码、数据库和原生 alias 均属于本检出。

H00 在 30.015 秒完成 10 个创建→查询→撤销订单流程：30 请求成功、失败/未知/未决均 0。工作台为五角色 `local-aip-stdio`，模型关闭、资源凭据数 0，没有发起事故。

停机依次正常关闭工作台和认证 supervisor，再调用原 native stop。57 个预先持有的自有进程只读句柄全部确认实际退出：52 个退出码 0；四个应用启动器/实际进程按原 native stop 显式终止，退出码 1；一个 PostgreSQL logical replication launcher 在日志记录的 fast shutdown 期间退出码 1。工作台/supervisor 及五个域 worker 均正常退出 0，native stop 入口退出 0。不能把“全部已退出”写成“全部进程退出码 0”。17:30:58（北京时间）的独立复查为自有残留 0、六端口监听 0。登记、数据、配置和日志保留。

首轮真实启动和停机也退出 0，但取证 helper 对 CIM 的空 ExecutablePath 处理错误，未进入独立 H00，该轮记失败。修正的仅是批次取证脚本，增加句柄 image/parent/creation/command 核验和部分失败的句柄清理；随后新 attempt 完成上述全链路。原失败、最初预检误选执行器祖先、沙箱 ensurepip 失败均保留，未覆盖或改判。

这是同机新检出验证：官方 ZIP 使用已有缓存；首次 pip 安装发生在新项目 venv，完整补轮复用自己的已安装依赖和已停数据库。它不代表另一台开发者机器、无缓存冷下载、正式平台、模型、故障修复或 T96 完成。产品源码没有为本次运行修改。

`summary.json` 汇总结果与边界，`H00.json` 保存独立业务观察，`process-exits.json` 保留逐进程实际退出及归属时间，`shutdown-selection.json` 为两轮停机/工作台安全字段，`final-inventory.json` 为末次只读盘点。`original-map.json` 将未公开的本机原件映射为相对标签、大小及 SHA256；不包含密码、token、私钥或完整环境。

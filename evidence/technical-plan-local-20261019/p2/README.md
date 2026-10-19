# P2 本地实现与验证

已新增七身份全寿命租约、先空闲关闭再交接的受管host、实验清理确认/隔离协议和三份登录任务模板；默认仍30分钟，10分钟仅显式选择，旧实验入口尚未接入且跨电脑独占仍需双方确认。
26个局部检查通过（租约/交接10、补充取消回归2、调度器7、状态6、启动模板1），记录见本目录；Windows沙箱默认TEMP曾拒绝测试写入，改用工作区临时目录后通过，异步mock测试依既有环境结论使用局部提权。
没有注册任务、启用自动登录、修改睡眠、启动Docker/WSL/平台身份或新增真实巡检；recorded-window-status.json只重算原10月18日30分钟历史输入，1800秒是联合心跳采样覆盖，进程uptime仍null，重启/24小时/真实实验自动交接验收待新范围执行。

实现入口：`ops/aic_lease.py`、`ops/longrun_host.py`、`ops/domain_entry.py`、`ops/longrun.consumers.yml`、`ops/startup.py`、`ops/longrun.example.json`；现有 `ops/schedule.py`、`ops/longrun_status.py` 和 `ops/install_startup.ps1` 增补受管暂停门控、采样中断和失败重启，操作见 `docs/windows_startup.md`。

安全边界：本机同ownership目录的OS锁为排他依据，元数据/时间戳不允许抢占；旧冻结run_authorized.py未改，嵌套旧coordinator_lock会冲突。恢复实验必须确认资源、30秒H00、消费者和所有自有ACL/队列/交换机清理，未知则隔离七身份；本机H00通过不能代替远端清理。容器停机只接受本受管host启动并记录的准确ID及正常退出，已有运行容器/替换ID不会被停止；SDK清理异常须非零退出，实际镜像与平台路径仍需正式验收。

# Linux 云端部署工具归档

这里保存 2026-10-20 云端 NEW7 部署阶段 5–8 实际使用的主管、日志采集和验收工具，供团队接手。Python helper 与当时的准备文件保持一致；测试只调整了所在目录和仓库定位。本目录未包含私密配置、证书、私钥、日志内容或固定容器 ID，也未复制旧的 `install-stage7.sh`。

这是已部署实例的可复用工具及路径记录。完整的新机器安装仍按 [SERVER.md](../SERVER.md) 和部署任务逐阶段验证；这里不代表另一台干净机器已经完成部署验收。

## 文件与安装位置

项目根目录固定为 `/opt/incident-pilot`，解释器为 `.venv/bin/python`。当前部署保留以下安装位置，不因本次归档迁移运行文件。

| 仓库文件 | 当前服务器安装位置 / 用途 |
| --- | --- |
| `cloud_runtime.py` | `/etc/incident-pilot/cloud_runtime.py`；启动四业务，或执行原阶段 5、7 交接 |
| `stop_managed_host.py` | `/etc/incident-pilot/stop_managed_host.py`；等待空闲、SDK 清理及租约释放后，使用 Linux pidfd 停止准确进程 |
| `wait_cloud_workbench.py` | `/etc/incident-pilot/wait_cloud_workbench.py`；只读等待真实工作台就绪 |
| `deployment-20261020/cloud_healthy.py` | `/etc/incident-pilot/cloud_healthy.py`；阶段 5 的健康验收依赖 |
| `deployment-20261020/runtime_snapshot.py` | `/etc/incident-pilot/runtime_snapshot.py`；读取 systemd、工作台、Discovery、巡检和 collector 状态 |
| `deployment-20261020/cloud_collector.py` | `/opt/incident-pilot/evidence/cloud-deployment-20261019/prepared-collector/cloud_collector.py`；分阶段采集及长期主管 |
| `daily_report.py`、`prepare_stage8_timer.py`、`incident-stage8-check.timer.in` | `/opt/incident-pilot/runtime/private/server-tools/`；日报、两小时验收及绝对时间 timer 生成 |
| 三个 `incident-{workbench,scheduler,collector}.service` | `/etc/systemd/system/`；运行主管模板 |
| `incident-daily-report.service`、`incident-daily-report.timer`、`incident-stage8-check.service` | `/etc/systemd/system/`；日报与验收模板 |
| `daily-report.example.json` | 填写后保存为 `/opt/incident-pilot/runtime/private/server/daily-report.json`，权限 600 |

安装 helper 时用 root 所有权和 700 目录、600 文件；systemd unit 使用 root 所有权和 644 权限。先核对已有文件、服务状态和准确配置，再逐个安装需要的文件，保留原件。Python 文件由解释器调用，不要求可执行权限。归档和复制本身不启动服务；需要上线时另外执行 unit 校验、`daemon-reload` 和相应 `enable --now`。

`runtime_snapshot.py` 和 collector unit 仍引用上表中的旧 collector 安装位置，必须保留该文件；仅把代码克隆到本目录不能替代该依赖。不要在运行中直接改成另一套路径或复制不同实例的运行状态。

## 当前实例绑定

`deployment-20261020/` 中三个 helper 保留该部署的路径约束：

- Compose 项目：`incident-pilot-new7-cloud-20261019`。
- 七身份 manifest：`runtime/private/cloud-new7-20261019/deployment.json`。
- host / schedule 配置：`runtime/private/cloud-longrun/{host,schedule}.json`。
- 统一身份租约：`runtime/private/cloud-longrun/leases/`。
- 主管交接目录：`runtime/private/cloud-longrun/control/`。
- 巡检记录：`runtime/private/cloud-new7-schedule/`。
- 协调者 AMP：`artifacts/cloud-longrun-workbench/transport/amp/`。
- collector 计划、准确容器绑定和收据：`artifacts/cloud-collector-20261019/`。

collector 从本机的 `held-*.json` 读取准确容器 ID，核对项目标签、七个只读来源、五个域状态卷以及固定 offset 卷，不在源码中保存实际 ID。它依赖仓库已有的 `deploy/fluent-bit/{prepare_linux_collector.py,render.py,parsers.conf,kafka-settings.wutong-public.example.json}`、`eval/secret_scan.py` 和 `tools/check_alive.py`。其他 helper 复用 `ops.startup`、`ops.longrun_host`、`ops.aic_lease`、`ops.longrun_status`、`deploy.prepare_deployment` 及阶段 5 所需的项目模块和 vendor SDK；应连同完整仓库及其依赖环境使用。

这些具名实例绑定是归档的一部分。新实例先按自己的 manifest、配置和来源重新准备并审查，不复用另一实例的七身份、held 记录或 offset 卷。`cloud_runtime.py` 默认只输出计划，须显式 `--execute` 才执行；`runtime_snapshot.py` 则是可执行的只读检查，运行时会访问本机状态和官方 Discovery，不能当成离线导入模块。

## 运行约定

四业务容器保持 `restart: unless-stopped`；六域使用 `restart: "no"`，由持有七身份租约的工作台主管恢复。巡检为每 600 秒一次，`drill_auto_approvals=[]`，不启用故障演练。实验必须通过既有 `eval.leased_batch` 和同一个租约目录交接。

工作台 unit 的 `KillMode=none` 与现有暂停协议配套：清理失败时保留现场；成功时由 `stop_managed_host.py` 核对 session、PID、启动时刻、准确命令及七身份后停止该进程。不能用强制关闭或绕过隔离的重启代替正常清理。

首次日志上线顺序是：准备并扫描实际新日志，先启动 `heartbeat,access`，等满 120 秒并核对七身份 `aliveMap` 在线，再正常停止初始 collector，使用同一个 offset 卷扩展为六类。`read_from_head=false`；不要清空 offset 或反复执行首次准备来补发旧日志。长期 supervisor 只接管或恢复已绑定的同一个 collector。

日报配置填写七个正式 AIC、七个准确 AMP 根目录和阶段 6 实际开始发送新日志的 `online_since`。排行榜只保存本队 caller / callee 各自的名次与计数。阶段 8 的排名要求是运行至少两小时后，本队在榜且有正数 Access；备用数据库未被正常巡检调用时不强求它进入调用榜。七身份同时在线由 Discovery 另行证明。

两小时 timer 必须使用实际 `online_since` 生成，不能直接安装含占位符的 `.in`：

```sh
/opt/incident-pilot/.venv/bin/python /opt/incident-pilot/runtime/private/server-tools/prepare_stage8_timer.py \
  --online-since '<与 daily-report.json 相同的实际时间>' \
  --output /etc/systemd/system/incident-stage8-check.timer
```

生成器只新建文件；文件存在时保留原件并报错。核验生成结果后再加载、启动 timer。日报每天北京时间 00:15 执行。两小时 timer 到期后必须读取实际服务结果及 `evidence/longrun-YYYYMMDD/summary-*.json`；安排成功不等于验收通过。24 小时连续运行也需单独积累真实证据。

## 离线测试

从仓库根目录使用已安装项目依赖的 Python 执行：

```sh
python -B -m unittest discover -s deploy/server/tests -v
```

归档后在 Windows 上 67 项通过。测试用假身份、假 Docker / transport / process 和合成排行榜，覆盖来源及 offset 保护、阶段交接、准确停机、日报字段与两小时门槛；不连接服务器，不启停真实服务，不发平台日志。`runtime_snapshot.py` 的真实重启观察仍以云端实际证据为准。

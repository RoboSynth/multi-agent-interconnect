# NEW7 云服务器接手说明

正式七身份只在服务器运行。本地电脑用于开发和离线实验，不启动正式 NEW7、8877 工作台或同身份的其他消费者。工作台仅监听 `127.0.0.1:8877`，订单业务端口不对公网开放。

## 目录与服务

项目根目录为 `/opt/incident-pilot`，以下路径均相对此目录。

| 路径 | 用途 |
| --- | --- |
| `.venv/` | 服务器 Python 环境 |
| `runtime/private/cloud-new7-20261019/deployment.json` | 当前部署清单与配置路径 |
| `runtime/private/cloud-longrun/host.json`、`schedule.json` | 工作台与十分钟巡检配置 |
| `runtime/private/cloud-longrun/control/` | 工作台状态、交接请求、停止回执和运行日志 |
| `runtime/private/cloud-longrun/leases/` | 七身份共用的独占租约与隔离记录 |
| `artifacts/cloud-longrun-workbench/` | 工作台记录；协调者 AMP 位于 `transport/amp/` |
| `artifacts/cloud-collector-20261019/` | 采集源映射、采集器容器绑定与转发记录 |
| `runtime/private/server/daily-report.json` | 每日报告配置 |
| `evidence/longrun-<日期>/` | 每日状态与仅含本队身份的排行榜记录 |

部署辅助脚本位于 `/etc/incident-pilot/`；systemd 单元位于 `/etc/systemd/system/`。证书、私钥和私密配置保留在 `runtime/private/`，不复制到 Git 或证据目录。

| 单元 | 用途 |
| --- | --- |
| `incident-workbench.service` | 启动业务、取得七身份租约、管理六域消费者与工作台 |
| `incident-scheduler.service` | 每 600 秒巡检；故障演练与高风险自动审批关闭 |
| `incident-collector.service` | 正常管理既有日志采集器，沿用采集源与 offset |
| `incident-daily-report.service` | 一次性生成本地状态和本队排行榜记录 |
| `incident-daily-report.timer` | 每天上海时间 00:15 触发报告，错过后补执行一次 |
| `incident-stage8-check.service`、`incident-stage8-check.timer` | 本次部署的一次性两小时查榜验收；已于上海时间 2026-10-20 09:46:49 执行并通过 |

三个常驻服务均设 `Restart=always`。四个业务容器使用 `unless-stopped`；六域身份容器使用 `restart: "no"`，由持有租约的工作台主管启动和关闭。不要给身份容器单独启用 Docker 自动重启，否则会绕过交接和隔离。

## 查看运行状态

```sh
sudo systemctl status incident-workbench.service incident-scheduler.service incident-collector.service --no-pager
sudo systemctl list-timers incident-daily-report.timer incident-stage8-check.timer --all
sudo journalctl -u incident-workbench.service -u incident-scheduler.service -u incident-collector.service -n 100 --no-pager
sudo cat /opt/incident-pilot/runtime/private/cloud-longrun/control/host.json
```

工作台与调度的详细日志也保存在 `runtime/private/cloud-longrun/control/logs/`。检查工作台状态应为 `running`，七身份一致，巡检配置为 600 秒；Discovery 在线、日志本地存在和排行榜计数分别核验。

需要立即生成一份每日报告时：

```sh
sudo systemctl start incident-daily-report.service
sudo journalctl -u incident-daily-report.service -n 50 --no-pager
```

## 正常停止

先停定时报告和采集、调度，再停工作台：

```sh
sudo systemctl stop incident-daily-report.timer
sudo systemctl stop incident-stage8-check.timer
sudo systemctl stop incident-collector.service
sudo systemctl stop incident-scheduler.service
sudo systemctl stop incident-workbench.service
```

工作台停止会请求 `stop_when_idle`，等待当前任务结束、SDK 正常关闭六域消费者并释放租约，随后只停止已核验的主管进程。可能需要等待数分钟。停止后检查 `control/last-stop.json`：`status=stopped`，且 `exact_process_exited`、`consumers_closed`、`lease_released` 均为 `true`。

停止常驻服务会保留业务容器、数据卷、AMP 日志和采集 offset。不要用 `docker compose down -v` 或强杀代替正常交接。

## 启动与恢复

启动工作台并等待实际就绪，然后启动调度和采集：

```sh
sudo systemctl start incident-workbench.service
sudo /opt/incident-pilot/.venv/bin/python -B /etc/incident-pilot/wait_cloud_workbench.py --project-root /opt/incident-pilot --host-config /opt/incident-pilot/runtime/private/cloud-longrun/host.json --execute
sudo systemctl start incident-scheduler.service
sudo systemctl start incident-collector.service
sudo systemctl start incident-daily-report.timer
```

等待命令成功后再执行后续启动命令。采集器自身也会在启动前等待工作台，并核验六域日志源映射；保留原采集器容器、offset 卷和分类型读取进度，只转发新日志，不清空 offset、不补发历史记录。服务器开机自启使用同一顺序，无需手工启动第二套身份。

若状态为 `quarantined`、存在隔离记录或正常停止失败，先保留现场和失败日志，核实具体身份、容器、远端群组及队列/交换机/ACL 的清理结果。不要删除租约或隔离文件、改用新目录绕过，也不要重复强启。确认恢复并保存证据后，再由负责部署的人按实际原因解除隔离。

## 本地打开工作台

在本地终端建立隧道，将占位符替换成自己的 SSH 配置：

```sh
ssh -i "<SSH_KEY>" -N -L 8877:127.0.0.1:8877 <SSH_ACCOUNT>@<SERVER>
```

保持该终端运行，浏览器打开 `http://127.0.0.1:8877`。本地 8877 必须空闲；不需要在本地启动工作台，也不要在服务器开放公网 8877。

## 后续平台实验

新实验通过 `eval/leased_batch.py` 的 `run_leased_batch()` 接入；该模块没有独立命令行，须由具体实验入口绑定计划和授权。显式共用：

- `control_directory=/opt/incident-pilot/runtime/private/cloud-longrun/control`
- `lease_directory=/opt/incident-pilot/runtime/private/cloud-longrun/leases`

实验先请求巡检空闲暂停、确认七身份释放后取得租约。每例恢复资源、通过 H00、关闭消费者及全部自有远端群组，验证完成后才归还身份并恢复巡检；清理不确定时保留隔离。不要另开消费者，或使用默认的另一套租约目录。正式故障实验须另行获得对应范围授权。

## 部署验收记录

时间均为上海时间。原始部署记录在服务器 `evidence/cloud-stage5-*`、`evidence/cloud-stage8-20261020/` 和 `evidence/longrun-20261020/`；可共享副本已汇总到团队仓库 [evidence/cloud-deployment-20261020](../evidence/cloud-deployment-20261020/README.md)。

| 检查 | 实际时间与证据 |
| --- | --- |
| 六域健康任务、30 秒／10 完整订单流程与正常清理 | 已通过。30 次请求、10 个订单流程，failed/unknown/pending=0；SDK 清理修复后六域正常退出、远端群组关闭，复用原 H00；`cloud-stage5-finalize-20261020-r2/result.json` |
| 新日志扫描通过、七身份 aliveMap 在线、六类转发启用 | 2026-10-20 07:51 已通过；零凭据命中/解析错误/读取错误；先 heartbeat+access，七身份在线后扩到全部六类，沿用 offset、不补历史 |
| 三常驻服务及每日报告 timer 开机启用 | 2026-10-20 07:54 已通过；`cloud-stage7-handoff-20261020/runtime-before-reboot.json`；首轮真实巡检已完成 |
| 真实重启后 10 分钟内七身份在线且巡检恢复 | 已通过。07:54:18 请求重启，07:56:23 七身份和三服务自动恢复；08:04:01 首轮巡检自动完成，距请求 582.976 秒；`stage8-reboot-acceptance.json` |
| 上线两小时后“含内部调用”榜出现本队身份 | 已通过。2026-10-20 09:46:49 查询，距日志上线 7201.082 秒；协调身份 caller 第 29 名，Access=76、Message=360，五个其他身份在 callee 榜；七身份全部在线；`stage8-two-hour-acceptance.json` |
| 24 小时连续运行 | 待实际观察完成后记录 |

两小时查榜结果保存在 `evidence/longrun-20261020/summary-*.json` 和 `leaderboard-team-*.json`，只含本队条目。可查看实际执行结果：

```sh
sudo systemctl show incident-stage8-check.service -p Result -p ExecMainStatus -p ActiveState
sudo journalctl -u incident-stage8-check.service --no-pager
```

本次定时器已实际成功执行，退出码 0。只保存本队 caller/callee 的各自名次，不将两榜合并为虚构名次；备用库未被正常巡检调用，未为入榜制造任务。正常停机时停止该一次性 timer；它不是日常巡检的一部分，无需随日常恢复重新启用。

验收窗口共 11 轮巡检全部完成，其中真实重启后 10 轮；没有故障演练。重启后三服务自动重启次数均为 0，内存采样约 38–40%。这些记录包含一次计划内真实重启，不能表述为连续两小时无中断；24 小时连续运行仍需实际观察。

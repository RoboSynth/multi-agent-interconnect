# NEW7 云服务器接手说明

## 2026-10-26 外部智能体轮流调用

服务器运行 `incident-external-rotation.service` 与 `incident-external-rotation.timer`。定时器已由每 30 分钟调整为每 5 分钟执行一个任务，在信息来源与事实核验、论文评审与学术写作、笔试训练、校园学习生活助手四个外部智能体之间轮换。

首批 12 项的结果已保存。后续按各服务公布的能力修订为 24 项不同请求，任务 ID 为 `aligned-01-1` 至 `aligned-06-4`，分别用于来源事实核验、研究内容评审、校招四选一训练及大学生学习规划；完成后停用定时器。原有成功、拒绝、失败和调度跳过记录继续保留，旧版未执行任务标记为 `superseded_before_execution`。本轮修订为新请求恢复三项服务，后续单个服务执行失败时仍跳过其剩余任务。

频率部署记录和当前请求列表见 `artifacts/external-call-20261026/frequency-update-*.json`、`aligned-update-*.json` 与 `aligned-five-minute-jobs.json`。服务器保留修改前的计划、状态及定时器副本，位于原计划目录的 `frequency-backup-*`、`scope-backup-*` 子目录。

- 运行器：`ops/external_rotation.py`、`ops/external_rpc_once.py`。
- 计划与状态：`runtime/private/external-rotation-20261026/plan.json`、`state.json`。
- 任务输入、返回原件和文本结果：`evidence/external-rotation-20261026/<任务编号>/`。
- 调用采用官方 SDK 的 HTTPS/mTLS RPC，通过现有协调者身份和采集目录记录实际访问。

查看队列与下次执行时间：

```sh
sudo /opt/incident-pilot/.venv/bin/python -B /opt/incident-pilot/ops/external_rotation.py --plan /opt/incident-pilot/runtime/private/external-rotation-20261026/plan.json --status
sudo systemctl list-timers incident-external-rotation.timer --all --no-pager
sudo journalctl -u incident-external-rotation.service -n 30 --no-pager
```

停止后续轮询：

```sh
sudo systemctl disable --now incident-external-rotation.timer
```

已经开始的任务会按本次执行的时限结束并保存结果。首次五服务试运行有四项完成、一项文献任务超时；文献服务未进入上述轮询名单。平台外部访问计数与业务成功数分别记录。

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

### 本机公网地址变化后恢复 SSH

服务器 UFW 的 SSH 规则限定连接来源。本机更换网络或校园网出口变化后，即使平台心跳正常，新 SSH 也可能超时。先核对本机当前公网 IP 与服务器现有规则；确认不一致后，在腾讯云实例的“执行命令”或网页终端执行：

```sh
sudo ufw allow from <YOUR_PUBLIC_IP> to any port 22 proto tcp
sudo ufw status numbered
```

在本机用原私钥和已保存的服务器指纹重新连接，并核实三个常驻服务和工作台状态。本次 2026-10-20 的连接中断即由来源地址变化引起；用户新增精确来源规则后恢复连接，原 host session 和采集器实例保持。

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

## 2026-10-20 后续维护

公开体检补丁通过统一租约交接上线，此次镜像为 `sha256:91e51b8c1c6a92ad60eeee9c67810307671d8f32e45454c94016771cecdcdac4`，原镜像保留为 `incident-pilot-pre-public-onboarding:20261020`。更新加入普通文本只读体检、中文结果和有上限的多群组接入；非公开资源域维持原限制。Linux 38 项测试、业务 H00、非白名单身份三项实际往返和群组正常关闭已通过，见[公开体检验收](../evidence/public-onboarding-20261020/README.md)。此计划内维护必须保留在长期运行时间线上。

随后[云端四例复验](../evidence/cloud-four-revalidation-20261020/README.md)取得2项功能通过，另2项因订单编号超限在初始业务基线失败；42/42真实任务、84条access完整配对，所有资源恢复与正常清理通过。未将两个未进入接管的案例改判为通过。

为修复上述基线问题，单独上线了 `business/load.py` 的长编号处理。**当前六域镜像为 `sha256:110d145f430217affeb09ed85257f59738a3c7b19509bc37905e79818ccd7d8b`**；仅此一个文件变化，其余25项核对一致，上一镜像保留为 `incident-pilot-pre-observer-key:20261020`。同27项检查在Windows和Linux分别通过；原失败形状的长编号真实H00完成30次成功请求、10个完整订单流程，创建和取消编号分别70/77字符。

本次通过相同租约交接于2026-10-20 **03:52:26 UTC**恢复，首轮定时巡检于03:57:02 UTC完成，最终11项运行检查均通过。原采集器、七源和42行offset保持，无倒退。见[长编号维护证据](../evidence/observer-key-maintenance-20261020/README.md)。24小时连续记录从这次最新恢复后继续积累；此次正常业务验证没有追加故障接管案例。后续P5调度修复仍为独立离线版本，未混入当前云镜像。

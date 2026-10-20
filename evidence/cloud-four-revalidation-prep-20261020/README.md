# 云端四例接管复验：准备与执行边界

本批按用户最新授权准备，不复用已消耗的旧四例授权，也不改写旧结果。当前目录只完成本地执行器和离线验证；尚未在云端生成绑定实际私密配置的四份计划，未请求巡检交接，未启动消费者或故障。正式开始前由负责云部署的主任务把当前代码同步到服务器并完成下面的只读检查。

| 顺序 | 例项 | 唯一中断 / 方法 | 实际效果 |
| ---: | --- | --- | --- |
| 1 | F10 | M0，一次 | 当前项目旧路由、数据库只读、失效连接池的复合故障与有审批修复 |
| 2 | E1-a | after_observation，一次 | 主库智能体观察后退出 81，备用继续；恢复写入与连接池 |
| 3 | E1-a | before_modification，一次 | 主库智能体收到修改请求但执行前退出 82，备用继续 |
| 4 | E1-a | after_applied，一次 | 主库智能体实际修改后、提交结果前退出 83，备用识别已应用结果 |

四例串行，模型调用 0。每例使用新事故 ID、操作 ID、计划、结果目录；计划和授权逐字节绑定。每例尝试关闭准确自有群组、恢复资源与正常数据库 worker，最后独立验证 30 秒、至少 10 个完整订单流程。主备原 journal 的 access 恢复在 `--network none`、只读根文件系统、限定原域配置与状态卷的容器中进行；不读任意历史目录，不补发旧日志。

## 云资源与交接

复用已部署的 `/opt/incident-pilot` 和 `incident-pilot-new7-cloud-20261019` 项目，不另建数据库或订单业务，不增公网端口。实际四个回环业务端口从本次 `deployment.json` 的 target 读取并冻结，执行前再次核对。沿用六域的五个状态卷（数据库主备共享一个）、原七身份与域配置、既有 agent 镜像；不在云端构建或拉取镜像。

固定使用：

- `control_directory=/opt/incident-pilot/runtime/private/cloud-longrun/control`
- `lease_directory=/opt/incident-pilot/runtime/private/cloud-longrun/leases`

执行器调用 `eval.leased_batch.run_leased_batch()`。先请求现有主管空闲暂停，确认六域和协调者正常关闭且七身份释放后，才取得这七个身份。不得另设租约目录、手删隔离或直接启动第二套消费者。每例结束关闭自己的六域并核对准确 ID、正常退出 0、六份匹配角色和 batch session 的 SDK 清理收据；全部已尝试例项的恢复、H00 与清理确认完成后才归还身份，请求主管恢复巡检。清理未知时保存原结果、隔离身份并保留未尝试例项。

现有 E1 校验要求正常数据库 `Config.Cmd` 保持 `python -m acps_mcp_bridge --config /domain/bridge.json`，所以本批不直接使用长期主管的 domain_entry 命令。准备器只生成本批 Compose override，通过单独 `entrypoint` 和两个只读脚本挂载，保留正常与实验 worker 的原 `Cmd`；适配器复用 `ops.domain_entry.run_managed()`，收到正常终止信号时等待原 SDK `finally` 完成。计划内 `os._exit(81/82/83)` 保留原行为。六域 `restart: no`，不绕过身份租约。长期 worker、体检代码和业务配置均不由本执行器修改。

collector 沿用现有容器和 offset 卷，域日志仍来自同五个状态卷；不清空进度。实验协调者 AMP 保存在各例独立输出目录，当前常驻 collector 的协调者来源仍是工作台目录。因此本批用于验证接管与日志持久性；不把其全部实验调用都说成已配对计入平台排名。正常巡检恢复后继续积累平台访问量。

## 云端只读前置检查

1. 工作台、scheduler、collector active/enabled，host 状态为 running；三个 systemd 主管 PID 与 API 状态一致。确认没有当前巡检、审批或未知操作占用七身份；交接本身会等待空闲，超时保留现场。
2. 本地及队友没有七身份消费者。统一租约目录无未解决隔离；远端旧批群组清理有确切收据。不删除旧隔离来通过前置检查。
3. 当前四业务健康，六域镜像和配置挂载属于准确项目；记录业务容器 ID、启动时刻与镜像 ID。核对 agent 镜像 ID 和当前 product / SDK 源码。`DOMAIN_SOURCE_FILES` 或 AMP 文件与镜像不符时先解决绑定，不能靠改 SHA 或计划掩盖。
4. 当前 SDK 已含网络重试与正常群组清理修复，相关测试通过。`ops/domain_entry.py` 的字节、原 worker 命令、单域只读配置挂载、原五状态卷均保持。
5. 可用磁盘/内存足以容纳四例记录与串行网络隔离的 journal 恢复容器；本批不运行模型。证书仍有效、主备 operation ledger 没有活动/unknown 操作，计划 ID 没有使用过。
6. 记录当前完整提交号、实际 agent image ID，之后运行文件准备。准备只读取配置与文件 SHA，不访问 Docker、平台或订单业务；生成后用 `validate` 重新校验。将真实用户授权记录绑定到这份新计划，不再次向用户索取已给授权。

## 命令入口

以下命令只是供主任务审查；本地准备阶段没有执行其中的云端命令。`<...>` 必须替换为当前实测值。先在服务器仓库根运行只读说明：

```sh
sudo /opt/incident-pilot/.venv/bin/python -B evidence/cloud-four-revalidation-prep-20261020/cloud_batch.py describe
```

创建全新私密目录，绑定当前部署、源码、镜像和三份 E1 worker bundle：

```sh
sudo /opt/incident-pilot/.venv/bin/python -B evidence/cloud-four-revalidation-prep-20261020/cloud_batch.py prepare \
  --directory runtime/private/cloud-four-revalidation-<本批唯一后缀> \
  --image-id '<实测 sha256:...>' --source-commit '<当前完整提交号>'
```

输出 `batch-plan.json`、三份严格 E1 计划与 bundle、一份 F10 计划，以及保留原命令的六域 override。准备器不会覆盖任何既有目录。将当前会话真实授权的接收时间和原文写入一份私密 JSON，只含 `received_at_utc`、`user_confirmation` 两个非空字符串，再执行：

```sh
sudo /opt/incident-pilot/.venv/bin/python -B evidence/cloud-four-revalidation-prep-20261020/cloud_batch.py bind-authorization \
  --plan runtime/private/cloud-four-revalidation-<本批唯一后缀>/batch-plan.json \
  --authorization-record '<本批真实授权记录路径>'
```

绑定只写本批授权，不启动运行。最后核对计划与授权后，主任务明确开始本批时执行：

```sh
sudo /opt/incident-pilot/.venv/bin/python -B evidence/cloud-four-revalidation-prep-20261020/cloud_batch.py execute \
  --plan runtime/private/cloud-four-revalidation-<本批唯一后缀>/batch-plan.json \
  --authorization-file runtime/private/cloud-four-revalidation-<本批唯一后缀>/authorization.json
```

结果位于计划指定的新 `eval/results/platform/cloud-four-*/` 和私密准备目录的 `ownership-*/`；原失败、清理错误、未尝试项全部保留。批次最后写 `inspection_returned`，它只证明已经归还租约和发出恢复请求；主任务仍须实际等待 host running、七身份 Discovery 在线、collector 源映射未变与巡检恢复，才能记录恢复完成。

## 验证与结论边界

本机测试命令：

```sh
python -B -m unittest discover -s evidence/cloud-four-revalidation-prep-20261020 -p test_cloud_batch.py -v
```

测试覆盖准确四例范围、统一租约、授权绑定、原命令保留、未知命令拒绝、仅采纳自有主备替换 ID，以及真实取消协议下等待清理 finally / 清理失败不出成功收据。测试只用假 worker，不启动真实消费者或故障。云端 Compose 渲染、镜像来源证明、正常停机和四例效果尚需实际验证。

每个 E1 通过后还需按本例 taskId 核验 access：原 journal 有结果的任务都恰有一条相应 access，缺口恢复是本例新增记录，不能把共享卷里旧例的记录当成本例成果。不要改写旧四例、旧 22/12 例结论；本批 4 次不能构成三方法性能比较，也不能代替另一台机器从零部署或 24 小时连续运行证据。

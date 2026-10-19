# 今晚计划：Windows 本地就绪度

本记录只覆盖离线检查、文件存在性和运行时只读查询，不是部署或平台入库验收。

后续已经生成新manifest并完成本地镜像构建、启动任务与collector文件准备，最新状态见[本轮汇总](../README.md)；下文保留这些动作之前的就绪度快照。

## 离线检查

`test_schedule.py`、`test_schedule_rotation.py`、`test_managed_startup.py`、`test_longrun_status.py` 共 **14 项通过，0 失败、0 错误、0 跳过**。完整输出见 `test-readiness.txt`，机器摘要见 `checks.json`。异步调度使用 MockTransport/AsyncMock；未派发真实任务或故障。

NEW7 的 `ops/schedule.new7.example.json` 为 600 秒，受管启动生成器 `prepare_tasks()` 与 `--inspect-minutes` 默认均为 10 分钟。修正了 `docs/windows_startup.md` 受管模式仍写默认 30 分钟，以及 `ops/startup.py` 非法参数错误提示仍写 30 为默认的文案。旧 `ops/schedule.example.json` 和 `Scheduler` 缺省 1800 秒保留兼容；旧单任务启动文档仍对应每 30 分钟。

三个受管任务的 XML 生成入口是 `ops/startup.py`，默认只准备文件；`--template-only` 跳过真实部署 manifest 检查，不能当成运行就绪。三任务分别准备业务资源、工作台、巡检，触发方式是当前用户登录；不设置自动登录或系统睡眠。原 `ops/install_startup.ps1` 仍是单 scheduler 的旧入口，不能替代三任务生成器。

## 当前本机运行时

只读查询 `runtime-read-only.json` 确认 `Ubuntu-22.04` 当前为 Running、WSL 2；`/usr/bin/docker --host unix:///var/run/docker.sock info` 返回 `linux`，Compose 版本 `2.40.3+ds1-0ubuntu1~22.04.1`。查询未启动 Docker 服务或任何容器。WSL 报告 localhost 代理没有镜像进 NAT 环境；本轮未改代理，镜像构建联网是否成功仍须实际构建验证。

`available-images.json` 保留当前 `incident-pilot*` 镜像清单；存在旧 NEW7 和后续验收镜像。它们不能代表本轮源码已构建。与既有 28 文件镜像来源记录相比，当前 8 文件已经变化，见 `deployment-preflight.json`；当前源码还增加了该历史清单未覆盖的新文件，因此不把该比较当成完整镜像来源证明。

`deploy/Dockerfile.agent` 从当前 checkout 复制 SDK、business、incident、acps_mcp_bridge、domains 等代码，重新构建后才能包含本轮 SDK 与 symptom_check 修改。`deploy/prepare_deployment.py` 的 `launch()` 为七身份模式构建两业务应用及一次共享智能体镜像，随后部署；本轮未调用。

## 新受管部署还缺实际准备

当前团队 checkout 没有 `runtime/private`，`ops/longrun.example.json` 的 `runtime/private/my-seven/deployment.json` 是占位路径。原 `incident-pilot/runtime/private/new7-container-20261018` 是旧手工配置，不能直接视为新受管 manifest。

可复用的身份文件候选为：

`D:/AI + 开源/incident-pilot/runtime/private/new7-container-20261018/source.json`

仅检查了结构和路径存在性：七个预期角色齐全、AIC 互异、7 份证书与 7 份私钥及信任链文件均存在；没有读取私钥内容，没有核验有效期、私钥匹配或跨电脑消费者独占。详见 `deployment-preflight.json`。

新 manifest 的准备流程见 `deploy/ISOLATED.md` 七身份段和 `deploy/README.md` 第 8 步：从团队 checkout 调用 `prepare_deployment.py --mode seven --identity-file <上述绝对路径> --output <checkout 内新空目录> --project <新项目> --wsl Ubuntu-22.04`，同时指定一组可用端口。它会生成新的 `deployment.json`、`target.json`、七域配置与独立业务凭据；之后让 longrun host/scheduler 指向该 manifest、同一持久状态目录及同一控制目录。仍需在实际启动前核对七身份独占、端口、旧消费者正常退出，并执行真实镜像构建与 H00。

## 日志扫描与用户消息边界

扫描对象应当是新部署后明确收集的六类日志，并保留每个来源/类型的路径与时间边界；不要扫描整个私密部署目录后把必然存在的域内凭据当成日志泄漏，也不要把旧日志扫描称为本轮新日志验收。扫描器的 JSON 解析和内容覆盖改进由本轮根代理单独处理，此处未重复修改或遍历历史日志。

`docs/接下来的行动_20261019.md` 末尾是可粘贴的授权模板。用户本次直接消息转述计划、说明模板位置，尚未直接粘贴其中“授权以下事项”正文；该附带模板自身不执行提交、推送、部署、日志外发或注册任务授权。本轮先完成可审阅的本地准备，由根代理确认后续实际动作范围。

本轮未注册任务、改睡眠/自动登录、启动消费者、发送 Kafka 日志、运行故障实验、提交或推送。24 小时窗口尚未开始。

# 服务器部署任务（给 GPT）

目标：把 NEW7 七个正式身份、订单业务、巡检调度和日志转发全部迁到一台国内云服务器（Ubuntu 22.04，2 核 4G）上 24 小时运行，访问量按平台口径进入梧桐排行榜。本地电脑以后只做开发和本地实验，不再运行任何正式身份。

## 开始前需要用户提供

- 服务器公网 IP、SSH 用户名、SSH 私钥在本机的路径（用密钥登录，不用密码）
- 确认本地 WSL 里的 NEW7 容器、8877 工作台和巡检都已停止（同一身份只能有一个消费者）

## 分阶段执行（每阶段完成后回报“完成 / 证据路径 / 问题”，失败就停）

### 阶段 1：服务器基础环境

1. `apt update && apt upgrade`；时区设为 `Asia/Shanghai`；开启 `chrony` 时间同步（证书校验和 AMP 时间戳依赖准确时间）。
2. 内存小于 8G 时建 2–4G 交换分区。
3. 安装 Docker Engine 和 compose 插件，设为开机自启；新建普通用户 `incident` 并加入 docker 组，项目目录 `/opt/incident-pilot`。
4. 防火墙只开放入站 22，并尽量限制为用户的 IP；不开放任何业务端口，工作台只监听 127.0.0.1。
5. 端口出站测试：`nc -vz wt.ioa.pub 443`、`5671`、`9007`、`19092` 全部成功。

### 阶段 2：代码与 Python 环境

1. `git clone` 团队仓库，切到 `tech-plan-20261019` 分支并记录提交号。改造后的 SDK 在 `vendor/ACPs-community`，确认它随仓库一起拿到。
2. Ubuntu 22.04 自带 Python 3.10，项目需要 3.12：用 `uv python install 3.12` 建 `.venv`，按 `requirements-high-score.txt` 安装；数据库 MCP 另建 `.venv-mcp-postgres`。
3. 在服务器上跑一遍离线测试（SDK、传输、租约、日志转发、调度相关），全部通过再继续。

### 阶段 3：镜像

1. 在本机 WSL 用同一提交构建 agent 镜像和两个应用镜像（先单独构建 agent 镜像，见 `deploy/NEW7.md`）。
2. `docker save … | gzip` 打包，`scp` 传到服务器，`docker load` 导入；核对镜像 ID 与本机一致。PostgreSQL、Nginx、Fluent Bit 等官方镜像同样从本机打包，不在服务器上直接拉取。

### 阶段 4：身份与私密配置

1. 用 `scp` 只传七个身份的证书、私钥、信任包和 `runtime/private` 下 NEW7 需要的配置；私钥权限 600，目录 700。这些文件不得进入 Git、日志或证据目录。
2. 按服务器路径重新生成部署配置（`deploy/prepare_agents.py` / `deploy/prepare_deployment.py`），体检智能体带 `--include-onboarding --public-onboarding`。
3. 对生成的配置跑一次 `eval/secret_scan.py`，确认协调者配置里资源凭据为 0。

### 阶段 5：部署与健康检查

1. 按 `deploy/NEW7.md` 首次部署 10 个容器（`up --no-build`），所有容器 `restart: unless-stopped`。
2. 启动协调者，跑一次 H00 健康窗口：六域 describe、观察、verify 全部完成，30 秒 / 10 个完整订单流程，failed/unknown/pending 均为 0。
3. 记录 `docker stats --no-stream` 和 `free -h`；巡检时内存长期超过 80% 就提醒用户升配。

### 阶段 6：日志上报（分阶段）

1. 对新部署产生的六类日志跑 `eval/secret_scan.py`：命中 0、解析错误 0 才继续。
2. 用 `deploy/fluent-bit/prepare_linux_collector.py --mode kafka --kinds heartbeat,access` 准备采集器（新的 offset 卷，只发新行），启动。
3. 2 分钟后用 `tools/check_alive.py --query` 查七个 AIC 的 `aliveMap`，全部在线后改为 `--kinds all` 重新准备并启动。
4. 不补发历史日志。

### 阶段 7：常驻运行

1. 用 systemd 管理三项：工作台（`workbench_server.py --port 8877`，只监听 127.0.0.1）、巡检调度（10 分钟一轮，`ops/schedule.new7.example.json` 为模板，故障演练和高风险自动审批保持关闭）、日志采集器。都设 `Restart=always`、开机自启，启动顺序为 Docker → 容器 → 工作台 → 调度 → 采集器。
2. 平台实验以后一律通过 `eval/leased_batch.py` 运行，自动暂停和恢复巡检。
3. 加一个每天运行一次的 systemd timer：执行 `ops/longrun_status.py`，再查询公开排行榜接口 `https://wt.ioa.pub/internal/matched-stats/top`（startAt 为 `2026-09-24T00:00:00+08:00`），结果存到 `evidence/longrun-<日期>/`，只保存本队七个 AIC 的条目。

### 阶段 8：验收

1. 重启服务器，不做任何操作，10 分钟内七个身份恢复在线、巡检恢复。
2. 上线 2 小时后查排行榜接口，本队 AIC 出现在“含内部调用”榜上（按小时汇总，可能有延迟）。
3. 写 `deploy/SERVER.md`：服务器上的目录结构、systemd 服务名、查看状态、停止和恢复的命令、本地如何通过 `ssh -L 8877:127.0.0.1:8877` 打开工作台。不写 IP、用户名和任何私密信息。

## 不要做的事

- 不在服务器上构建镜像、跑大模型或做 P5 本地实验。
- 不在本地电脑再启动任何正式身份；本地开发用本地通道。
- 不加快巡检频率、不写空转调用；不对外发消息（QQ 群由用户发）。
- 不修改已冻结的历史结果。

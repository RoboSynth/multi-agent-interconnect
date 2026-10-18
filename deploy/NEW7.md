# 新七角色隔离容器 profile

2026-10-18 已逐角色核实七个新版身份的名称、正式 AIC 和审核通过状态；用户授权后，七个身份分别领取 EAB，官方 CLI 各签发一次客户端证书且退出码均为 0。各证书的 AIC、clientAuth、当前有效期和私钥匹配检查通过，均有效至 2026-12-06 的对应 UTC 时刻。源材料保存在独立私密目录；公开摘要见[证书办理记录](../evidence/platform-certificates-20261018/summary.json)。此前 2026-10-17 的证书暂缓安排已被本次授权与实际结果更新。

七个新版 AIC 的官方 ADP 精确只读查询均已通过，公开 Inbox 端点与已提交 ACS 的身份绑定一致，见[元数据观察](../evidence/platform-certificates-20261018/adp-identity-observation.json)。本轮已实际部署独立 NEW7 容器项目，并由独占的 Windows 协调进程完成六域正式 AMQPS 健康运行：6 项 describe 和 6 项正常任务、30.003 秒/30 次成功请求/10 个完整流程，自有群组正常关闭。首次健康运行见[历史截面](../docs/new7_platform_20261018.md)。后续[正式 E3](../docs/new7_e3_20261018.md)已闭合 45 格：37 格确认、8 格 M1 未确认；8877 持续巡检已启动，[第九次点观察](../evidence/new7-runtime-followup-20261018/inspect-ninth-cycle.json)仅核当时身份与最新周期。正式接管与 24 小时验收仍待完成。

## 资源和身份归属

| 项目 | 新 profile | 现有资源 |
| --- | --- | --- |
| Compose project | `incident-pilot-new7` | 旧 T07 为 `incident-pilot-container` |
| 业务入口 | `127.0.0.1:38088` | 旧 18088、团队冷部署 28088、原生 8088 分离 |
| 应用 v1 / v2 | 回环 38081 / 38082 | 旧 18081 / 18082、原生 8081 / 8082 分离 |
| 协调工作台 | Windows 回环 8877，已启动独占身份的持续巡检 | 旧 8767 / T07 保持原身份与原资源 |
| 业务数据库 | `incident-pilot-new7_orders-data`，无主机端口 | 不挂旧业务或原生数据库目录 |
| 路由目录 | `runtime/private/new7-container-20261018/nginx-runtime` | 不写 `deploy/nginx/runtime` 或旧路由 |
| 配置与证书 | 同目录下 `domains/<role>`，每容器一个只读 `/domain` | 不复用旧身份的私钥、挂载目录或 Inbox |
| 域状态 | `incident-pilot-new7_<role>-agent-state` | 与旧 project 卷分离 |

六域为 application、verification、database、database-backup、ops、onboarding。应用只收到本域 APP_ADMIN_TOKEN；数据库主备只收到 bridge_operator 的 DATABASE_URI 和审批校验密钥；运维只收到本域审批校验密钥，并独占 Docker socket 挂载。验证和 onboarding 无资源管理环境文件。onboarding 仅检查公开 ADP/ACS 元数据，不主动探测目标端点。协调者只持自己的证书、审批签发能力和公开发现配置，不持上述资源凭据。

数据库主备在新项目内共享同一个 `database-agent-state:/state`，因而共享 `/state/operations.sqlite`；各自 AMP 子目录分离。协调者的权威任期库放在新 profile 的 `domains/coordinator/coordinator-terms.sqlite`，namespace 为 `incident-pilot-new7/orders`。它仅授权新业务卷，不能拿来操作旧 180xx 资源。

新主数据库 AIC 的实体段为 `OJQHYH`，备用为 `FZXFJS`；备用字典序在前。准备器生成 `trusted_participant_aics.database=[主,备]`，并显式生成 `initial_participant_aics.database=主 AIC`。初选按这个精确身份与 trusted 集合求交；接管仍可发现完整可信集合。列表顺序不表示优先级。verification / onboarding 的正式 AIC 已从各自详情页核实，实体段分别为 `3NST76` / `46ZKB8`；全七角色证书现已实际签发。源配置须引用此次逐角色匹配的材料，不能复用旧四身份或仅靠 ADP 候选填写。

## 证书就绪后的准备步骤

以下为首次准备与部署的复现步骤；本轮对应项目已部署，不应在现有非空输出目录重复初始化或另启同 AIC 消费者。准备器会在读取资源环境和复制证书前拒绝跨域或协调者 AIC 重复。签证后仍需核对部署副本中的 AIC、信任链及有效期，并确认同 AIC 没有第二个 Inbox 消费者。源配置格式沿用 `domains/setup_platform.py`：`agents.leader/application/verification/database/database_backup/ops/onboarding` 各指自己的绝对 cert/key 路径及精确 AMQPS Inbox endpoint。

1. 在 `runtime/private/new7-container-20261018` 新建独立的 compose.env 和 approval.env，生成新的随机凭据；不得复制旧 container.env。compose.env 包含 `POSTGRES_PASSWORD`、`ORDERS_DB_PASSWORD`、`APP_ADMIN_TOKEN`、`BRIDGE_DB_PASSWORD`，approval.env 只保存新的 `INCIDENT_APPROVAL_SECRET`。
2. compose.env 另加 `NEW7_DOMAIN_ROOT` 和 `NEW7_ROUTE_DIR`，值使用 WSL 可见的绝对路径，例如 `/mnt/d/AI + 开源/incident-pilot/runtime/private/new7-container-20261018/domains` 和同级 `nginx-runtime`。本 overlay 固定回环 380xx，不使用基础 APP_V1_PORT / APP_V2_PORT / ORDER_PORT。
3. 用准备器生成本域文件。输出目录须为空；准备器不会联网、启动或注册身份，也不验证证书密码学有效性。若缺 BRIDGE_DB_PASSWORD，它会把新随机值追加到本次指定的 compose.env。

```powershell
.\.venv\Scripts\python.exe domains/setup_platform.py --source integration/private/new7/source.json --output runtime/private/new7-container-20261018/platform
.\.venv\Scripts\python.exe deploy/prepare_agents.py --source runtime/private/new7-container-20261018/platform --output runtime/private/new7-container-20261018/domains --business-env runtime/private/new7-container-20261018/compose.env --approval-env runtime/private/new7-container-20261018/approval.env --project incident-pilot-new7 --include-onboarding --include-coordinator --ops-service app-v2
if (-not (Test-Path runtime/private/new7-container-20261018/nginx-runtime/route.conf)) {
    New-Item -ItemType Directory -Force runtime/private/new7-container-20261018/nginx-runtime | Out-Null
    Copy-Item deploy/nginx/route.default.conf runtime/private/new7-container-20261018/nginx-runtime/route.conf
}
```

路由复制只在本次新目录不存在 route.conf 时执行，后续运行保留实际路由。协调者配置在 `domains/coordinator/config.json`，是 Windows 绝对证书路径；六域配置使用 `/domain`、`/state` 和固定容器 DNS。准备器仅做静态准备，即使文件存在也标记 `ready_for_live_start=false`；该字段不能代替当前运行状态，真实握手和业务验收在本轮运行证据中另记。

4. 在 WSL 的项目目录依次运行同一组 Compose 参数。真实 env 仅用 `config --quiet` 验证，不向终端打印展开配置。若需要核对 scope，完整 JSON 只捕获到本机私有文件，再仅输出 project、端口、mount、volume 元数据；本次 sentinel dry-run 的 JSON 可直接渲染。

```sh
new7_compose() {
    env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
        docker --host unix:///var/run/docker.sock compose -p incident-pilot-new7 \
        --env-file runtime/private/new7-container-20261018/compose.env \
        -f deploy/compose.yml -f deploy/agents.yml -f deploy/new7.yml --profile new7 "$@"
}
new7_compose config --quiet
# 首次部署先确认新 project 与端口可用；当前已部署项目不要重复启动协调者。
docker --host unix:///var/run/docker.sock build -f deploy/Dockerfile.agent -t incident-pilot-agent:new7 .
new7_compose build app-v1 app-v2
new7_compose up -d --no-build
```

`deploy/new7.yml` 需要 Compose 2.24.4+ 的 `!override`，清除旧 808x 端口；本机离线验证使用现有 Compose 2.40.3。新 agent 镜像使用 `incident-pilot-agent:new7`，先单独构建一次，再构建 app-v1/app-v2，最后 `up --no-build`，避免六域同时构建同一个 tag。首次必须从当时的冻结源码重建；不能把旧镜像缓存当成当前版本。记录实际 image ID，并只读采集容器内固定源码 SHA 与冻结源码对应；后续 cell 可复用相同 image ID 的稳定性证据。同 tag 重建不会改变已经运行的旧容器，本批不对旧 T07 执行 up/recreate。六个域目录和独立路由目录必须先存在，避免 Docker 把缺失文件路径创建成目录。初次空业务卷通过现有 init.sh 创建 bridge_operator 最小权限；若人为复用已有卷，必须明确执行本项目 provisioning，不能删除卷冒充迁移成功。

运维私有 policy 固定三项 scope：`compose_project=incident-pilot-new7`、`compose_service=app-v2`、`container_name=incident-pilot-new7-app-v2-1`；观察使用 incident-pilot、project、service 三标签，restart/logs 不接受任务传入目标容器。桥接层重新核验实时标签和名字，再使用 immutable container ID。新配置不会放宽原有 high 审批或幂等策略。

## leader 独占和验收顺序

`platform_smoke`、E3 `eval/run.py`、8877 工作台都会创建 Wutong leader，不能同时复用新版 coordinator AIC。域参与者也只接受一个 active inbound group。平台健康 smoke 和正式 E3 均已闭合，随后已启动独占身份的 8877 巡检。后续新实验前，须先在空闲边界正常停止同 AIC 的巡检并核对群组关闭；新故障或正式接管须另行明确范围，不能复用已结束 E3 的原批授权。异常/超时组先保留证据，不通过杀域进程或删除未知远端组绕过。旧 8767/T07 使用旧 AIC，继续只操作旧 180xx，不加入新组。

2026-10-17 的非秘密 E3 target 保留为历史草稿：`artifacts/new7-container-plan-20261017/evaluator-target.draft.json`。它仍含 20261017 的旧 env/route 路径，不能作为上表 20261018 部署的当前评测入口；原件不改写。后续已生成独立 revision 2 并完成上述 E3；新实验仍须重新绑定 env、route、源码摘要及授权，不能使用该历史草稿直接运行。评测器独立子进程读取业务 env；协调者只读 target 描述及文件 hash。正式注入前评测器还会核验 live project 标签、loopback 端口、数据库卷名前缀及 nginx/ops 的精确路由 bind。

最后启动工作台时，使用系统环境白名单加显式项目网络变量（本机平台直连可设仅此进程的 `NO_PROXY=wt.ioa.pub,127.0.0.1,localhost`），并以实际子进程的环境名称探针证明资源凭据为 0。不要将 resource compose.env 加载进协调者 shell。保留 Windows 回环 8877 的现有本机访问规则。健康基线须完成 30 秒 / 10 个创建、查询、取消流程，再声明业务可用；running 不能代替 describe 或业务 ready。

## 2026-10-17 离线准备记录（历史）

`artifacts/new7-container-plan-20261017/dry-run-results.json` 记录实际 Compose CLI 渲染断言：基础不带 profile 仍仅四个业务服务；旧 agents profile 仍仅五域，onboarding 必须显式选择；新 profile 为六域、固定 380xx、独立路由及新项目卷。`compose.dry-run.env` 全部使用明显 sentinel，不读取真实私有 env；仅运行 config，没有 Docker up、远端群组或新身份启动。准备器测试使用临时文本证书路径 fixture，证明每域只复制本身份材料、协调者无资源凭据、主备账本及初选主配置一致；这些不是证书签发或真实平台运行证据。

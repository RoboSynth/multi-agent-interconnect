# 隔离七身份部署与正式 E1/F12 准备：只读审阅

检查基线为本批 checkout `4f157a1`。未执行构建、Compose、Docker、平台、模型或故障；只读取源码。

唯一实质阻断：`deploy/compose.yml:84` 的 reply-drop 只有 build，没有显式 image；`deploy/prepare_deployment.py:64` 的 overlay 原来只绑定六域的镜像。`eval/inject.py:380` 强制该服务有已存在的 image，且不可变 ID 等于正在运行的 app-v2。仅构建 app-v2 和 agent 不能保证这一前置。应把 app-v2 与 reply-drop 显式绑定到同一项目的应用镜像，并严格保留旧 manifest/overlay 读取兼容；不得放宽 Injector 守卫。

其余所查主线一致：

- 六域统一 `<project>-agent:local` 和 isolated profile；基础 agents 使用 init:true/read_only:true。E1-c 仅主 overlay 明示 init:true，父控制器允许此窄差异并核它为 true。
- 主备正常 Cmd 均为 `python -m acps_mcp_bridge --config /domain/bridge.json`；各自 /domain 只读，二者共享同一项目的 database-agent-state 卷和 /state/operations.sqlite。实验只另挂只读 /experiment，父控制器逐项绑定。
- 宿主协调者最终 cert/key/trust/approval 与 term 路径均为本 checkout 内绝对路径，term namespace 为 `<project>/orders`；审批 secret 由同一生成值分发给各域和协调者，不由协调者加载业务数据库凭据。
- 新 seven target 显式携带互异 reply_drop 第四端口，旧三端口仅用于旧场景。ops 与 nginx 指向本输出独立 route 目录，数据库卷按项目隔离。

只构建 agent 可直接使用当前 checkout 的 Dockerfile.agent 和 tag `<project>-agent:local`；不调用 prepare_deployment --launch（它包含 up）。复用已有 Docker 层缓存，不加 --no-cache/--pull；SDK COPY 或依赖清单变化可能使 pip 层重新下载，缓存命中不能静态保证。若必须禁止依赖网络，可加 build --network=none，使未命中依赖层明确失败。Docker build 本身不创建平台 consumer。

构建后应只用 network-none 临时探针和 image inspect 绑定不可变 ID、实际 import 路径、UID/GID、当前 DOMAIN_SOURCE_FILES、AMP emitter 和 business/receipts.py/load.py；实际启动后的挂载与 StartedAt 仍要由现有 Injector/Controller 重新检查。Dockerfile COPY business/incident/bridge/domains 及 .dockerignore 的私密排除与这一方案一致。

本阶段可以准备 E1-a 三点、E1-b 三方法、E1-c 和 F12 的独立 bundle/plan；准备与镜像构建不等于正式实验已运行。每个计划仍需要当前实际镜像 ID、新输出与精确执行授权，同 AIC 必须保持独占。

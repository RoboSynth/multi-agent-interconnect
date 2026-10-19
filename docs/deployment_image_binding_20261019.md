# 部署镜像绑定（2026-10-19）

新生成的 `incident-deployment/1.1` 清单将 app-v2 与 reply-drop 都绑定到 `<project>-app-v2:local`，适用于 business 和 seven。仅构建 app-v2 后，F12 可以复用它的镜像；F12 仍会检查实际镜像 ID 与正在运行的 app-v2 相同，且只通过显式授权的专用 runner 启动自有代理。构建配置不证明镜像已经存在，也不等于故障已运行。

旧 `incident-deployment/1.0` 清单继续按原 overlay 形状、原文件指纹严格读取，不重写配置；旧七身份三端口 target 仍只用于已有场景。新 1.1 七身份 target 必须含第四端口。旧清单不会自动获得新的 F12 镜像绑定，需要时准备新目录。

从项目根按 [隔离部署说明](../deploy/ISOLATED.md) 只生成配置。需要单独构建时，复用 `deploy.prepare_deployment.load_deployment` 和 `compose_command(manifest, sanitized=True)` 的同一项目、env、Compose 文件及 WSL 路径，对其命令追加 `build app-v2`；构建六域共享镜像只追加 `build application-agent`。这两个 build 命令不启动容器或平台 consumer。保留既有子环境过滤，勿把 compose.env 加载进协调进程。

正常 `--launch` 仍按既有顺序构建 app-v1/app-v2、只构建一次共享 agent 镜像，再 up；reply-drop 保留 faults profile，不因本改动自动启动。当前正式验收准备阶段只构建 agent 镜像，尚未启动新平台参与者或运行 E1/F12。

镜像构建可以复用已有 Docker 层缓存。不要为了此次代码变化使用 --no-cache；若依赖层未命中，pip 可能需要网络。构建完成后应单独绑定不可变 image ID 和实际源码，运行时仍由 Injector/Controller 核对来源、挂载、端口与进程身份。

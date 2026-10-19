# 正式验收准备（2026-10-19）

本轮从 `4f157a1d557eba3008eec338d0cde5d7d523ee8a` 继续。已准备独立项目 `incident-pilot-acceptance-20261019`、七身份配置及 22 个新的正式验收计划。没有启动本项目业务服务、平台消费者或新故障，计划尚未执行。原 34 个容器、旧实验和私密目录保持原样；新增的依赖与镜像探针是独立、无网络的临时容器，终态与原始失败保留在[本轮证据](../evidence/p0-acceptance-prep-20261019/README.md)。

## 已解决的部署问题

第一，F12 代理需要复用正在运行的 app-v2 镜像，原 Compose 定义只声明 build，缺少可核对的镜像名称。现在新生成的 `incident-deployment/1.1` 将 app-v2 和 reply-drop 绑定到同一项目镜像，旧 `/1.0` 仍按原配置形状和文件哈希读取。15 个部署测试全部通过；新配置也通过真实 Compose 的静态检查和渲染。详见[镜像绑定说明](deployment_image_binding_20261019.md)。

第二，构建时 `postgres-mcp==0.3.0` 要求的 `pglast==7.2.0` 在本机实际查询的 PyPI 当前索引中缺失，原构建失败。本轮从官方文件服务器取得原版 `pglast 7.2` 文件，分别核对 Linux 和 Windows CPython 3.12 x64 文件的 SHA-256；在数据库域 requirements 中用平台条件和哈希固定这些来源，保留原数据库工具版本。Linux 隔离环境中安装、`pip check`、`7.2.0` 版本要求匹配和实际 `SELECT 1` 解析均通过。Windows 原文件已校验，独立新 Windows 环境的安装仍需验收。

原始 Linux 文件：[官方 wheel](https://files.pythonhosted.org/packages/58/e6/bf739bd61518c4a90ff05dbd456c973b21ca2a7b664d1f9910c1fe4f3088/pglast-7.2-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl#sha256=e2613ad4228165125047706c26925230202d63adc4d5a10cbe8a8896af024ced)；Windows 文件：[官方 wheel](https://files.pythonhosted.org/packages/be/4b/a4d244211dd3dcfd99c704bb6195d9c5c564da175531b0fb8c844f311b8d/pglast-7.2-cp312-cp312-win_amd64.whl#sha256=06a5b2d3dd63c44ca71e29fcc0fe162f959708bd348754e420ac1b9332d1d340)。两个文件都已实际下载并校验；搜索缓存中的旧发布页面不作为当前可安装性的证明。依赖调查与最初失败分别归档。

本机 Docker CLI 没有 buildx，最初带 `--progress` 的构建被拒绝。随后使用现有构建器支持的参数构建独立镜像；没有改全局代理或安装系统插件。带 buildx 的环境可以继续使用正常 Compose build，本次已有镜像的启动方式另存于证据中的启动检查。

## 本次目标与镜像

| 项目 | 实际绑定 |
| --- | --- |
| Compose project | `incident-pilot-acceptance-20261019` |
| 回环端口 | app-v1 `48081`，app-v2 `48082`，公共入口 `48088`，F12 代理 `48090` |
| 智能体镜像 | `sha256:ccc35272ab4086325292ddfcaedac156e95ab4086df6a0d93276c030efaab837` |
| app-v2 / reply-drop 镜像 | `sha256:165a53fd42371edbb3618b7dfd269208d080526c0ce07ef686ab2a53d1240c25` |
| 身份 | 原七个新版身份；本地证书、公钥匹配、AIC、clientAuth、有效期及已有公开 Inbox 记录逐项通过 |
| 私密配置 | 当前 checkout 的 `runtime/private/acceptance-20261019`，每域只复制本身份材料和本域权限 |

两个镜像均已实际构建成功并读取不可变 ID。构建成功不能代替业务、AMQPS、恢复或新机器部署验收。身份的 Inbox 一致性引用 2026-10-18 的公开平台观察，本轮身份核查未联网刷新；本机无消费者也不能排除另一台机器使用相同身份。

## 22 个计划的范围

| 场景 | 单例定义 | 数量 |
| --- | --- | ---: |
| E1-a | 观察后、修改前、修改完成回报前，各重复 3 次 | 9 |
| E1-b | 从头开始、完整历史、接续包，各重复 3 次 | 9 |
| E1-c | 暂停旧主，备用接管后恢复同一进程的原请求，重复 3 次 | 3 |
| F12/E5 | 原请求回复丢失，包含现有缺键对照 | 1 |

计划已分别生成并通过原 runner 的文件校验，绑定当前源码、私密配置、目标、镜像和新的输出目录。先执行八类首轮，再根据原始结果继续重复；全部串行，不复用旧批授权或失败输出。每次仍要求正常关组、恢复目标和独立 H00，失败保留；若恢复不成功，停止后续运行。完整逐例 SHA 和顺序见[运行范围](../evidence/p0-acceptance-prep-20261019/plan-preparation/run-scope.md)。

本轮准备器没有生成 `authorized=true` 的执行授权。下一步是在确认同一身份未被其他机器消费后，按这份具体范围获得新运行许可，启动独立项目并执行。新机器 T11/T96、平台 Kafka/Monitor 入库和长期在线仍分别待验收。

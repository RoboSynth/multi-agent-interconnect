# 独立 Linux 七源 collector

2026-10-19 当前梧桐公开 Kafka profile 见[kafka-settings.wutong-public.example.json](kafka-settings.wutong-public.example.json)，为 PLAINTEXT 且无需 TLS/SASL 材料。下文传输材料挂载仅适用于采用 TLS/SASL 的其他部署，当前上报按[接入一页纸](../../docs/kafka_接入一页纸.md)准备。实际启动及发送仍需明确新行时间窗，生成 Compose 不等于已发送或已入库。

`prepare_linux_collector.py` 只生成一个 collector 的 Compose JSON、配置、parser 和计划，不调用 Docker、不联网。源映射复用 `collection-plan.example.json`：协调者日志只读 bind；六域使用五个既有 external named volume，主备共享卷但只挂各自的 `amp-*` subpath。不存在子目录时必须修正来源，不能退回挂载整个 `/state`。

stdout 默认 `network_mode: none`，根文件系统只读，无业务环境变量、私密配置、密钥目录或 Docker socket。42 个 flat offset DB 放在新独立 named volume；卷标签绑定七角色/来源路径/subpath 的 SHA256 和模式。每次启动前要只读 inspect 已有状态卷并调用 `validate_existing_state(metadata, source_collection_sha256, mode)`；更换来源或模式必须使用新的状态卷。stdout 与 Kafka 的状态不共享。

镜像必须为官方 `cr.fluentbit.io/fluent/fluent-bit@sha256:...` 的本地已解析引用，`pull_policy: never`。[官方 Docker 文档](https://docs.fluentbit.io/manual/installation/downloads/docker) 列出 Linux 5.1.3。若通过 crane tar 导入，分别保留远端 platform manifest digest、tar SHA256 和 Docker 实装 image ID/本地 RepoDigest，不能把导入后的本地别名当作远端 manifest digest。

本机 tar-load 后可解析的 `repo@imageID` 别名 `0c768b8263e8935e19cea66fbd7e1c768db7f9edc710e832e93f058bad0ef027` 仅用于本机引用。其他机器应从官方 registry 拉取远端 linux/amd64 platform manifest `sha256:07bd537485182b73af016c67dae99521e40fdf50922b39912f378c5befb8e3b1` 后重新 inspect，不能照抄本机 `0c768…` 别名作为远端 manifest。

```powershell
.venv/Scripts/python.exe deploy/fluent-bit/prepare_linux_collector.py --output artifacts/<新的独立目录> --image cr.fluentbit.io/fluent/fluent-bit@sha256:<本地已验证摘要>
```

`Read_From_Head True` 是显式历史 stdout 采集范围，只匹配稳定正文 `amp_<kind>_*.jsonl`。实际日志持续增长，验收检查 JSON 解析、七个配置 AIC 和六类日志、只读挂载与自然追加；不发送业务任务，也不把自然增长后的文件 SHA 变化当作失败。外部 rename/copytruncate/停机归档仍未获得无漏读、无重放保证。

实际启动由操作者审阅计划后执行：先核唯一 collector 所有权、全部源子目录、固定镜像 ID 与状态卷标签，记录原有 29 个容器的 ID/StartedAt/restart count。仅启动新 collector。停止前再次核其实际 ID/name/labels，再正常 SIGTERM、等待退出 0；保持原 29 个容器、来源卷和采集 offset，不执行整体 down。

Kafka 仅在显式 `--mode kafka --kafka-settings <私密profile.json>` 时生成：复用原 `validate_kafka` 的字段、环境引用及 TLS 宿主文件预检；三类 TLS 材料只读逐文件映射到 `/collector-transport/`，配置不展开密码，Compose 只传所引用的环境变量名。输出仍为官方 `amp.<kind>` 主题，默认六类，可用 `--kinds heartbeat,access` 先选择两类；计划中的输入数、DB 数、输出数和验收类型随选择变化，卷标签继续绑定来源和模式，扩展类型不重置原 offset。Kafka 默认 `Read_From_Head False`，历史采集需显式 `--read-from-head`；已有 offset 仍会续读，首次只发新行必须用独立的新状态卷，先启动 collector 再产生日志。当前梧桐公开连接资料已齐，准备成功不代表投递或 Monitor 入库成功，实际发送按单独运行计划执行。

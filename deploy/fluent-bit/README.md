# AMP 转发准备

原有默认行为保留：`render.py` 写配置，`run.ps1` 默认启动 stdout 模式的 Fluent Bit。网络发送需显式 `-Mode kafka`，并提供通过字段/路径预检的私密 profile。未完成 Kafka、Monitor 或 Discovery 入库验收。

只读检查：

```powershell
.venv/Scripts/python.exe deploy/fluent-bit/render.py --log-directory <本地AMP目录> --check
pwsh -NoProfile -File deploy/fluent-bit/run.ps1 -LogDirectory <本地AMP目录> -CheckOnly
pwsh -NoProfile -File deploy/fluent-bit/run.ps1 -Mode kafka -LogDirectory <本地AMP目录> -KafkaSettings <私密profile.json> -CheckOnly
```

Python 预检只检查六类 `amp_<kind>_*.jsonl` 文件存在性、parser、Kafka 字段和 TLS 文件路径，不读取 TLS 内容，不解析日志正文，不联网、不运行子进程、不建目录/文件、不创建 subst。PowerShell `-CheckOnly` 是调用该 Python 预检的薄入口，不查找或运行 Fluent Bit。输出仅含源哈希、文件数量、字段名和错误码，不输出 broker、账户、密码或证书路径。缺一类输入时失败，先让相应 Emitter 生成文件；文件存在不等于记录有效或平台可见。

Kafka profile 延用 `brokers` 与 `rdkafka` 结构，模板见 `kafka-settings.example.json`。SSL/SASL_SSL 要求显式存在的绝对 `ssl.ca.location`；如使用客户端证书，`ssl.certificate.location` 和 `ssl.key.location` 成对存在。SASL 要求机制、用户名和密码；密码只能为 `${ENV_NAME}`，引用的环境变量须已设置。预检不会尝试认证。七张 AIC 证书的 clientAuth 用途不能代替 Kafka 信任/ACL 确认，Monitor 的 OIDC/local-auth 也须另行配置。

实际运行仍使用原入口：

```powershell
pwsh -NoProfile -File deploy/fluent-bit/run.ps1 -LogDirectory <本地AMP目录>
pwsh -NoProfile -File deploy/fluent-bit/run.ps1 -Mode kafka -LogDirectory <本地AMP目录> -KafkaSettings <私密profile.json>
```

默认状态改为 `runtime/fluent-bit-state/<source_id>/<mode>/`；每个源/模式拥有独立配置和六个 offset DB。`source_id` 是规范化绝对输入路径的 SHA256，Windows 大小写与相对路径写法归一；可用 `-StateRoot` 选择状态根目录。stdout 与 Kafka 的 offset 分离，stdout 消费不能被当作已发 Kafka。

运行前持有固定 `runtime/fluent-bit-owners/<source_id>.lock` 的非阻塞 OS 锁，覆盖配置写入到 Fluent Bit 前台退出。改变 `StateRoot` 或模式不能绕过同源互斥；不同源可同时运行。异常/非零退出会释放锁，并保留真实退出码。锁文件可能保留，其存在不代表仍有进程持锁。本项目同机锁不排除其他 checkout、机器或未经本入口启动的采集器。

旧共享配置和 offset DB 保留，不自动迁移或重播。新 DB 默认 `Read_From_Head False`；需要历史补发时，应先明确时间窗/去重策略，再用 renderer 已有 `--read-from-head` 显式准备。直接调用 renderer 的 `--state-directory ... --output ...` 继续可用，它只写配置；同源运行互斥由 `run.ps1` 使用的 `--executable` 前台监督路径提供。

七源收集设计见 `collection-plan.example.json` 与 `collector-stdout.example.conf`：Windows 协调者日志需显式只读 bind；六域日志位于五个 Docker named volume（主备共享一卷），仅用 `volume.subpath` 挂入日志子目录，不把操作账本或整个 `/state` 暴露给 collector。配置例只展示一个独立 Linux collector 的 42 个 Tail 输入、隔离 offset 和六类 stdout 路由。镜像、挂载、collector owner、Kafka profile/认证与生命周期尚需单独准备及审阅；没有改现有 Compose、启动 collector 或据此宣称已读到容器卷。`run.ps1` 的 Windows portable 无法直接读取容器内的 `/state` 路径。

## 七个本地目录的集合入口

`render.py --collection-sources <sources.json> --state-root <独立状态目录>` 接受七个固定角色到本机日志目录的 JSON 映射：`coordinator`、`application`、`database`、`database-backup`、`ops`、`verification`、`onboarding`。规范路径必须互不相同；不接受缺角色、同目录别名、逗号或换行路径。默认仍为 stdout；只有显式 `--mode kafka --kafka-settings <私密profile.json>` 才生成 Kafka 路由。缺少可用 profile 时拒绝，不推断官方地址、CA 或认证方式。`--check` 仍只读；添加 `--executable <fluent-bit.exe>` 才实际运行，期间按稳定顺序持有七个源锁，获取失败会释放已经取得的锁。

```powershell
.venv/Scripts/python.exe deploy/fluent-bit/render.py --collection-sources <sources.json> --mode kafka --kafka-settings <私密profile.json> --check
```

集合两种模式共用原六类路由和 Kafka 字段/TLS 文件预检。配置分别写为 `collection-stdout.conf`、`collection-kafka.conf`，42 个 DB 分别位于 `<state-root>/<source_id>/stdout/` 或 `kafka/`，不把 stdout offset 当成已发送 Kafka。同一源仍不能同时被本入口的两种模式消费。Kafka 自动建 topic 关闭，只有 audit 附加 `_fb_ts`；密码保留环境引用，不展开写入配置。

Linux collector 的纯配置接口为 `render_collection_paths(sources, state_paths, parser_file, *, mode="stdout", kafka=None, read_from_head=True)`：七角色日志目录例如 `/sources/ops`，每角色 DB 模板例如 `/collector-state/amp-ops-{kind}.db`。它复用相同的 42 Tail / 六路输出，不检查宿主目录、读取文件、创建别名或启动进程；调用者先用 `validate_kafka` 检查宿主 profile，再把 TLS 位置替换为各自只读容器挂载路径。该接口不授予 Kafka 访问权限，也不验证服务器连接。

集合配置有 42 个 Tail、42 个隔离的 offset DB，以及六个选定模式的输出。单源和集合都只匹配正文 `amp_<kind>_*.jsonl`，不把 `.jsonl.1` 等归档或临时文件加入 Path；[官方 Tail 轮转说明](https://docs.fluentbit.io/manual/data-pipeline/inputs/tail#file-rotation) 提醒，Path 匹配轮转归档会造成重复采集。当前 SDK 六类 Emitter 向固定文件追加；支持这些稳定文件的追加，以及保留原文件并创建新的稳定 `*.jsonl` 文件。集合入口显式 `Read_From_Head True`，复用原状态目录以持久 offset 续读，新正文文件从头读取。初次 Kafka 状态可能补发既有正文，须先约定历史范围与平台去重口径。外部 rename、copytruncate 和停机归档尚未获得无漏读、无重放保证。

独立合成验收入口：

```powershell
.venv/Scripts/python.exe deploy/fluent-bit/verify_collection.py --prepare --output artifacts/t06-seven-source-local-<独立名称>
# 审阅 plan.json 和源码后才运行：
.venv/Scripts/python.exe deploy/fluent-bit/verify_collection.py --run --output artifacts/t06-seven-source-local-<独立名称>
```

准备阶段只生成 SDK 合成记录和计划，不启动 Fluent Bit。实际阶段使用既有 Windows portable 二进制，三个采集器串行验证实时追加、运行中新稳定文件发现、正常关闭后的原文件追加续读，以及停机时向已发现的稳定文件追加并新建另一正文文件；总计六批、252 个唯一 ID，保留原输入与 stdout 并逐条核对内容和重复/遗漏。此次范围明确为 `no_rename_tested`。每个采集器的 stdlib host 拥有隐藏独立 console，验证只含自身和其采集器后仅向该 console 发送 CTRL_C；必须记录真实正常退出 0，强制清理或超时均失败。首个进程同时验证该二进制是否支持此正常停止方式，失败则停止后续阶段。

历史 revision3 的 rename 场景第二阶段输出 126 条，其中 84 条为跨阶段重放；该失败及原 offset DB、stdout 保留在独立证据目录。新的追加语义验收不会把该失败改写为 rename 已修复，也不代表 Kafka/Monitor 已验收。

上述 252 条 stdout 实采对应原已封存版本；新增 Kafka 集合与 Linux 路径接口仅有独立离线检查，不把旧实采当成新版本的 Kafka 验收。验收不读取真实角色日志/配置、AIC 卷或凭据，不使用 Kafka、HTTP、模型或 Docker。`verify_local.py` 的六条旧演示也现要求进程退出 0，不能仅凭输出齐全把 timeout/terminate 算作成功。新集合的实际运行结果以独立运行证据为准。

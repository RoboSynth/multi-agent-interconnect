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

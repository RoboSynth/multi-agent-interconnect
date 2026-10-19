# Kafka 接入一页纸

依据 2026-10-19 无登录公开快照：[平台说明](https://wt.ioa.pub/docs.html)、[AMP 第 3–4 节](https://wt.ioa.pub/amp)、[抓取收据](../evidence/next-stage-local-20261019/public-platform-docs/result.json)。

1. 当前公开 Kafka 端点为 `wt.ioa.pub:19092`、`PLAINTEXT`；官方明确无 TLS/SASL、无需账号或客户端证书，不再等待这些字段，也不要替换为 `localhost:19092`。
2. 复制公开示例：`Copy-Item deploy/fluent-bit/kafka-settings.wutong-public.example.json runtime/private/kafka-settings.json`；如目录不存在先创建 `runtime/private`，无需填密码。
3. 六类主题为 `amp.audit/heartbeat/metrics/access/message/system`，保持独立 tail DB；渲染器已为每路配置 `Workers 1`、acks=1 和禁止自动建主题。
4. 单源只读预检：`python deploy/fluent-bit/render.py --log-directory <AMP目录> --mode kafka --kafka-settings runtime/private/kafka-settings.json --check`。
5. 七源只读预检：`python deploy/fluent-bit/render.py --collection-sources <七角色本机目录映射.json> --mode kafka --kafka-settings runtime/private/kafka-settings.json --check`；两种预检都不联网。
6. Docker 卷采集按 [Linux collector](../deploy/fluent-bit/linux-collector.md) 使用只读日志子目录挂载；Windows 不能直接读取 `/state`，采集器运行机须可达 TCP 19092。
7. 获准发送后，单源前台入口：`pwsh -NoProfile -File deploy/fluent-bit/run.ps1 -Mode kafka -LogDirectory <AMP目录> -KafkaSettings runtime/private/kafka-settings.json`；需先有项目 Python 环境及 Fluent Bit 可执行程序。
8. 单源、七源集合命令行和 Linux Kafka collector 默认 `Read_From_Head False`。首次发送使用独立的新 Kafka offset 状态，先启动 collector 再产生新日志；既有 offset 仍会续读，不能仅靠这个开关排除积压。历史补发需另定范围并显式选择 `--read-from-head`，不用 stdout 的 offset。
9. 先确认六个 Kafka worker 启动，再让 Agent 产生新日志；保留 AIC、带时区时间窗、log_id 和错误输出，交平台管理员确认主题水位及入库，接入方不运行中心容器管理命令。
10. 官方 access 计数按 `taskId` 配对调用两端；`correlationId` 应填 `taskId`。两端各一行是一次调用/被调用，不能把本地总行数直接当访问排名。
11. 如以 Message 统计任务，须带任务关联、同一消息标识及发送/接收事件；一消息多个接收者分别计任务。详见 [统计口径与离线收据](../evidence/next-stage-local-20261019/g2-kafka-public-profile/README.md)。
12. 无平台管理权限时，在 Discovery 响应中核本队 AIC 的 `aliveMap`；普通 Registry 登录及 Agent 证书均不能用于 `acps-cli monitor`，Monitor 日志、访问量和排名须请管理员核对。
13. 分阶段发送：`render.py`、`run.ps1 -Kinds`、`prepare_linux_collector.py` 都支持 `--kinds`（逗号分隔，默认 all）。第一阶段用 `--kinds heartbeat,access`，确认 `aliveMap` 在线后再改为 all；每类日志有独立 offset，后加的类型只从新行开始。
14. 无登录文档对比：`python tools/check_platform_docs.py --output <新的快照目录> --previous <上次result.json>`；首次省略 `--previous`，该命令一次性运行，未注册每日任务。

当前完成：公开配置与离线校验；仍待获准后的真实发送、管理员入库/访问统计确认及长期在线记录。

本地配对：原`eval/reconcile_access.py`输出新增`platform_pairing`，按taskId核对caller/callee及两端AIC，缺端、重复、冲突单列；它不推定业务成功或平台排名。`tools/check_alive.py --aic <AIC> --response <已有Discovery响应.json> --output <新文件.json>`离线读取官方布尔型`aliveMap`；需要实际只读查询时显式加`--query --url <Discovery地址>`并省略`--response`，可重复给七个`--aic`；在线只证明心跳同步，不代表access已入库。

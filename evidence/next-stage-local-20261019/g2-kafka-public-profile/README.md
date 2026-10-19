# G2：公开 Kafka 配置与统计口径

2026-10-19 的[无登录抓取收据](../public-platform-docs/result.json)已确认两份官方页面 HTTP 200。本轮基于该固定快照准备配置并离线校验，没有再次联网、启动 Fluent Bit、发送 Kafka 或查询 Monitor。

## 官方当前配置

[平台说明](https://wt.ioa.pub/docs.html)列出外部 Agent 的 `wt.ioa.pub:19092` 上报地址；[AMP 第 3 节](https://wt.ioa.pub/amp)进一步说明使用 PLAINTEXT，不启用 TLS/SASL，不需要 Kafka 账号或客户端证书。因此当前不应再把“等待 TLS/账号”列为转发准备的前置缺口。

直接使用[公开 profile](../../../deploy/fluent-bit/kafka-settings.wutong-public.example.json)；保持官方六类 `amp.*` 主题及独立文件位点。既有渲染器已包含每路单个 worker、acks=1 和禁用自动建主题，未为当前配置修改产品代码。单源默认仅转发新增行，七源集合接口的默认值为从头读取；[本例配置](seven-source-public.example.conf)显式选择新增行模式，路径均为待映射的 Linux 示例路径，不能当作本机现成的运行计划。

## 官方访问统计说明

[平台说明快照](../public-platform-docs/docs.txt)第 86–93 行给出以下口径：

- access 将任务标识放进关联字段，按同一任务的调用、被调用双方匹配计一次，而不是累加双方日志行数。
- 用 Message 统计任务时，要能关联任务；同一消息的两端要有相同消息标识，并分别记录发送与接收事件。
- 一个消息由多个接收者处理时，按接收者分别计任务，避免群组模式少算。

这些说明给出了配对依据，没有披露排行的全部窗口、并列处理或去重细节，不能据本地条数计算官方名次。本轮未检查或改变旧实验的日志关联字段，也没有回填旧缺失记录。

## 普通 Agent 开发者如何验收

[AMP 快照](../public-platform-docs/amp.txt)第 3.3 节要求先启动采集，再生成新日志，向平台管理员提供 AIC 和带时区时间窗，核对中心主题新增记录及入库。第 4.2–4.3 节明确：`acps-cli monitor` 需要平台 Monitor 管理账号，普通 Registry 用户及 Agent 证书不具备该查询权限；普通接入者可以核对本地增长和 Discovery 的 `aliveMap`，最终日志及访问统计请管理员协助确认。

本地文件增长、采集器无报错、Discovery 在线和 Monitor 已入库分别留证。未取得管理权限时，不要求参赛者通过普通账号运行中心容器或 Monitor 管理命令；也不把某个 AIC 在线当作 access 统计已完成。

## 本次实际离线检查

[offline-validation.json](offline-validation.json)记录：公开 profile 通过既有 `render.validate_kafka`；六类既有归档文件的只读路径预检通过；纯配置生成包含 42 个输入和 6 个 Kafka 输出，全部显式采用新增行模式。校验不读取 TLS 材料、不连接 broker，不构造或发送新的 AMP 业务记录。

操作入口为[接入一页纸](../../../docs/kafka_接入一页纸.md)。待办仅为获准后的真实发送、平台管理员确认入库/访问统计，以及实际长期在线窗口；每日文档检查工具是一次性命令，本轮未注册自动任务。

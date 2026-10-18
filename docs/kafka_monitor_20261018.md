# 官方 Kafka / Monitor 接入状态（2026-10-18）

Kafka 是本地 AMP 日志送入平台的通道，Monitor 是平台存储、验签和查询这些记录的后台。两者与智能体已通过的 AMQPS 任务链路分别配置。

本轮无登录态读取[官方说明](https://wt.ioa.pub/docs.html)返回 HTTP 200。页面仍把 `wt.ioa.pub:19092` 写作“外部 Agent 规划上报端点（Kafka/TLS）”，并链接[平台 AMP 文档](https://wt.ioa.pub/amp)；后一个入口本轮请求超时。这能证明公开说明中的规划地址，不能证明 Kafka 已开放或尚未上线。

当前项目尚没有可用的梧桐 Kafka / Monitor profile。已核的两套 NEW7 readiness 中，Kafka 的 broker、安全协议和认证字段仍为空；现有 CLI 配置也没有 Monitor 节。官方源码的 `localhost:19092`、`http://localhost:9009` 是本地部署示例。七张 AIC 证书及 Registry 登录不能代替 Kafka ACL 或 Monitor 查询授权。

平台侧仍需提供：

- 实际 broker / advertised 地址、安全协议、服务器 CA 与主机名验证要求；采用 mTLS 时确认接受的客户端身份，采用 SASL 时确认机制及独立认证材料。
- `amp.audit`、`amp.heartbeat`、`amp.metrics`、`amp.access`、`amp.message`、`amp.system` 六个 topic 的预建、写入权限及所需元数据权限，另确认 LogAppendTime 与租户/AIC 范围。
- Monitor 的实际地址、API 前缀和查询登录方式。官方 OIDC 使用独立 Monitor 登录，并检查角色、`tenant_id`、`allowed_aics`；Registry 用户登录不自动授予这些权限。

当前可复用[转发入口](../deploy/fluent-bit/README.md)准备 stdout 或显式 Kafka 配置。字段与宿主 TLS 文件预检失败时拒绝生成；不会把未知项填成默认官方参数。七源 Kafka 与 Linux 路径生成已有离线覆盖，实际平台发送、Monitor 六类可见性、Audit 验签和 Discovery 存活还需分别取得证据。

取得平台配置后，最短链是：完整私密 profile → 只读预检 → 明确只读挂载和独立 Kafka offset → 真实发送 → 按同一 AIC / 时间窗查 Monitor 和 Discovery。此前 stdout、AMQPS、访问对账及长期采样记录各自保留，不能相互替代。

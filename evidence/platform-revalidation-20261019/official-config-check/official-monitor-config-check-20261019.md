# Kafka / Monitor 有界官方配置查证（2026-10-19）

Kafka 是把本地 AMP 日志送进平台的通道；Monitor 是平台保存、验签、查询和统计这些记录的后台。智能体经 AMQPS 互发任务已经跑通，并不能证明这条日志通道也已开通。

本次检查仓库截止 `94c701846dffe664be1f893ed0850ef53e234236`。外部只读请求共 3 组，时间为 05:56-05:57 UTC（北京时间 13:56-13:57）：直接读取官方页面不可达，匿名 HTTP 读取均为 URLError，限定官方域的搜索无结果。未取得新的生产接入参数；这些网络失败不能证明平台停服或其他位置没有文档。

| 核对项 | 有来源支持的事实 | 尚缺内容 |
| --- | --- | --- |
| Kafka broker / 端口 | [官方固定版本 Fluent Bit 示例](https://github.com/AIP-PUB/ACPs-community/blob/3985c1330209f075c124669cc9d31f0e75448140/monitor-server/config/fluent-bit/fluent-bit.conf)使用 `localhost:19092`，对应六个 `amp.*` topic。已从本机官方 Git blob 核对。 | 这只是本地部署示例，不是梧桐生产地址。项目 10-18 记录的 `wt.ioa.pub:19092` 仍只是当时公开说明中的规划端点，本轮未能重新读取该说明。 |
| TLS / SASL 字段 | 项目支持显式 `brokers`、`security.protocol`、`ssl.ca.location`、成对的客户端证书/私钥路径，以及 SASL 机制/用户名/密码；模板的 broker 和安全协议仍为空。 | 这些是项目可接收的字段，不是赛方已发放的 profile。实际协议、CA、主机名校验、认证及 ACL 尚未确认。 |
| AIC 证书能否通用 | [官方 AMP 教程](https://github.com/AIP-PUB/ACPs-community/blob/3985c1330209f075c124669cc9d31f0e75448140/acps-docs/tutorials/amp-agent-observability.md)说明本地日志、Forwarder 和 Monitor 是分段链路。 | 本范围未找到 Kafka 接受现有 AIC 客户端证书及其 ACL 映射的确认；不能从已通过的 AMQPS 或 audit 签名推断可复用。 |
| Monitor 地址 / API | [官方 CLI 参考](https://github.com/AIP-PUB/ACPs-community/blob/3985c1330209f075c124669cc9d31f0e75448140/acps-docs/references/cli-reference.md)有独立 `[monitor]` 配置，样例是 `http://localhost:9009`、`/acps-amp-v1`、15 秒超时；健康查询为 `/health`。 | 未确认梧桐实际 Monitor 根地址、对外 API 前缀。不能把本地样例直接替换成猜测的公网地址。 |
| Monitor 查询权限 | [官方 OIDC 教程](https://github.com/AIP-PUB/ACPs-community/blob/3985c1330209f075c124669cc9d31f0e75448140/acps-docs/tutorials/oidc-acps-cli-device-login.md)单独配置 `monitor.auth`；业务查询使用 Bearer token，并校验 role / scope / AIC 范围，包含 `tenant_id`、`allowed_aics`。 | 仍需平台授予实际查询主体与相应范围。Registry 浏览器已登录，不足以证明这些独立权限已授予。 |

现有官方公开入口仍是[接入说明](https://wt.ioa.pub/docs.html)与[AMP 入口](https://wt.ioa.pub/amp)，本次均未成功读取。当前最小缺口为：确认可用的 broker/advertised 地址、TLS/CA 与认证方式、六类 topic 权限及历史补发/去重口径、实际 Monitor 地址和查询授权。没有据此填写默认连接参数或调整现有配置。

同名 JSON 保留各组请求时间与错误类别、仓库来源哈希、官方 Git blob 指纹和逐项结论。它只含安全事实与直接来源 URL；没有读取浏览器会话、私钥、密码或 token，没有连接 Kafka、查询 Monitor、登录、重启或发起平台任务。

# [Docs] 区分正式 MQ Group API 与 localhost 示例，并说明 AMQP 相关字段

首次接入时，我们能找到 AMQPS Broker，却难以确定 SDK `auth_service_url` 对应的正式
Group API。建议在正式站点的基础设施信息与双智能体示例中同时给出这两类地址，并明确
哪些值仅用于本机开发。

本材料记录 2026-10-17 的正式站点与固定 SDK `2.2.0` 接入观察，不是对当前所有部署的
地址保证。固定源码提交为 `3985c1330209f075c124669cc9d31f0e75448140`。

## 已确认的观察

匿名 GET 正式站点公开模块
`https://wt.ioa.pub/registry/static/js/client_list-BFH51SW2.js`，响应 200。保存的公开构建产物
含 `VITE_MQ_AUTH_URL:"https://localhost:9007"`；检查到的基础设施弹层路径直接使用此值，
没有在该路径替换为部署主机名。

在后续持有官方 clientAuth 证书的真实联调中，以下组合完成了两个方向各一轮任务，均有
accepted / working / awaiting-completion / completed，退出码为 0：

| 用途 | 实际成功使用的值 | SDK / CLI 配置位置 |
| --- | --- | --- |
| 消息 Broker | amqps://wt.ioa.pub:5671/acps | RabbitMQ host/port/vhost/SSL |
| 群组授权与管理 API | https://wt.ioa.pub:9007 | rabbitmq_config.auth_service_url / [mq].group_api_url |

这证明了当时该部署的可用组合。`https://localhost:9007` 本身是合理的本机开发示例，
问题是接入者在正式站点看到它时，无法判断是否应替换、如何替换、是否另有路径。

## 可复核步骤

1. 检查上述公开模块快照中 VITE_MQ_AUTH_URL 及其弹层渲染路径。
2. 按接入文档配置 Broker，检查是否还能明确获知独立的 HTTPS Group API origin。
3. 在有官方身份、证书及权限的测试环境中，用明确配置的 Group API 完成最小双向任务。

第三步是运行验收，需要真实身份；读取 bundle 或 TCP 端口可达不能替代它。

## 建议

在部署配置中注入正式服务地址；本地示例继续使用 localhost，但标明仅限本机。提供一个
最小 Inbox 邀请示例，同时列出 Broker、Group API、trust bundle、Leader mTLS 与群组
授权前置条件，避免接入者通过猜端口补配置。

也请说明三个字段的对应关系：`endPoints[].transport` 可以为 `AMQP`，TLS 地址使用
`amqps://`，`capabilities.messageQueue` 的协议版本值可以为 `amqp:0.9.1`。三者不要求
字符串相同。我们没有成对请求证据证明某个协议值差异本身导致了发现失败，因此这里只
提出文档澄清，不将其列为平台协议缺陷。

公开原始响应及脱敏双向成功结果可随 Issue 附上；不需要附带证书私钥或 EAB。

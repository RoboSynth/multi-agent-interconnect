# 仅改本队服务器的叮当接入路线调查

结论：保留现有 AMQPS 地址、且要求可信调用方身份时，目前没有找到能在接收端恢复缺失 `user_id` 的方案。可以另做**仅公开元数据的匿名兼容路径**，尝试继续完成协议交互，但它改变身份保证，不能宣称叮当来源已认证；尚未编写或部署该兼容路径，不能保证端到端成功。

## 路线对比

| 路线 | 仅改本队服务器是否足够 | 调查结果 |
| --- | --- | --- |
| 显式白名单 | 足以配置，不足以修通 | 已真实复试，仍是相同身份缺失错误 |
| 改用官方 v2.2.0 | 不能解决当前身份缺失 | 当天指南推荐该版本；tag 中 Leader、Partner 仍默认开启身份绑定，校验模块与已调查 main 相同 |
| 直接 HTTPS/mTLS RPC | 服务可自建，但当前入口切换还需要 Registry 更新 | 官方本地回环 TLS 测试 3/3 通过；现行 ACS 仅公布 AMQPS，普通 CLIENT 不能更新已批准记录 |
| 依据 Registry、群组 ACL 或路由判断发送者 | 不能替代逐消息认证 | 注册身份存在不证明其发送了该消息；官方 ACL 允许合法身份向其他 Inbox 发布，并允许多个群成员写群交换机 |
| 公开体检的匿名兼容路径 | 接收端代码可自改，是尚未实测的候选 | 只能提供公开只读查询，不能把 body.senderId 当成认证身份，也不能复用资源域的授权边界 |

## 为什么单改一个 SDK 开关不够

1. `integration/wutong_smoke.py::_dispatch_inbox` 直接验证 `message.user_id`，没有读取一个“兼容模式”配置开关。
2. 后续群组任务在 SDK `GroupPartnerMqClient._start_consuming` 再做身份校验，因此只放行邀请可能只是把失败后移。
3. `DomainExecutorAdapter.bind_partner` 明确拒绝 `_identity_binding_enabled=False` 的客户端。
4. SDK 的同一个绑定开关还控制发送消息携带的 `user_id`。直接关闭会让本队回执也失去该属性，可能引入新的互操作失败。

所以不能把“把缺失属性补成 body.senderId”称为认证修复；那只是把消息自报的身份重新填了一遍。

## 可在本队实现的兼容实验边界

若继续尝试，最小范围应是现有 onboarding 接收进程内**独立的匿名分支**，而不是再起一个进程竞争同一 Inbox。认证属性正常的消息继续走原来的严格路径；属性存在但身份不匹配时仍拒绝。

对于缺失认证属性的兼容请求：

- 调用方标记为未经认证，消息里的 AIC 仅作声明值记录；白名单不能将它升级为已验证身份。
- 只开放 `aip.onboarding.check`、`deep=false`，只访问固定官方 Discovery，禁止数据库、运维修复、任意地址请求及主动目标探测。
- 独立处理邀请、任务、回复和关闭，验证群组/目标/任务上下文，限制消息大小、并发、时长和重放；这些限制不能替代发送者身份认证。
- 保持本队发送消息的标准 `user_id`，不直接使用关闭双向绑定的全局开关。
- 不把该分支产生的未经认证 AIC 记为已认证 caller，也不将其作为可信跨队调用证据。平台是否接收、如何计数尚未确认，不能承诺上榜。
- 若无法在保持上述隔离的情况下完成回执，应停止该路线，保留失败。

这是设计候选，当前没有部署，也没有增加真实叮当调用次数。调用次数、任务创建和业务结果均未获得新的成功证据。

## HTTPS 路线的验证与限制

本机使用当前官方 SDK、生成的临时测试 CA/证书和真实回环 TLS listener，单独执行官方 `test_aip_direct_mtls_identity.py`：

1. 客户端证书身份与 senderId 相同：成功。
2. 证书有效但 senderId 伪造：返回身份不匹配。
3. HTTP 处理层未取得证书身份：拒绝。

结果 **3/3 通过**。它证明官方直接 RPC 的认证机制，不证明叮当已尝试或支持当前登记身份走该入口，也不是体检完整业务测试。

测试准备期间两次失败也保留：第一次项目解释器未安装 pytest；第二次隔离副本未保留官方测试所需的目录层级。复用已有 SDK 测试解释器并修正目录布局后，未改官方测试和 SDK，第三次运行通过。临时私钥和原始日志留在被忽略的工作目录。

2026-10-20 22:31（北京时间）只读核对：当前 ACS 只有 `amqps://wt.ioa.pub:5671/...`，输入模式为 `application/json`；Registry 的 CLIENT 更新接口仍声明已审核通过记录不可更新。因此，在我们服务器新开 HTTPS 端口本身不会改变叮当发现到的地址。需要平台支持的 ACS 更新流程，或正常注册另一个入口并通过审核；这些均超出“只改服务器”的条件。

## 来源和证据

- [上一轮白名单真实复试](../dingdang-allowlist-retry-20261020/README.md)。
- [本轮结果摘要](validation.json)与[官方源码获取清单](source-manifest.json)。
- [官方 v2.2.0 群组 Partner](https://github.com/AIP-PUB/ACPs-community/blob/v2.2.0/acps-sdk/acps_sdk/aip/aip_group_partner.py)及[身份模块](https://github.com/AIP-PUB/ACPs-community/blob/v2.2.0/acps-sdk/acps_sdk/aip/aip_group_identity.py)。
- [官方 MQ 授权源码](https://github.com/AIP-PUB/ACPs-community/blob/94077d10b336bfdb9a7d68e4859390bf44a67a27/mq-auth-server/app/services/authz.py)与[群组接口](https://github.com/AIP-PUB/ACPs-community/blob/94077d10b336bfdb9a7d68e4859390bf44a67a27/mq-auth-server/app/api/groups.py)。这是公开实现的代码证据，未取得线上 MQ 管理权限或核验线上具体版本。
- [官方直接 mTLS 测试](https://github.com/AIP-PUB/ACPs-community/blob/94077d10b336bfdb9a7d68e4859390bf44a67a27/acps-sdk/tests/integration/test_aip_direct_mtls_identity.py)。
- [Registry OpenAPI](https://wt.ioa.pub/registry-server/openapi.json)、[当前体检 ACS](https://wt.ioa.pub/registry-server/acps-atr-v2/acs/1.2.156.3088.1.BUPT.8N4WSS.46ZKB8.5GNEFA.03KF)、[平台指南](https://wt.ioa.pub/docs.html)。
- [RabbitMQ Validated User-ID](https://www.rabbitmq.com/docs/validated-user-id)：发送方不设置该属性时，接收端不会因此获知发布者身份。

本轮仅访问官方公开资料和执行本地测试；云端只用来读取公开 HTTP 接口，未修改云端文件、配置或运行服务。

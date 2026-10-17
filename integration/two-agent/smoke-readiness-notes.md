# 双智能体 AMQPS Inbox 冒烟脚本独立就绪审查

审查日期：2026-10-17。对象：`integration/wutong_smoke.py`；参照本地官方 ACPs SDK v2.2.0（README 记录的固定提交 `3985c1330209f075c124669cc9d31f0e75448140`）。

## 结论

当前代码的 Inbox 邀请、入群通知、任务 start、accepted/working/awaiting-completion、Leader complete、Partner completed 调用契约与所读官方 SDK 一致；没有发现需要修改冒烟脚本的确定运行阻断。未更改 `wutong_smoke.py`、官方 SDK 或现有私密文件。

这只是源码与离线调用检查，不是平台成功记录。没有连接真实平台建群，没有读取 credentials，也没有用本地自签身份替代正式身份。真实测试仍依赖双方已获批 AIC、双方正式 clientAuth 证书、官方 CA bundle、已确认可达的 MQ ACL 服务地址。

## 已核实的调用链

1. Partner `start_inbox_consuming(callback)` 连接 broker，声明自己的长期 Inbox，消费邀请。消费回调签名是 `async (invitation) -> None`。
2. `set_invitation_handler(policy)` 的策略签名是 `async (invitation) -> bool`；SDK 在 `join_group_from_invitation` 内调用它。当前脚本注册两种回调的方式正确。
3. Leader 创建 session 时，经 `GroupAclClient.add_member` 为自己授权，然后建立群 exchange / Leader queue。
4. Leader 根据 Partner ACS 的同 broker、同端口、同 vhost AMQP 端点选择 Inbox 路由；`auth_service_url` 是该路由必需项。
5. Leader 先给 Partner 授权，再发布带 token、expiry 的邀请。Partner join 后的 ACK 是 `GroupMgmtResult(status.connected=true)` 经群 exchange 回传；不是脚本伪造成功。SDK Leader 以这一实收状态完成 pending invitation future。
6. Partner 正式回调为 `async (TaskCommand, is_mentioned: bool)`。现有只读处理器核对 Leader、group、session、task、mention 和 nonce，再依次调用官方 accepted、working、awaiting-completion 方法。
7. Leader 验证实收产品，发 complete；Partner 回 completed。脚本只在实收历史包含四个状态后置 `platform_run_success=true`。

源码定位：

- `acps_sdk/aip/aip_group_partner.py:335`：Inbox 消费及身份校验。
- `acps_sdk/aip/aip_group_partner.py:514`：入群与策略回调。
- `acps_sdk/aip/aip_group_partner.py:971`：connected=true 入群通知。
- `acps_sdk/aip/aip_group_leader.py:1711`：ACL、自身入群资源、会话创建。
- `acps_sdk/aip/aip_group_leader.py:1812`：邀请路由。
- `acps_sdk/aip/aip_group_leader.py:1935`：Inbox 授权、邀请及等待 ACK。
- `acps_sdk/aip/aip_group_leader.py:2453`：实收消息处理与 pending invitation 完成。

## ssl_cert、身份与 nonce

`GroupLeader.ssl_cert` 只在 RPC 邀请分支传给 `client_cert`。本测试只采用 Inbox，所以不需要另填这个参数。`validate_certificates` 已把双方各自证书/私钥装入两个 SSLContext；GroupLeader 以 Leader context 连接 broker，同时把同一 context 交给 `GroupAclClient` 的 httpx 客户端，故 ACL mTLS 不依赖额外 `ssl_cert` 参数。

双方 AMQP 用户名/密码均为 None，因此 SDK 使用 AMQPS + SASL EXTERNAL。`identity_binding_enabled=True` 导致出站 AMQP `user_id` 与本地 AIC 一致，入站核对 `senderId == AMQP user_id`、groupId。能否通过平台 EXTERNAL 认证、broker 对证书和 user_id 的最终权限检查，仍须真实运行证明。

当前是同一个 Python 进程中的两个独立 SDK 客户端、两个真实 AIC 和两个客户端证书。nonce/session/task 由编排代码提前给双方配置，因此不能称为两个独立部署或盲测。但这不会绕过消息服务器：Partner 仅由实收 TaskCommand 回调触发；Leader 仅从 SDK 实收消息历史/快照读取返回产品，没有调用本地处理器制造 Leader 结果。只要未 monkeypatch 传输，成功结果即可证明两身份客户端经 broker 往返。

## 清理限制

脚本按 Partner close、Leader close 顺序关闭。Partner leave 通知并删除自己的群队列；Leader close 解散群、删除 ACL 群记录并清理群队列/exchange。双方长期 Inbox 及 `inbox.topic` 按 SDK 设计保留，不能把这类长期地址当成本轮群资源泄漏。

重要证据限制：官方 SDK 的 ACL delete、queue delete、exchange delete 有多处捕获异常后仅记录 warning。现有 `cleanup_errors=[]` 只证明 close 方法未向上抛错，**不能独立证明平台资源全部删除**。后续真实运行应保留完整 stderr/log；若要证明清理，可使用实际平台授权的管理/状态接口只检查本轮唯一 groupId，不扫描或删除他人资源。

## 离线验证结果

执行：

```powershell
& '.\.venv\Scripts\python.exe' '.\integration\check_wutong_smoke.py'
```

结果：退出码 0；14 个官方方法签名检查通过；缺少正式配置时即使 `--run` 也被阻断；完成前置、session、mention、nonce、产品、拒绝和四阶段状态模型检查通过。输出明确 `network_attempted=false`、`platform_run_success=false`。

尝试执行官方邀请/身份相关 pytest 用例时，项目虚拟环境报 `No module named pytest`，因此没有把这些官方 pytest 用例记为已运行或通过；未为此安装额外依赖。

## 真实运行所需本地私密布局

以下为建议布局，不要求用户上传私钥：

```text
integration/private/two-agent/
  config.json
  leader-chain.pem
  leader.key
  partner-chain.pem
  partner.key
  trust-bundle.pem
```

`leader.key` 与 `partner.key` 应由官方 CLI 在本机生成，私钥始终留在本机。双方证书均需对应各自正式 AIC 的 clientAuth 用途。EAB 和 CLI 登录材料另置受限本地文件，不能写进演示日志、源代码或报告。

`config.json` 的字段契约如下（说明用占位值不能作为已就绪配置运行）：

```json
{
  "leader_aic": "<正式Leader AIC>",
  "partner_aic": "<正式Partner AIC>",
  "partner_amqp_endpoint": "amqps://wt.ioa.pub:5671/acps?inbox=inbox_<正式Partner AIC>",
  "mq_auth_url": "<平台确认的HTTPS MQ ACL服务根地址>",
  "leader_cert": "leader-chain.pem",
  "leader_key": "leader.key",
  "partner_cert": "partner-chain.pem",
  "partner_key": "partner.key",
  "trust_bundle": "trust-bundle.pem"
}
```

若私钥已加密，另提供 `leader_key_password_env` / `partner_key_password_env`，值为已有环境变量名；密码本身不得放在命令参数、JSON 或输出中。

先离线检查，再真实执行，各次证据使用新文件：

```powershell
& '.\.venv\Scripts\python.exe' '.\integration\wutong_smoke.py' --check-config --config '.\integration\private\two-agent\config.json' --output '.\integration\two-agent\config-check-unique.json'
& '.\.venv\Scripts\python.exe' '.\integration\wutong_smoke.py' --run --config '.\integration\private\two-agent\config.json' --timeout 30 --output '.\integration\two-agent\live-run-unique.json'
```

最小通过门槛：真实两个正式身份、Inbox 路由、真实 groupId、四阶段实收状态、nonce 产品核验均通过；清理 warning 单列。当前未达到这个门槛，不能声称已完成梧桐双向交流。

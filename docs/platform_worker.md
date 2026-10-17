# 应用域与验证域正式群组进程

`incident/platform_worker.py` 把已有 `ApplicationPartner`、`VerificationPartner`
接入官方梧桐 AMQPS 群组。它复用 `BridgeGroupRuntime` 的单 Inbox dispatcher；
子 `GroupPartnerMqClient` 保留官方 AMQP `user_id` 校验，并注入官方 access/message
发射器。仅允许配置中的 Leader，任务还必须来自当前群组实际 Leader。

配置相对路径按配置文件所在目录解析。资源环境文件仅由各域进程读取。
下面的示例只包含公开身份、端点及文件路径；证书、私钥和应用令牌不写入 JSON。
身份引用来自本地已批准 ACS 记录，正式使用前应核对当前登记状态。

```json
{
  "name": "application-platform",
  "role": "application",
  "aic": "1.2.156.3088.1.BUPT.8N4WSS.7H5SK8.93B7PX.0S53",
  "allowed_leaders": ["1.2.156.3088.1.BUPT.8N4WSS.AKAA8C.7HEMBG.1B4B"],
  "endpoint": "amqps://wt.ioa.pub:5671/acps?inbox=inbox_1.2.156.3088.1.BUPT.8N4WSS.7H5SK8.93B7PX.0S53",
  "mq_auth_url": "https://wt.ioa.pub:9007",
  "cert": "../private/application/fullchain.pem",
  "key": "../private/application/key.pem",
  "trust_bundle": "../private/platform/trust-bundle.pem",
  "env_file": "../private/application.env",
  "ledger_path": "../application-operations.sqlite",
  "amp_directory": "../amp-platform",
  "evidence_path": "../application-platform-events.jsonl",
  "base_url": "http://127.0.0.1:8082"
}
```

验证域将 `role/name/aic/endpoint/cert/key` 改为验证身份，`base_url` 使用订单公开入口，
并设置 `verification_duration=30`。它不需要应用管理令牌、数据库环境文件或数据库私钥。
本地验证身份记录为 `1.2.156.3088.1.BUPT.8N4WSS.8L5I9C.6YGAAA.0S8S`。
加密私钥可设置 `key_password_env`，该环境变量由本域 `env_file` 提供；解密仅在内存中发生。

```powershell
# 离线：配置、AIC、证书链/CN/SAN/clientAuth、私钥匹配及签名依赖；不连接平台。
& .venv/Scripts/python.exe -m incident.platform_worker --config <准备包>/application.json --check
& .venv/Scripts/python.exe -m incident.platform_worker --config <准备包>/verification.json --check

# 确认身份/ACS 与唯一 Inbox owner 后，每个域各自启动一个进程。
& .venv/Scripts/python.exe -m incident.platform_worker --config <准备包>/application.json
& .venv/Scripts/python.exe -m incident.platform_worker --config <准备包>/verification.json
```

`domains/setup_platform.py` 生成的 application/verification 配置可直接作为输入。
数据库和运维桥继续使用现有 `acps_mcp_bridge` CLI，不在本模块重写 MCP 客户端。

程序接口为 `load_config(path)`、`PlatformWorker(config)`、`prepare()`、
`await start()`、`await close()`；`prepare()` 读取本域材料但不连接 broker。
`DomainExecutorAdapter` 可组合实现 `async execute(payload, authenticated_caller)`
的其他域执行器。`DomainGroupRuntime` 仍沿用基线每进程一个活跃入站群组的限制。

IFC 支持 describe/observe/act/verify，schema 为 `ifc/1.0`。AIP Start 返回
accepted → working → awaiting-completion，收到合法 Complete 后返回 completed。
同任务重放返回缓存产物；session 冲突、其他群组 Leader、非法 schema 均拒绝。
应用修改继续通过本域 `OperationLedger`；AIP 的 sessionId 与业务 incident_id
可以不同，产品必须回显原业务 incident/logical task 标识。

AMP 输出 heartbeat、metrics、access、message、audit、system 六类，审计使用本域
clientAuth 证书对应私钥签名。子 Partner 统计首次 Start，Complete/重放不重复计 access；
业务 rejected/tool_error 会记录失败。原生消息仍保留 send/receive/ack 和 W3C trace。
周期任务在关闭时取消，域环境变量或 stderr 不作为 AIP 产品转发。

已运行的 10 项离线测试使用临时真实证书与模拟 broker：

```powershell
& .venv/Scripts/python.exe -m unittest discover -s tests -p test_platform_worker.py -v
```

测试包括签名验签、加密私钥、官方 Inbox/群组消费者身份边界、邀请策略、join 前绑定、
Start/Complete/重放、trace 和六类 AMP。此结果不表示新版域进程已在正式平台启动或完成事故恢复。

# 正式身份与 ACS 缺口

当前本地 `integration/incident/*.approved.acs.json` 保留四个业务身份：

| 角色 | 原技能 | 本轮处理 |
| --- | --- | --- |
| 协调 | incident.coordinate | 复用身份，更新新版工作台/协作描述 |
| 应用 | incident.application | 复用身份，更新应用状态、池重建、版本回退及 IFC 描述 |
| 数据库主 | incident.database | 复用身份，增加新版发现所需 db.observe/db.act；更新固定 SQL 与审批约束 |
| 验证 | incident.verification | 复用身份，更新真实 PostgreSQL 订单及 30 秒/10 流程验收描述 |
| 运维 | 尚无此角色身份记录 | 新注册独立 AIC、clientAuth 证书及 ops.observe/ops.act ACS |
| 数据库备 | 尚无此角色身份记录 | 新注册独立 AIC/证书；与主相同技能及资源域，共享域内账本 |

数据库旧技能 `incident.database` 与新版协调者默认查询 `db.observe` 不相同。
更新登记前，新协调者不能据旧 ACS 完成该角色发现。数据库备不能复制主身份的 AIC/私钥。
ACS 应准确描述实际资源后端；本地 Windows 进程后端不可写成已验证的 Docker 部署。

正式接入还需核对审核后的 ACS、公开端点 Inbox 与 AIC 一致、证书路径及权限、Leader
白名单、真实 describe 往返、消息/访问量与平台 AMP 入库。新旧程序不可同时消费同一 AIC
的 Inbox。平台 Kafka 地址/认证及持续运行数据仍由部署验收确认。

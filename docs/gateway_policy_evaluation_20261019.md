# E2-c 逐条策略与签名审计验证（2026-10-19）

一次独立调用集共15例：14次拒绝、1次合法审批正控；四类必需请求全部拦截。14次拒绝均有且仅有1条真实落盘、签名与字段关联正确的audit，实际转发MCP调用0。正控转发3次MCP（含资源前后观察）并使测试工具内的修改计数增加1。16次独立健康探测另计，不宣称全部MCP调用为0。

| 请求组 | 拒绝例数 | 到达的实际边界 |
| --- | ---: | --- |
| 未授权调用方 | 1 | caller白名单 |
| 任意SQL/SQL参数注入 | 2 | 工具别名白名单、参数schema |
| high缺审批 | 1 | 独立审批验证 |
| 旧令牌 | 1 | 合法schema及有效审批后到真实OperationLedger |
| 审批绑定、时间和伪造 | 7 | operation/caller/incident/args、过期、未来签发和错误密钥 |
| 风险伪装与参数越界 | 2 | kind与风险匹配、PID参数范围 |

真实路径是项目Policy/Bridge/OperationLedger，经官方MCP Python SDK与项目自有`tests/fixtures/bridge_mcp_server.py`的stdio服务交互。审计使用AmpAuditSink和官方CertificateAuditSigner；临时自签Ed25519证书只用于本地验签，不是平台CA证书，也不是官方数据库服务。

验证会在执行后重新读取audit文件，校验官方schema、JCS签名、证书kid/alg、actor/action/target/result、trace/correlation及返回引用。4项独立验证器行为检查覆盖缺失/重复/篡改/未签名、重新签名但字段错误，以及官方Emitter静默写失败和签名降级；仅返回log_id不能通过。

## 运行

使用自己的开发环境安装项目依赖后：

```text
python -m eval.gateway_policy_experiment
python -m eval.gateway_policy_experiment --run --output artifacts/my-e2c-run
python -m unittest discover -s tests -p test_gateway_policy_experiment.py
```

第一条只说明范围；第二条显式启动项目本地stdio测试服务，并创建临时SQLite及证书。输出目录必须不存在。临时私钥和审批材料会清理，公开输出只含自签公钥证书、签名audit、计数和来源摘要。Windows若在事件循环创建阶段被本机回环限制阻塞，需保留环境失败，再在允许本机回环的终端重试；无需修改代理。

## 实际证据与边界

[15例结果](../evidence/gateway-policy-e2c-20261019/run-attempt-1/results.json)、[签名记录](../evidence/gateway-policy-e2c-20261019/run-attempt-1/amp-audit.jsonl)、[公钥证书](../evidence/gateway-policy-e2c-20261019/run-attempt-1/audit-certificate.json)、[来源与初次环境失败](../evidence/gateway-policy-e2c-20261019/provenance.json)及[独立审阅](../evidence/gateway-policy-e2c-20261019/peer-review.json)分别保存。调用集实际exit0，4项验证器检查实际exit0；先前Windows初始化失败发生在test setUp前，原失败保留，不计为策略拒绝。

这是四类策略和签名审计链的本地组件验收。没有运行真实PostgreSQL、Docker、梧桐身份认证或Monitor入库，也不改原22例、旧E3、T05缺端与未知订单结论。平台身份绑定、生产CA验证及部署后行为仍以各自证据为准。

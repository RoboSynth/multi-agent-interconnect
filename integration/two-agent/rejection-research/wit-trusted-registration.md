# Identity 与可信注册

本地 `WitAgent` 要成为可信且可访问的 ACPs Agent，需要通过 ATR 注册取得 AIC 和证书，并发布 ACS。准备接入 Direct、Group 或 AMP，或者正在处理 `pending_review`、证书材料和监听地址时，可用本页串起完整流程。

## 先选择注册形态

`AcpsRegistration` 决定一个 workspace 走哪条 ATR 注册路径：

| 形态 | 用途 | endpoint |
|---|---|---|
| `AcpsRegistration.integrated()` | 默认开发路径；一次受审流程注册可运行实体 AIC | 可以发布 |
| `AcpsRegistration.ontology()` | 只注册可复用的 ontology AIC | 必须为空 |
| `AcpsRegistration.entity(ontology_workspace=...)` | 使用已 active 的 ontology workspace，通过 Registry mTLS 派生另一个可运行实体 | 可以发布 |

`entity()` 要求 `ontology_workspace` 中已经存在 active 的 ontology 身份及 client certificate、private key、trust bundle，并要求当前 `AcpsConfig` 显式配置 `registry_mtls_url`。

多数应用从 `integrated()` 开始。

## 完成一次 integrated 注册

下面是完整的注册脚本。它生成 ACS candidate，保存草稿，读取开发者凭据并推进状态机。示例地址是占位符，真实注册前应替换为环境清单中的地址。

```python
import asyncio

from wit import (
    AcpsConfig,
    AcpsDirect,
    AcpsRegistration,
    AgentCertificateRequest,
    AgentProviderProfile,
    RegistryPasswordCredentials,
    WitAgent,
    WitRuntime,
    capability,
)


@capability(
    id="travel.accessibility",
    description="为指定目的地生成无障碍旅行检查清单。",
    acps_skill=True,
    tags=["旅行", "无障碍"],
)
def accessible_checklist(destination: str) -> list[str]:
    return [
        f"确认 {destination} 的无台阶通行条件",
        "确认无障碍交通方式",
        "保存当地紧急联系人",
    ]


async def main() -> None:
    agent = WitAgent(
        id="accessible-travel-partner",
        display_name="无障碍旅行 Partner",
        description="生成无障碍旅行检查清单。",
        version="1.0.0",
        instructions="收到无障碍旅行请求时调用 accessible_checklist，并据此作答。",
        capabilities=[accessible_checklist],
        protocols=[AcpsDirect()],
    )

    acps = AcpsConfig.custom(
        registry_url="https://registry.example.com",
        registry_mtls_url="https://registry-mtls.example.com",
        ca_url="https://ca.example.com",
        discovery_url="https://discovery.example.com/acps-adp-v2/discover",
        public_endpoint="https://travel.example.com/acps/aip/v1",
        provider=AgentProviderProfile(
            organization="示例机构",
            country_code="CN",
        ),
        certificate=AgentCertificateRequest(requested_validity=365),
        registration=AcpsRegistration.integrated(),
        strict_interop=True,
        request_timeout_seconds=90,
    )

    runtime = WitRuntime(
        agent,
        workspace=".wit/accessible-travel-partner",
        acps=acps,
    )

    draft_path = runtime.save_acs()
    print(f"ACS 草稿：{draft_path}")

    credentials = RegistryPasswordCredentials.from_env()
    result = await runtime.up_until_ready(credentials=credentials)
    print(result.summary())

    if result.waiting_for_review:
        print("Registry 正在审核；审核通过后重新运行此脚本。")
    elif result.ready:
        status = await runtime.serve_direct_partner(
            host="0.0.0.0",
            port=8443,
        )
        print(status.to_dict())


asyncio.run(main())
```

`RegistryPasswordCredentials.from_env()` 只读取 `ACPS_USERNAME` 和 `ACPS_PASSWORD`。管理员审核凭据不是 Agent 开发者凭据，也不应放入 Agent 进程。

## AcpsConfig 是唯一部署配置源

`AcpsConfig` 同时承载两类事实：

- 基础设施：`registry_url`、`registry_mtls_url`、`ca_url`、`discovery_url`、可选的 `mq_url` 和 `mq_group_api_url`；
- ACS 与运行时：`public_endpoint`、`provider` 或 `acs_path`、证书请求、注册形态、strict 模式、超时和 Group 生命周期参数。

协议绑定不重复这些字段。`AcpsDirect` 不保存 Registry URL，`AcpsGroup` 也不保存 MQ 凭据。

使用生成式 ACS 时必须提供 `provider`。如果已经有完整、符合 ACS v02.02 candidate contract 的 JSON，可以改用 `acs_path`；两者互斥。`acs_path` 也不能再与 `certificate`、`icon_url`、`entity_meta` 等生成字段混用。

严格模式会要求：

- Registry、CA、Discovery 和 `public_endpoint` 使用 HTTPS；
- Group 的 `mq_url` 使用带显式 5671 端口和 `/acps` vhost 的 AMQPS URL；
- `mq_url` 与 `mq_group_api_url` 成对配置；
- Notification callback origin 是无路径的 HTTPS origin。

## ACS 从声明到权威版本

`WitAgent.compile(acps=...)` 根据公开 Capability 和协议绑定生成 ACS candidate。`runtime.acs_draft()` 返回规范化结果，`runtime.save_acs()` 默认写到 workspace 下的 `acps/acs.draft.json`。

注册过程中，wit 的 ACS 边界做三件事：

1. `project_registry_acs()` 只保留 ACS v02.02 已知字段，不靠隐式修复掩盖错误；
2. `validate_registry_acs()` 用带路径的错误定位缺失字段或非法值；
3. Registry 分配 AIC 后，wit 获取并校验 authoritative ACS，再提交本地 finalization。

ACS 是 Agent 对外公开的能力名片，不是本地运行配置的镜像。workspace 中的 token、private key、状态文件不会进入 ACS。

## 注册状态机怎样推进

`up()` 只推进一个可观察的状态机 tick。`up_until_ready()` 是小应用的便捷入口，会连续推进本地可完成的步骤，并在需要外部动作时停止。

典型主线是：

```text
needs_login → draft_ready → submitted → pending_review
→ approved → issuing_certificates → finalizing → active → serving
```

实际中还可能出现 `entity_registered`、`blocked`、`rejected`、`needs_renewal` 或 `failed`。应读取 `EnrollmentResult.status`、`next_action` 和 `summary()`，不要把一次 `up()` 调用理解成“注册一定已经完成”。

`EnrollmentResult` 提供三个便捷判断：

- `ready`：状态为 `active` 或 `serving`；
- `waiting_for_review`：状态为 `pending_review`；
- `blocked`：需要登录、修复配置或人工恢复，或已被拒绝等不能自动继续的状态。

审核是外部 Registry 行为。`up_until_ready()` 到达 `pending_review` 后会如实返回；审核完成后再次调用即可继续。

## 证书签发与验证

Registry 批准并分配 AIC 后，wit 获取 EAB 信息，通过 CA 签发 clientAuth 和 serverAuth 两套证书，下载 trust bundle，并在写入 active identity 前验证：

- leaf certificate 的 CN 与 AIC 一致；
- 恰好存在一个 `acps://{AIC}` URI SAN；
- client/server EKU 分别严格匹配 clientAuth/serverAuth；
- private key 与 leaf public key 匹配；
- 证书在有效期内，证书链可到达 trust bundle；
- 使用 Direct 时，server certificate 的 DNS/IP SAN 覆盖 `public_endpoint` 主机。

identity 只有在全部检查通过后才会进入 active 状态，strict listener 也只使用已验证的证书材料启动。

## up、serve 与生命周期入口

| 方法 | 作用 |
|---|---|
| `login(credentials=...)` | 登录 Registry，并安全保存开发者 token |
| `enroll(credentials=...)` | 推进一次注册状态 |
| `up(...)` | `enroll()` 的单 tick 入口；可在 active 后选择启动服务 |
| `up_until_ready(...)` | 连续推进本地步骤，到外部审核、active、serving 或 blocker 停止 |
| `serve(...)` | 启动已声明的 Direct/Group 服务，并默认启动 AMP |
| `serve_direct_partner(...)` | 只启动 Direct Partner listener |
| `serve_group(...)` | 只启动 Group consumer 与后台服务 |
| `stop_serving()` | 停止 AMP、listener、Coordinator 与 Group transport |

这些 `serve*()` 方法的 listener 参数与 `AcpsConfig.public_endpoint`、DNS/代理映射及证书 SAN 的关系，统一见 [ACPs 总览](overview.md)。


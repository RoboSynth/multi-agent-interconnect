# AIP Group

AIP Group 面向一个 Leader 与多个 Partner 的长期群组协作，让各 Partner 独立执行同一个任务。搭建多成员工作流、配置 RabbitMQ transport、管理 Group membership 或编写 Group admission 策略时，可以从本页开始。

AIP Group 作为独立的数据平面，专注于多成员广播与组内任务调度。它与 Direct 共用可信身份、Discovery 和 Partner Agent 执行器，但 Group 成员关系、transport、store 和任务聚合由 `AipGroupCoordinator` 单独管理。

## Group 结构规范

在 wit 的开发者视角中，一个 Group 最终包含：

- 一个 Leader；
- 一个或多个 Partner；
- 一个 Group exchange；
- 每个 Agent 自己的 queue；
- 每个 Agent 自己的本地 Group 视角与持久化状态。

Leader 先通过 Discovery 取得 Partner 的 Group 可用性，再创建 Group。wit 使用已配置的 mq-auth-server 建立访问授权，并通过 RabbitMQ 建立 consumer 和消息投递；这些外部服务的职责边界统一见 [ACPs 总览](overview.md)。

Group invitation 默认走 Partner 的 inbox queue。当显式启用 `group_rpc_invitation_fallback=True` 且 Partner 具备可用 Direct endpoint 时，邀请支持平滑切至 Direct RPC 路径；加入后业务流量仍走 Group MQ。

## Group 基础设施配置

Group 需要 `mq_url` 与 `mq_group_api_url` 成对出现。strict 模式下，`mq_url` 必须是 AMQPS、显式端口 5671，并使用 `/acps` vhost。

```python
from wit import (
    AcpsConfig,
    AcpsRegistration,
    AgentCertificateRequest,
    AgentProviderProfile,
)


acps = AcpsConfig.custom(
    registry_url="https://registry.example.com",
    registry_mtls_url="https://registry-mtls.example.com",
    ca_url="https://ca.example.com",
    discovery_url="https://discovery.example.com/acps-adp-v2/discover",
    mq_url="amqps://mq.example.com:5671/acps",
    mq_group_api_url="https://mq-auth.example.com",
    provider=AgentProviderProfile(
        organization="示例机构",
        country_code="CN",
    ),
    certificate=AgentCertificateRequest(requested_validity=365),
    registration=AcpsRegistration.integrated(),
    strict_interop=True,
    group_rpc_invitation_fallback=False,
    request_timeout_seconds=90,
)
```

`public_endpoint` 在纯 Group Agent 场景中为可选配置；在同时启用 Direct 或需暴露 RPC 邀请地址时配置。

## Partner 接入与任务消费

Partner 声明 `AcpsGroup()`，可用 `AipGroupAdmissionHooks` 决定是否加入陌生 Group。该扩展放在 `aip_hooks` 中。

```python
import os

from wit import (
    AipGroupAdmissionDecision,
    AipGroupAdmissionHooks,
    AcpsGroup,
    OpenAIChatProvider,
    WitAgent,
    capability,
)


@capability(
    id="review.security",
    description="审查一项变更中的安全风险。",
    acps_skill=True,
)
def security_review(change: str) -> dict:
    return {"change": change, "risks": ["验证授权边界"]}


def admit_group(request):
    if request.publisher_verified:
        return AipGroupAdmissionDecision.accept()
    return AipGroupAdmissionDecision.reject("需要已验证的发布者身份")


partner = WitAgent(
    id="security-review-partner",
    display_name="安全审查 Partner",
    description="审查单项变更中的安全风险。",
    version="1.0.0",
    instructions="处理每个入站 Group Task 时调用 security_review。",
    model=OpenAIChatProvider(
        model=os.environ["OPENAI_MODEL"],
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ),
        temperature=0,
    ),
    capabilities=[security_review],
    protocols=[AcpsGroup()],
    aip_hooks=[AipGroupAdmissionHooks(admit_group)],
)
```

Group invitation admission 与 task admission 是两件事：

- `AipGroupAdmissionHooks` 决定是否加入 Group；
- `AipPartnerAdmissionHooks` 决定是否接受某个 task，Direct 和 Group 共用这个 task 准入接口，Group 时 `delivery="group"`。

获得 active identity 后，Partner 使用：

```python
from wit import WitRuntime


async def start_partner(runtime: WitRuntime) -> None:
    status = await runtime.serve_group()
    if status.status != "serving":
        raise RuntimeError(str(status.to_dict()))
```

`serve_group()` 不开启 HTTP listener；它验证 MQ 配置和 active certificate material，启动 inbox consumer、恢复已加入 Group 的 consumer、对账中断任务，并启动 outbox 与维护循环。也可以调用 `runtime.serve(direct=False)`。

## Leader 管理流程

Leader 注册 `AipGroupDelegationHooks` 后得到三个模型工具：

| 工具 | 作用 |
|---|---|
| `acps_discover` | 查找并缓存 Group-capable Partner |
| `acps_group` | `create`、`list`、`inspect`、`status`、`mute`、`unmute`、`remove`、`dissolve` |
| `acps_group_task` | `start`、`list`、`inspect`、`wait`、`continue`、`complete`、`cancel` |

完整 Leader 声明如下：

```python
import os

from wit import (
    AipGroupDelegationHooks,
    AcpsGroup,
    OpenAIChatProvider,
    WitAgent,
)


leader = WitAgent(
    id="change-review-leader",
    display_name="变更审查 Leader",
    description="协调多个 Partner 共同审查一项变更。",
    version="1.0.0",
    instructions=(
        "创建 Group 前先调用 acps_discover。持续检查 Group，直到所需 Partner "
        "全部连接；随后启动一个 Group Task，等待成员结果，并完成状态允许的成员任务。"
    ),
    model=OpenAIChatProvider(
        model=os.environ["OPENAI_MODEL"],
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ),
        temperature=0,
    ),
    protocols=[AcpsGroup()],
    hooks=[AipGroupDelegationHooks()],
)
```

`acps_group(action="create")` 返回 `inviting` 只表示邀请已开始，不证明所有 Partner 已加入。开始任务前应 `inspect` Group，并检查目标成员的 `connected` 状态。

## 程序化 Group 控制

不通过模型工具时，可以直接使用 `WitRuntime` 的高层方法：

```python
import asyncio

from wit import AgentState, TextPart, WitRuntime


async def run_group_review(runtime: WitRuntime) -> dict:
    state = AgentState()
    discovery = await runtime.aip_discover(
        "安全与可靠性审查",
        limit=20,
        include_unavailable=False,
    )
    partner_aics = [
        item["aic"]
        for item in discovery["agents"]
        if item["active"] and item["group_available"]
    ][:2]
    if len(partner_aics) != 2:
        raise RuntimeError("Two active Group Partners are required")

    group = await runtime.aip_group(
        state,
        action="create",
        group_id="release-review-2026-08",
        partners=partner_aics,
    )
    for _ in range(30):
        group = await runtime.aip_group(
            state,
            action="inspect",
            group_ref=group["group_ref"],
        )
        selected = [
            member
            for member in group["members"]
            if member["aic"] in partner_aics
        ]
        if len(selected) == 2 and all(member["connected"] for member in selected):
            break
        await asyncio.sleep(2)
    else:
        raise TimeoutError("Partners did not join the Group")

    task = await runtime.aip_group_task(
        state,
        action="start",
        group_ref=group["group_ref"],
        request=[TextPart("请审查 2026.08 发行候选版本。")],
        partner_aics=partner_aics,
    )
    while task["aggregate_state"] not in {
        "awaiting-input",
        "awaiting-completion",
        "finished",
    }:
        task = await runtime.aip_group_task(
            state,
            action="wait",
            task_ref=task["task_ref"],
        )
    if task["aggregate_state"] == "awaiting-input":
        raise RuntimeError("A Partner requested additional input")
    if task["aggregate_state"] == "awaiting-completion":
        task = await runtime.aip_group_task(
            state,
            action="complete",
            task_ref=task["task_ref"],
        )
    return task
```

Group 和 task 的 `list` 动作都支持 `offset` 分页，并返回 `returned`、`total` 与 `has_more`。

## 独立任务状态维护

一个 Group Task 有共同的 task id，但每个 Partner 分别执行，并独立维护自己的 state 与 Products；成员之间不共享一份可变任务状态。Leader 看到的是成员结果的聚合视图：某个 Partner 可以已经 `awaiting-completion`，另一个仍在 `working`，第三个可能 `failed`。

因此 `inspect` 需要查看 member 级结果；`continue`、`complete`、`cancel` 也可以通过 `partner_aics` 只指向一个子集。wit 会先检查所选成员是否都允许目标状态转移，再发送命令。

Partner 侧仍使用共享的 `AipPartnerExecutor`，所以 `aip_submit`、`aip_request_input`、`aip_fail` 和 `AipPartnerTransformHooks` 在 Group 中同样有效。

## 运行生命周期与停止

Group transport 使用 at-least-once delivery。wit 负责消息去重、receipt、outbox 重试和本地恢复，但应用仍应让业务处理具备合理的幂等性。

调用 `runtime.stop_serving()` 会停止 AMP、Group Coordinator、consumer 和 transport。推荐通过 `WitRuntime` 生命周期统一管理 `RabbitMqGroupTransport` 或本地 store。


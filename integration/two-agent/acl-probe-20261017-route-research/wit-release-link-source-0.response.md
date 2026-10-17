# 梧桐智能体开发框架（wit）

梧桐（wit）是一个原生支持 ACPs 的智能体开发框架。你可以用 `WitAgent` 声明模型、指令、业务能力和扩展，用 `compile()` 生成可检查的运行配置，再由 `WitRuntime` 执行模型调用、工具循环和事件流。

```python
import asyncio
import os

from wit import OpenAIChatProvider, WitAgent, WitRuntime, capability


@capability(id="math.add", description="计算两个整数的和。")
def add(a: int, b: int) -> int:
    return a + b


async def main() -> None:
    provider = OpenAIChatProvider(
        model=os.environ["OPENAI_MODEL"],
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        temperature=0,
    )
    runtime = WitRuntime(
        WitAgent(
            id="calculator",
            instructions="需要计算时调用 math_add，并用一句话给出结果。",
            model=provider,
            capabilities=[add],
        )
    )
    try:
        result = await runtime.run("2 + 3 等于多少？")
        print(result.final_text)
    finally:
        await provider.aclose()


asyncio.run(main())
```

> [!TIP]
> wit `v2.1.0` 要求 Python `>=3.12`，并与 `acps-sdk 2.2.0` 配套使用。开始前请完成[安装与发行校验](get-started/install.md)。

## 核心能力

### 声明、编译与运行

`WitAgent` 描述 Agent 的模型、指令、Capability 和 Hooks；`CompiledAgent` 固化编译结果；`WitRuntime` 负责执行。业务声明、运行机制与生命周期扩展因此可以分别复用、检查和测试。

### 原生 ACPs 协作

wit 将 Agent 接入 ACPs 的可信身份、任务委派与可观测能力。同一个 `WitAgent` 可以在清晰的协议绑定和部署配置下成为 Leader 或 Partner，并使用 AIP Direct、AIP Group 与 AMP 完成跨 Agent 协作。参见 [ACPs 总览](acps/overview.md)。

### Provider 中立的内容与事件

文本、推理、多模态附件、工具调用和流式事件先由 wit 的统一类型表达，再交给 Provider 与 Adapter 处理。业务代码可以使用稳定的内容和事件层，同时对接不同模型服务。

### 可组合的开发路径

Capability 将 Python 业务函数变成类型化工具；Hooks 在固定生命周期节点接入策略与状态；核心指南与 API 参考则分别提供完整任务路径与签名速查。

## 从这里开始

- [安装](get-started/install.md)：准备 Python 环境，安装配套 wheel 并完成 preflight。
- [快速开始](get-started/quickstart.md)：构建第一个 Agent，逐步加入 Capability、Hooks 和流式事件。
- [核心概念](core-concepts/wit-agent-and-compile.md)：理解声明、编译、运行时与内容模型。
- [构建 Agent](building-agents/organizing-capabilities.md)：组织能力、扩展、MCP 工具和测试。
- [模型接入](providers/model-providers.md)：连接模型服务并处理网关差异与内容转换。
- [ACPs](acps/overview.md)：接入可信身份、AIP 协作与 AMP 可观测性。
- [架构](architecture.md)：查看 kernel、Provider 与 ACPs 适配层的整体结构。
- [API 参考](api-reference/index.md)：按模块查找公开类、函数与签名。
- [错误参考](errors/aip-errors.md)：定位运行时、Provider 与 ACPs 错误。
- [更新记录](changelog.md)：查看版本能力与兼容要求。

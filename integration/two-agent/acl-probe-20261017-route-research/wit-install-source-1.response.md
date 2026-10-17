# 快速开始

> [!NOTE]
> **目标**：先运行一个最小 Agent，再依次加入 `@capability`、`WitHooks` 和流式事件。完成后，你将了解 wit 如何把 Agent 声明、业务能力、运行机制和观察接口组合起来。

## 前置要求

- 已按[安装指南](install.md)完成安装并通过发行预检。
- 已设置 `OPENAI_MODEL` 和 `OPENAI_API_KEY`。
- 如果使用兼容 OpenAI API 的服务根地址，可额外设置 `OPENAI_BASE_URL`，例如 `https://api.example.com/v1`。不要把 `/chat/completions` 写进 `base_url`。

下面每一步都可以保存成 Python 文件直接运行。

## 步骤 1：运行基础 Agent

`WitAgent` 声明 Agent，`WitRuntime` 执行它。`run()` 是异步方法，返回完整的 `RunResult`。

```python
import asyncio
import os

from wit import OpenAIChatProvider, WitAgent, WitRuntime


async def main() -> None:
    provider = OpenAIChatProvider(
        model=os.environ["OPENAI_MODEL"],
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        temperature=0,
    )
    runtime = WitRuntime(
        WitAgent(
            id="assistant",
            instructions="请用中文简洁回答。",
            model=provider,
        )
    )
    try:
        result = await runtime.run("用一句话说明什么是 Agent runtime。")
        print(result.final_text)
    finally:
        await provider.aclose()


asyncio.run(main())
```

## 步骤 2：添加 Capability

`@capability` 保留原 Python 函数，同时附加一份 `Capability` 声明。类型标注会生成模型可见的输入、输出 schema；被装饰的函数可以直接放进 `WitAgent.capabilities`。

```python
import asyncio
import os

from wit import OpenAIChatProvider, WitAgent, WitRuntime, capability


@capability(id="math.add", description="计算两个整数之和。")
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
            instructions="遇到加法时，先调用 math_add，再用中文回答。",
            model=provider,
            capabilities=[add],
        )
    )
    try:
        result = await runtime.run("计算 17 + 25。")
        print(result.final_text)
        print(result.observations)
    finally:
        await provider.aclose()


asyncio.run(main())
```

> [!NOTE]
> `math.add` 是业务侧的 Capability `id`；提供给模型的工具名会把点号等不接受的字符规范化为 `_`，因此 `instructions` 中要写 `math_add`。字母、数字、`-` 和 `_` 本身会保留。

工具执行结果会写入 `RunResult.observations`，也会作为 `tool` 消息追加到这次对话中。如果模型还需继续处理，它会在下一步看到这条结果。

## 步骤 3：配置 Hooks

Capability 表达 Agent 能执行什么业务动作；Hooks 定义模型、工具和整次 `run` 会经过哪些机制。下面的扩展用于观察生命周期，不修改业务结果。

```python
import asyncio
import os

from wit import (
    OpenAIChatProvider,
    RunEndEvent,
    RunStartEvent,
    WitAgent,
    WitHooks,
    WitRuntime,
    capability,
)


@capability(id="math.add", description="计算两个整数之和。")
def add(a: int, b: int) -> int:
    return a + b


class RunLogger(WitHooks):
    id = "example.run-logger"

    async def on_run_start(self, event: RunStartEvent) -> None:
        print("run started:", event.context.compiled.agent_id)

    async def on_run_end(self, event: RunEndEvent) -> None:
        print("run ended:", event.result.status)


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
            instructions="遇到加法时，先调用 math_add，再用中文回答。",
            model=provider,
            capabilities=[add],
            hooks=[RunLogger()],
        )
    )
    try:
        result = await runtime.run("计算 17 + 25。")
        print(result.final_text)
    finally:
        await provider.aclose()


asyncio.run(main())
```

## 步骤 4：订阅事件流

把 `run()` 换成 `astream_events()`，就能在执行过程中逐个读取类型化的 `WitStreamEvent`，实时观察同一条业务执行循环。

```python
import asyncio
import os

from wit import OpenAIChatProvider, WitAgent, WitRuntime


async def main() -> None:
    provider = OpenAIChatProvider(
        model=os.environ["OPENAI_MODEL"],
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    runtime = WitRuntime(
        WitAgent(
            id="streaming-assistant",
            instructions="请用中文简洁回答。",
            model=provider,
        )
    )
    try:
        async for event in runtime.astream_events("介绍一下事件流。"):
            print(event.event, event.name)
    finally:
        await provider.aclose()


asyncio.run(main())
```

`stream()` 提供同一事件的字典形式；`astream_tokens()`、`astream_reasoning()` 和 `astream_messages()` 分别只保留答案文本增量、推理文本或追加的消息。

## 预期运行结果

不含工具调用的 `run` 通常依次出现 `run.start`、`step.start`、模型事件、`message.append`、`step.end` 和 `run.end`。包含 Capability 的 `run` 还会出现 `tool.start`、`tool.end`，随后进入下一个 `step`。具体答案由所选模型决定，事件的职责和层级保持稳定。


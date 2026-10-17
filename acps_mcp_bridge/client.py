"""Official MCP Python SDK stdio transport. No protocol emulation."""
from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta
import os
from typing import Any


@dataclass(frozen=True)
class ServerConfig:
    command: str
    args: list[str] = field(default_factory=list)
    env_names: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 15


class McpStdioClient:
    def __init__(self, config: ServerConfig):
        self.config = config
        self._stack = None
        self.session = None

    async def __aenter__(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        env = {name: os.environ[name] for name in self.config.env_names if name in os.environ}
        missing = set(self.config.env_names) - set(env)
        if missing:
            raise ValueError("Missing MCP environment names: " + ", ".join(sorted(missing)))
        env.update(self.config.env)
        stack = AsyncExitStack()
        try:
            reader, writer = await stack.enter_async_context(stdio_client(
                StdioServerParameters(command=self.config.command, args=self.config.args, env=env)))
            self.session = await stack.enter_async_context(ClientSession(
                reader, writer, read_timeout_seconds=timedelta(seconds=self.config.timeout_seconds)))
            await self.session.initialize()
        except BaseException:
            await stack.aclose()
            raise
        self._stack = stack
        return self

    async def __aexit__(self, *exc):
        if self._stack:
            await self._stack.__aexit__(*exc)
        self.session = None

    async def tools(self) -> list[dict[str, Any]]:
        if not self.session:
            raise RuntimeError("MCP client has not been entered")
        tools, cursor = [], None
        while True:
            page = await self.session.list_tools(cursor=cursor)
            tools.extend(tool.model_dump(mode="json", exclude_none=True) for tool in page.tools)
            cursor = page.nextCursor
            if not cursor:
                return tools

    async def call(self, name: str, arguments: dict) -> dict:
        if not self.session:
            raise RuntimeError("MCP client has not been entered")
        result = await self.session.call_tool(name, arguments)
        return result.model_dump(mode="json", exclude_none=True)

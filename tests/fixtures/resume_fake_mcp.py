"""Real stdio MCP server backed only by an isolated unittest file resource."""
from pathlib import Path
import json
import sys
from mcp.server.fastmcp import FastMCP

resource = Path(sys.argv[1])
mcp = FastMCP("f15-isolated-file-resource")


@mcp.tool()
def execute_sql(sql: str):
    state = json.loads(resource.read_text(encoding="utf-8"))
    if sql == "SELECT restore_writes":
        state["read_only"] = False
        state["modifying_calls"] += 1
        resource.write_text(json.dumps(state), encoding="utf-8")
    elif sql != "SELECT read_only":
        raise ValueError("fixture query is outside its fixed allowlist")
    return [{"read_only": state["read_only"]}]


if __name__ == "__main__":
    mcp.run(transport="stdio")


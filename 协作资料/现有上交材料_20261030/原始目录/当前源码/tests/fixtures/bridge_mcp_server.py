"""Real stdio MCP fixture; no database or Docker effects."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("bridge-transport-test")
_writes = 0


@mcp.tool()
def execute_sql(sql: str) -> list[dict]:
    global _writes
    if sql == "SELECT incident_ops.restore_writes() AS read_only":
        _writes += 1
        return [{"read_only": False}]
    if "pg_db_role_setting" in sql:
        return [{"read_only": _writes == 0}]
    if "pg_stat_activity" in sql:
        return []
    raise ValueError("SQL is outside the fixture templates")


@mcp.tool()
def analyze_db_health(health_type: str = "connection") -> dict:
    return {"healthy": True, "health_type": health_type, "writes": _writes}


if __name__ == "__main__":
    mcp.run(transport="stdio")

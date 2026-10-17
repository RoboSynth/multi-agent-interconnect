"""Provision the experiment bridge role without printing or sharing admin secrets."""
from __future__ import annotations

import asyncio
from pathlib import Path
import secrets
from urllib.parse import quote

import asyncpg

ROOT = Path(__file__).resolve().parents[2]


def read_env(path):
    return {name.strip(): value.strip().strip('"').strip("'") for line in Path(path).read_text(
        encoding="utf-8-sig").splitlines() if "=" in line and not line.lstrip().startswith("#")
            for name, _, value in [line.partition("=")]}


async def provision():
    env = read_env(ROOT / "runtime/private/postgres-superuser.env")
    connection = await asyncpg.connect(host=env["PGHOST"], port=int(env["PGPORT"]),
        database="orders", user=env["PGUSER"], password=env["PGPASSWORD"])
    try:
        await connection.execute((Path(__file__).with_name("bootstrap.sql")).read_text(encoding="utf-8"))
        destination = ROOT / "runtime/private/database-bridge.env"
        # Preserve the domain's existing password on repeated provisioning.
        previous = read_env(destination) if destination.exists() else {}
        password = previous.get("PGPASSWORD", secrets.token_urlsafe(32))
        await connection.execute("ALTER ROLE bridge_operator PASSWORD '" + password.replace("'", "''") + "'")
        uri = f"postgresql://bridge_operator:{quote(password, safe='')}@{env['PGHOST']}:{env['PGPORT']}/orders"
        destination.write_text("\n".join([f"PGHOST={env['PGHOST']}", f"PGPORT={env['PGPORT']}",
            "PGDATABASE=orders", "PGUSER=bridge_operator", f"PGPASSWORD={password}", f"DATABASE_URI={uri}"]) + "\n", encoding="utf-8")
        print("bridge_operator provisioned; domain-only environment written to runtime/private/database-bridge.env")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(provision())

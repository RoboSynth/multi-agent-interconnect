"""Read-only systemd pre-start wait; never start a transport or domain process."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys


async def wait_ready(root, host_config, *, waiter=None):
    settings = json.loads(Path(host_config).read_text(encoding="utf-8-sig"))
    sys.path[:0] = [str(root), str(root / "vendor/ACPs-community/acps-sdk")]
    if waiter is None:
        from cloud_runtime import wait_workbench
        waiter = wait_workbench
    state = await waiter(settings, root=root)
    return dict(status="ready", host_status=state["status"], pid=state["pid"],
                host_session=state["session_id"], identity_consumers_started=0,
                checked="loopback API connected/formal/resource0 plus managed host running")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("/opt/incident-pilot"))
    parser.add_argument("--host-config", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    host_config = args.host_config or root / "runtime/private/cloud-longrun/host.json"
    if not args.execute:
        print(json.dumps(dict(status="prepared_not_executed", identity_consumers_started=0,
                              host_config=str(host_config), network_attempted=False)))
        return 0
    try:
        result = asyncio.run(wait_ready(root, host_config))
        print(json.dumps(result))
        return 0
    except Exception as error:
        print(json.dumps(dict(status="failed", error_class=type(error).__name__, identity_consumers_started=0)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

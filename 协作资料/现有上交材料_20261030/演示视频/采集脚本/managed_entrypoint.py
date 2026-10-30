"""Batch-only signal adapter; preserve the worker's original Docker Cmd.

The normal and E1 worker implementations remain unchanged. Docker appends their
original command to this entrypoint. A planned os._exit keeps its original code;
ordinary SIGTERM waits for the worker's original SDK cleanup finally.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import runpy
import signal
import sys


def dispatch(command):
    if command == ["python", "-m", "acps_mcp_bridge", "--config", "/domain/bridge.json"]:
        return "module", "acps_mcp_bridge", command[3:]
    if command == ["python", "incident/platform_worker.py", "--config", "/domain/config.json"]:
        return "path", "/srv/incident/platform_worker.py", command[2:]
    if (command[:2] == ["python", "/experiment/source/eval/platform_database_worker.py"]
            and "--serve" in command and command.count("--config") == 1
            and command[command.index("--config") + 1] == "/domain/bridge.json"):
        return "path", command[1], command[2:]
    raise ValueError("Only the bound normal/E1 domain worker commands are allowed")


async def managed(work, *, role, session, run_managed):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for number in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(number, stop.set)
    await run_managed(work, stop)
    print(json.dumps(dict(status="managed_consumer_closed", role=role,
                          session=session, sdk_cleanup_completed=True)), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    kind, name, tail = dispatch(command)
    spec = importlib.util.spec_from_file_location("batch_managed_protocol", "/batch/domain_entry.py")
    protocol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(protocol)
    original_run = asyncio.run

    def run(work, **kwargs):
        asyncio.run = original_run
        return original_run(managed(work, role=args.role, session=args.session,
                                    run_managed=protocol.run_managed), **kwargs)

    asyncio.run = run
    sys.argv = [name, *tail]
    sys.path.insert(0, "/srv")
    try:
        if kind == "module":
            runpy.run_module(name, run_name="__main__")
        else:
            runpy.run_path(name, run_name="__main__")
    finally:
        asyncio.run = original_run


if __name__ == "__main__":
    main()

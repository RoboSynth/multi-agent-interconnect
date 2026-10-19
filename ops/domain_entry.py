"""Managed-container signal adapter; wait for the existing SDK cleanup finally."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def run_managed(work, stop):
    worker = asyncio.create_task(work)
    stopping = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait({worker, stopping}, return_when=asyncio.FIRST_COMPLETED)
        if worker in done:
            await worker
            raise RuntimeError("Managed consumer ended without a stop signal")
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
    finally:
        stopping.cancel()
        await asyncio.gather(stopping, return_exceptions=True)
        # Supervisor/asyncio cancellation can arrive before the signal branch.
        # Await the worker's original finally in that path as well; a cleanup
        # exception must remain visible rather than becoming a successful exit.
        if not worker.done():
            worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


async def run(args):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for number in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(number, stop.set)
    if not os.environ.get("INCIDENT_MANAGED_SESSION"):
        raise ValueError("Managed consumer requires a supervisor session")
    if args.kind == "platform":
        from incident.platform_worker import load_config, serve
        work = serve(load_config(Path(args.config)))
    else:
        from acps_mcp_bridge.__main__ import run as bridge_run
        args.acs_base = args.payload = args.caller_aic = None
        work = bridge_run(args)
    await run_managed(work, stop)
    # Exit 0 is emitted only after normal SDK/MCP shutdown. Cleanup exceptions
    # reach the supervisor as nonzero; it must quarantine rather than hand off.
    print(json.dumps(dict(status="managed_consumer_closed", role=args.role,
                          session=os.environ["INCIDENT_MANAGED_SESSION"], sdk_cleanup_completed=True)), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["platform", "bridge"], required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--role", required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()

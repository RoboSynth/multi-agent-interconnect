"""Prepare/run 252 synthetic records through seven local stdout Tail sources.

No Kafka, HTTP, real AIC data, Docker, or shared service controls. The Windows
collector host gets its own hidden console and signals only that console.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render as fluent

BATCHES = ("seed", "live_append", "live_new_file", "offline_append", "offline_existing", "offline_new_file")
BINARY = ROOT / "tools/runtime/fluent-bit-5.1.3/fluent-bit-5.1.3-win64/bin/fluent-bit.exe"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    temporary = Path(str(path) + ".writing")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def utc():
    return datetime.now(timezone.utc).isoformat()


def owned_output(value):
    path = Path(value).resolve()
    if not path.is_relative_to(ROOT / "artifacts") or path == ROOT / "artifacts":
        raise ValueError("Output must be a dedicated project artifact directory")
    return path


def runtime_sources():
    return {name: sha(Path(__file__).with_name(name)) for name in
            ("render.py", "verify_collection.py", "verify_local.py", "parsers.conf")}


async def prepare_records(output):
    write(output / "preparation-progress.json", {"stage": "async_fixture_generator_entered", "observed_utc": utc()})
    from verify_local import emit_examples
    write(output / "preparation-progress.json", {"stage": "fixture_emitter_imported", "observed_utc": utc()})
    expected = {}
    for batch in BATCHES:
        for role in fluent.COLLECTION_ROLES:
            directory = output / "records" / batch / role
            directory.mkdir(parents=True)
            await emit_examples(directory)
            for kind in fluent.KINDS:
                path = directory / f"amp_{kind}_routing.jsonl"
                lines = path.read_text(encoding="utf-8").splitlines()
                if len(lines) != 1:
                    raise RuntimeError("Expected one SDK-emitted fixture record per source/kind/batch")
                record = json.loads(lines[0])
                # Keep synthetic timings exactly representable for content comparison.
                def stable(value):
                    if isinstance(value, float):
                        return round(value, 3)
                    if isinstance(value, dict):
                        return {key: stable(item) for key, item in value.items()}
                    if isinstance(value, list):
                        return [stable(item) for item in value]
                    return value
                record = stable(record)
                path.write_text(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
                identity = record["log_id"]
                if identity in expected:
                    raise RuntimeError("Fixture log_id is not unique")
                expected[identity] = {"role": role, "kind": kind, "batch": batch, "record": record,
                                      "source": path.relative_to(output).as_posix(), "sha256": sha(path)}
    return expected


def append_batch(output, batch):
    suffix = {"live_new_file": "_2", "offline_existing": "_2", "offline_new_file": "_3"}.get(batch, "")
    mode = "xb" if batch in {"live_new_file", "offline_new_file"} else "ab"
    for role in fluent.COLLECTION_ROLES:
        for kind in fluent.KINDS:
            name = f"amp_{kind}_routing.jsonl"
            target = f"amp_{kind}_routing{suffix}.jsonl"
            with (output / "inputs" / role / target).open(mode) as stream:
                stream.write((output / "records" / batch / role / name).read_bytes())


def prepare(output):
    output.mkdir(parents=True, exist_ok=False)
    sources = {role: output / "inputs" / role for role in fluent.COLLECTION_ROLES}
    for directory in sources.values():
        directory.mkdir(parents=True)
    write(output / "preparation-progress.json", {"stage": "starting_async_fixture_generator", "observed_utc": utc()})
    expected = asyncio.run(prepare_records(output))
    append_batch(output, "seed")
    # Archived and temporary near-matches must never reach Tail.
    for directory in sources.values():
        for kind in fluent.KINDS:
            for suffix in (".1", ".tmp", ".1.tmp", ".db"):
                (directory / (f"amp_{kind}_routing.jsonl" + suffix)).write_text('{"log_id":"forbidden-near-match"}\n', encoding="utf-8")
    write(output / "expected.json", expected)
    write(output / "sources.json", {role: str(directory) for role, directory in sources.items()})
    plan = {"schema_version": "fluent-bit-seven-source-local/1", "status": "prepared_not_started",
        "prepared_utc": utc(), "sources": len(sources), "tail_inputs": 42, "offset_databases": 42,
        "unique_expected_records": len(expected), "batches": list(BATCHES),
        "executable": str(BINARY), "executable_sha256": sha(BINARY), "source_sha256": runtime_sources(),
        "expected_sha256": sha(output / "expected.json"), "sources_sha256": sha(output / "sources.json"),
        "actual_collectors_started": 0, "actual_helpers_started": 0,
        "phase_expected_counts": {"phase1": 126, "phase2": 42, "phase3": 84},
        "stop": "Own hidden-console host checks its console contains only itself and its collector, ignores CTRL_C only after spawning the child, then sends CTRL_C to that console; normal child exit must be 0",
        "boundaries": {"synthetic_only": True, "network": False, "kafka": False, "docker": False,
                       "formal_identities": False, "shared_services": False, "copytruncate_claim": False,
                       "no_rename_tested": True, "append_only_stable_files": True}}
    if len(expected) != 252:
        raise RuntimeError("Expected 252 unique fixture records")
    write(output / "plan.json", plan)
    return plan


def console_members(kernel):
    import ctypes
    from ctypes import wintypes
    pids = (wintypes.DWORD * 16)()
    count = kernel.GetConsoleProcessList(pids, len(pids))
    if count == 0 or count > len(pids):
        raise RuntimeError("Cannot verify exclusive collector console")
    return set(pids[:count])


def wait_console_pair(kernel, child, *, timeout=5):
    """Allow only the initial host-only attachment race, bounded to five seconds."""
    started = time.monotonic()
    host = os.getpid()
    evidence = {"ready": False, "initial_members": None, "observations": []}
    while True:
        members = console_members(kernel)
        elapsed = time.monotonic() - started
        if evidence["initial_members"] is None:
            evidence["initial_members"] = sorted(members)
        evidence["observations"].append({"elapsed_seconds": round(elapsed, 6), "members": sorted(members)})
        evidence["wait_seconds"] = round(elapsed, 6)
        actual_exit = child.poll()
        if actual_exit is not None:
            return dict(evidence, reason="child_exited", collector_actual_exit_code=actual_exit)
        if members == {host, child.pid}:
            return dict(evidence, ready=True, reason="exclusive_pair_ready")
        if members != {host}:
            return dict(evidence, reason="unexpected_console_member")
        if elapsed >= timeout:
            return dict(evidence, reason="console_attachment_timeout")
        time.sleep(min(0.05, timeout - elapsed))


def collector_host(spec_path):
    """Internal child: never attach to, detach from or signal a shared console."""
    if os.name != "nt":
        raise RuntimeError("This real portable-binary verification requires Windows")
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetConsoleProcessList.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    kernel.GetConsoleProcessList.restype = wintypes.DWORD
    kernel.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
    kernel.SetConsoleCtrlHandler.restype = wintypes.BOOL
    kernel.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
    if console_members(kernel) != {os.getpid()}:
        raise RuntimeError("Refuse to launch from an existing/shared console")
    if not kernel.SetConsoleCtrlHandler(None, False):
        raise OSError("Cannot clear inherited CTRL_C-ignore state in own console")
    spec = read(spec_path)
    phase = owned_output(Path(spec_path).parent)
    executable = Path(spec["executable"]).resolve()
    if executable != BINARY.resolve() or sha(executable) != spec["executable_sha256"]:
        raise RuntimeError("Collector binary differs from prepared portable binary")
    result = {"started_utc": utc(), "host_pid": os.getpid(), "stop_requested": False, "forced_cleanup": False}
    child = None
    try:
        with (phase / "stdout.log").open("xb") as out, (phase / "stderr.log").open("xb") as err:
            child = subprocess.Popen([str(executable), "-c", spec["config"]], stdout=out, stderr=err,
                                     stdin=subprocess.DEVNULL, cwd=ROOT)
            result["collector_pid"] = child.pid
            result["console_attachment"] = wait_console_pair(kernel, child)
            if not result["console_attachment"]["ready"]:
                raise RuntimeError("Collector console readiness failed: " + result["console_attachment"]["reason"])
            # Do this AFTER Popen: the child must not inherit CTRL_C-ignore state.
            if not kernel.SetConsoleCtrlHandler(None, True):
                raise OSError("Cannot protect the collector host from its own console event")
            write(phase / "host-ready.json", {**result, "console_exclusive": True})
            while child.poll() is None:
                if (phase / "stop-request.json").exists():
                    result["stop_requested"] = True
                    if console_members(kernel) != {os.getpid(), child.pid}:
                        raise RuntimeError("Console membership changed; signal refused")
                    if not kernel.GenerateConsoleCtrlEvent(0, 0):
                        raise OSError("Own-console CTRL_C delivery failed")
                    result["signal"] = "CTRL_C_EVENT to exclusive host+collector console"
                    child.wait(timeout=20)
                    break
                time.sleep(0.1)
            result["collector_actual_exit_code"] = child.returncode
            result["passed"] = result["stop_requested"] and child.returncode == 0
    except Exception as error:
        result.update(passed=False, error_class=type(error).__name__, error=str(error))
    finally:
        if child is not None and child.poll() is None:
            result["forced_cleanup"] = True
            child.terminate()  # Only this held Popen handle; never a normal-stop pass.
            child.wait(timeout=10)
        if child is not None:
            result["collector_actual_exit_code"] = child.returncode
        result["completed_utc"] = utc()
        write(phase / "host-result.json", result)
    return 0 if result.get("passed") and not result["forced_cleanup"] else 1


def observed(phase, expected, *, final=False):
    path = phase / "stdout.log"
    if not path.exists():
        return Counter()
    raw = path.read_bytes()
    if final and raw and not raw.endswith(b"\n"):
        raise RuntimeError("Collector left an incomplete stdout record")
    complete = raw[:raw.rfind(b"\n") + 1]
    result = Counter()
    for line in complete.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict) or record.get("log_id") not in expected:
            raise RuntimeError("Unexpected/invalid collector output record")
        identity = record["log_id"]
        if record != expected[identity]["record"]:
            raise RuntimeError("Collector changed a fixture record")
        result[identity] += 1
    if any(count != 1 for count in result.values()):
        raise RuntimeError("Collector duplicated a log_id")
    return result


def wait_records(phase, expected, target):
    deadline = time.monotonic() + 30
    while True:
        counts = observed(phase, expected)
        if not set(counts).issubset(target):
            raise RuntimeError("Offset replay or unexpected phase output")
        if set(counts) == target:
            return counts
        if (phase / "host-result.json").exists():
            raise RuntimeError("Collector exited before all expected records arrived")
        if time.monotonic() >= deadline:
            raise TimeoutError("Fixture records did not arrive within 30 seconds")
        time.sleep(0.1)


def launch_phase(output, name, sources):
    phase = output / name
    phase.mkdir()
    state = output / "state"
    text = fluent.render_collection(sources, state, Path(__file__).with_name("parsers.conf"))
    if text.count("    Name tail\n") != 42 or text.count("    Name stdout\n") != 6 or "    Name kafka" in text:
        raise RuntimeError("Unexpected collection input/output graph")
    text = text.replace("    Name stdout\n", "    Name stdout\n    Format json_lines\n    Json_Date_Key false\n")
    for directory in fluent.collection_sources(sources).values():
        (state / fluent.source_id(directory) / "stdout").mkdir(parents=True, exist_ok=True)
    config = phase / "collector.conf"
    config.write_text(text, encoding="utf-8")
    write(phase / "host-spec.json", {"config": str(config), "config_sha256": sha(config),
        "executable": str(BINARY), "executable_sha256": sha(BINARY)})
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0  # Hidden, independent console; never AttachConsole.
    with (phase / "host.stdout.log").open("xb") as out, (phase / "host.stderr.log").open("xb") as err:
        # Bypass the Windows venv launcher: its extra attached process would
        # violate the exclusive-console PID check. The host uses stdlib only.
        process = subprocess.Popen([sys._base_executable, "-B", "-X", "utf8", str(Path(__file__).resolve()),
            "--collector-host", str(phase / "host-spec.json")], cwd=ROOT, stdout=out, stderr=err,
            creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
    return phase, process


def wait_host_ready(phase, process):
    deadline = time.monotonic() + 15
    while not (phase / "host-ready.json").exists():
        if process.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError("Exclusive collector console failed to become ready")
        time.sleep(0.1)


def stop_phase(phase, process):
    write(phase / "stop-request.json", {"requested_utc": utc()})
    actual = process.wait(timeout=35)
    result = read(phase / "host-result.json")
    if actual != 0 or result["collector_actual_exit_code"] != 0 or not result["passed"] or result["forced_cleanup"]:
        raise RuntimeError("Collector did not confirm normal signal handling and zero exit")
    return {"host_actual_exit_code": actual, **result}


def run(output):
    if os.name != "nt":
        raise RuntimeError("Actual portable verification requires Windows")
    plan = read(output / "plan.json")
    if plan["status"] != "prepared_not_started" or runtime_sources() != plan["source_sha256"] or sha(BINARY) != plan["executable_sha256"]:
        raise RuntimeError("Prepared runtime sources or binary changed")
    if sha(output / "expected.json") != plan["expected_sha256"] or sha(output / "sources.json") != plan["sources_sha256"]:
        raise RuntimeError("Prepared fixture manifest changed")
    with (output / "run-started.json").open("x", encoding="utf-8") as stream:
        json.dump({"started_utc": utc()}, stream)
    expected = read(output / "expected.json")
    sources = {role: Path(path) for role, path in read(output / "sources.json").items()}
    if any(path.resolve() != output / "inputs" / role for role, path in sources.items()):
        raise RuntimeError("Source escaped the seven prepared fixture directories")
    for value in expected.values():
        if sha(output / value["source"]) != value["sha256"]:
            raise RuntimeError("Prepared synthetic record changed")
    batch_ids = lambda batches: {key for key, value in expected.items() if value["batch"] in batches}
    result = {"started_utc": utc(), "passed": False, "phases": {}, "synthetic_only": True,
              "kafka_connected": False, "platform_ingestion_tested": False, "copytruncate_tested": False,
              "no_rename_tested": True, "append_only_stable_files": True}
    current = None
    try:
        with fluent.collection_owner(sources):
            try:
                phase, process = launch_phase(output, "phase1", sources); current = phase, process
                wait_host_ready(phase, process)
                wait_records(phase, expected, batch_ids({"seed"}))
                append_batch(output, "live_append")
                wait_records(phase, expected, batch_ids({"seed", "live_append"}))
                append_batch(output, "live_new_file")
                wait_records(phase, expected, batch_ids({"seed", "live_append", "live_new_file"}))
                result["phases"]["phase1"] = stop_phase(phase, process); current = None
                append_batch(output, "offline_append")
                phase, process = launch_phase(output, "phase2", sources); current = phase, process
                wait_host_ready(phase, process)
                wait_records(phase, expected, batch_ids({"offline_append"}))
                result["phases"]["phase2"] = stop_phase(phase, process); current = None
                append_batch(output, "offline_existing"); append_batch(output, "offline_new_file")
                phase, process = launch_phase(output, "phase3", sources); current = phase, process
                wait_host_ready(phase, process)
                wait_records(phase, expected, batch_ids({"offline_existing", "offline_new_file"}))
                result["phases"]["phase3"] = stop_phase(phase, process); current = None
                combined = Counter()
                for name in ("phase1", "phase2", "phase3"):
                    combined.update(observed(output / name, expected, final=True))
                databases = list((output / "state").glob("*/stdout/amp-*.db"))
                if set(combined) != set(expected) or any(count != 1 for count in combined.values()) or len(databases) != 42:
                    raise RuntimeError("Final 252-ID/42-offset-database reconciliation failed")
                result.update(passed=True, unique_records=len(combined), duplicates=0, missing=0,
                    role_counts=dict(Counter(expected[key]["role"] for key in combined)),
                    kind_counts=dict(Counter(expected[key]["kind"] for key in combined)),
                    offset_databases=42, normal_collector_exits=[item["collector_actual_exit_code"] for item in result["phases"].values()])
            except Exception as error:
                result.update(error_class=type(error).__name__, error=str(error))
                raise
            finally:
                if current is not None and current[1].poll() is None:
                    try:
                        result["failed_phase_cleanup"] = stop_phase(*current)
                    except Exception as error:
                        result.update(cleanup_error_class=type(error).__name__, cleanup_error=str(error),
                                      cleanup_host_pid=current[1].pid, cleanup_host_actual_exit_code=current[1].poll())
    except Exception as error:
        result.update(error_class=type(error).__name__, error=str(error))
    finally:
        result["completed_utc"] = utc()
        write(output / "results.json", result)
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--run", action="store_true")
    action.add_argument("--collector-host", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.collector_host:
        return collector_host(args.collector_host)
    if args.output is None:
        parser.error("--output is required")
    output = owned_output(args.output)
    if args.prepare:
        result = prepare(output)
        print(json.dumps({"status": result["status"], "records": result["unique_expected_records"], "actual_collectors_started": 0}))
        return 0
    return run(output)


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the current combined SDK's entire test tree in its isolated snapshot."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
OUT = HERE / "sdk-integration-evidence"
ARTIFACTS = HERE.parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    expected_interpreter = ARTIFACTS / "upstream-full-suite-20261018/runtime-venv/Scripts/python.exe"
    assert Path(sys.executable).resolve() == expected_interpreter.resolve()
    assert sys.flags.isolated and sys.flags.utf8_mode
    preparation_raw = (OUT / "preparation.json").read_bytes()
    preparation = json.loads(preparation_raw)
    manifest_raw = (OUT / "source-manifest.json").read_bytes()
    assert sha(manifest_raw) == preparation["source_manifest_sha256"]
    manifest = json.loads(manifest_raw)
    tree = OUT / "suite-copy"
    sdk = tree / "acps-sdk"
    locked = ARTIFACTS / "upstream-full-suite-20261018/locked-dependencies"
    dependency_audit = ARTIFACTS / "upstream-full-suite-20261018/locked-dependency-audit.json"
    assert sha(dependency_audit.read_bytes()) == preparation["locked_dependency_audit_sha256"]
    def check_source():
        assert {p:sha((tree / p).read_bytes()) for p in manifest["source_sha256"]} == manifest["source_sha256"]
        assert {p:sha((tree / p).read_bytes()) for p in preparation["synthetic_fixture_sha256"]} == preparation["synthetic_fixture_sha256"]
    check_source()
    run = OUT / "full-first"
    run.mkdir(exist_ok=False)
    for name in ("temporary", "durable-temporary", "coordinator-processes"):
        (run / name).mkdir()
    os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
        NO_PROXY="127.0.0.1,localhost,::1", no_proxy="127.0.0.1,localhost,::1", PYTHONNOUSERSITE="1",
        TEMP=str(run / "temporary"), TMP=str(run / "temporary"), INCIDENT_TEST_TMPDIR=str(run / "durable-temporary"),
        INCIDENT_T30_EVIDENCE_DIR=str(run / "coordinator-processes"))
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONHOME", "PYTHONUSERBASE"):
        os.environ.pop(name, None)
    sys.dont_write_bytecode = True
    base = Path(sys.base_prefix)
    sys.path[:] = [str(sdk), str(locked), str(base / "Lib"), str(base / "DLLs"),
                  str(base / ("python" + str(sys.version_info.major) + str(sys.version_info.minor) + ".zip"))]
    os.chdir(sdk)
    import acps_sdk
    import anyio
    import pytest
    import pytest_asyncio
    assert Path(acps_sdk.__file__).resolve().is_relative_to(sdk)
    for mod in (anyio, pytest, pytest_asyncio):
        assert Path(mod.__file__).resolve().is_relative_to(locked)
    backends = list(anyio.get_available_backends())
    collected, phases, calls, warnings, collection_errors = [], Counter(), Counter(), Counter(), []
    class Recorder:
        def pytest_collection_finish(self, session):
            collected.extend(item.nodeid for item in session.items)
        def pytest_runtest_logreport(self, report):
            phases[(report.when, report.outcome)] += 1
            if report.when == "call":
                calls[report.outcome] += 1
        def pytest_collectreport(self, report):
            if report.failed:
                collection_errors.append(dict(nodeid=report.nodeid, longrepr=str(report.longrepr)))
        def pytest_warning_recorded(self, warning_message, when, nodeid, location):
            warnings[(warning_message.category.__name__, when, str(warning_message.message))] += 1
    arguments = ["-c", str(sdk / "pyproject.toml"), "--rootdir=" + str(sdk), "--confcutdir=" + str(sdk),
        "-p", "pytest_asyncio.plugin", "-p", "anyio.pytest_plugin", "-ra",
        "--basetemp=" + str(run / "pytest-temporary"), "-o", "cache_dir=" + str(run / "pytest-cache"),
        "--junitxml=" + str(run / "junit.xml"), str(sdk / "tests")]
    started = time.monotonic()
    write(run / "start.json", dict(status="CURRENT_SDK_COMPLETE_SUITE_STARTED",
        source_manifest_sha256=sha(manifest_raw), preparation_sha256=sha(preparation_raw),
        runner_sha256=sha(Path(__file__).read_bytes()), actual_interpreter=sys.executable,
        sdk_tree=str(sdk), dependencies=str(locked), arguments=arguments, backend=backends,
        all_tests_included=True, test_filter_used=False, platform_or_model_started=False,
        started_at_utc=datetime.now(timezone.utc).isoformat()))
    code = int(pytest.main(arguments, plugins=[Recorder()]))
    check_source()
    imports = {name:str(Path(module.__file__).resolve()) for name,module in tuple(sys.modules.items())
        if name.startswith("acps_sdk") and getattr(module,"__file__",None)}
    assert all(Path(p).is_relative_to(sdk) for p in imports.values())
    result = dict(status="CURRENT_SDK_COMPLETE_SUITE_TERMINAL", pytest_exit_code=code,
        collected=len(collected), collected_nodeids=collected, call_outcomes=dict(calls),
        phase_outcomes=[dict(phase=p,outcome=o,count=n) for (p,o),n in sorted(phases.items())],
        collection_errors=collection_errors,
        warnings=[dict(category=c,when=w,message=m,count=n) for (c,w,m),n in sorted(warnings.items())],
        source_manifest_sha256=sha(manifest_raw), source_before_after_exact=True,
        synthetic_tls_before_after_exact=True, loaded_sdk_modules=imports,
        runtime_unchanged_by_integration=manifest["runtime_unchanged"], backend=backends,
        dependencies=str(locked), actual_interpreter=sys.executable, all_tests_included=True,
        test_filter_used=False, elapsed_seconds=round(time.monotonic()-started,3),
        platform_or_model_started=False, upstream_CI_executed=False,
        limits="Complete current combined SDK suite; fake/ASGI transports, local ephemeral TLS, owned disposable child processes. Not formal platform, native deployment, or upstream CI.",
        completed_at_utc=datetime.now(timezone.utc).isoformat())
    write(run / "results.json", result)
    print(json.dumps({key:result[key] for key in ("status","pytest_exit_code","collected","call_outcomes","elapsed_seconds")}))
    raise SystemExit(code)


if __name__ == "__main__":
    main()

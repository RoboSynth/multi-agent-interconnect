"""Copy and run a repository's complete vendored SDK suite with offline TLS fixtures.

Usage: python run_sdk_suite.py --repo-root PATH --output NEW_PATH [--python ENV_PYTHON]
The selected Python environment must already contain the SDK's test dependencies.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

HERE = Path(__file__).resolve().parent
SDK_RELATIVE = Path("vendor/ACPs-community/acps-sdk")
GENERATED_DIRECTORIES = {"__pycache__", ".pytest_cache", ".venv", ".git"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def source_inventory(sdk):
    files = {}
    for directory, child_dirs, names in os.walk(sdk, topdown=True, followlinks=False):
        current = Path(directory)
        for name in child_dirs:
            if (current / name).is_symlink():
                raise ValueError("SDK source directory is a symlink: " + str(current / name))
        child_dirs[:] = [name for name in child_dirs if name not in GENERATED_DIRECTORIES]
        for name in names:
            if name.endswith((".pyc", ".pyo")):
                continue
            path = current / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("SDK source is not a regular file: " + str(path))
            files[path.relative_to(sdk).as_posix()] = sha(path.read_bytes())
    return dict(sorted(files.items()))


def selected_python(value):
    candidate = shutil.which(value) if value else sys.executable
    if candidate is None:
        candidate = value
    if not candidate or not Path(candidate).is_file():
        raise ValueError("Python environment executable was not found")
    # Preserve the venv executable's spelling: resolving a POSIX symlink can
    # select the base interpreter and discard that environment's packages.
    return Path(os.path.abspath(candidate))


def prepare(repo, output):
    sdk = repo / SDK_RELATIVE
    if not (sdk / "pyproject.toml").is_file() or not (sdk / "tests").is_dir():
        raise ValueError("--repo-root does not contain the vendored SDK and its tests")
    if output == repo or output.is_relative_to(sdk):
        raise ValueError("--output must be a new directory outside the SDK source tree")
    inventory = source_inventory(sdk)
    output.mkdir(parents=True, exist_ok=False)
    for name in ("temporary", "durable-temporary", "coordinator-processes"):
        (output / name).mkdir()
    snapshot = output / "suite-copy/acps-sdk"
    for name, expected in inventory.items():
        source, target = sdk / name, snapshot / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target.read_bytes()) != expected:
            raise RuntimeError("Source changed while copying: " + name)
    reference = repo / "evidence/sdk-test-integration-20261019/source-manifest.json"
    reference_state = {"available": reference.is_file()}
    if reference.is_file():
        raw = reference.read_bytes()
        expected = json.loads(raw)["source_sha256"]
        expected = {name.removeprefix("acps-sdk/"):value for name,value in expected.items()}
        reference_state.update(sha256=sha(raw), matched=expected == inventory,
            differing_paths=sorted(name for name in set(expected) | set(inventory)
                                   if expected.get(name) != inventory.get(name)))
    manifest = dict(schema_version="portable-sdk-suite-input/1", source_repo=str(repo),
        sdk_relative_path=SDK_RELATIVE.as_posix(), source_files=len(inventory),
        source_sha256=inventory, source_cache_exclusions=sorted(GENERATED_DIRECTORIES),
        test_name_or_marker_filters=[], published_reference=reference_state)
    write(output / "source-manifest.json", manifest)
    return manifest


def drive(args):
    repo, output = args.repo_root.resolve(), args.output.resolve()
    interpreter = selected_python(args.python)
    manifest = prepare(repo, output)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
        TEMP=str(output / "temporary"), TMP=str(output / "temporary"), TMPDIR=str(output / "temporary"))
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        env.pop(name, None)
    command = [str(interpreter), "-I", "-B", "-X", "utf8", str(Path(__file__).resolve()),
               "--worker", "--repo-root", str(repo), "--output", str(output)]
    write(output / "driver-start.json", dict(status="PORTABLE_COMPLETE_SDK_SUITE_STARTED",
        command=command, selected_python=str(interpreter), source_files=manifest["source_files"],
        runner_sha256=sha(Path(__file__).read_bytes()),
        tls_generator_sha256=sha((HERE / "synthetic_tls.py").read_bytes()),
        started_at_utc=datetime.now(timezone.utc).isoformat()))
    print(json.dumps(dict(status="PORTABLE_COMPLETE_SDK_SUITE_STARTED", output=str(output),
                          source_files=manifest["source_files"])), flush=True)
    started = time.monotonic()
    with (output / "stdout.log.txt").open("wb") as stdout, (output / "stderr.log.txt").open("wb") as stderr:
        child = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
        code = child.wait()
    result_path = output / "results.json"
    result = json.loads(result_path.read_bytes()) if result_path.is_file() else None
    exact = source_inventory(repo / SDK_RELATIVE) == manifest["source_sha256"]
    final_code = code if exact else 1
    write(output / "driver-result.json", dict(status="PORTABLE_COMPLETE_SDK_SUITE_EXECUTOR_TERMINAL",
        actual_worker_pid=child.pid, actual_worker_returncode=code, driver_exit_code=final_code,
        source_repo_before_after_exact=exact, result_sha256=sha(result_path.read_bytes()) if result else None,
        pytest_exit_code=result.get("pytest_exit_code") if result else None,
        collected=result.get("collected") if result else None, call_outcomes=result.get("call_outcomes") if result else None,
        stdout_sha256=sha((output / "stdout.log.txt").read_bytes()),
        stderr_sha256=sha((output / "stderr.log.txt").read_bytes()),
        elapsed_seconds=round(time.monotonic()-started,3), completed_at_utc=datetime.now(timezone.utc).isoformat()))
    print(json.dumps(dict(status="PORTABLE_COMPLETE_SDK_SUITE_EXECUTOR_TERMINAL", actual_worker_returncode=code,
        driver_exit_code=final_code, collected=result.get("collected") if result else None,
        call_outcomes=result.get("call_outcomes") if result else None,
        source_repo_before_after_exact=exact)), flush=True)
    return final_code


def worker(repo, output):
    if not sys.flags.isolated or not sys.flags.utf8_mode:
        raise RuntimeError("Worker must use the selected Python with -I -B -X utf8")
    manifest_raw = (output / "source-manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    sdk = output / "suite-copy/acps-sdk"
    os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
        NO_PROXY="127.0.0.1,localhost,::1", no_proxy="127.0.0.1,localhost,::1", PYTHONNOUSERSITE="1",
        TEMP=str(output / "temporary"), TMP=str(output / "temporary"), TMPDIR=str(output / "temporary"),
        INCIDENT_TEST_TMPDIR=str(output / "durable-temporary"),
        INCIDENT_T30_EVIDENCE_DIR=str(output / "coordinator-processes"))
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONHOME", "PYTHONUSERBASE"):
        os.environ.pop(name, None)
    sys.dont_write_bytecode = True
    original_sdk = (repo / SDK_RELATIVE).resolve()
    sys.path[:] = [str(sdk)] + [item for item in sys.path if item
        and Path(item).resolve() != repo and not Path(item).resolve().is_relative_to(original_sdk)]
    os.chdir(sdk)
    # The helper is local source only; its make_tls() function performs no I/O.
    spec = importlib.util.spec_from_file_location("portable_sdk_synthetic_tls", HERE / "synthetic_tls.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    tls_files, public_tls = helper.make_tls()
    for name,data in tls_files.items():
        target = output / "suite-copy" / name
        target.parent.mkdir(parents=True,exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    write(output / "public-tls.json", public_tls)
    import anyio
    import pytest
    # Do not import pytest_asyncio before pytest: retain assertion rewriting.
    versions = {}
    for distribution in ("pytest", "pytest-asyncio", "anyio", "pydantic", "httpx", "aio-pika", "fastapi", "uvicorn", "jcs", "cryptography", "PyJWT"):
        versions[distribution] = importlib.metadata.version(distribution)
    arguments = ["-c",str(sdk / "pyproject.toml"), "--rootdir="+str(sdk), "--confcutdir="+str(sdk),
        "-p","pytest_asyncio.plugin", "-p","anyio.pytest_plugin", "-ra",
        "--basetemp="+str(output / "pytest-temporary"), "-o","cache_dir="+str(output / "pytest-cache"),
        "--junitxml="+str(output / "junit.xml"), str(sdk / "tests")]
    tls_hashes = {name:sha(data) for name,data in tls_files.items()}
    write(output / "preparation.json", dict(status="PORTABLE_COMPLETE_SDK_SUITE_PREPARED",
        source_manifest_sha256=sha(manifest_raw), actual_interpreter=sys.executable,
        actual_base_interpreter=getattr(sys,"_base_executable",sys.executable), python_prefix=sys.prefix,
        python_version=sys.version, dependency_versions=versions, sdk_tree=str(sdk),
        synthetic_fixture_sha256=tls_hashes, private_keys_local_only=True,
        public_tls_sha256=sha((output / "public-tls.json").read_bytes()),
        runner_sha256=sha(Path(__file__).read_bytes()), tls_generator_sha256=sha((HERE / "synthetic_tls.py").read_bytes()),
        pytest_arguments=arguments, backend=list(anyio.get_available_backends()),
        plugin_autoload_disabled=True, all_tests_included=True, platform_or_model_started=False))
    collected, phases, calls, warnings, collection_errors = [], Counter(), Counter(), Counter(), []
    class Recorder:
        def pytest_collection_finish(self, session):
            collected.extend(item.nodeid for item in session.items)
        def pytest_runtest_logreport(self, report):
            phases[(report.when,report.outcome)] += 1
            if report.when == "call":
                calls[report.outcome] += 1
        def pytest_collectreport(self, report):
            if report.failed:
                collection_errors.append(dict(nodeid=report.nodeid,longrepr=str(report.longrepr)))
        def pytest_warning_recorded(self, warning_message, when, nodeid, location):
            warnings[(warning_message.category.__name__,when,str(warning_message.message))] += 1
    started = time.monotonic()
    code = int(pytest.main(arguments,plugins=[Recorder()]))
    snapshot_exact = source_inventory(sdk) == manifest["source_sha256"]
    repo_exact = source_inventory(repo / SDK_RELATIVE) == manifest["source_sha256"]
    tls_exact = all(sha((output / "suite-copy" / name).read_bytes()) == expected for name,expected in tls_hashes.items())
    imports = {name:str(Path(module.__file__).resolve()) for name,module in tuple(sys.modules.items())
        if name.startswith("acps_sdk") and getattr(module,"__file__",None)}
    imports_exact = bool(imports) and all(Path(path).is_relative_to(sdk) for path in imports.values())
    integrity = snapshot_exact and repo_exact and tls_exact and imports_exact
    final_code = code if integrity else 1
    write(output / "results.json", dict(status="PORTABLE_COMPLETE_SDK_SUITE_TERMINAL",
        pytest_exit_code=code, worker_exit_code=final_code, collected=len(collected),collected_nodeids=collected,
        call_outcomes=dict(calls), phase_outcomes=[dict(phase=p,outcome=o,count=n) for (p,o),n in sorted(phases.items())],
        collection_errors=collection_errors,
        warnings=[dict(category=c,when=w,message=m,count=n) for (c,w,m),n in sorted(warnings.items())],
        source_manifest_sha256=sha(manifest_raw), source_snapshot_before_after_exact=snapshot_exact,
        source_repo_before_after_exact=repo_exact, synthetic_tls_before_after_exact=tls_exact,
        sdk_imports_from_snapshot=imports_exact, loaded_sdk_modules=imports,
        actual_interpreter=sys.executable, all_tests_included=True, test_filter_used=False,
        elapsed_seconds=round(time.monotonic()-started,3), platform_or_model_started=False,
        upstream_CI_executed=False, completed_at_utc=datetime.now(timezone.utc).isoformat()))
    return final_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True,help="New output directory; existing paths are never overwritten")
    parser.add_argument("--python",help="Python environment with SDK test dependencies; defaults to this interpreter")
    parser.add_argument("--worker",action="store_true",help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        return worker(args.repo_root.resolve(),args.output.resolve()) if args.worker else drive(args)
    except Exception as error:
        if args.worker:
            output = args.output.resolve()
            failure = output / "worker-failure.json"
            if output.is_dir() and not failure.exists():
                write(failure,dict(status="PORTABLE_SDK_SUITE_WORKER_FAILED",error_type=type(error).__name__,
                    message=str(error),traceback=traceback.format_exc()))
        raise


if __name__ == "__main__":
    raise SystemExit(main())

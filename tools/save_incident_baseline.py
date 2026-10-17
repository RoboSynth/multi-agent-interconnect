"""Save the working four-agent baseline and its recorded platform results."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from importlib.metadata import distributions
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v0.2.0"
SDK_COMMIT = "3985c1330209f075c124669cc9d31f0e75448140"


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = ROOT / "baselines" / f"incident-{VERSION}-{stamp}"
    destination.mkdir(parents=True, exist_ok=False)
    copied = []

    def copy(source, relative=None):
        source = ROOT / source
        target = destination / (relative or source.relative_to(ROOT))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target.relative_to(destination).as_posix())

    for name in ("services.py", "run_pilot.py", "integration/wutong_incident.py",
                 "integration/wutong_smoke.py", "integration/wutong_discovery.py"):
        copy(name)
    for component in ("acps-sdk", "acps-cli"):
        source = ROOT / "vendor/ACPs-community" / component
        for file in source.rglob("*"):
            if (file.is_file() and not any(part in {"__pycache__", ".git", ".venv", ".pytest_cache"}
                                           or part.endswith(".egg-info") for part in file.relative_to(source).parts)
                    and file.suffix not in {".pyc", ".pyo"}):
                copy(file.relative_to(ROOT))
    copy("vendor/ACPs-community/LICENSE")
    copy("vendor/ACPs-community/README.md")
    for name in ("RESULT.json", "README.md", "registration-status.json", "leader-cli-entry-update.json",
                 "discovery-root-cause.json", "business-discovery-20261017T043831Z.json"):
        copy("integration/incident/" + name)
    for role in ("leader", "application", "database", "verification"):
        copy(f"integration/incident/{role}.approved.acs.json")
    for run in ("wutong-incident-20261017T0439Z", "wutong-incident-20261017T0440Z"):
        for file in (ROOT / "integration/artifacts" / run).rglob("*"):
            if file.is_file():
                copy(file.relative_to(ROOT))
    copy("output/playwright/wutong-incident-approved.png")
    copy("integration/two-agent/approved-registry-agents.json", "archive/old-test-agents.json")
    copy("integration/two-agent/RESULT.json", "archive/old-test-result.json")

    packages = {dist.metadata["Name"]: dist.version for dist in distributions() if dist.metadata.get("Name")}
    external = [f"{name}=={version}" for name, version in packages.items()
                if name.lower() not in {"acps-sdk", "acps-cli", "pip"}]
    (destination / "requirements-lock.txt").write_text("\n".join(sorted(external, key=str.lower)) + "\n", encoding="utf-8")
    (destination / "environment.json").write_text(json.dumps(packages, indent=2) + "\n", encoding="utf-8")
    result = json.loads((ROOT / "integration/incident/RESULT.json").read_text(encoding="utf-8"))
    tests = json.loads((ROOT / "integration/two-agent/approved-registry-agents.json").read_text(encoding="utf-8"))["agents"]
    manifest = {
        "version": VERSION, "saved_utc": stamp, "sdk_commit": SDK_COMMIT,
        "baseline": "four official identities; official ADP discovery; ten Wutong business tasks",
        "identities": result["identities"], "successful_run": "integration/artifacts/wutong-incident-20261017T0440Z/RESULT.json",
        "runtime_config": str(ROOT / "integration/private/incident/config.json"),
        "credentials": "Existing integration/private/incident directory stays on this computer; credentials are outside this archive",
        "diagnosis": "deterministic policy", "business_services": "local HTTP/SQLite",
        "cleanup_requested": [{"id": row["id"], "aic": row["aic"], "name": row["acs"]["name"]} for row in tests],
        "platform_cleanup_status": "login_required",
    }
    (destination / "BASELINE.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "README.md").write_text(
        "# 故障协作基线 v0.2.0\n\n"
        "保留协调、应用、数据库和恢复分析四个正式智能体。官方 ADP 发现及十个梧桐业务任务已完成，组合故障恢复和正常状态运行记录包含在本基线中。\n\n"
        "运行入口：`integration/wutong_incident.py`。源码同时包含它仍依赖的 `run_pilot.py` 与 `wutong_smoke.py`，以及固定版本官方 SDK/CLI。\n\n"
        "依赖清单来自本次实际环境，包含 cryptography。证书和私钥继续保存在原项目的 `integration/private/incident/`；本包通过 BASELINE.json 记录配置位置。\n\n"
        "组合故障：503→200，8 个任务、2 次恢复操作、6.190 秒；正常状态：200→200，2 个任务、0 次恢复操作。诊断采用规则，业务服务为本机 HTTP/SQLite。\n\n"
        "平台旧回声测试身份的资料已归档在 archive/old-test-agents.json；其清理状态见项目 integration/incident/platform-cleanup.json。\n",
        encoding="utf-8")
    inventory = []
    for file in sorted(destination.rglob("*")):
        if file.is_file():
            inventory.append({"file": file.relative_to(destination).as_posix(), "bytes": file.stat().st_size,
                              "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
    (destination / "FILES.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive = destination.with_name(destination.name + ".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as stream:
        for file in sorted(destination.rglob("*")):
            if file.is_file():
                stream.write(file, file.relative_to(destination))
    with zipfile.ZipFile(archive) as stream:
        damaged = stream.testzip()
        if damaged:
            raise RuntimeError(f"Archive entry failed CRC: {damaged}")
    record = {"baseline": str(destination), "archive": str(archive), "files": len(inventory) + 1,
              "archive_bytes": archive.stat().st_size, "version": VERSION, "platform_cleanup_status": "login_required"}
    (ROOT / "integration/incident/baseline-saved.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, ensure_ascii=True))


if __name__ == "__main__":
    main()

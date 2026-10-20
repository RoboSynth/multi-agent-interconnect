"""Read-only cloud image/source/host snapshot; do not start any consumer."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys

ROOT = Path("/opt/incident-pilot")
sys.path.insert(0, str(ROOT))
from deploy.prepare_deployment import load_deployment
from eval.targets import DOMAIN_SOURCE_FILES, DockerTarget


def command(argv):
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main():
    manifest = load_deployment(ROOT / "runtime/private/cloud-new7-20261019/deployment.json", root=ROOT)
    target = DockerTarget.from_file(ROOT / manifest["target_config"], root=ROOT)
    files = sorted(set(DOMAIN_SOURCE_FILES) | {"acps_mcp_bridge/platform.py", "incident/platform_worker.py",
        "domains/onboarding/text.py", "domains/setup_platform.py",
        "vendor/ACPs-community/acps-sdk/acps_sdk/amp/message_emitter.py"})
    ids = command(target.compose + ["ps", "-a", "-q"]).split()
    rows = json.loads(command(target.docker + ["inspect", *ids]))
    safe = []
    for row in rows:
        labels = row["Config"].get("Labels") or {}
        entry = dict(service=labels.get("com.docker.compose.service"), id=row["Id"], image_id=row["Image"],
            running=row["State"]["Running"], started_at=row["State"]["StartedAt"], restart=row["HostConfig"]["RestartPolicy"]["Name"])
        if entry["service"].endswith("-agent"):
            code = ("import json,hashlib;from pathlib import Path;print(json.dumps({p:hashlib.sha256((Path('/srv')/p).read_bytes()).hexdigest() for p in "
                    + repr(files) + "}))")
            entry["source_sha256"] = json.loads(command(target.docker + ["exec", row["Id"], "python", "-c", code]))
        safe.append(entry)
    host = json.loads((ROOT / "runtime/private/cloud-longrun/control/host.json").read_text())
    config = json.loads((ROOT / manifest["coordinator_config"]).read_text())
    units = {name: command(["systemctl", "show", name, "--property=MainPID,ActiveState,UnitFileState,NRestarts"]).strip().splitlines()
             for name in ("incident-workbench.service", "incident-scheduler.service", "incident-collector.service")}
    result = dict(observed_at=datetime.now(timezone.utc).isoformat(),
        head=command(["git", "-c", "safe.directory=/opt/incident-pilot", "-C", str(ROOT), "rev-parse", "HEAD"]).strip(),
        project=target.project, ports=target.ports, host={key: host.get(key) for key in ("status", "pid", "session_id", "aics")},
        units=units, containers=safe, host_source_sha256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
        new7_trusted_aics=sorted({config["leader"]["aic"], *(aic for values in config["trusted_participant_aics"].values() for aic in values)}))
    print(json.dumps(result))


if __name__ == "__main__":
    main()

"""Issue client certificates for the approved incident identities."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "integration/incident"
PRIVATE = ROOT / "integration/private/incident"


def main():
    status = json.loads((PUBLIC / "registration-status.json").read_text(encoding="utf-8"))
    if len(status["agents"]) != 4 or any(row["status"] != "APPROVED" for row in status["agents"]):
        raise RuntimeError("Four approved incident identities are required")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    config = {"discovery_url": "https://wt.ioa.pub/discovery/acps-adp-v2/discover",
              "mq_auth_url": "https://wt.ioa.pub:9007", "trust_bundle": str(PRIVATE / "trust-bundle.pem"),
              "agents": {}}
    for agent in status["agents"]:
        role, aic = agent["role"], agent["aic"]
        cert, key = PRIVATE / f"{role}-chain.pem", PRIVATE / f"{role}.key"
        if cert.exists() or key.exists():
            raise RuntimeError(f"Certificate files already exist for {role}; preserve them before a new issuance")
        command = [str(ROOT / ".venv/Scripts/acps-cli.exe"), "--config", str(ROOT / "integration/acps-cli.toml"),
                   "cert", "issue", "--aic", aic, "--eab-file", str(PRIVATE / f"{role}-eab.json"),
                   "--usage", "clientAuth", "--key-path", str(key), "--cert-path", str(cert),
                   "--trust-bundle-path", config["trust_bundle"]]
        with (PRIVATE / f"{role}-issuance.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError(f"Certificate issuance failed for {role}; see its private issuance log")
        config["agents"][role] = {"aic": aic, "cert": str(cert), "key": str(key),
                                   "endpoint": agent["acs"]["endPoints"][0]["url"]}
        if role != "leader":
            config["agents"][role]["skill_id"] = f"incident.{role}"
        (PUBLIC / f"{role}.approved.acs.json").write_text(json.dumps(agent["acs"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"role": role, "aic": aic, "certificate_issued": True}), flush=True)
    with (PRIVATE / "config.json").open("x", encoding="utf-8") as stream:
        json.dump(config, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"config_created": True, "identities": len(config["agents"])}))


if __name__ == "__main__":
    main()

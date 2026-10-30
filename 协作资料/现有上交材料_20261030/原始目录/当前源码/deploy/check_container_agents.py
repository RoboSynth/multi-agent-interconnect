"""Read-only TLS checks from the actual agent image, without starting an AIC."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

CHECK = r'''
import hashlib,json,socket,ssl
from urllib.parse import urlparse
from pathlib import Path
path=Path('/domain/config.json')
if path.exists():
    config=json.loads(path.read_text())
else:
    config=json.loads(Path('/domain/bridge.json').read_text())['platform']
context=ssl.create_default_context(cafile=config['trust_bundle'])
context.load_cert_chain(config['cert'],config['key'])
checks=[]
for value in [config['endpoint'],config['mq_auth_url']]:
    endpoint=urlparse(value)
    port=endpoint.port or (443 if endpoint.scheme=='https' else 5671)
    with socket.create_connection((endpoint.hostname,port),timeout=12) as raw:
        with context.wrap_socket(raw,server_hostname=endpoint.hostname) as connection:
            checks.append({'host':endpoint.hostname,'port':port,'tls':connection.version(),
                'peer_sha256':hashlib.sha256(connection.getpeercert(binary_form=True)).hexdigest(),'passed':True})
print(json.dumps({'passed':True,'aic':config['aic'],'checks':checks,'aip_task_sent':False}))
'''


def wsl_path(path):
    value = str(path.resolve())
    return "/mnt/" + value[0].lower() + value[2:].replace("\\", "/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domains", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wsl")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Choose a fresh output path")
    prefix = ["wsl.exe", "-d", args.wsl, "--exec", "docker"] if args.wsl else ["docker"]
    report = {"at": datetime.now(timezone.utc).isoformat(), "mode": "agent-container-outbound-TLS-only",
              "platform_group_tested": False, "checks": {}, "passed": False}
    for role in ("application", "verification", "database"):
        directory = args.domains / role
        mount = wsl_path(directory) if args.wsl else str(directory.resolve())
        result = subprocess.run(prefix + ["run", "--rm", "-i", "--read-only", "--tmpfs", "/tmp", "-v",
                                mount + ":/domain:ro", "incident-pilot-agent:local", "python", "-"],
            input=CHECK, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
        if result.returncode:
            report["checks"][role] = {"passed": False, "returncode": result.returncode,
                                      "diagnostic": result.stderr[-1500:]}
        else:
            report["checks"][role] = json.loads(result.stdout)
    report["passed"] = all(value["passed"] for value in report["checks"].values())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(args.output)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

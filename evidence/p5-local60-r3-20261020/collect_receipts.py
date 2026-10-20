"""Copy selected lifecycle receipts without rewriting their original bytes."""
import json
import runpy
import shutil
from report import ARTIFACTS, BATCH, OUTPUT, load, save, sha
from package_evidence import known_secrets

NAMES = [
    "controller-process.json", "scope.json", "helper-provenance.json",
    "database-prepare-command.json", "database-prepare.txt",
    "native-start-command.json", "native-start.txt",
    "model-process.json", "model-start-command.json", "model-start.txt",
    "preflight.json", "preflight-command.json", "preflight.txt", "supervisor-process.json",
    "evaluator-output-command.json", "evaluator-output.txt",
    "cleanup-output-command.json", "cleanup-output.txt",
    "native-stop-output.txt", "controller-result.json", "controller-output.txt",
]


def main():
    if load(ARTIFACTS / "continuation/cleanup-result.json")["status"] != "STOPPED":
        raise ValueError("Lifecycle evidence collection requires completed cleanup")
    patterns = runpy.run_path(str(BATCH / "binding/source/eval/secret_scan.py"))["PATTERNS"]
    secrets, files = known_secrets(), {}
    missing = []
    selected = [(label, directory, name)
                for label, directory in [("original", ARTIFACTS), ("continuation", ARTIFACTS / "continuation")]
                for name in NAMES + (["restore-interrupted-command.json", "restore-interrupted.txt", "cleanup-recovery.json"]
                                     if label == "continuation" else [])]
    for label, directory, name in selected:
        source = directory / name
        if not source.exists() and label == "original":
            missing.append(label + "/" + name)
            continue
        raw = source.read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        if source.suffix == ".json":
            json.loads(text)
        if any(pattern.search(text) for pattern in patterns.values()) or any(secret in text for secret in secrets):
            raise ValueError("Credential scan failed in lifecycle receipt: " + name)
        target = OUTPUT / "execution-receipts" / label / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha(target) != sha(source):
            raise ValueError("Existing receipt differs from original: " + name)
        shutil.copyfile(source, target)
        if sha(target) != sha(source):
            raise ValueError("Receipt copy mismatch: " + name)
        files[label + "/" + name] = {"sha256": sha(source), "bytes": len(raw)}
    save(OUTPUT / "execution-receipts/artifact-manifest.json", {
        "source_directory": str(ARTIFACTS), "files": files, "secret_hits": 0,
        "raw_bytes_preserved": True, "original_receipts_absent_after_user_exit": missing,
        "text_scan": "UTF-8 replacement decoding for mixed Windows log encodings; original bytes unchanged",
    })
    print(json.dumps({"status": "COPIED", "receipts": len(files), "secret_hits": 0}))


if __name__ == "__main__":
    main()

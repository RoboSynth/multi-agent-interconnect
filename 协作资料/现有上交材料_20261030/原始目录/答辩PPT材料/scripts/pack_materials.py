"""Package only the reviewed PPT handoff directory; no network operations."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--archive", type=Path, required=True)
parser.add_argument("--private-scan-report", type=Path, required=True)
parser.add_argument("--verification", type=Path, required=True)
args = parser.parse_args()
root = args.root.resolve()
assert not args.archive.exists(), "Choose a new archive path or retain the previous archive first."
scan = json.loads(args.private_scan_report.read_text(encoding="utf-8"))
assert not scan["report"]["findings"] and not scan["report"]["errors"]
expected = {row["path"]: row for row in scan["files"]}
files = sorted(p for p in root.rglob("*") if p.is_file())
assert not any(p.is_symlink() for p in root.rglob("*"))
assert all(p.suffix.lower() in {".py", ".md", ".json", ".csv", ".svg", ".png", ".txt"} for p in files)
assert {p.relative_to(root).as_posix() for p in files} == set(expected) | {"匿名核验.json"}
for path in files:
    name = path.relative_to(root).as_posix()
    if name in expected:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected[name]["sha256"], name
    else:
        assert json.loads(path.read_text(encoding="utf-8")) == scan["report"]
with zipfile.ZipFile(args.archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in files:
        archive.write(path, "答辩PPT材料/" + path.relative_to(root).as_posix())
with zipfile.ZipFile(args.archive) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist()) == len(files)
    assert set(archive.namelist()) == {"答辩PPT材料/" + p.relative_to(root).as_posix() for p in files}
report = {"archive": args.archive.name, "bytes": args.archive.stat().st_size, "files": len(files),
          "crc_check": "passed", "exact_file_set": "passed", "privacy_findings": 0, "uploaded": False}
args.verification.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=False))

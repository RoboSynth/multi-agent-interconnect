"""Verify the audited SDK payload against its three complete manifests, using local files only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--git", default="git", help="Git executable; no remote operation is performed")
    args = parser.parse_args(argv)
    here = Path(__file__).resolve().parent
    root = here.parents[1]
    prefix = "vendor/ACPs-community/acps-sdk/"
    sdk = root / prefix
    source = json.loads((here / "source-ready.json").read_bytes())
    names = set()
    for bucket, count in (("official_native",127), ("modified_official",3), ("project_added",10)):
        rows = json.loads((here / (bucket + "-manifest.json")).read_bytes())
        if len(rows) != count:
            raise ValueError("Manifest count mismatch: " + bucket)
        records = []
        for row in rows:
            name = row["path"]
            path = (sdk / name).resolve()
            if name in names or not path.is_relative_to(sdk.resolve()) or not path.is_file():
                raise ValueError("Duplicate, absent or invalid SDK path: " + name)
            names.add(name)
            raw = path.read_bytes()
            if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
                raise ValueError("SDK differs from audited source: " + name)
            records.append({key:row[key] for key in ("path","bytes","sha256")})
        canonical = (json.dumps(sorted(records,key=lambda row:row["path"]), sort_keys=True, indent=2)+"\n").encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != source["attribution_buckets"][bucket]["raw_manifest_sha256"]:
            raise ValueError("Manifest binding mismatch: " + bucket)
    command = [args.git,"-C",str(root),"ls-files","-z","--",prefix]
    tracked = subprocess.run(command,check=True,capture_output=True).stdout
    actual = {name.decode("utf-8").removeprefix(prefix) for name in tracked.split(b"\0") if name}
    if actual != names:
        raise ValueError("Tracked SDK file coverage differs from the audited140-file scope")
    print(json.dumps({"status":"AUDITED_SDK_FILES_MATCH", "files":len(names),
        "source_commit":source["current_repository_commit"], "runtime_tests_or_platform_calls":0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

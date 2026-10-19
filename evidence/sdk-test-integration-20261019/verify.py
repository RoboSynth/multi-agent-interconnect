"""Verify this SDK suite's exact source inputs locally; do not run the suite."""
import hashlib
import json
from pathlib import Path, PurePosixPath


def main():
    here = Path(__file__).resolve().parent
    root = here.parents[1]
    vendor = root / "vendor/ACPs-community"
    manifest = json.loads((here / "source-manifest.json").read_bytes())
    sources = manifest["source_sha256"]
    if len(sources) != manifest["sdk_files"]:
        raise ValueError("SDK manifest count mismatch")
    for name, expected in sources.items():
        relative = PurePosixPath(name)
        target = (vendor / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not target.is_relative_to(vendor.resolve()):
            raise ValueError("Invalid SDK manifest path: " + name)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError("Current SDK differs from tested source: " + name)
    for row in manifest["installed_test_blobs"]:
        target = root / row["path"]
        if hashlib.sha256(target.read_bytes()).hexdigest() != row["source_sha256"]:
            raise ValueError("Integrated test differs from source Git blob: " + row["path"])
    print(json.dumps(dict(status="CURRENT_SDK_TESTED_SOURCE_MATCH", files=len(sources),
                         integrated_test_blobs=len(manifest["installed_test_blobs"]), runtime_tests_or_platform_calls=0)))


if __name__ == "__main__":
    main()

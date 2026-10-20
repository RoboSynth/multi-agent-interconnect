"""Package only the public-onboarding patch; no runtime credentials."""
from pathlib import Path
import hashlib
import json
import tarfile

ROOT = Path(r"D:\AI + 开源\team-repository-multi-agent-interconnect")
OUT = Path(__file__).resolve().parent
FILES = ("acps_mcp_bridge/platform.py", "incident/platform_worker.py",
         "domains/onboarding/text.py", "domains/setup_platform.py")
TESTS = ("tests/test_onboarding.py", "tests/test_onboarding_text.py", "tests/test_platform_worker.py",
         "tests/test_public_onboarding_groups.py", "tests/test_bridge_platform_preparation.py")
manifest = {"base_image_id": "sha256:ebe76d42a02a3986a57e0c1df17a92856f515b09ca1da1e619eaa4315cd501f1",
            "base_tag": "incident-pilot-new7-cloud-20261019-agent:local",
            "patch_tag": "incident-pilot-public-onboarding:20261020",
            "files": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES},
            "tests": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in TESTS}}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
with tarfile.open(OUT / "patch-source.tar.gz", "w:gz") as archive:
    for name in (*FILES, *TESTS):
        archive.add(ROOT / name, arcname=name)
    archive.add(OUT / "manifest.json", arcname="manifest.json")
print(json.dumps({"archive": str(OUT / "patch-source.tar.gz"), "files": len(FILES)}))

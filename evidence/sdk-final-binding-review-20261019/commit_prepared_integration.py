"""Create a local-only reviewed SDK integration commit with the team's configured identity."""
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
GIT = r"C:\Users\shared-user\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe"
WORK = HERE / "integration-checkout"
TEAM = Path(r"D:\AI + 开源\team-repository-multi-agent-interconnect")
def git(root, *args):
    return subprocess.run([GIT, "-C", str(root), *args], check=True, capture_output=True).stdout

parent = "09fe13bd699f4a9df279507ed23861f6f817babe"
tree = "a656374c5030ca59c37daa3e93f447d2fcada1cc"
sdk_tree = "2796a70756eba2405c108414e14b36186c188601"
assert git(WORK, "rev-parse", "HEAD").decode().strip() == parent
assert git(WORK, "write-tree").decode().strip() == tree
name = git(TEAM, "config", "user.name").decode().strip()
email = git(TEAM, "config", "user.email").decode().strip()
assert name and email
output = git(WORK, "-c", "core.autocrlf=false", "-c", "user.name=" + name,
             "-c", "user.email=" + email, "commit", "-m",
             "Integrate durable access with resumable SDK and concurrent emitter")
(HERE / "local-commit.stdout.log").write_bytes(output)
commit = git(WORK, "rev-parse", "HEAD").decode().strip()
assert git(WORK, "rev-parse", "HEAD^{tree}").decode().strip() == tree
assert git(WORK, "rev-parse", "HEAD:acps-sdk").decode().strip() == sdk_tree
assert git(WORK, "rev-parse", "HEAD^").decode().strip() == parent
assert not git(WORK, "-c", "core.autocrlf=false", "status", "--porcelain=v1")
sdk_rows = git(WORK, "ls-tree", "-r", "-z", "HEAD:acps-sdk").split(b"\0")
assert len([row for row in sdk_rows if row]) == 147
receipt = dict(schema_version="local-sdk-integration-commit/1", status="LOCAL_COMMIT_VERIFIED_NOT_PUBLIC",
    created_at_utc=datetime.now(timezone.utc).isoformat(), commit=commit, parent=parent,
    repository_tree_oid=tree, sdk_tree_oid=sdk_tree, sdk_files=147,
    branch="integration/incident-ext-20261019", public_push_executed=False,
    same_tested_sdk_tree=True, sdk_suite_rerun=False, team_configured_author_identity_reused=True)
(HERE / "local-commit.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt))

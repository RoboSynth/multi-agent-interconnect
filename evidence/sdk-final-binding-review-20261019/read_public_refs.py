"""Bounded anonymous public GitHub GETs; no GCM, authentication, or writes."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(exist_ok=False)
    receipts = []

    def get(endpoint, name):
        req = Request("https://api.github.com" + endpoint, method="GET", headers={
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "incident-pilot-read-only-source-binding"})
        with urlopen(req, timeout=30) as response:
            raw = response.read()
            status = response.status
        value = json.loads(raw)
        receipts.append(dict(endpoint=endpoint, method="GET", HTTP_status=status,
                             response_sha256=hashlib.sha256(raw).hexdigest(),
                             observed_at_utc=datetime.now(timezone.utc).isoformat()))
        # These endpoints contain public repository/commit metadata and no account secrets.
        (args.output / (name + ".json")).write_bytes(raw + b"\n")
        return value

    summary = dict(status="INCOMPLETE", authentication_used=False, credential_helper_calls=0,
                   policy="Anonymous public GET only, bounded endpoints, stop after first failure")
    try:
        official = get("/repos/AIP-PUB/ACPs-community", "official-repository")
        fork = get("/repos/RoboSynth/ACPs-community", "fork-repository")
        branch = get("/repos/AIP-PUB/ACPs-community/branches/" + official["default_branch"], "official-default-branch")
        branches = get("/repos/RoboSynth/ACPs-community/branches?per_page=100", "fork-branches")
        prs = []
        for number in (13, 14):
            value = get(f"/repos/AIP-PUB/ACPs-community/pulls/{number}", f"pr-{number}")
            prs.append(dict(number=number, state=value["state"], draft=value["draft"], merged=value["merged"],
                            head=value["head"]["sha"], branch=value["head"]["ref"],
                            base=value["base"]["sha"], updated_at=value["updated_at"],
                            comments=value["comments"], review_comments=value["review_comments"],
                            changed_files=value["changed_files"], commits=value["commits"]))
        licenses = []
        for path, label in (("LICENSE", "root-license"), ("acps-sdk/LICENSE", "sdk-license")):
            value = get("/repos/AIP-PUB/ACPs-community/contents/" + path + "?ref=" + branch["commit"]["sha"], label)
            data = base64.b64decode(value["content"])
            licenses.append(dict(path=path, git_blob_oid=value["sha"], bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
        summary.update(status="PUBLIC_SOURCE_REFS_VERIFIED", official_default_branch=official["default_branch"],
                       official_head=branch["commit"]["sha"], fork_default_branch=fork["default_branch"],
                       fork_is_public=fork["private"] is False, fork=fork["fork"],
                       fork_parent=fork.get("parent", {}).get("full_name"),
                       fork_branches=[dict(name=x["name"], sha=x["commit"]["sha"]) for x in branches],
                       branches_complete=len(branches) < 100, prs=prs, official_current_licenses=licenses)
    except BaseException as error:
        summary.update(status="STOPPED_AT_FIRST_FAILURE", error_class=type(error).__name__)
    summary["observations"] = receipts
    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] == "PUBLIC_SOURCE_REFS_VERIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

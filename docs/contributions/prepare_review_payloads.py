"""Generate local review payloads. No network or GitHub client is used."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
ISSUES = ("01-task-result-order", "02-mq-endpoint-docs", "03-group-access", "04-discovery-alive")
PULL_REQUESTS = ("PR-sdk-resumable", "PR-message-emitter")


def document(stem):
    title, _, body = (ROOT / (stem + ".md")).read_text(encoding="utf-8").partition("\n")
    return {"title": title.removeprefix("# "), "body": body.strip() + "\n"}


def main():
    output = ROOT / "payloads"
    output.mkdir(exist_ok=True)
    for stem in ISSUES:
        (output / (stem + ".json")).write_text(json.dumps(document(stem), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for stem in PULL_REQUESTS:
        request = document(stem)
        request.update(base="main", head="<reviewed-branch>", draft=True)
        (output / (stem + ".json")).write_text(json.dumps({
            "repository": "AIP-PUB/ACPs-community", "ready_to_submit": False,
            "reason": "正文待用户审阅；head 尚未创建；本文件仅为本地草稿。", "request": request,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"issues": len(ISSUES), "pull_request_drafts": len(PULL_REQUESTS), "published": False}))


if __name__ == "__main__":
    main()

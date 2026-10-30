"""Render and check the already-built draft using existing local Poppler/Pillow.

No package installation, network request, resource call or PDF mutation.
Visual review is a separate recorded step; automatic checks do not imply it.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
PDF = HERE / "technical-report-development.pdf"


def command(name):
    found = shutil.which(name)
    if found:
        return found
    folder = Path("D:/16080/CodexData/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin")
    path = folder / (name + ".exe")
    if not path.exists():
        raise FileNotFoundError("Existing Poppler executable not found: " + name)
    return str(path)


def main():
    previews = HERE / "previews"
    previews.mkdir(exist_ok=True)
    info = subprocess.run([command("pdfinfo"), str(PDF)], check=True, capture_output=True).stdout.decode("utf-8", "replace")
    fonts = subprocess.run([command("pdffonts"), str(PDF)], check=True, capture_output=True).stdout.decode("utf-8", "replace")
    subprocess.run([command("pdftotext"), "-enc", "UTF-8", "-layout", str(PDF), str(HERE / "extracted.txt")], check=True, capture_output=True)
    subprocess.run([command("pdftoppm"), "-r", "110", "-png", str(PDF), str(previews / "page")], check=True, capture_output=True)
    text = (HERE / "extracted.txt").read_text(encoding="utf-8")
    pages = [page for page in text.split("\f") if page.strip()]
    pngs = sorted(previews.glob("page-*.png"))
    for start in range(0, len(pngs), 6):
        subset = pngs[start:start+6]
        sheet = Image.new("RGB", (3*305, 2*460), "#e5e9eb")
        draw = ImageDraw.Draw(sheet)
        for index, path in enumerate(subset):
            image = Image.open(path).convert("RGB")
            image.thumbnail((289, 410))
            x, y = (index%3)*305+8, (index//3)*460+25
            sheet.paste(image, (x, y))
            draw.text((x, y-17), f"PAGE {start+index+1:02d}", fill="#173b50")
        sheet.save(previews / f"contact-{start//6+1:02d}.png")
    sections = ["作品概述", "需求分析", "技术选型与方案设计", "项目实施", "应用成效", "总结与展望", "附录"]
    patterns = {"registered_aic_namespace": r"(?i)\b[A-Z0-9_-]*BUPT[A-Z0-9_.:-]*\b",
                "private_key": r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----",
                "authenticated_uri": r"(?i)(?:postgres(?:ql)?|amqps?)://[^\s/@:]+:[^\s/@]+@",
                "developer_user_path": r"(?i)(?:C:\\Users\\shared-user\\16080)"}
    hits = {key:len(re.findall(pattern, text)) for key,pattern in patterns.items()}
    build = json.loads((HERE / "build-info.json").read_text(encoding="utf-8"))
    checks = {"pages_13": len(pages)==len(pngs)==13,
              "all_seven_chapters_present": all(section in text for section in sections),
              "draft_label_present": "非最终提交版" in text,
              "historical_m1_scope_present": "仅自由选择观察" in text,
              "m2_negative_result_present": "探测减少" in text and "恢复更慢" in text,
              "e1_segmentation_explicit": "17例连续完成" in text and "控制器中断后续验" in text,
              "no_replacement_character": "\ufffd" not in text,
              "no_known_identity_or_credential_pattern": not any(hits.values()),
              "pdf_under_10MiB": PDF.stat().st_size < 10*1024*1024,
              "layout_frame_no_overflow": build["frame_overflow"] is False,
              "fonts_embedded": all("yes" in row for row in fonts.splitlines()[2:] if row.strip())}
    validation = {"created_at":datetime.now(timezone.utc).isoformat(),
        "artifact_kind":"technical report development draft; not final submission",
        "pdf":PDF.name,"pdf_sha256":hashlib.sha256(PDF.read_bytes()).hexdigest(),"pdf_bytes":PDF.stat().st_size,
        "page_count":len(pages),"rendered_pages":[str(path.relative_to(HERE)) for path in pngs],
        "checks":checks,"automatic_checks_passed":all(checks.values()),
        "identity_scan_scope":"bounded text patterns plus manual visual review; no private source identity material read",
        "identity_pattern_hits":hits,"pdfinfo":info,"pdffonts":fonts,
        "visual_review":{"status":"pending","pages_reviewed":[],"note":"Must inspect latest rendered pages before delivery."},
        "runtime_or_model_or_external_calls":False,
        "source_fingerprints":build["source_sha256"],
        "limitations":["Formal platform is partial three old participant domains; new roles/ACS still pending.",
                        "Old M1 selects observations only; free-tools-v1 has no real fault matrix here.",
                        "E1a/b is segmented local execution: 17 uninterrupted cases and one controller continuation; not formal platform takeover.",
                        "Short local AMP windows do not prove 24h/7x24, Kafka/Monitor ingestion or backend visit counts."]}
    (HERE / "validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"automatic_checks_passed":validation["automatic_checks_passed"],"checks":checks,"page_count":len(pages)},ensure_ascii=True))
    return 0 if validation["automatic_checks_passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())

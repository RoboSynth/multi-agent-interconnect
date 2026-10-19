"""Render the exact revision-3 PDF; verify content and Git-frozen source bounds."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PDF = HERE / "technical-report-development.pdf"


def tool(name):
    found = shutil.which(name)
    if found:
        return found
    for root in [Path(sys.base_prefix).parents[1], Path.home() / ".cache/codex-runtimes/codex-primary-runtime"]:
        path = root / "dependencies/native/poppler/Library/bin" / (name + ".exe")
        if path.is_file():
            return str(path)
    raise FileNotFoundError("Poppler is required: " + name)


def main():
    out = HERE / "previews"
    out.mkdir(exist_ok=True)
    def run(name, *args):
        options = ["-enc", "UTF-8", "-isodates"] if name == "pdfinfo" else []
        raw = subprocess.run([tool(name), *options, *map(str, args)], capture_output=True, check=True).stdout
        return raw.decode("utf-8", errors="strict")
    info = run("pdfinfo", PDF)
    fonts = run("pdffonts", PDF)
    metadata = run("pdfinfo", "-meta", PDF)
    run("pdftotext", "-enc", "UTF-8", "-layout", PDF, HERE / "extracted.txt")
    run("pdftoppm", "-r", 120, "-png", PDF, out / "page")
    text = (HERE / "extracted.txt").read_text(encoding="utf-8")
    compact_text = re.sub(r"\s+", "", text)
    def contains_all(*values):
        return all(re.sub(r"\s+", "", value) in compact_text for value in values)
    pages = [page for page in text.split("\f") if page.strip()]
    pngs = sorted(out.glob("page-*.png"))
    build = json.loads((HERE / "build-info.json").read_bytes())
    source = json.loads((HERE / "evidence.json").read_bytes())
    content = json.loads((HERE / "content.json").read_bytes())
    patterns = {"private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                "authenticated_uri": r"(?i)(?:postgres(?:ql)?|amqps?)://[^\s/@:]+:[^\s/@]+@",
                "local_home": re.escape(str(Path.home())),
                "registered_namespace": r"(?i)\b[A-Z0-9_-]*" + "BU" + "PT" + r"[A-Z0-9_.:-]*\b"}
    drive_pattern = r"\b" + "[A-Za-z]" + re.escape(chr(58)) + "[" + re.escape(chr(92) + chr(47)) + "]"
    patterns["absolute_drive_path"] = drive_pattern
    hits = {name: len(re.findall(pattern, text + info + metadata)) for name, pattern in patterns.items()}
    frozen = {}
    for path in source["inputs"]:
        frozen[path] = subprocess.run(["git", "-C", str(ROOT), "show", source["source_commit"] + ":" + path],
                                      capture_output=True, check=True).stdout
    rendered_dependencies = {"deliverables/development-report-20261017/build.py"}
    rendered_dependencies.update(block["path"] for page in content["pages"]
                                 for block in page["blocks"] if block["type"] == "figure")
    checks = {
        "fifteen_pages": len(pages) == len(pngs) == 15,
        "seven_chapters": all(value in text for value in ("作品概述", "需求分析", "技术选型与方案设计", "项目实施", "应用成效", "总结与展望", "附录")),
        "three_innovations_and_excerpts": all(value in text for value in ("创新一", "创新二", "创新三", "核心代码原文节选")),
        "cutoff_613ecbf": source["source_commit"] == "613ecbfc6e7500a30264bfec3c702d17152f0b6a" and "613ecbf" in text,
        "original_and_new_batches_separate": contains_all("原 22 例 18/4", "新 12 例 11/1", "不与原三断点分母合并"),
        "new_results_terminal_included": source["revalidation"]["status"] == "terminal" and source["revalidation"]["results_included"] is True,
        "T05_18_and_12_missing_retained": all(value in text for value in ("缺 18 条", "缺 12 条", "T05=false")),
        "T62_separate_zero_hit_scope": all(value in text for value in ("214", "68", "133", "73", "本批 T62=true", "overall=false")),
        "offline_groups_separate": all(value in text for value in ("17 项通过", "8 项通过", "20 个不同方法", "18 项复跑", "新增 2 项", "6/6")),
        "offline_not_deployed": "离线修复已验证，尚未部署" in text and source["local_offline"]["deployed_to_platform_image"] is False,
        "two_landscape_E1b_figures": sum(page.get("orientation") == "landscape" for page in content["pages"]) == 2,
        "post_handover_time_and_missing": "时间只从确认接管之后起计" in text and "缺值未补 0" in text,
        "historical_attribution_scope": contains_all("该截面跟踪 140 份文件", "+916 / -12"),
        "pending_gates_retained": all(value in text for value in ("T01 尚未完成", "T11/T96", "24 小时", "非最终提交版")),
        "old_E3_bad_rows_retained": "11 条坏行" in text and "overall=false" in text,
        "no_replacement_character": "\ufffd" not in text,
        "bounded_text_metadata_patterns_zero": not any(hits.values()),
        "fonts_embedded": all("yes" in line for line in fonts.splitlines()[2:] if line.strip()),
        "under_10MiB": PDF.stat().st_size < 10 * 1024 * 1024,
        "exact_built_bytes": hashlib.sha256(PDF.read_bytes()).hexdigest() == build["pdf_sha256"],
        "frame_no_overflow": build["frame_overflow"] is False,
        "frozen_source_inputs_verified": all(hashlib.sha256(frozen[path]).hexdigest() == row["sha256"] for path, row in source["inputs"].items()),
        "rendered_dependencies_match_frozen_source": all((ROOT / path).read_bytes() == frozen[path] for path in rendered_dependencies),
        "code_excerpts_match_frozen_source": all("\n".join(frozen[row["path"]].decode("utf-8").splitlines()[row["first_line"]-1:row["last_line"]]) == row["exact_source_excerpt"] for row in source["code_snippets"]),
    }
    result = {"pdf_sha256": build["pdf_sha256"], "pdf_bytes": PDF.stat().st_size, "page_count": len(pages),
              "checks": checks, "automatic_checks_passed": all(checks.values()), "bounded_pattern_hits": hits,
              "pdfinfo": info, "pdffonts": fonts, "xmp_metadata": metadata,
              "rendered_pages": [{"path": path.relative_to(HERE).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in pngs],
              "visual_review": {"status": "pending", "pages": []},
              "limits": ["A dated development revision, not final T90 or all P0 acceptance.",
                         "Bounded identity checks cover supplied patterns; unprovided school/teacher/provider terms and final media remain separate."]}
    (HERE / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"automatic_checks_passed": result["automatic_checks_passed"], "checks": checks, "page_count": len(pages)}, ensure_ascii=False))
    return 0 if result["automatic_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

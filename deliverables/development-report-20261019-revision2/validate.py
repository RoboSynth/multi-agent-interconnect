"""Render the exact current PDF and validate its content, fonts and source bounds."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
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
    run("pdftotext", "-enc", "UTF-8", "-layout", PDF, HERE / "extracted.txt")
    run("pdftoppm", "-r", 110, "-png", PDF, out / "page")
    text = (HERE / "extracted.txt").read_text(encoding="utf-8")
    pages = [p for p in text.split("\f") if p.strip()]
    pngs = sorted(out.glob("page-*.png"))
    build = json.loads((HERE / "build-info.json").read_bytes())
    patterns = {"private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "authenticated_uri": r"(?i)(?:postgres(?:ql)?|amqps?)://[^\s/@:]+:[^\s/@]+@", "local_user_path": re.escape(str(Path.home())), "registered_namespace": r"(?i)\b[A-Z0-9_-]*BUPT[A-Z0-9_.:-]*\b"}
    hits = {name: len(re.findall(pattern, text)) for name, pattern in patterns.items()}
    checks = {"twelve_pages": len(pages) == len(pngs) == 12, "seven_chapters": all(x in text for x in ["作品概述", "需求分析", "技术选型与方案设计", "项目实施", "应用成效", "总结与展望", "附录"]), "trust_domains": "信任域" in text and "数据库主 / 备" in text, "three_innovation_excerpts": all(x in text for x in ["创新一", "创新二", "创新三", "核心代码原文节选"]), "precise_SDK_delta": all(x in text for x in ["+71 / -12", "+916 / -12", "12073", "845"]), "Windows_fixture_scope": "69" in text and "fixture" in text and "T11/T96" in text, "local_E2c_scope": "14" in text and "本地自签" in text and "16" in text, "revalidation_excluded": "运行中未纳入本稿" in text, "fork_binding_pending": "T01 尚未完成" in text, "cutoff_412f791": "412f791" in text, "missing_14_confirmed_4_unknown": "14 条确证硬退出" in text and "4 条原因未定" in text, "current_formal_counts": "22" in text and "18" in text and "4" in text, "keeps_draft_and_T05_failure": "非最终提交版" in text and "严格闭合检查未通过" in text, "fix_platform_revalidation_pending": "离线通过不等同于平台复验通过" in text, "old_E3_bad_rows_retained": "11" in text and "overall=false" in text, "no_replacement_character": "\ufffd" not in text, "bounded_identity_patterns_zero": not any(hits.values()), "fonts_embedded": all("yes" in line for line in fonts.splitlines()[2:] if line.strip()), "under_10MiB": PDF.stat().st_size < 10*1024*1024, "exact_built_bytes": hashlib.sha256(PDF.read_bytes()).hexdigest() == build["pdf_sha256"], "frame_no_overflow": build["frame_overflow"] is False}
    source = json.loads((HERE / "evidence.json").read_bytes())
    checks["source_inputs_verified"] = all((HERE.parents[1]/name).is_file() and
        hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest() == row["sha256"]
        for name, row in source["inputs"].items())
    checks["code_excerpts_match_source"] = all("\n".join(
        (HERE.parents[1]/row["path"]).read_text(encoding="utf-8").splitlines()[row["first_line"]-1:row["last_line"]]
        ) == row["exact_source_excerpt"] for row in source["code_snippets"])
    checks["revalidation_results_not_inputs"] = source["revalidation"]["results_included"] is False and not any(
        "results/platform/revalidation-" in name for name in source["inputs"])
    result = {"pdf_sha256": build["pdf_sha256"], "pdf_bytes": PDF.stat().st_size, "page_count": len(pages), "checks": checks, "automatic_checks_passed": all(checks.values()), "bounded_pattern_hits": hits, "pdfinfo": info, "pdffonts": fonts, "rendered_pages": [{"path": p.relative_to(HERE).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in pngs], "visual_review": {"status": "pending", "pages": []}, "limits": ["Bounded text and visual checks do not prove anonymity against school/teacher/provider terms not supplied to this run.", "This dated draft does not close pending platform, independent-machine or long-term gates."]}
    (HERE / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"automatic_checks_passed": result["automatic_checks_passed"], "checks": checks, "page_count": len(pages)}, ensure_ascii=False))
    return 0 if result["automatic_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Render the current seven-chapter draft with the existing report layout."""
from pathlib import Path
import importlib.util
import json
import hashlib

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("prior_report_layout", HERE.parent / "development-report-20261017/build.py")
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class CurrentReport(layout.Report):
    def start_page(self, page):
        self.page += 1
        c = self.c
        c.setFillColor(layout.MUTED); c.setFont("CN", 7.5)
        c.drawString(layout.LEFT, layout.HEIGHT-29, "INCIDENT PILOT  /  技术报告开发稿")
        c.drawRightString(layout.WIDTH-layout.RIGHT, layout.HEIGHT-29, "非最终提交版  /  " + self.content["date"])
        c.setStrokeColor(layout.RULE); c.setLineWidth(.7)
        c.line(layout.LEFT, layout.HEIGHT-38, layout.WIDTH-layout.RIGHT, layout.HEIGHT-38)
        self.y = layout.HEIGHT-62
        self.paragraph(page["eyebrow"], 8.5, 14, color=layout.TEAL, bold=True, gap=5)
        self.paragraph(page["title"], 22 if self.page == 1 else 20, 31 if self.page == 1 else 29, color=layout.NAVY, bold=True, gap=15)

    def finish_page(self):
        self.page_min_y.append(round(self.y, 2))
        c = self.c
        c.setStrokeColor(layout.RULE); c.setLineWidth(.5)
        c.line(layout.LEFT, 43, layout.WIDTH-layout.RIGHT, 43)
        c.setFillColor(layout.MUTED); c.setFont("CN", 7.5)
        c.drawString(layout.LEFT, 29, "冻结实验与独立修复分别记录；原失败、未知意图与缺失记录保留。")
        c.drawRightString(layout.WIDTH-layout.RIGHT, 29, f"{self.page:02d} / {len(self.content['pages']):02d}")
        c.showPage()


def main():
    layout.register_fonts()
    content = json.loads((HERE / "content.json").read_bytes())
    evidence = json.loads((HERE / "evidence.json").read_bytes())
    target = HERE / "technical-report-development.pdf"
    report = CurrentReport(target, content, evidence)
    report.build()
    paths = [HERE / "build.py", HERE / "content.json", HERE / "evidence.json", HERE.parent / "development-report-20261017/build.py"]
    result = {"pdf": target.name, "pdf_sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "pdf_bytes": target.stat().st_size, "page_count": len(content["pages"]), "frame_overflow": False, "page_body_min_y": report.page_min_y, "source_sha256": {str(p.relative_to(HERE.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, "rendered_visual_review": "pending", "runtime_or_external_actions": 0}
    (HERE / "build-info.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

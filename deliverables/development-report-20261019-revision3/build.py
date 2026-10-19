"""Render revision 3 from fixed-cutoff inputs using the existing report layout."""
from pathlib import Path
import importlib.util
import json
import hashlib
import os
from PIL import Image

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("prior_report_layout", HERE.parent / "development-report-20261017/build.py")
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class CurrentReport(layout.Report):
    def start_page(self, page):
        landscape = page.get("orientation") == "landscape"
        layout.WIDTH, layout.HEIGHT = ((841.8897637795277, 595.2755905511812) if landscape
                                      else (595.2755905511812, 841.8897637795277))
        layout.BODY = layout.WIDTH - layout.LEFT - layout.RIGHT
        self.c.setPageSize((layout.WIDTH, layout.HEIGHT))
        self.page += 1
        c = self.c
        c.setFillColor(layout.MUTED); c.setFont("CN", 7.5)
        c.drawString(layout.LEFT, layout.HEIGHT-29, "INCIDENT PILOT  /  技术报告开发稿 / 修订三")
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

    def figure(self, relative):
        path = HERE.parents[1] / relative
        with Image.open(path) as source:
            width, height = source.size
        drawn_height = layout.BODY * height / width
        bottom = self.reserve(drawn_height)
        self.c.drawImage(str(path), layout.LEFT, bottom, width=layout.BODY,
                         height=drawn_height, preserveAspectRatio=True)
        self.reserve(10)

    def build(self):
        for page in self.content["pages"]:
            self.start_page(page)
            for block in page["blocks"]:
                kind = block["type"]
                if kind == "p":
                    self.paragraph(block["text"], size=block.get("size", 10), leading=block.get("leading", 17))
                elif kind == "h": self.heading(block["text"])
                elif kind == "small": self.paragraph(block["text"], 7.7, 12, color=layout.MUTED, gap=7)
                elif kind == "callout": self.callout(block["title"], block["text"], block.get("warning", False))
                elif kind == "table": self.table(block["headers"], block["rows"], block.get("widths"), block.get("size", 8.8))
                elif kind == "figure": self.figure(block["path"])
                elif kind == "space": self.reserve(block["height"])
                elif kind in ("architecture", "ledger_flow", "action_flow", "model_chart", "cost_bars"):
                    getattr(self, kind)()
                else: raise ValueError(kind)
            self.finish_page()
        self.c.save()


def main():
    layout.register_fonts()
    layout.pdfmetrics.registerFont(layout.TTFont("ReportMono", str(Path(os.environ["WINDIR"]) / "Fonts/consola.ttf")))
    content = json.loads((HERE / "content.json").read_bytes())
    evidence = json.loads((HERE / "evidence.json").read_bytes())
    target = HERE / "technical-report-development.pdf"
    report = CurrentReport(target, content, evidence)
    report.build()
    paths = [HERE / "build.py", HERE / "content.json", HERE / "evidence.json", HERE.parent / "development-report-20261017/build.py"]
    result = {"pdf": target.name, "pdf_sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "pdf_bytes": target.stat().st_size, "page_count": len(content["pages"]), "frame_overflow": False, "page_body_min_y": report.page_min_y, "source_sha256": {p.relative_to(HERE.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}, "rendered_visual_review": "pending", "runtime_or_external_actions": 0}
    (HERE / "build-info.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

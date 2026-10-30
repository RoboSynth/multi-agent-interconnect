"""Export the existing report Diagram class without executing its document builder."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.shapes import Drawing, Rect, Line, Polygon, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2] / "排版脚本/build_materials.py")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "图")
    parser.add_argument("--font", default=os.environ.get("MATERIAL_UI_FONT", "C:/Windows/Fonts/msyh.ttc"))
    parser.add_argument("--pdftoppm", default=os.environ.get("MATERIAL_PDFTOPPM") or shutil.which("pdftoppm"))
    args = parser.parse_args()
    if not args.pdftoppm:
        raise SystemExit("Set MATERIAL_PDFTOPPM or provide --pdftoppm")
    args.output.mkdir(parents=True, exist_ok=True)
    source = args.source.read_text(encoding="utf-8-sig")
    syntax = ast.parse(source)
    diagram = next(node for node in syntax.body if isinstance(node, ast.ClassDef) and node.name == "Diagram")
    constants = [node for node in syntax.body if isinstance(node, ast.Assign)
                 and all(isinstance(target, ast.Name) and target.id in {"INK", "MUTED", "PALE", "BORDER", "WIDTH"} for target in node.targets)]
    captured = []
    environment = {"Flowable": Flowable, "Drawing": Drawing, "Rect": Rect, "Line": Line, "Polygon": Polygon,
                   "String": String, "colors": colors, "A4": A4, "pdfmetrics": pdfmetrics,
                   "renderPDF": SimpleNamespace(draw=lambda drawing, *_: captured.append(drawing))}
    module = ast.fix_missing_locations(ast.Module(body=constants + [diagram], type_ignores=[]))
    exec(compile(module, "existing-report-diagram", "exec"), environment)
    pdfmetrics.registerFont(TTFont("UI", args.font, subfontIndex=0))
    receipt = {"source": "原始目录/排版脚本/build_materials.py", "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
               "source_lines": [diagram.lineno, diagram.end_lineno],
               "method": "Extract Diagram AST and its color/width constants; intercept existing renderPDF.draw; no document builder execution",
               "type": "existing report explanatory diagrams, not experimental screenshots", "files": []}
    for kind, basename in [("architecture", "图1-系统架构"), ("recovery", "图2-任务接续流程")]:
        graphic = environment["Diagram"](kind)
        graphic.canv = None
        graphic.draw()
        drawing = captured.pop()
        # Preserve all text and geometry; add outer whitespace for deck placement.
        padded = Drawing(drawing.width + 24, drawing.height + 24)
        drawing.translate(12, 12)
        padded.add(drawing)
        svg_path = args.output / (basename + ".svg")
        svg = renderSVG.drawToString(padded)
        if isinstance(svg, bytes):
            svg = svg.decode("utf-8")
        svg = svg.replace("font-family: UI", "font-family: Microsoft YaHei, Noto Sans CJK SC, sans-serif")
        svg_path.write_text(svg, encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="ppt-diagram-") as directory:
            temp = Path(directory)
            pdf = temp / "figure.pdf"
            renderPDF.drawToFile(padded, str(pdf))
            subprocess.run([str(args.pdftoppm), "-png", "-singlefile", "-scale-to-x", "2400", "-scale-to-y", "-1",
                            str(pdf), str(temp / "figure")], check=True, capture_output=True)
            png_path = args.output / (basename + ".png")
            shutil.copyfile(temp / "figure.png", png_path)
        with Image.open(png_path) as image:
            dimensions = list(image.size)
        receipt["files"].append({"kind": kind, "svg": svg_path.name, "png": png_path.name, "png_dimensions": dimensions})
    (args.output / "图源说明.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

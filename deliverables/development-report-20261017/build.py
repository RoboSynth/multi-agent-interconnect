"""Build the anonymous development draft from local content and aggregate data.

Usage: .venv-report/Scripts/python.exe artifacts/technical-report-draft-20261017/build.py
No network, model, service, or source-code mutation is performed.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT = A4
LEFT, RIGHT, BOTTOM = 48, 48, 59
BODY = WIDTH - LEFT - RIGHT
INK = colors.HexColor("#243540")
NAVY = colors.HexColor("#173b50")
TEAL = colors.HexColor("#087e87")
ORANGE = colors.HexColor("#b45c32")
MUTED = colors.HexColor("#5c6f7c")
LIGHT = colors.HexColor("#f0f5f6")
RULE = colors.HexColor("#d9e2e6")
RED = colors.HexColor("#9e3e37")


def register_fonts():
    fonts = Path("C:/Windows/Fonts")
    pdfmetrics.registerFont(TTFont("CN", str(fonts / "msyh.ttc"), subfontIndex=0))
    pdfmetrics.registerFont(TTFont("CNBold", str(fonts / "msyhbd.ttc"), subfontIndex=0))
    pdfmetrics.registerFontFamily("CN", normal="CN", bold="CNBold", italic="CN", boldItalic="CNBold")


def style(size=10, leading=17, *, color=INK, bold=False, align=TA_LEFT):
    return ParagraphStyle("body", fontName="CNBold" if bold else "CN", fontSize=size,
        leading=leading, textColor=color, wordWrap="CJK", alignment=align,
        spaceAfter=0, allowWidows=0, allowOrphans=0)


class Report:
    def __init__(self, path, content, data):
        self.c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1,
                               initialFontName="CN", initialFontSize=10, invariant=1)
        self.c.setTitle(content["title"] + " - 技术报告开发稿")
        self.c.setAuthor("")
        self.c.setSubject("匿名开发稿；非最终提交版；仅引用已闭合证据")
        self.content, self.data = content, data
        self.page, self.y = 0, 0
        self.page_min_y = []

    def reserve(self, height):
        if self.y - height < BOTTOM:
            raise ValueError(f"Page {self.page}: block exceeds content frame ({self.y-height:.1f} < {BOTTOM})")
        self.y -= height
        return self.y

    def paragraph(self, text, size=10, leading=17, *, color=INK, bold=False, gap=8):
        p = Paragraph(text, style(size, leading, color=color, bold=bold))
        _, height = p.wrap(BODY, HEIGHT)
        bottom = self.reserve(height)
        p.drawOn(self.c, LEFT, bottom)
        self.reserve(gap)

    def heading(self, text):
        self.paragraph(text, 12, 20, color=NAVY, bold=True, gap=5)

    def table(self, headers, rows, widths=None, size=8.8):
        widths = widths or [BODY / len(headers)] * len(headers)
        def para(value, bold=False):
            return Paragraph(str(value), style(size, 14, color=colors.white if bold else INK, bold=bold))
        grid = [[para(value, True) for value in headers]] + [[para(value) for value in row] for row in rows]
        table = Table(grid, colWidths=widths, hAlign="LEFT")
        commands = [("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("FONTNAME", (0, 0), (-1, -1), "CN"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 1), (-1, -1), .35, RULE)]
        for row in range(1, len(grid)):
            commands.append(("BACKGROUND", (0, row), (-1, row), LIGHT if row % 2 else colors.white))
        table.setStyle(TableStyle(commands))
        _, height = table.wrap(BODY, HEIGHT)
        bottom = self.reserve(height)
        table.drawOn(self.c, LEFT, bottom)
        self.reserve(12)

    def callout(self, title, text, warning=False):
        color = ORANGE if warning else TEAL
        p = Paragraph(f"<b>{title}</b><br/>{text}", style(9.5, 16, color=INK))
        _, height = p.wrap(BODY - 26, HEIGHT)
        bottom = self.reserve(height + 20)
        self.c.setFillColor(colors.HexColor("#fcf4ee") if warning else LIGHT)
        self.c.roundRect(LEFT, bottom, BODY, height + 20, 4, fill=1, stroke=0)
        self.c.setStrokeColor(color)
        self.c.setLineWidth(3)
        self.c.line(LEFT + 1.5, bottom + 6, LEFT + 1.5, bottom + height + 14)
        p.drawOn(self.c, LEFT + 13, bottom + 10)
        self.reserve(12)

    def box(self, x, y, width, height, title, body, tint=TEAL):
        self.c.setFillColor(LIGHT)
        self.c.setStrokeColor(RULE)
        self.c.roundRect(x, y, width, height, 5, fill=1, stroke=1)
        self.c.setFillColor(tint)
        self.c.rect(x, y + height - 4, width, 4, fill=1, stroke=0)
        t = Paragraph(title, style(10.5, 16, bold=True, color=NAVY))
        _, th = t.wrap(width - 20, height)
        t.drawOn(self.c, x + 10, y + height - 11 - th)
        p = Paragraph(body, style(8.7, 14, color=INK))
        _, ph = p.wrap(width - 20, height)
        if ph + th + 20 > height:
            raise ValueError(f"Diagram box overflow: {title}")
        p.drawOn(self.c, x + 10, y + height - 16 - th - ph)

    def arrow(self, x1, y1, x2, y2, color=MUTED):
        self.c.setStrokeColor(color)
        self.c.setFillColor(color)
        self.c.setLineWidth(.9)
        self.c.line(x1, y1, x2, y2)
        p = self.c.beginPath()
        if abs(y2-y1) > abs(x2-x1):
            sign = 1 if y2 > y1 else -1
            p.moveTo(x2, y2); p.lineTo(x2-3, y2-sign*6); p.lineTo(x2+3, y2-sign*6)
        else:
            sign = 1 if x2 > x1 else -1
            p.moveTo(x2, y2); p.lineTo(x2-sign*6, y2-3); p.lineTo(x2-sign*6, y2+3)
        p.close()
        self.c.drawPath(p, fill=1, stroke=0)

    def architecture(self):
        base = self.reserve(292)
        center = LEFT + BODY/2
        self.box(center-148, base+224, 296, 64, "协调入口 / 人工审批", "持有本域身份与审批签发能力；不加载数据库、应用或Docker资源凭据")
        self.arrow(center, base+224, center, base+211)
        self.box(LEFT, base+151, BODY, 60, "官方互联层：ADP + AIP群组 + AMP", "身份与能力发现、双向任务及证据日志；本地验收另标 AIP stdio", tint=NAVY)
        self.arrow(LEFT+121, base+151, LEFT+121, base+139)
        self.arrow(LEFT+BODY-121, base+151, LEFT+BODY-121, base+139)
        width = (BODY-14)/2
        self.box(LEFT, base+74, width, 65, "应用域", "应用管理凭据 / 连接池状态与受控重建<br/>直接观察不代替公共入口验证", tint=TEAL)
        self.box(LEFT+width+14, base+74, width, 65, "数据库域：主 / 备", "最小权限PostgreSQL MCP<br/>主备共享本域操作账本及fence", tint=ORANGE)
        self.box(LEFT, base, width, 65, "运维域", "Docker标签边界 / 登记进程与固定路由<br/>运维权限不交给协调入口", tint=colors.HexColor("#70639c"))
        self.box(LEFT+width+14, base, width, 65, "独立业务验证域", "无管理凭据；执行新建、查询、取消<br/>原请求沿原键查证，未决则人工核对", tint=TEAL)
        self.reserve(12)

    def ledger_flow(self):
        base = self.reserve(186)
        w, gap = (BODY-36)/3, 18
        titles = [("received", "持久记录原操作和参数摘要"), ("executing", "进入修改前先持久记录"), ("applied", "存储事实；重放返回缓存")]
        for i,(title,body) in enumerate(titles):
            x=LEFT+i*(w+gap)
            self.box(x, base+108, w, 69, title, body, tint=ORANGE if i==1 else TEAL)
            if i<2: self.arrow(x+w,base+143,x+w+gap,base+143)
        self.arrow(LEFT+w+gap+w/2,base+108,LEFT+w+gap+w/2,base+82)
        self.box(LEFT,base,BODY,82,"结果未知：先核验，不能盲目再做", "执行中断可能已经生效。查询真实资源：若已满足后置条件，则登记 reconciled_applied；无法证明则保持unknown / reconciliation_required，停止自动修改并交人工。新fence只阻断旧令牌，不证明旧动作没有发生。",tint=RED)
        self.reserve(12)

    def action_flow(self):
        base=self.reserve(124)
        w=(BODY-28)/3
        for i,(title,body) in enumerate([("1 入口路由", "v1 -> v2<br/>ops.route_rollback"),("2 数据库", "恢复写入，绑定审批<br/>db.restore_writes"),("3 应用连接池", "检查revision后重建<br/>application.pool_rebuild")]):
            x=LEFT+i*(w+14)
            self.box(x,base+34,w,84,title,body,tint=ORANGE if i==1 else TEAL)
            if i<2: self.arrow(x+w,base+76,x+w+14,base+76)
        p=Paragraph("随后由独立验证域执行30秒新业务；工作台保留每次审批、operation_id与结果。",style(9,15,color=MUTED))
        _,h=p.wrap(BODY,30);p.drawOn(self.c,LEFT,base+7)
        self.reserve(12)

    def model_chart(self):
        base=self.reserve(235)
        chart=self.data["model_comparison"]
        x0, x1 = LEFT+104, LEFT+BODY-13
        top=base+201
        span=x1-x0
        maximum=max(40,math.ceil(max(value for row in chart["by_scenario"] for method in row["methods"].values() for value in method["observed_seconds"])/10)*10)
        methods=[("M0",MUTED), ("M1",TEAL), ("M2",ORANGE)]
        self.c.setFont("CNBold",10.5);self.c.setFillColor(NAVY)
        self.c.drawString(LEFT,base+222,"1 rps采样恢复时间 / 秒")
        for value in range(0,maximum+1,10):
            x=x0+span*value/maximum
            self.c.setStrokeColor(RULE);self.c.setLineWidth(.5);self.c.line(x,base+28,x,top+10)
            self.c.setFillColor(MUTED);self.c.setFont("CN",8);self.c.drawCentredString(x,base+11,str(value))
        for i,row in enumerate(chart["by_scenario"]):
            y=top-i*37
            self.c.setFillColor(NAVY);self.c.setFont("CNBold",10);self.c.drawString(LEFT,y-8,row["scenario"])
            self.c.setFillColor(MUTED);self.c.setFont("CN",7.8);self.c.drawString(LEFT,y-22,"F06-v3" if row["scenario"]=="F06" else "v2")
            for j,(method,color) in enumerate(methods):
                values=row["methods"][method]["observed_seconds"]
                yy=y-j*10
                lo,hi=min(values),max(values)
                self.c.setStrokeColor(color);self.c.setFillColor(color);self.c.setLineWidth(1.1)
                self.c.line(x0+span*lo/maximum,yy,x0+span*hi/maximum,yy)
                for value in values: self.c.circle(x0+span*value/maximum,yy,2.2,fill=1,stroke=0)
                median=row["methods"][method]["median_observed_seconds"]
                x=x0+span*median/maximum
                self.c.setLineWidth(1.3);self.c.line(x,yy-4,x,yy+4)
                self.c.setFont("CN",7.8);self.c.drawRightString(x0-9,yy-2.5,method)
                label=f"{median:.2f}"
                label_x=min(x0+span*hi/maximum+7,x1-31)
                self.c.setFillColor(colors.white)
                self.c.rect(label_x-1,yy-4,pdfmetrics.stringWidth(label,"CN",7.8)+2,10,fill=1,stroke=0)
                self.c.setFillColor(color)
                self.c.drawString(label_x,yy-2.5,label)
        self.reserve(10)

    def cost_bars(self):
        base=self.reserve(95)
        totals=self.data["model_comparison"]["totals"]
        panels=[("探测总次数", "probes", 120), ("实际模型token / 千", "tokens", 130000)]
        panelw=(BODY-25)/2
        for i,(title,key,maximum) in enumerate(panels):
            x=LEFT+i*(panelw+25)
            self.c.setFillColor(NAVY);self.c.setFont("CNBold",10);self.c.drawString(x,base+83,title)
            for j,(method,color) in enumerate([("M0",MUTED),("M1",TEAL),("M2",ORANGE)]):
                y=base+59-j*21
                value=totals[method][key]
                self.c.setFillColor(MUTED);self.c.setFont("CN",8.5);self.c.drawString(x,y,method)
                barw=(panelw-75)*value/maximum
                self.c.setFillColor(color)
                if barw: self.c.roundRect(x+28,y-1,barw,9,2,fill=1,stroke=0)
                self.c.setFillColor(INK);self.c.setFont("CN",8.5)
                label=f"{value/1000:.1f}" if key=="tokens" else str(value)
                self.c.drawString(x+35+barw,y,label)
        self.reserve(8)

    def start_page(self, page):
        self.page+=1
        self.c.setFillColor(MUTED);self.c.setFont("CN",7.5)
        self.c.drawString(LEFT,HEIGHT-29,"INCIDENT PILOT  /  技术报告开发稿")
        self.c.drawRightString(WIDTH-RIGHT,HEIGHT-29,"非最终提交版  ·  2026-10-17")
        self.c.setStrokeColor(RULE);self.c.setLineWidth(.7);self.c.line(LEFT,HEIGHT-38,WIDTH-RIGHT,HEIGHT-38)
        self.y=HEIGHT-62
        self.paragraph(page["eyebrow"],8.5,14,color=TEAL,bold=True,gap=5)
        self.paragraph(page["title"],22 if self.page==1 else 20,31 if self.page==1 else 29,color=NAVY,bold=True,gap=15)

    def finish_page(self):
        self.page_min_y.append(round(self.y,2))
        self.c.setStrokeColor(RULE);self.c.setLineWidth(.5);self.c.line(LEFT,43,WIDTH-RIGHT,43)
        self.c.setFillColor(MUTED);self.c.setFont("CN",7.5)
        self.c.drawString(LEFT,29,"本地真实证据、正式平台partial及待补项分别标注；空白项不代表通过。")
        self.c.drawRightString(WIDTH-RIGHT,29,f"{self.page:02d} / {len(self.content['pages']):02d}")
        self.c.showPage()

    def build(self):
        for page in self.content["pages"]:
            self.start_page(page)
            for block in page["blocks"]:
                kind=block["type"]
                if kind=="p": self.paragraph(block["text"],size=block.get("size",10),leading=block.get("leading",17))
                elif kind=="h": self.heading(block["text"])
                elif kind=="small": self.paragraph(block["text"],7.7,12,color=MUTED,gap=7)
                elif kind=="callout": self.callout(block["title"],block["text"],block.get("warning",False))
                elif kind=="table": self.table(block["headers"],block["rows"],block.get("widths"),block.get("size",8.8))
                elif kind=="architecture": self.architecture()
                elif kind=="ledger_flow": self.ledger_flow()
                elif kind=="action_flow": self.action_flow()
                elif kind=="model_chart": self.model_chart()
                elif kind=="cost_bars": self.cost_bars()
                elif kind=="space": self.reserve(block["height"])
                else: raise ValueError(kind)
            self.finish_page()
        self.c.save()


def main():
    register_fonts()
    content=json.loads((HERE/"content.json").read_text(encoding="utf-8"))
    data=json.loads((HERE/"evidence.json").read_text(encoding="utf-8"))
    target=HERE/"technical-report-development.pdf"
    report=Report(target,content,data)
    report.build()
    info={"pdf":target.name,"page_count":len(content["pages"]),"page_body_min_y":report.page_min_y,
          "page_frame_bottom":BOTTOM,"frame_overflow":False,"pdf_bytes":target.stat().st_size,
          "pdf_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
          "source_sha256":{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ("build.py","content.json","evidence.json")},
          "fonts":"Windows Microsoft YaHei regular/bold, embedded subset; font files not redistributed"}
    (HERE/"build-info.json").write_text(json.dumps(info,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(info,ensure_ascii=True))


if __name__=="__main__":
    main()

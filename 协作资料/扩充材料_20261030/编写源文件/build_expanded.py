"""从结构化正文生成协作稿PDF与Markdown。"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import sys
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from pypdf import PdfReader
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Rect, Line, Polygon, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
                               Table, TableStyle, PageBreak, KeepTogether, Preformatted, Flowable, CondPageBreak)
from reportlab.platypus.tableofcontents import TableOfContents
import reportlab.platypus.paragraph as paragraph_engine
import reportlab.lib.textsplit as textsplit_engine

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('kinds', nargs='*', choices=['PLAN', 'REPORT', 'EVIDENCE'])
parser.add_argument('--evidence-root', type=Path)
args = parser.parse_args()
SOURCE = args.evidence_root or next((p for p in [ROOT.parent/'上交材料', ROOT.parent/'现有上交材料_20261030'] if p.exists()), ROOT.parent/'上交材料')

PDFDIR = ROOT/'PDF'
MDDIR = ROOT/'可编辑正文'
ASSETS = ROOT/'引用图像'
QA = ROOT/'核对记录'
for path in [PDFDIR, MDDIR, ASSETS, QA]:
    path.mkdir(exist_ok=True)

pdfmetrics.registerFont(TTFont('Body', os.getenv('MATERIAL_BODY_FONT','C:/Windows/Fonts/simsun.ttc'), subfontIndex=0))
pdfmetrics.registerFont(TTFont('UI', os.getenv('MATERIAL_UI_FONT','C:/Windows/Fonts/msyh.ttc'), subfontIndex=0))
pdfmetrics.registerFont(TTFont('Bold', os.getenv('MATERIAL_BOLD_FONT','C:/Windows/Fonts/msyhbd.ttc'), subfontIndex=0))
pdfmetrics.registerFontFamily('Body', normal='Body', bold='Bold', italic='Body', boldItalic='Bold')
pdfmetrics.registerFontFamily('UI', normal='UI', bold='Bold', italic='UI', boldItalic='Bold')

INK = colors.HexColor('#18354A')
ACCENT = colors.HexColor('#176E82')
MUTED = colors.HexColor('#5B6B75')
PALE = colors.HexColor('#F0F4F6')
LINECOLOR = colors.HexColor('#CBD5DC')
WIDTH = A4[0] - 100
ST = {
 'cover_kicker': ParagraphStyle('CoverKicker',fontName='UI',fontSize=10,leading=16,textColor=ACCENT,spaceAfter=16),
 'cover_title': ParagraphStyle('CoverTitle',fontName='Bold',fontSize=24,leading=36,textColor=INK,spaceAfter=9),
 'cover_kind': ParagraphStyle('CoverKind',fontName='UI',fontSize=18,leading=26,textColor=INK,spaceAfter=14),
 'cover_meta': ParagraphStyle('CoverMeta',fontName='UI',fontSize=9,leading=16,textColor=MUTED,spaceAfter=18),
 'cover_abstract': ParagraphStyle('CoverAbstract',fontName='Body',fontSize=11,leading=21,textColor=INK,spaceAfter=18,wordWrap='CJK',allowWidows=0,allowOrphans=0),
 'toc_title': ParagraphStyle('TOCTitle',fontName='Bold',fontSize=18,leading=29,textColor=INK,spaceAfter=18),
 'toc': ParagraphStyle('TOC',fontName='UI',fontSize=9.5,leading=17,textColor=INK,leftIndent=0,firstLineIndent=0,spaceBefore=3),
 'chapter': ParagraphStyle('Chapter',fontName='Bold',fontSize=15,leading=25,textColor=INK,spaceBefore=20,spaceAfter=12,keepWithNext=True,wordWrap='CJK'),
 'section': ParagraphStyle('Section',fontName='Bold',fontSize=11.5,leading=20,textColor=INK,spaceBefore=12,spaceAfter=6,keepWithNext=True,wordWrap='CJK'),
 'body': ParagraphStyle('Body',fontName='Body',fontSize=10.6,leading=19.1,textColor=colors.HexColor('#20282D'),spaceAfter=9,wordWrap='CJK',allowWidows=0,allowOrphans=0),
 'note': ParagraphStyle('Note',fontName='UI',fontSize=8.2,leading=13.2,textColor=MUTED,spaceBefore=3,spaceAfter=10,wordWrap='CJK',splitLongWords=True),
 'cell': ParagraphStyle('Cell',fontName='UI',fontSize=8.7,leading=14.3,textColor=INK,wordWrap='CJK',splitLongWords=True),
 'th': ParagraphStyle('TH',fontName='Bold',fontSize=8.7,leading=14.3,textColor=colors.white,wordWrap='CJK'),
 'caption': ParagraphStyle('Caption',fontName='UI',fontSize=8.5,leading=14,textColor=MUTED,spaceBefore=5,spaceAfter=12,wordWrap='CJK'),
 'code': ParagraphStyle('Code',fontName='Courier',fontSize=8.1,leading=13,textColor=INK,leftIndent=10,spaceBefore=7,spaceAfter=7),
}

# ReportLab's default CJK splitter omits Chinese commas/semicolons and can
# separate a short identifier. Apply line-break rules within this renderer.
NO_START='，。；：！？、）》】」』”’％%…,.!?;:'
NO_END='（《【「『“‘('
textsplit_engine.ALL_CANNOT_START += NO_START
paragraph_engine.ALL_CANNOT_START += NO_START


def chinese_word_split(word,maxWidths,fontName,fontSize,encoding='utf8'):
    encoded=not isinstance(word,str)
    value=word.decode(encoding) if encoded else word
    widths=textsplit_engine.getCharWidths(value,fontName,fontSize)
    limits=list(maxWidths) if isinstance(maxWidths,(list,tuple)) else [maxWidths]
    prefix=[0.0]
    for width in widths:prefix.append(prefix[-1]+width)
    tokens={}
    for match in re.finditer(r'[A-Za-z0-9_./:+#-]+',value):
        for index in range(match.start(),match.end()):
            tokens[index]=(match.start(),match.end(),prefix[match.end()]-prefix[match.start()])
    result=[];start=0
    while start<len(value):
        limit=limits[min(len(result),len(limits)-1)]
        end=start
        while end<len(value) and (prefix[end+1]-prefix[start]<=limit+.001 or end==start):end+=1
        if end<len(value):
            while end>start+1 and (value[end] in NO_START or value[end-1] in NO_END):end-=1
            token=tokens.get(end)
            if token and token[0]<end<token[1] and token[2]<=limit and token[0]>start:
                end=token[0]
            while end>start+1 and value[end-1] in NO_END:end-=1
        line=value[start:end].strip()
        extra=limit-pdfmetrics.stringWidth(line,fontName,fontSize)
        result.append([extra,line.encode(encoding) if encoded else line])
        start=end
    return result


paragraph_engine.wordSplit=chinese_word_split


def para(value, kind='body'):
    return Paragraph(escape(str(value)).replace('\n','<br/>'), ST[kind])


class SourceImage(Flowable):
    def __init__(self,path,width,crop=None):
        super().__init__()
        self.path = str(path)
        with PILImage.open(path) as source:
            self.sw,self.sh = source.size
        self.crop = crop or [0,0,self.sw,self.sh]
        left,top,right,bottom = self.crop
        assert 0<=left<right<=self.sw and 0<=top<bottom<=self.sh,(path,crop)
        self.width = min(width,WIDTH)
        self.scale = min(self.width/(right-left), 335/(bottom-top))
        self.width=(right-left)*self.scale
        self.height=(bottom-top)*self.scale
        self.hAlign='CENTER'
    def draw(self):
        left,top,right,bottom=self.crop
        self.canv.saveState()
        clip=self.canv.beginPath();clip.rect(0,0,self.width,self.height)
        self.canv.clipPath(clip,stroke=0,fill=0)
        self.canv.drawImage(self.path,-left*self.scale,-(self.sh-bottom)*self.scale,
                            width=self.sw*self.scale,height=self.sh*self.scale)
        self.canv.restoreState()


class Diagram(Flowable):
    def __init__(self,kind):
        super().__init__();self.kind=kind;self.width=WIDTH;self.height=235 if kind=='architecture' else 178
    def draw(self):
        d=Drawing(self.width,self.height)
        def box(x,y,w,h,lines,size=8.8):
            d.add(Rect(x,y,w,h,rx=3,ry=3,fillColor=PALE,strokeColor=LINECOLOR,strokeWidth=.65))
            for i,s in enumerate(lines):
                fit=min(size,(w-10)/max(pdfmetrics.stringWidth(s,'UI',1),1))
                d.add(String(x+w/2,y+h/2+(len(lines)-1)*7-i*14-3,s,fontName='UI',fontSize=fit,textAnchor='middle',fillColor=INK))
        def arrow(x1,y1,x2,y2):
            d.add(Line(x1,y1,x2,y2,strokeColor=ACCENT,strokeWidth=.8))
            if abs(y2-y1)>abs(x2-x1):
                pts=[x2,y2,x2-3,y2+(5 if y2<y1 else -5),x2+3,y2+(5 if y2<y1 else -5)]
            else:
                pts=[x2,y2,x2+(5 if x2<x1 else -5),y2-3,x2+(5 if x2<x1 else -5),y2+3]
            d.add(Polygon(pts,fillColor=ACCENT,strokeColor=None))
        if self.kind=='architecture':
            box(0,192,94,36,['操作者','工作台与审批'])
            box(129,192,198,36,['A01 协调智能体','检查 计划 任务记录'])
            box(367,192,123,36,['模型提出故障原因','按配置启用'])
            arrow(94,210,129,210);arrow(367,210,327,210)
            box(0,139,490,35,['梧桐平台  登记角色与能力  查找执行者  传递任务与结果'])
            arrow(228,192,228,174)
            roles=[['A02 应用','连接池与订单'],['A03/A04 数据库','主备共用操作记录'],['A05 运维','入口与进程'],['A06 业务验证','原请求与新订单'],['A07 接入检查','公开登记信息']]
            for x,lines in zip([0,100,200,300,400],roles):
                box(x,74,90,45,lines,8.1);arrow(x+45,139,x+45,119)
            box(0,8,390,45,['资源端检查权限、参数与审批，再调用MCP工具','Nginx入口  订单应用  PostgreSQL'])
            for x in [45,145,245,345]:arrow(x,74,x,53)
        else:
            box(0,132,134,38,['执行中断或结果未确认'])
            box(177,132,134,38,['查询日志与资源状态'])
            box(355,132,135,38,['查找同一资源的备用'])
            arrow(134,151,177,151);arrow(311,151,355,151)
            box(355,67,135,40,['确认新的接管版本','发送剩余任务']);arrow(422,132,422,107)
            for x,w,lines in [(0,141,['已执行','返回已有结果']),(174,142,['确认未执行','按条件继续操作']),(348,142,['结果未确认','核对资源与操作记录'])]:
                box(x,4,w,43,lines);arrow(422,67,x+w/2,47)
        renderPDF.draw(d,self.canv,0,0)


class Document(BaseDocTemplate):
    def __init__(self,path,kind):
        super().__init__(str(path),pagesize=A4,leftMargin=50,rightMargin=50,topMargin=53,bottomMargin=48,
                         title='联枢多智能体协同运维系统 '+kind+' 扩充协作稿',author='参赛团队',pageCompression=1)
        self.kind=kind;self.heading_count=0
        frame=Frame(50,48,WIDTH,A4[1]-101,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        self.addPageTemplates(PageTemplate(id='Main',frames=frame,onPage=self.paint_page))
    def beforeDocument(self):
        self.heading_count=0
    def afterFlowable(self,flowable):
        if isinstance(flowable,Paragraph) and flowable.style.name=='Chapter':
            self.heading_count+=1
            key=f'section-{self.heading_count}'
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.getPlainText(),key,0,False)
            self.notify('TOCEntry',(0,flowable.getPlainText(),self.page,key))
    def paint_page(self,canvas,doc):
        canvas.saveState()
        if doc.page>1:
            canvas.setFillColor(MUTED);canvas.setFont('UI',8)
            canvas.drawString(50,A4[1]-30,'联枢  /  '+self.kind)
            canvas.drawRightString(A4[0]-50,A4[1]-30,'扩充协作稿 · 2026.10.30')
            canvas.setStrokeColor(LINECOLOR);canvas.setLineWidth(.5);canvas.line(50,A4[1]-38,A4[0]-50,A4[1]-38)
        canvas.setFillColor(MUTED);canvas.setFont('UI',7.5)
        canvas.drawString(50,27,'AIC-2026-23708513  ·  智能体互联')
        canvas.drawRightString(A4[0]-50,27,str(doc.page))
        canvas.restoreState()


def table(block):
    data=[[para(v,'th') for v in block['headers']]]+[[para(v,'cell') for v in row] for row in block['rows']]
    ratios=block.get('widths') or [1]*len(block['headers'])
    widths=[v/sum(ratios)*WIDTH for v in ratios]
    result=Table(data,colWidths=widths,repeatRows=1,rowSplitRange=(3,-2),hAlign='LEFT',spaceBefore=5,spaceAfter=12)
    commands=[('BACKGROUND',(0,0),(-1,0),INK),('VALIGN',(0,0),(-1,-1),'TOP'),
              ('LINEBELOW',(0,0),(-1,0),.6,INK),('LINEBELOW',(0,-1),(-1,-1),.5,LINECOLOR),
              ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
              ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]
    for i in range(1,len(data)):
        if i%2==0:commands.append(('BACKGROUND',(0,i),(-1,i),PALE))
        commands.append(('LINEBELOW',(0,i),(-1,i),.3,LINECOLOR))
    result.setStyle(TableStyle(commands))
    return result


def copy_image(block):
    value=Path(block['path'])
    if value.is_absolute():
        source=value
        relative=Path(value.name)
    else:
        source=SOURCE/value
        relative=value
    destination=ASSETS/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():shutil.copy2(source,destination)
    return destination,relative


def block_flow(block):
    kind=block['type']
    if kind in ['p','h','note']:
        return [para(block['text'],{'p':'body','h':'section','note':'note'}[kind])]
    if kind=='table':return [table(block)]
    if kind=='diagram':return [KeepTogether([Spacer(1,4),Diagram(block['kind']),para(block['caption'],'caption')])]
    if kind=='code':
        return [KeepTogether([Preformatted(block['text'],ST['code']),para(block['caption'],'caption')])]
    if kind=='image':
        path,_=copy_image(block)
        return [KeepTogether([Spacer(1,5),SourceImage(path,block.get('width',470),block.get('crop')),para(block['caption'],'caption')])]
    raise ValueError(kind)


def chapter_flows(page):
    blocks=page['blocks']
    heading=para(page['title'],'chapter')
    first=0
    flows=[]
    lead=0
    while lead<len(blocks) and blocks[lead]['type']=='h':lead+=1
    if lead<len(blocks) and blocks[lead]['type'] in ['diagram','image','code']:
        visual=block_flow(blocks[lead])[0]
        content=visual._content if isinstance(visual,KeepTogether) else [visual]
        subheadings=[item for block in blocks[:lead] for item in block_flow(block)]
        flows.append(KeepTogether([heading,*subheadings,*content]))
        first=lead+1
    else:
        flows.extend([CondPageBreak(120),heading])
    for i,block in enumerate(blocks[first:],first):
        items=block_flow(block)
        if i+1<len(blocks) and blocks[i+1]['type']=='note' and items:
            items[-1].keepWithNext=True
        flows.extend(items)
    return flows


ABSTRACT = {
 'PLAN':'围绕订单应用、数据库和入口服务，说明七类智能体怎样通过梧桐协作，怎样在资源端检查权限，以及怎样在执行中断后继续任务。正文展开技术选择、模块衔接、恢复步骤、部署和验收安排。',
 'REPORT':'从业务问题、系统设计、开源改造和实施过程出发，结合代码说明发现、审批、资源操作与任务恢复。使用10月29日的故障修复、备用接管和平台记录，分析每个运行结果的来源与含义。',
 'EVIDENCE':'按接入、执行、恢复和结果核对组织E01至E15证据，保存关键截图、字段、数值与原始文件入口。将平台访问、测试、订单采样和工具任务回执分别对应到具体记录。',
}


def markdown(pages,kind):
    lines=['# 联枢多智能体协同运维系统', '',f'## {kind} · 扩充协作稿','',
           '团队编号：AIC-2026-23708513  ', '数据采集：2026年10月29日；正文扩充：2026年10月30日。','']
    for page in pages:
        lines += ['## '+page['title'],'']
        for block in page['blocks']:
            t=block['type']
            if t in ['p','note']:lines += [block['text'],'']
            elif t=='h':lines += ['### '+block['text'],'']
            elif t=='table':
                cell=lambda v:str(v).replace('|','｜').replace('\n','<br>')
                lines += ['| '+' | '.join(map(cell,block['headers']))+' |',
                          '| '+' | '.join(['---']*len(block['headers']))+' |']
                lines += ['| '+' | '.join(map(cell,row))+' |' for row in block['rows']]
                lines.append('')
            elif t=='code':lines += ['```text',block['text'],'```','',block['caption'],'']
            elif t=='image':
                _,relative=copy_image(block)
                lines += [f"![{block['caption']}](../引用图像/{relative.as_posix()})",'',block['caption'],'']
            elif t=='diagram':lines += [block['caption']+'（矢量图见同名PDF）','']
    return '\n'.join(lines)


def build(name,kind):
    data=json.loads((HERE/(name+'_expanded.json')).read_text(encoding='utf-8'))
    basename=f'AIC-2026-23708513-联枢多智能体协同运维系统-{kind}-扩充协作稿'
    destination=PDFDIR/(basename+'.pdf')
    story=[Spacer(1,16),para('2026 AIC  /  智能体互联','cover_kicker'),
           para('联枢多智能体协同运维系统','cover_title'),para(kind,'cover_kind'),
           para('扩充协作稿  ·  AIC-2026-23708513<br/>数据采集 2026.10.29  /  正文扩充 2026.10.30'.replace('<br/>','\n'),'cover_meta'),
           para(ABSTRACT[name],'cover_abstract')]
    facts=Table([[para('7个协作角色','th'),para('2个云端恢复案例','th'),para('15组证据编号','th')]],colWidths=[WIDTH/3]*3)
    facts.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),INK),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10),('LEFTPADDING',(0,0),(-1,-1),12)]))
    story += [facts,Spacer(1,20),Diagram('architecture'),Spacer(1,14),
              para('工程范围：订单应用、PostgreSQL、Nginx入口；平台注册、发现和任务传递由梧桐提供。','note'),PageBreak(),
              para('目录','toc_title')]
    toc=TableOfContents();toc.levelStyles=[ST['toc']];toc.dotsMinLevel=0
    story += [toc,PageBreak()]
    for page in data:story += chapter_flows(page)
    document=Document(destination,kind)
    document.multiBuild(story,maxPasses=5)
    (MDDIR/(basename+'.md')).write_text(markdown(data,kind),encoding='utf-8')
    pdf=PdfReader(destination)
    text='\n'.join(page.extract_text() or '' for page in pdf.pages)
    (QA/(kind+'-提取文本.txt')).write_text(text,encoding='utf-8')
    return dict(kind=kind,key=name,pdf=destination.relative_to(ROOT).as_posix(),markdown=(MDDIR/(basename+'.md')).relative_to(ROOT).as_posix(),
                sections=len(data),pages=len(pdf.pages),bytes=destination.stat().st_size,
                prose_characters=sum(len(block.get('text','')) for page in data for block in page['blocks'] if block['type']!='code'),
                visual_review='pending')


if __name__=='__main__':
    specs=[('PLAN','技术方案'),('REPORT','技术报告'),('EVIDENCE','佐证材料')]
    chosen=set(args.kinds)
    previous=json.loads((QA/'PDF生成记录.json').read_text(encoding='utf-8')) if (QA/'PDF生成记录.json').exists() else []
    result={item['key']:item for item in previous}
    for key,kind in specs:
        if not chosen or key in chosen:result[key]=build(key,kind)
    rows=[result[key] for key,_ in specs if key in result]
    (QA/'PDF生成记录.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(rows,ensure_ascii=False,indent=2))

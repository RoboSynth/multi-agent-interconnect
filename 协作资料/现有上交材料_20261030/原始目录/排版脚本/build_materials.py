from pathlib import Path
import sys, json, hashlib, re, os
from datetime import datetime, timezone, timedelta
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether, Flowable, Preformatted
from reportlab.graphics.shapes import Drawing, Rect, Line, Polygon, String
from reportlab.graphics import renderPDF
from pypdf import PdfReader
from material_content import TITLE, TEAM, DATE, INTRO, REPORT, PLAN, EVIDENCE

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'原始目录'/'排版核验'
OUT.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('CN',os.getenv('MATERIAL_BODY_FONT','C:/Windows/Fonts/simsun.ttc'),subfontIndex=0))
pdfmetrics.registerFont(TTFont('UI',os.getenv('MATERIAL_UI_FONT','C:/Windows/Fonts/msyh.ttc'),subfontIndex=0))
pdfmetrics.registerFont(TTFont('UIB',os.getenv('MATERIAL_BOLD_FONT','C:/Windows/Fonts/msyhbd.ttc'),subfontIndex=0))
pdfmetrics.registerFontFamily('CN',normal='CN',bold='UIB',italic='CN',boldItalic='UIB')
pdfmetrics.registerFontFamily('UI',normal='UI',bold='UIB',italic='UI',boldItalic='UIB')
INK=colors.HexColor('#152C40'); MUTED=colors.HexColor('#56616B'); PALE=colors.HexColor('#F2F5F7'); BORDER=colors.HexColor('#D9D9D9')
WIDTH=A4[0]-104
ST={
 'title':ParagraphStyle('title',fontName='UIB',fontSize=22,leading=32,textColor=colors.black,spaceAfter=9),
 'subtitle':ParagraphStyle('subtitle',fontName='UI',fontSize=12,leading=20,textColor=colors.black,spaceAfter=4),
 'meta':ParagraphStyle('meta',fontName='UI',fontSize=8.6,leading=14,textColor=MUTED,spaceAfter=16),
 'heading':ParagraphStyle('heading',fontName='UIB',fontSize=16,leading=25,spaceAfter=14,textColor=colors.black),
 'h':ParagraphStyle('h',fontName='UIB',fontSize=11.5,leading=20,spaceBefore=9,spaceAfter=6,textColor=colors.black,keepWithNext=True),
 'p':ParagraphStyle('p',fontName='CN',fontSize=10.6,leading=18.4,spaceAfter=10,wordWrap='CJK',textColor=colors.black),
 'note':ParagraphStyle('note',fontName='CN',fontSize=8.5,leading=14,spaceBefore=3,spaceAfter=8,wordWrap='CJK',textColor=MUTED),
 'cell':ParagraphStyle('cell',fontName='UI',fontSize=8.4,leading=13.5,wordWrap='CJK',textColor=colors.black),
 'th':ParagraphStyle('th',fontName='UIB',fontSize=8.6,leading=14,wordWrap='CJK',textColor=colors.white),
 'caption':ParagraphStyle('caption',fontName='CN',fontSize=8.5,leading=14,alignment=TA_CENTER,textColor=MUTED,spaceBefore=5,spaceAfter=12),
 'code':ParagraphStyle('code',fontName='Courier',fontSize=8.4,leading=13,spaceBefore=5,spaceAfter=5),
}
def para(t,style='p'):
    return Paragraph(escape(str(t)).replace('\n','<br/>'),ST[style])

class ImageRegion(Flowable):
    """在PDF内裁切查看原截图，不改写原始图片文件。"""
    def __init__(self,path,width,crop):
        from PIL import Image as PImage
        super().__init__()
        self.path=str(path)
        with PImage.open(path) as im:
            self.source_width,self.source_height=im.size
        self.left,self.top,self.right,self.bottom=crop
        assert 0 <= self.left < self.right <= self.source_width
        assert 0 <= self.top < self.bottom <= self.source_height
        self.width=width
        self.scale=width/(self.right-self.left)
        self.height=(self.bottom-self.top)*self.scale
        self.hAlign='CENTER'
    def draw(self):
        self.canv.saveState()
        clip=self.canv.beginPath()
        clip.rect(0,0,self.width,self.height)
        self.canv.clipPath(clip,stroke=0,fill=0)
        self.canv.drawImage(self.path,-self.left*self.scale,
                            -(self.source_height-self.bottom)*self.scale,
                            width=self.source_width*self.scale,
                            height=self.source_height*self.scale)
        self.canv.restoreState()

class Diagram(Flowable):
    def __init__(self,kind):
        super().__init__(); self.kind=kind; self.width=WIDTH; self.height=242 if kind=='architecture' else 182
    def draw(self):
        d=Drawing(self.width,self.height)
        def box(x,y,w,h,lines,fill=PALE,size=9):
            d.add(Rect(x,y,w,h,rx=4,ry=4,fillColor=fill,strokeColor=colors.HexColor('#A9B6BF'),strokeWidth=.6))
            if isinstance(lines,str): lines=[lines]
            for i,s in enumerate(lines):
                font_size=min(size,(w-8)/max(pdfmetrics.stringWidth(s,'UI',1),1))
                d.add(String(x+w/2,y+h/2+(len(lines)-1)*7-i*14-3,s,fontName='UI',fontSize=font_size,textAnchor='middle',fillColor=INK))
        def arrow(x1,y1,x2,y2):
            d.add(Line(x1,y1,x2,y2,strokeColor=MUTED,strokeWidth=.8))
            if abs(y2-y1)>abs(x2-x1): pts=[x2,y2,x2-3,y2+(5 if y2<y1 else -5),x2+3,y2+(5 if y2<y1 else -5)]
            else: pts=[x2,y2,x2+(5 if x2<x1 else -5),y2-3,x2+(5 if x2<x1 else -5),y2+3]
            d.add(Polygon(pts,fillColor=MUTED,strokeColor=None))
        if self.kind=='architecture':
            box(0,197,93,36,['操作者','工作台与审批'])
            box(132,197,195,36,['A01 协调智能体','事实 计划 任务日志'])
            box(367,197,123,36,['模型提出故障原因','按配置启用'])
            arrow(93,215,132,215); arrow(367,215,327,215)
            box(0,143,490,35,['梧桐平台  登记角色与能力  查找执行者  传递任务与结果'])
            arrow(229,197,229,178)
            for x,text in [(0,['A02 应用','连接池与订单']), (100,['A03/A04 数据库','主备共用操作记录']), (200,['A05 运维','入口与进程']), (300,['A06 业务验证','原请求与新订单']), (400,['A07 接入检查','公开登记信息'])]:
                box(x,77,90,46,text,size=8.1); arrow(x+45,143,x+45,123)
            box(0,10,390,46,['资源端检查权限、参数与审批，再调用MCP工具','Nginx入口  订单应用  PostgreSQL'])
            for x in [45,145,245,345]:arrow(x,77,x,56)
        else:
            box(0,133,134,39,['执行中断或结果未确认'])
            box(177,133,134,39,['查询日志与资源状态'])
            box(355,133,135,39,['查找同一资源的备用'])
            arrow(134,152,177,152); arrow(311,152,355,152)
            box(355,68,135,40,['确认新的接管版本','发送剩余任务'])
            arrow(422,133,422,108)
            box(0,4,141,43,['已执行','返回已有结果'])
            box(174,4,142,43,['确认未执行','按条件继续操作'])
            box(348,4,142,43,['结果未确认','核对资源与操作记录'])
            for x in [70,245,419]: arrow(422,68,x,47)
        renderPDF.draw(d,self.canv,0,0)

def footer(canvas,doc):
    canvas.saveState()
    canvas.setFont('UI',7.6); canvas.setFillColor(MUTED)
    canvas.drawString(52,27,TEAM+'  智能体互联')
    canvas.drawRightString(A4[0]-52,27,str(doc.page))
    canvas.restoreState()

def blocks_to_flow(blocks):
    flow=[]
    for b in blocks:
        t=b['type']
        if t in ['p','h','note']: flow.append(para(b['text'],t))
        elif t=='table':
            data=[[para(x,'th') for x in b['headers']]]+[[para(x,'cell') for x in row] for row in b['rows']]
            widths=b.get('widths') or [1]*len(b['headers'])
            widths=[x/sum(widths)*WIDTH for x in widths]
            table=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT',spaceBefore=5,spaceAfter=13)
            cmds=[('BACKGROUND',(0,0),(-1,0),INK),('GRID',(0,0),(-1,-1),.45,BORDER),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]
            for i in range(1,len(data)):
                if i%2==0:cmds.append(('BACKGROUND',(0,i),(-1,i),PALE))
            table.setStyle(TableStyle(cmds)); flow.append(table)
        elif t=='diagram':flow.extend([Diagram(b['kind']),para(b['caption'],'caption')])
        elif t=='code':flow.extend([Preformatted(b['text'],ST['code']),para(b['caption'],'caption')])
        elif t=='image':
            from PIL import Image as PImage
            path=ROOT/b['path']; im=PImage.open(path); w=b.get('width',300); h=w*im.height/im.width
            picture=ImageRegion(path,w,b['crop']) if b.get('crop') else Image(str(path),width=w,height=h)
            flow.extend([picture,para(b['caption'],'caption')])
    return flow

def markdown(pages,kind):
    out=[f'# {TITLE}',f'\n{kind}\n\n团队编号：{TEAM}\n\n日期：{DATE}\n']
    for page in pages:
        out.append('## '+page['title'])
        for b in page['blocks']:
            if b['type']=='h':out.append('### '+b['text'])
            elif b['type'] in ['p','note']:out.append(b['text'])
            elif b['type']=='table':
                out.append('| '+' | '.join(b['headers'])+' |\n| '+' | '.join(['---']*len(b['headers']))+' |\n'+'\n'.join('| '+' | '.join(str(v) for v in r)+' |' for r in b['rows']))
            elif b['type']=='code':out.append('```python\n'+b['text']+'\n```\n\n'+b['caption'])
            elif b['type']=='image':
                out.append('!['+b['caption']+'](../../'+b['path']+')\n\n'+b['caption'])
            else:out.append(b['caption'])
    return '\n\n'.join(out)+'\n'

def make(kind,pages,folder):
    dest=ROOT/folder; dest.mkdir(parents=True,exist_ok=True)
    name=f'{TEAM}-智能体互联-{TITLE}-{kind}'
    pdf=dest/(name+'.pdf')
    doc=SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=52,leftMargin=52,topMargin=45,bottomMargin=48,title=TITLE+' '+kind,author='参赛团队',subject='智能体互联竞赛材料',pageCompression=1)
    story=[]
    for i,page in enumerate(pages):
        if i:story.append(PageBreak())
        else:story.extend([para(TITLE,'title'),para(kind,'subtitle'),para(TEAM+'  |  '+DATE,'meta')])
        story.append(para(page['title'],'heading'));story.extend(blocks_to_flow(page['blocks']))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    md_dir=ROOT/'原始目录'/'正文源稿';md_dir.mkdir(parents=True,exist_ok=True)
    md=md_dir/(name+'-可编辑稿.md');md.write_text(markdown(pages,kind),encoding='utf-8')
    reader=PdfReader(pdf);text='\n'.join(p.extract_text() or '' for p in reader.pages)
    (OUT/(kind+'-提取文本.txt')).write_text(text,encoding='utf-8')
    return {'kind':kind,'path':str(pdf.relative_to(ROOT)),'source':str(md.relative_to(ROOT)),'pages':len(reader.pages),'planned_pages':len(pages),'bytes':pdf.stat().st_size,'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'text':text}

def main():
    assert len(TITLE)<=20,(len(TITLE),TITLE)
    assert len(INTRO)<=300,(len(INTRO),INTRO)
    info=ROOT/'作品名称与简介';info.mkdir(exist_ok=True)
    info_text=f'参赛团队编号：{TEAM}\n赛题名称：智能体互联\n作品名称：{TITLE}\n作品名称字数：{len(TITLE)}\n\n作品简介\n{INTRO}\n\n简介字符数：{len(INTRO)}（含标点与英文字母）\n'
    (info/f'{TEAM}-智能体互联-{TITLE}-作品名称与简介.txt').write_text(info_text,encoding='utf-8')
    specs=[('技术方案',PLAN,'技术方案'),('技术报告',REPORT,'技术报告'),('佐证材料',EVIDENCE,'佐证材料')]
    wanted=set(sys.argv[1:])
    previous=json.loads((OUT/'document-build.json').read_text(encoding='utf-8')) if (OUT/'document-build.json').exists() else {}
    results=[]
    for s in specs:
        if not wanted or s[0] in wanted:results.append(make(*s))
        else:
            saved=next(dict(x) for x in previous['files'] if x['kind']==s[0])
            saved['text']='\n'.join(p.extract_text() or '' for p in PdfReader(ROOT/saved['path']).pages)
            results.append(saved)
    forbidden=[r'1\.2\.156\.3088\.1\.[A-Z]+\.',r'\b(?:\d{1,3}\.){3}\d{1,3}\b',r'[A-Z]:[\\/]Users[\\/][^\\/\s]+',r'指导教师\s*[:：]\s*\S+',r'BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY',r'(?i)sk-[A-Za-z0-9]{16,}']
    privacy=[]
    for r in results:
        hits=[p for p in forbidden if re.search(p,r['text'])]
        privacy.append({'file':r['path'],'matched_patterns':hits})
        r.pop('text')
    qa={'created_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'title_chars':len(TITLE),'intro_chars':len(INTRO),'files':results,'privacy_checks':privacy,'render_review':'pending','upload_performed':False}
    (OUT/'document-build.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(qa,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

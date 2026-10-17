"""Build one anonymous supporting-evidence PDF from local frozen projections."""
from pathlib import Path
import hashlib
import json
import math
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle
from PIL import Image

HERE=Path(__file__).resolve().parent
W,H=A4
L=48
BODY=W-2*L
BOTTOM=57
INK=colors.HexColor('#243540')
NAVY=colors.HexColor('#173b50')
TEAL=colors.HexColor('#087e87')
MUTED=colors.HexColor('#5c6f7c')
RULE=colors.HexColor('#d9e2e6')
LIGHT=colors.HexColor('#f0f5f6')

def font_setup():
    root=Path('C:/Windows/Fonts')
    pdfmetrics.registerFont(TTFont('CN',str(root/'msyh.ttc'),subfontIndex=0))
    pdfmetrics.registerFont(TTFont('CNBold',str(root/'msyhbd.ttc'),subfontIndex=0))
    pdfmetrics.registerFontFamily('CN',normal='CN',bold='CNBold',italic='CN',boldItalic='CNBold')

def style(size=10,leading=17,bold=False,color=INK):
    return ParagraphStyle('p',fontName='CNBold' if bold else 'CN',fontSize=size,leading=leading,textColor=color,wordWrap='CJK',alignment=TA_LEFT,spaceAfter=0,allowWidows=0,allowOrphans=0)

class EvidencePDF:
    def __init__(self,content,data):
        self.content,self.data=content,data
        self.total=len(content['pages'])+math.ceil(len(data['sources'])/9)
        self.path=HERE/'supporting-evidence-development.pdf'
        self.c=canvas.Canvas(str(self.path),pagesize=A4,pageCompression=1,invariant=1,initialFontName='CN',initialFontSize=10)
        self.c.setTitle(content['title']+' - 匿名佐证开发稿')
        self.c.setAuthor('')
        self.c.setCreator('Anonymous supporting-evidence builder')
        self.c.setSubject('非最终提交版；固定闭合数据；不含身份值、原始日志或资源凭据')
        self.page=0
        self.frame=[]
    def reserve(self,h):
        self.y-=h
        if self.y<BOTTOM:raise ValueError(f'Page {self.page} overflow at {self.y:.1f}')
        return self.y
    def p(self,text,size=10,leading=17,bold=False,color=INK,gap=8):
        p=Paragraph(text,style(size,leading,bold,color))
        _,h=p.wrap(BODY,H)
        p.drawOn(self.c,L,self.reserve(h))
        self.reserve(gap)
    def table(self,headers,rows,widths=None,size=8.8):
        widths=widths or [BODY/len(headers)]*len(headers)
        grid=[[Paragraph(escape(str(v)),style(size,13,True,colors.white)) for v in headers]]
        grid += [[Paragraph(escape(str(v)),style(size,13)) for v in row] for row in rows]
        t=Table(grid,colWidths=widths,hAlign='LEFT')
        t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'CN'),('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('ROWBACKGROUNDS',(0,1),(-1,-1),[LIGHT,colors.white]),('LINEBELOW',(0,1),(-1,-1),0.35,RULE)]))
        _,h=t.wrap(BODY,H)
        t.drawOn(self.c,L,self.reserve(h))
        self.reserve(10)
    def callout(self,title,text,warning=False):
        p=Paragraph('<b>'+title+'</b><br/>'+text,style(9.5,16))
        _,h=p.wrap(BODY-24,H)
        y=self.reserve(h+18)
        self.c.setFillColor(colors.HexColor('#fcf4ee') if warning else LIGHT)
        self.c.rect(L,y,BODY,h+18,fill=1,stroke=0)
        p.drawOn(self.c,L+12,y+9)
        self.reserve(11)
    def start(self,section,title):
        self.page+=1
        self.c.setFillColor(MUTED);self.c.setFont('CN',7.5)
        self.c.drawString(L,H-29,'跨域故障协同 / 佐证材料开发稿')
        self.c.drawRightString(W-L,H-29,'非最终提交版')
        self.c.setStrokeColor(RULE);self.c.setLineWidth(.7);self.c.line(L,H-38,W-L,H-38)
        self.y=H-60
        self.p(section,8.5,14,True,TEAL,5)
        self.p(title,21,30,True,NAVY,14)
    def finish(self):
        self.frame.append(round(self.y,2))
        self.c.setStrokeColor(RULE);self.c.setLineWidth(.5);self.c.line(L,42,W-L,42)
        self.c.setFillColor(MUTED);self.c.setFont('CN',7.1)
        self.c.drawString(L,28,'证据截止2026-10-17 12:50:41 UTC；缺项不计为通过')
        self.c.drawRightString(W-L,28,f'{self.page:02d} / {self.total:02d}')
        self.c.showPage()
    def special(self,kind):
        d=self.data
        if kind=='platform_cycles':
            self.table(['周期','观察秒','请求 / 完整流程','结果'],[['首次',30.003,'30 / 10','健康'],['自然周期2',30.002,'30 / 10','健康，无修复/审批']], [106,83,139,171.28])
        elif kind=='access_summary':
            a=d['access'];self.table(['真实Start','预期双端access','实际','缺失 / 额外'],[[a['native_start_tasks'],a['expected_access_records'],a['actual_access_records'],f"{a['missing_records']} / {a['extra_records']}"]],[110,150,80,159.28])
        elif kind=='amp_counts':
            self.table(['日志类型','唯一本地记录'],list(d['amp']['log_types'].items()),[240,259.28])
        elif kind=='historical_samples':
            rows=[]
            for row in d['historical_model']['by_scenario']:
                rows.append([row['scenario']]+[' / '.join(f'{v:.3f}' for v in row['methods'][m]['observed_seconds']) for m in ['M0','M1','M2']])
            self.table(['场景','M0三次 / 秒','旧M1三次 / 秒','M2三次 / 秒'],rows,[62,145,146,146.28],8.3)
        elif kind=='model_costs':
            t=d['historical_model']['totals']
            self.table(['方法','探测总数','实际模型token'],[[m,t[m]['probes'],t[m]['tokens']] for m in ['M0','M1','M2']],[140,155,204.28])
        elif kind=='e1_payload':
            rows=[]
            for key,name in [('from_scratch','从头'),('full_history','完整历史'),('resume_package','恢复包')]:
                x=d['E1b'][key];rows.append([name,x['ifc_payload_utf8_bytes_median'],x['handover_information_utf8_bytes_median'],x['additional_post_handover_observations_median']])
            self.table(['策略','完整IFC字节','信息字节','额外应用观察'],rows,[130,123,123,123.28])
        elif kind=='blocker_checks':
            x=d['blocker'];self.table(['拒绝/动作','实际结果'],[['无审批',x['without_approval']],['非阻塞目标',x['non_blocking_target']],['受控终止 / 等待解除',x['controlled_termination']+' / '+str(x['waiter_released']).lower()],['同操作重放',x['duplicate']]],[230,269.28])
        else:raise ValueError(kind)
    def build(self):
        for page in self.content['pages']:
            self.start(page['section'],page['title'])
            for b in page['blocks']:
                k=b['type']
                if k=='p':self.p(b['text'])
                elif k=='h':self.p(b['text'],12,20,True,NAVY,5)
                elif k=='small':self.p(b['text'],7.8,12,color=MUTED,gap=7)
                elif k=='table':self.table(b['headers'],b['rows'],b.get('widths'),b.get('size',8.8))
                elif k=='callout':self.callout(b['title'],b['text'],b.get('warning',False))
                elif k=='image':
                    file=HERE/b['asset']
                    with Image.open(file) as im:iw,ih=im.size
                    h=BODY*ih/iw
                    self.c.drawImage(str(file),L,self.reserve(h),width=BODY,height=h,preserveAspectRatio=True)
                    self.reserve(6);self.p(b['caption'],7.8,12,color=MUTED)
                else:self.special(k)
            self.finish()
        for start in range(0,len(self.data['sources']),9):
            self.start('附录 / 原件定位与SHA',f"证据索引 {start//9+1} / {math.ceil(len(self.data['sources'])/9)}")
            self.p('以下定位相对于原开发项目根目录，SHA标识该次捕获的原件。它们不保证团队副本同路径存在；正文只含匿名派生值。',8,12,color=MUTED,gap=10)
            for s in self.data['sources'][start:start+9]:
                self.p(s['id']+'  '+s['label'],9.5,15,True,NAVY,2)
                self.p(escape(s['relative_path']),7.8,11,gap=2)
                self.p('SHA256  '+s['sha256'],6.8,10,color=MUTED,gap=10)
            self.finish()
        assert self.page==self.total
        self.c.save()
        info={'pdf':self.path.name,'page_count':self.page,'page_body_min_y':self.frame,'frame_bottom':BOTTOM,'frame_overflow':False,'pdf_bytes':self.path.stat().st_size,'pdf_sha256':hashlib.sha256(self.path.read_bytes()).hexdigest(),'source_sha256':{f:hashlib.sha256((HERE/f).read_bytes()).hexdigest() for f in ['build.py','content.json','data.json']},'fonts':'Microsoft YaHei regular/bold embedded subsets; font files not distributed'}
        (HERE/'build-info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(info))

def main():
    font_setup()
    content=json.loads((HERE/'content.json').read_text(encoding='utf-8'))
    data=json.loads((HERE/'data.json').read_text(encoding='utf-8'))
    assert content['cutoff_utc']==data['cutoff_utc']=='2026-10-17T12:50:41.317Z'
    EvidencePDF(content,data).build()

if __name__=='__main__':main()

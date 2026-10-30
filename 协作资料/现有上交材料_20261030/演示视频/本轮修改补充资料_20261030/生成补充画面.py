"""从现有检查和提交记录制作本轮修改所需的说明画面。"""
from pathlib import Path
from html import escape
import json
import shutil
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent
OUT = ROOT/'替换画面'
OUT.mkdir(exist_ok=True)
S = 2
COL = dict(bg='#F2F7FA',ink='#19394B',muted='#5B7382',blue='#087D9A',green='#187B64',
           red='#B74343',white='#FFFFFF',line='#C8DAE3',pale='#E6F2F6',palered='#FAECEA')

class Picture:
    def __init__(self,name,height=1080):
        self.name=name;self.height=height
        self.im=Image.new('RGB',(1920*S,height*S),COL['bg']);self.d=ImageDraw.Draw(self.im)
        self.svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="{height}" viewBox="0 0 1920 {height}">',
                  f'<rect width="1920" height="{height}" fill="{COL["bg"]}"/>']
    def box(self,x,y,w,h,color='white'):
        self.d.rounded_rectangle((x*S,y*S,(x+w)*S,(y+h)*S),radius=18*S,fill=COL[color])
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{COL[color]}"/>')
    def text(self,x,y,t,size=34,color='ink',bold=False):
        f=ImageFont.truetype('C:/Windows/Fonts/'+('msyhbd.ttc' if bold else 'msyh.ttc'),size*S)
        b=self.d.textbbox((0,0),t,font=f,anchor='lt')
        assert x+(b[2]-b[0])/S<1855,(self.name,t)
        self.d.text((x*S,y*S),t,font=f,fill=COL[color],anchor='lt')
        self.svg.append(f'<text x="{x}" y="{y}" font-family="Microsoft YaHei,sans-serif" font-size="{size}" '
                        f'dominant-baseline="text-before-edge" font-weight="{700 if bold else 400}" fill="{COL[color]}">{escape(t)}</text>')
    def header(self,title,sub):
        self.text(78,65,'联枢  /  本次记录说明',25,'blue',True)
        self.text(76,147,title,52,bold=True);self.text(78,238,sub,30,'muted')
    def save(self):
        self.im.save(OUT/(self.name+'.png'))
        (OUT/(self.name+'.svg')).write_text('\n'.join(self.svg+['</svg>']),encoding='utf-8')

policy=json.loads((SOURCE/'V6-safety/policy-denials.json').read_text(encoding='utf-8'))
selected=[next(c for c in policy['cases'] if c['case_key']==k) for k in ['high-without-approval','approval-expired']]
assert all(c['actual_status']=='rejected' and c['mcp_calls']==0 and c['modification_calls']==0 for c in selected)
assert (policy['rejected_cases'],policy['positive_controls_passed'])==(14,1)
c=Picture('01_没有批准的修改会被挡住')
c.header('没有批准的修改，会被挡住','从本地检查中选出两个例子')
for x,title,request,reason in [(76,'例子一  还没有得到批准','请求：修改数据库','缺少有效批准'),
                              (994,'例子二  拿过期的批准继续修改','请求：修改数据库','原来的批准已经过期')]:
    c.box(x,338,850,338);c.text(x+30,372,title,37,'blue',True)
    c.text(x+30,444,request,34);c.text(x+30,502,reason,31,'muted')
    c.box(x+30,568,780,76,'palered');c.text(x+54,587,'拒绝执行  ·  数据库没有被改动',33,'red',True)
c.box(76,758,1768,166,'pale')
c.text(110,786,'本地检查结果',31,'blue',True)
c.text(110,845,'14 项违规请求被拒绝     1 项合法请求放行',43,bold=True)
c.text(78,988,'依据：2026年10月29日本地检查记录；被拒绝的请求均未进入工具执行。',26,'muted')
c.save()

titles=[('02_中断任务继续处理','让中断的任务可以继续处理','任务处理记录保留下来，接手后继续推进。',
         [('任务进行中','记录已经处理的内容'),('执行者退出','保留已有处理记录'),('任务继续','依据已有记录接着做')],'编号为13的提交记录'),
        ('03_同一文件依次写入','让写到同一文件的消息依次保存','同一个程序内，多处写入先排队、再写入。',
         [('多个写入请求','都要写入同一个文件'),('先排好顺序','逐个取得写入机会'),('依次保存','减少同时写入的干扰')],'编号为14的提交记录')]
for name,title,sub,steps,ref in titles:
    c=Picture(name);c.header(title,sub)
    for i,(head,body) in enumerate(steps):
        x=76+i*610;c.box(x,390,548,252);c.text(x+30,432,head,40,'blue',True);c.text(x+30,514,body,32)
        if i<2:c.text(x+560,478,'→',40,'blue')
    c.box(76,755,1768,156,'pale');c.text(110,790,'已向官方开源仓库提交代码改进',38,'blue',True)
    c.text(112,851,'截至2026年10月29日：已提交，尚未合并。',31)
    c.text(78,990,'对应'+ref+'；配合原提交页面展示。',26,'muted');c.save()
    overlay=Picture(name+'_中文标题条',230)
    overlay.text(60,38,title,48,'blue',True)
    overlay.text(62,116,sub,30)
    overlay.text(62,174,'截至2026年10月29日：已提交，尚未合并。',24,'muted')
    overlay.save()

original=ROOT/'原页面';original.mkdir(exist_ok=True)
sources=[('V5-access/status-A01.png','协调者访问统计.png'),('V5-access/status-A03.png','数据库执行体访问统计.png'),
         ('V7-opensource/pr-13-overview.png','第十三项代码改进原页面.png'),('V7-opensource/pr-14-overview.png','第十四项代码改进原页面.png')]
for src,target in sources:shutil.copy2(SOURCE/src,original/target)
(ROOT/'来源.json').write_text(json.dumps({'source_date':'2026-10-29','prepared_date':'2026-10-30',
 'checks':[{'case_id':c['case_id'],'case_key':c['case_key'],'decision':c['actual_status'],'mcp_calls':c['mcp_calls']} for c in selected],
 'safety_source':'V6-safety/policy-denials.json','contribution_source':'V7-opensource/contributions.json',
 'original_pages':[{'source':s,'copy':'原页面/'+t} for s,t in sources]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
sheet=Image.new('RGB',(640,1080),'#E1EAF0')
for i,name in enumerate(['01_没有批准的修改会被挡住','02_中断任务继续处理','03_同一文件依次写入']):
    im=Image.open(OUT/(name+'.png'));im.thumbnail((640,360));sheet.paste(im,(0,i*360))
sheet.save(ROOT/'补充画面预览.jpg',quality=94)
print(json.dumps({'full_cards':3,'title_strips':2,'original_pages':4}))

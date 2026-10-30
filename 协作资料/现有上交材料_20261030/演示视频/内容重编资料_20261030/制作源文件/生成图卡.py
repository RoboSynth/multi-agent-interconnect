"""读取已采集的运行记录，生成视频说明图卡。"""
from collections import Counter
from html import escape
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

BUNDLE = Path(__file__).resolve().parents[1]
SOURCE = BUNDLE.parent
OUT = BUNDLE / '图卡'
OUT.mkdir(exist_ok=True)
SCALE = 2
C = dict(bg='#F2F7FA', ink='#19394B', muted='#5B7382', blue='#087D9A',
         green='#187B64', red='#B74343', amber='#A3701B', white='#FFFFFF',
         line='#C8DAE3', pale='#E6F2F6', palegreen='#E5F3ED', palered='#FAECEA')

def read(relative):
    return json.loads((SOURCE / relative).read_text(encoding='utf-8-sig'))

state = read('V3-f10/incident-state.json')
evaluation = read('V3-f10/evaluation-result.json')[0]
order = state['result']['order_observation']
samples = read('V3-f10/order-samples.json')['samples']
counts = Counter(s['outcome'] for s in samples)
takeover = read('V4-takeover/result.json')
takeover_order = takeover['business_verification']
assert takeover['crash_point'] == 'after_applied'
assert takeover['model_calls'] == 0
assert (takeover_order['requests'], takeover_order['success'], takeover_order['completed_workflows'],
        takeover_order['failed'], takeover_order['unknown']) == (30, 30, 10, 0, 0)
assert takeover['worker_exit_and_mcp']['counts']['operations'][0]['invocations'] == 1
assert set(state['diagnosed_causes']) == {'database_read_only', 'stale_route'}
assert evaluation['model_calls'] == 0
assert (order['requests'], order['success'], order['completed_workflows'], order['unknown']) == (30, 30, 10, 0)
assert counts == {'success': 36, 'unknown': 16}
actions = [t['tool'] for t in state['tasks'] if t['tool'] in
           {'ops.route_rollback', 'db.restore_writes', 'application.pool_rebuild'}]
assert actions == ['ops.route_rollback', 'db.restore_writes', 'application.pool_rebuild']

class Card:
    def __init__(self, name, title, subtitle, kind='示意图'):
        self.name = name
        self.im = Image.new('RGB', (1920*SCALE, 1080*SCALE), C['bg'])
        self.draw = ImageDraw.Draw(self.im)
        self.svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">',
                    f'<rect width="1920" height="1080" fill="{C["bg"]}"/>']
        self.rect(76, 64, 430, 48, 'pale', radius=9)
        self.text(96, 75, '联枢  /  ' + kind, 24, 'blue', True)
        self.text(76, 152, title, 54, bold=True)
        self.text(78, 239, subtitle, 30, 'muted')
        self.line(76, 994, 1844, 994)
        self.text(78, 1021, '内容依据 2026年10月29日采集记录  ·  资料整理 2026年10月30日', 23, 'muted')
    def text(self, x, y, value, size=32, color='ink', bold=False):
        value = str(value)
        f = ImageFont.truetype('C:/Windows/Fonts/' + ('msyhbd.ttc' if bold else 'msyh.ttc'), size*SCALE)
        box = self.draw.textbbox((0, 0), value, font=f, anchor='lt')
        if x + (box[2]-box[0])/SCALE > 1848:
            raise ValueError(f'{self.name}: text exceeds safe area: {value}')
        self.draw.text((x*SCALE, y*SCALE), value, font=f, fill=C.get(color, color), anchor='lt')
        self.svg.append(f'<text x="{x}" y="{y}" font-family="Microsoft YaHei, sans-serif" font-size="{size}" '
                        f'font-weight="{700 if bold else 400}" dominant-baseline="text-before-edge" '
                        f'fill="{C.get(color,color)}">{escape(value)}</text>')
    def rect(self, x, y, w, h, fill='white', outline=None, radius=20):
        self.draw.rounded_rectangle((x*SCALE,y*SCALE,(x+w)*SCALE,(y+h)*SCALE), radius=radius*SCALE,
                                    fill=C.get(fill,fill), outline=C.get(outline,outline) if outline else None,
                                    width=2*SCALE)
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
                        f'fill="{C.get(fill,fill)}" stroke="{C.get(outline,outline) if outline else "none"}" stroke-width="2"/>')
    def line(self,x1,y1,x2,y2,color='line',width=3):
        self.draw.line((x1*SCALE,y1*SCALE,x2*SCALE,y2*SCALE),fill=C[color],width=width*SCALE)
        self.svg.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{C[color]}" stroke-width="{width}"/>')
    def arrow(self,x1,y1,x2,y2,color='blue'):
        self.line(x1,y1,x2,y2,color,4)
        if y1 == y2:
            pts=[(x2,y2),(x2-14,y2-9),(x2-14,y2+9)]
        else:
            pts=[(x2,y2),(x2-9,y2-14),(x2+9,y2-14)]
        self.draw.polygon([(x*SCALE,y*SCALE) for x,y in pts],fill=C[color])
        self.svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in pts)}" fill="{C[color]}"/>')
    def node(self,x,y,w,h,title,lines=(),color='blue'):
        self.rect(x,y,w,h,outline='line')
        self.text(x+28,y+30,title,34,color,True)
        for i,s in enumerate(lines): self.text(x+28,y+98+i*49,s,29)
    def save(self):
        self.im.save(OUT/(self.name+'.png'))
        (OUT/(self.name+'.svg')).write_text('\n'.join(self.svg+['</svg>']),encoding='utf-8')

cards=[]
def done(card):
    card.save(); cards.append(card.name)

c=Card('01_订单为什么失败','一笔订单，遇到两个故障','演示设置：入口错指旧版本，数据库应用账号只读')
for x,title,lines,col in [(76,'提交订单',['用户请求进入系统'],'blue'),
                         (526,'订单入口',['仍指向旧版本'],'red'),
                         (976,'应用服务',['接收订单请求'],'blue'),
                         (1426,'数据库',['应用账号无法写入'],'red')]:
    c.node(x,385,418,220,title,lines,col)
for x in [494,944,1394]: c.arrow(x,494,x+32,494)
c.rect(76,716,1768,166,'palered')
c.text(110,749,'恢复入口后，继续恢复数据库写入。',40,'red',True)
c.text(112,815,'再更新应用连接，创建、查询并取消订单。',30)
done(c)

c=Card('02_谁负责哪一步','协调者分配任务，各服务按职责执行','运维、数据库、应用和订单验证，各有明确职责')
c.node(650,326,620,152,'协调智能体',['通过梧桐组织任务与收集结果'])
for x,title,lines in [(76,'运维智能体',['检查并恢复入口']), (686,'数据库智能体',['检查只读状态，获批后恢复写入']), (1296,'应用智能体',['检查应用状态，重建连接池'])]:
    c.node(x,574,548,182,title,lines)
c.line(350,528,1570,528,'blue'); c.line(960,478,960,528,'blue')
for x in [350,960,1570]: c.arrow(x,528,x,574)
c.rect(76,832,1768,106,'palegreen')
c.text(110,861,'订单验证：创建、查询、取消订单，检查恢复效果。',34,'green',True)
done(c)

c=Card('03_三步恢复怎么衔接','恢复入口，再恢复写入，最后更新连接','顺序来自本次运行中的三个修改任务')
for x,title,lines in [(76,'1  恢复正确入口',['运维智能体','让请求进入预期版本']),
                     (686,'2  获批后恢复写入',['数据库智能体','将应用账号的只读状态解除']),
                     (1296,'3  重建应用连接池',['应用智能体','让新连接采用恢复后的状态'])]:
    c.node(x,390,548,280,title,lines)
for x in [624,1234]: c.arrow(x,530,x+62,530)
c.rect(76,778,1768,138,'pale')
c.text(110,811,'修改后复查状态，再验证订单流程。',39,'blue',True)
c.text(112,870,'录制时，审批按钮由授权脚本点击。',27,'muted')
done(c)

c=Card('04_用订单确认恢复','恢复效果，要用订单请求确认','主案例  ·  最终30秒订单验证',kind='运行记录')
for x,title,lines in [(76,'创建订单',['POST /orders','状态码 200']),
                     (686,'查询订单',['GET /orders/[订单编号]','状态码 200']),
                     (1296,'取消订单',['POST /orders/[编号]/cancel','状态码 200'])]:
    c.node(x,348,548,232,title,lines,'green')
for x in [624,1234]: c.arrow(x,464,x+62,464,'green')
for x,big,label in [(76,'30 / 30','请求成功'),(686,'10','完整订单流程'),(1296,'0','失败和未知')]:
    c.rect(x,663,548,232,'palegreen')
    c.text(x+32,696,big,74,'green',True); c.text(x+34,801,label,34)
c.text(80,932,'全过程52条采样另见图卡08，其中16条当时结果未知。',27,'muted')
done(c)

c=Card('05_为什么不能直接重试','修改已完成，确认却没有回来','接管案例：数据库智能体修改完成后，工作进程退出')
c.node(76,380,825,270,'数据库与操作记录',['数据库写入已经恢复','共用操作记录：修改已完成'],'green')
c.node(1019,380,825,270,'协调侧',['主执行智能体在回复前退出','主执行智能体工具任务回执未确认'],'amber')
c.line(916,500,1003,500,'red',6)
c.text(76,744,'备用先读取操作记录，核对修改是否已完成。',43,'red',True)
c.text(78,821,'已经完成的修改，复用结果并跳过。',34)
done(c)

c=Card('06_备用怎样接着完成','备用复用已完成结果，继续后续步骤','接管案例  ·  读取记录，跳过已完成修改')
for x,title,lines in [(76,'主执行智能体退出',['修改已记入操作记录']), (526,'备用接管',['读取共用操作记录']),
                     (976,'确认已经应用',['复用已有执行结果']), (1426,'跳过这次修改',['继续后续恢复'])]:
    c.node(x,365,418,218,title,lines)
for x in [494,944,1394]: c.arrow(x,474,x+32,474)
c.rect(76,676,1768,182,'palegreen')
c.text(110,706,'继续重建连接池，并完成订单验证。',42,'green',True)
c.text(112,783,'最终窗口：30 / 30 请求成功，10 个完整流程。',33)
c.text(80,910,'修改工具调用1次；主执行智能体工具任务回执未确认。',29,'muted')
done(c)

c=Card('07_平台怎样支撑协作','平台的四步，分别解决什么问题','登记能力、找到执行者、传递任务、检查结果')
for x,title,lines in [(76,'1  注册',['登记角色与能力']), (526,'2  发现',['按技能找到执行者']),
                     (976,'3  互联',['发送任务，回传结果']), (1426,'4  访问',['用实际请求验证恢复'])]:
    c.node(x,386,418,240,title,lines)
for x in [494,944,1394]: c.arrow(x,506,x+32,506)
c.rect(76,744,1768,156,'pale')
c.text(110,780,'先找到合适的执行者，再发送任务，用订单检查结果。',35,'blue',True)
done(c)

c=Card('08_从订单异常到业务恢复','从订单异常，到业务恢复','全过程采样与最终30秒验证分别展示',kind='运行记录')
c.text(78,344,'覆盖故障注入和恢复的 52 条连续采样',35,bold=True)
c.rect(76,424,1768,146,'white')
for i,s in enumerate(samples):
    color='green' if s['outcome']=='success' else 'amber'
    c.rect(110+i*32,460,23,66,color,radius=5)
c.text(80,615,'36 条成功  ·  16 条当时结果未知',35)
c.text(80,679,'其中5条采于故障设置前。',28,'muted')
c.rect(76,773,1768,144,'palegreen')
c.text(110,802,'最终30秒订单验证',32,'green',True)
c.text(110,853,'30 / 30 请求成功  ·  10 个完整流程  ·  0 失败  ·  0 未知',35,bold=True)
done(c)

sources={
 '01_订单为什么失败': ['V3-f10/incident-state.json#/diagnosed_causes','V3-f10/incident-state.json#/planning_history'],
 '02_谁负责哪一步': ['V3-f10/incident-state.json#/tasks','V2-discovery/describe-A02.json','V2-discovery/describe-A03.json','V2-discovery/describe-A05.json','V2-discovery/describe-A06.json'],
 '03_三步恢复怎么衔接': ['V3-f10/incident-state.json#/tasks','V3-f10/incident-state.json#/planning_history','V3-f10/approvals.json'],
 '04_用订单确认恢复': ['V3-f10/incident-state.json#/result/order_observation'],
 '05_为什么不能直接重试': ['V4-takeover/primary-trace.jsonl','V4-takeover/result.json#/journal_resolution'],
 '06_备用怎样接着完成': ['V4-takeover/backup-trace.jsonl','V4-takeover/result.json','V4-takeover/takeover-timeline.json'],
 '07_平台怎样支撑协作': ['V1-registry/registry-observation.json','V2-discovery/capture.json','V3-f10/access/pairing-summary.json','V3-f10/incident-state.json#/result/order_observation'],
 '08_从订单异常到业务恢复': ['V3-f10/order-samples.json#/samples','V3-f10/incident-state.json#/result/order_observation']
}
(BUNDLE/'图卡来源.json').write_text(json.dumps({'capture_date':'2026-10-29','prepared_date':'2026-10-30',
 'kind':'editorial_diagrams_and_record_excerpts','new_experiment_performed':False,'platform_screenshots':False,
 'main_case':{'scenario':'F10','method':'M0','model_calls':evaluation['model_calls']},
 'cards':[{'name':n,'png':'图卡/'+n+'.png','svg':'图卡/'+n+'.svg','sources':sources[n]} for n in cards]},
 ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

sheet=Image.new('RGB',(1280,1440),'#E1EAF0')
for i,n in enumerate(cards):
    im=Image.open(OUT/(n+'.png')); im.thumbnail((640,360)); sheet.paste(im,((i%2)*640,(i//2)*360))
sheet.save(BUNDLE/'图卡总览.jpg',quality=93)
print(json.dumps({'cards':len(cards),'png_size':[3840,2160],'editable_svg':True},ensure_ascii=False))

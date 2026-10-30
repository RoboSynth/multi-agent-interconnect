"""将现有技术方案的部署检查表并入完整报告，输出独立合并试稿。"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import re

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from reportlab.platypus.tableofcontents import TableOfContents

import build_materials as layout
from material_content import TITLE, TEAM, REPORT, PLAN

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'技术方案合并试稿'
QA = ROOT/'原始目录'/'排版核验'/'合并试稿'
OUT.mkdir(exist_ok=True)
QA.mkdir(parents=True, exist_ok=True)
NAME = f'{TEAM}-智能体互联-{TITLE}-技术方案-合并试稿'


def page(title, blocks, chapter=False):
    return {'title':title, 'blocks':blocks, 'chapter':chapter}


def assemble():
    r = deepcopy(REPORT)
    result = [page('摘要',r[0]['blocks'])]
    chapters = {
        1:'一 作品概述',2:'二 需求分析',3:'三 智能体互联技术选型与方案设计',
        8:'四 项目实施',9:'五 应用成效',16:'六 总结与展望',
    }
    # 后续页面用具体节标题，避免反复出现同级的第三章、第五章。
    continuations = {
        4:'角色分工与任务流程',5:'智能体互联与资源工具调用',6:'操作记录与中断恢复',
        7:'检查顺序与业务验证',10:'官方平台画面',11:'本地代码与进程中断验证',
        12:'复合故障恢复验证',13:'数据库执行者中断后的备用接管',
        14:'历史访问查询与持续运行',15:'权限检查与开源贡献',
    }
    for i in range(1,17):
        if i == 8:
            # 原报告保留开源改造说明，部署细节从简版方案补入下一页。
            original = r[i]['blocks']
            blocks = original[:3]+[
                {'type':'h','text':'4.2 部署环境与职责分工'},
                original[4],original[7],
            ]
            result.append(page(chapters[i],blocks,True))
            result.append(page('部署步骤与代码版本',[
                {'type':'h','text':'4.3 六步部署与验证'},
                deepcopy(PLAN[3]['blocks'][0]),
                {'type':'h','text':'4.4 代码版本与实验对应'},
                original[5],original[6],
            ]))
            continue
        blocks = r[i]['blocks']
        if i == 9:
            for b in blocks:
                if b['type']=='h' and b['text']=='5.1 验证场景与证据':
                    b['text']='流程验证与证据对应'
            blocks.insert(0,{'type':'h','text':'5.1 平台接入与访问数据'})
        if i == 12:
            blocks.insert(1,{'type':'p','text':
                '本例同时设置两个故障：入口仍指向旧版本，数据库应用账号处于只读状态。'
                '运维执行者先将入口恢复到预期版本；协调者为恢复数据库写入申请审批，获批后由数据库执行者解除只读。'
                '复查确认数据库已经可写后，应用执行者重建连接池，使新连接采用恢复后的状态，最后执行业务订单验证。'})
        if i == 15:
            for b in blocks:
                if b['type']=='h' and b['text']=='官方开源仓库状态':
                    b['text']='5.7 官方开源仓库贡献'
        result.append(page(chapters.get(i,continuations.get(i,r[i]['title'])),blocks,i in chapters))

    # 证据编号集中列出；实现入口、版本与参考资料放在后一页。
    evidence_table = {
        'type':'table', 'headers':['编号','记录来源','支持内容'],
        'rows':r[17]['blocks'][0]['rows']+r[18]['blocks'][0]['rows'],
        'widths':[40,220,227],
    }
    result.append(page('七 附录',[
        {'type':'h','text':'7.1 验证记录索引'},evidence_table,
    ],True))
    result.append(page('实现入口、版本对应与参考资料',[
        {'type':'h','text':'7.2 主要实现入口'},r[17]['blocks'][2],
        {'type':'h','text':'7.3 代码版本与运行记录'},r[18]['blocks'][3],r[18]['blocks'][1],
        {'type':'h','text':'7.4 参考资料'},*r[17]['blocks'][4:7],
    ]))
    return result


class MergedDocument(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        title = getattr(flowable,'toc_title',None)
        if title:
            key = flowable.toc_key
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title,key,level=0)
            self.notify('TOCEntry',(0,title,self.page,key))


def editable_text(pages):
    text = [f'# {TITLE}','技术方案 合并试稿',f'团队编号：{TEAM}',
            '实验记录采集：2026年10月29日；文稿合并：2026年10月30日。']
    for p in pages:
        level = '## ' if p['chapter'] or p['title']=='摘要' else '### '
        text.append(level+p['title'])
        for b in p['blocks']:
            kind=b['type']
            if kind=='h':text.append(('### ' if p['chapter'] else '#### ')+b['text'])
            elif kind in ['p','note']:text.append(b['text'])
            elif kind=='table':
                text.append('| '+' | '.join(b['headers'])+' |\n| '+
                    ' | '.join(['---']*len(b['headers']))+' |\n'+
                    '\n'.join('| '+' | '.join(map(str,row))+' |' for row in b['rows']))
            elif kind=='code':text.append('```python\n'+b['text']+'\n```\n\n'+b['caption'])
            elif kind=='image':text.append(f'![{b["caption"]}](../{b["path"]})\n\n'+b['caption'])
            else:text.append(b['caption'])
    return '\n\n'.join(text)+'\n'


def main():
    pages = assemble()
    pdf=OUT/(NAME+'.pdf')
    md=OUT/(NAME+'-可编辑稿.md')
    doc=MergedDocument(str(pdf),pagesize=layout.A4,rightMargin=52,leftMargin=52,
        topMargin=45,bottomMargin=48,title=TITLE+' 技术方案',author='参赛团队',
        subject='智能体互联 技术方案与技术报告合并试稿',pageCompression=1)
    story=[layout.para(TITLE,'title'),layout.para('技术方案','subtitle'),
           layout.para('技术报告合并试稿','subtitle'),
           layout.para(TEAM+'  |  采集：2026年10月29日  |  合并：2026年10月30日','meta'),
           layout.para('摘要','heading')]
    story.extend(layout.blocks_to_flow(pages[0]['blocks']))
    story.extend([PageBreak(),layout.para('目录','heading')])
    toc=TableOfContents()
    toc.levelStyles=[ParagraphStyle('MergedContents',fontName='UI',fontSize=11,leading=25,
        leftIndent=0,firstLineIndent=0,textColor=colors.black,wordWrap='CJK',spaceBefore=8)]
    story.extend([toc,PageBreak()])
    for index,p in enumerate(pages[1:],1):
        if index>1:story.append(PageBreak())
        heading=layout.para(p['title'],'heading')
        if p['chapter']:
            heading.toc_title=p['title'];heading.toc_key='chapter-'+str(index)
        story.append(heading)
        story.extend(layout.blocks_to_flow(p['blocks']))
    doc.multiBuild(story,onFirstPage=layout.footer,onLaterPages=layout.footer)
    md.write_text(editable_text(pages),encoding='utf-8')
    (QA/'merged-content.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    reader=PdfReader(pdf)
    extracted='\n'.join(p.extract_text() or '' for p in reader.pages)
    (QA/'提取文本.txt').write_text(extracted,encoding='utf-8')
    required=['四 项目实施','4.3 六步部署与验证','5.3 F10','52','16','OutcomeUnconfirmed','143','146','5.7 官方开源仓库贡献']
    missing=[s for s in required if s not in extracted]
    assert not missing,missing
    assert pdf.stat().st_size<10_000_000
    report={'pdf':str(pdf),'editable':str(md),'pages':len(reader.pages),
        'expected_pages':len(pages)+1,'bytes':pdf.stat().st_size,
        'chapters':[p['title'] for p in pages if p['chapter']],
        'preserved_result_ranges':True,'visual_review':'pending'}
    (QA/'合并核对.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':main()

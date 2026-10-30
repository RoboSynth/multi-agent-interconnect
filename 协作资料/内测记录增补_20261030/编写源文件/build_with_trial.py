"""按用户提供的24页佐证PDF版式，增补E16首次使用测试记录。"""
from __future__ import annotations

import copy
from io import BytesIO
import json
from pathlib import Path
import re
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import Link
from pypdf.generic import ContentStream, DecodedStreamObject, FloatObject, NameObject
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageBreak,
                               PageTemplate, Paragraph, Spacer, Table, TableStyle)
import reportlab.platypus.paragraph as paragraph_engine
import reportlab.lib.textsplit as textsplit_engine

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'原始记录/用户提供的24页佐证材料.pdf'
OUTPUT=ROOT/'PDF/AIC-2026-23708513-智能体互联-联枢多智能体协同运维系统-佐证材料-内测增补版.pdf'
QA=ROOT/'核对记录'
WIDTH,HEIGHT=595.303937,841.889764
LEFT,RIGHT=85.15,510.30
BODY_WIDTH=RIGHT-LEFT

pdfmetrics.registerFont(TTFont('Song','C:/Windows/Fonts/simsun.ttc',subfontIndex=0))
pdfmetrics.registerFont(TTFont('Hei','C:/Windows/Fonts/simhei.ttf'))
pdfmetrics.registerFont(TTFont('Times','C:/Windows/Fonts/times.ttf'))
pdfmetrics.registerFontFamily('Song',normal='Song',bold='Song',italic='Song',boldItalic='Song')

# 沿用扩充材料中的中文换行规则，避免逗号落在行首、引号留在行末。
NO_START='，。；：！？、）》】」』”’％%…,.!?;:'
NO_END='（《【「『“‘('
textsplit_engine.ALL_CANNOT_START+=NO_START
paragraph_engine.ALL_CANNOT_START+=NO_START


def chinese_word_split(word,maxWidths,fontName,fontSize,encoding='utf8'):
    encoded=not isinstance(word,str)
    value=word.decode(encoding) if encoded else word
    widths=textsplit_engine.getCharWidths(value,fontName,fontSize)
    limits=list(maxWidths) if isinstance(maxWidths,(list,tuple)) else [maxWidths]
    prefix=[0.0]
    for width in widths:prefix.append(prefix[-1]+width)
    tokens={}
    for match in re.finditer(r'\d{1,3}(?:,\d{3})+(?:\.\d+)?|[A-Za-z0-9_./:+#-]+',value):
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
            if token and token[0]<end<token[1] and token[2]<=limit and token[0]>start:end=token[0]
            while end>start+1 and value[end-1] in NO_END:end-=1
        line=value[start:end].strip()
        result.append([limit-pdfmetrics.stringWidth(line,fontName,fontSize),line.encode(encoding) if encoded else line])
        start=end
    return result


paragraph_engine.wordSplit=chinese_word_split

ST={
 'body':ParagraphStyle('body',fontName='Song',fontSize=12,leading=16.65,firstLineIndent=24,
                       alignment=TA_JUSTIFY,wordWrap='CJK',spaceAfter=9,allowWidows=0,allowOrphans=0),
 'summary':ParagraphStyle('summary',fontName='Song',fontSize=12,leading=24.95,firstLineIndent=24,
                         alignment=TA_JUSTIFY,wordWrap='CJK',spaceAfter=13,allowWidows=0,allowOrphans=0),
 'h1':ParagraphStyle('h1',fontName='Song',fontSize=16,leading=24,spaceAfter=12,keepWithNext=True),
 'h2':ParagraphStyle('h2',fontName='Song',fontSize=14,leading=21,spaceBefore=9,spaceAfter=9,keepWithNext=True),
 'caption':ParagraphStyle('caption',fontName='Song',fontSize=10.5,leading=14,alignment=TA_CENTER,spaceBefore=5,spaceAfter=5,keepWithNext=True),
 'cell':ParagraphStyle('cell',fontName='Song',fontSize=10.5,leading=12.85,wordWrap='CJK',alignment=TA_LEFT),
 'th':ParagraphStyle('th',fontName='Hei',fontSize=10.5,leading=12.85,wordWrap='CJK',alignment=TA_CENTER,textColor=colors.white),
}


def mixed(value):
    text=str(value)
    result=''.join('<font name="Times">'+escape(part)+'</font>' if re.fullmatch(r'[\x20-\x7e]+',part) else escape(part)
                   for part in re.split(r'([\x20-\x7e]+)',text) if part).replace('\n','<br/>')
    if text=='https://github.com/RoboSynth/multi-agent-interconnect':
        result='<font name="Times">https://github.com/RoboSynth/<br/>multi-agent-interconnect</font>'
    return '<link href="'+escape(text,{'"':'&quot;'})+'">'+result+'</link>' if text.startswith('https://') else result


class BoldParagraph(Paragraph):
    def draw(self):
        self.canv.saveState()
        self.canv.setLineWidth(self.style.fontSize/30)
        self.canv._code.append('BT 2 Tr ET')
        super().draw()
        self.canv.restoreState()


def para(text,kind='body'):
    return (BoldParagraph if kind in {'h1','h2'} else Paragraph)(mixed(text),ST[kind])


def table(block,with_header=True):
    widths=[v/sum(block['widths'])*BODY_WIDTH for v in block['widths']]
    rows=[]
    if with_header:rows.append([para(x,'th') for x in block['headers']])
    rows += [[para(x,'cell') for x in row] for row in block['rows']]
    tab=Table(rows,colWidths=widths,repeatRows=1 if with_header else 0,hAlign='LEFT',spaceAfter=9)
    commands=[('GRID',(0,0),(-1,-1),.5,colors.HexColor('#8A9BAE')),
              ('LINEABOVE',(0,0),(-1,0),1,colors.HexColor('#1F3A5F')),
              ('LINEBELOW',(0,-1),(-1,-1),1,colors.HexColor('#1F3A5F')),
              ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
              ('LEFTPADDING',(0,0),(-1,-1),3.5),('RIGHTPADDING',(0,0),(-1,-1),3.5),
              ('TOPPADDING',(0,0),(-1,-1),3.5),('BOTTOMPADDING',(0,0),(-1,-1),3.5)]
    if with_header:commands.append(('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1F3A5F')))
    for i in range(1 if with_header else 0,len(rows)):
        if (i-(1 if with_header else 0))%2:commands.append(('BACKGROUND',(0,i),(-1,i),colors.HexColor('#EEF2F6')))
    tab.setStyle(TableStyle(commands))
    return tab


def position(block):
    for operands,op in block:
        if op in {b'Td',b'TD'}:return float(operands[0]),float(operands[1])
        if op==b'Tm':return float(operands[4]),float(operands[5])
    return None


def edit_text_blocks(page,reader,remove=None,shift=None):
    """仅删改指定坐标内的文字对象，保留原表格、图像及其他文字。"""
    stream=ContentStream(page.get_contents(),reader)
    operations=stream.operations
    result=[];i=0;removed=shifted=0
    while i<len(operations):
        if operations[i][1]!=b'BT':result.append(operations[i]);i+=1;continue
        end=i+1
        while end<len(operations) and operations[end][1]!=b'ET':end+=1
        block=operations[i:end+1]
        point=position(block)
        if point and remove and remove(*point):
            removed+=1;i=end+1;continue
        if point and shift and (delta:=shift(*point)):
            seen=False;changed=[]
            for operands,op in block:
                operands=list(operands)
                if op in {b'Td',b'TD'} and not seen:
                    operands[1]=FloatObject(float(operands[1])+delta);seen=True
                elif op==b'Tm':
                    operands[5]=FloatObject(float(operands[5])+delta);seen=True
                changed.append((operands,op))
            block=changed;shifted+=1
        result.extend(block);i=end+1
    stream.operations=result
    data=DecodedStreamObject();data.set_data(stream.get_data())
    if isinstance(reader,PdfWriter):page.replace_contents(data)
    else:page[NameObject('/Contents')]=data
    return {'removed_blocks':removed,'shifted_blocks':shifted}


def overlay(page,painter):
    buffer=BytesIO();c=canvas.Canvas(buffer,pagesize=(WIDTH,HEIGHT))
    painter(c);c.save();buffer.seek(0)
    page.merge_page(PdfReader(buffer).pages[0])


def draw_mixed(c,text,x,y,size=10.5,center=False):
    segments=[(p,'Times' if re.fullmatch(r'[\x20-\x7e]+',p) else 'Song') for p in re.split(r'([\x20-\x7e]+)',text) if p]
    width=sum(pdfmetrics.stringWidth(p,font,size) for p,font in segments)
    if center:x-=width/2
    for part,font in segments:
        c.setFont(font,size);c.drawString(x,y,part);x+=pdfmetrics.stringWidth(part,font,size)


def draw_at_top(c,p,x,top,width=BODY_WIDTH):
    _,height=p.wrap(width,1000)
    p.drawOn(c,x,top-height)
    return top-height-p.style.spaceAfter


def header_fragment(reader):
    header=copy.copy(reader.pages[1])
    header.pop(NameObject('/Annots'),None)
    edit_text_blocks(header,reader,remove=lambda x,y:y<760)
    original=header.get_contents().get_data()
    content=DecodedStreamObject()
    content.set_data(b'q\n0 765 595.304 65 re W n\n'+original+b'\nQ')
    header[NameObject('/Contents')]=content
    return header


class AnnexDocument(BaseDocTemplate):
    def __init__(self,path,source_pages):
        super().__init__(str(path),pagesize=(WIDTH,HEIGHT),leftMargin=LEFT,rightMargin=WIDTH-RIGHT,
                         topMargin=92,bottomMargin=83,title='首次使用测试与反馈')
        self.source_pages=source_pages
        frame=Frame(LEFT,83,BODY_WIDTH,HEIGHT-92-83,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        self.addPageTemplates(PageTemplate(id='annex',frames=frame,onPage=self.paint))
    def paint(self,c,doc):
        c.setFont('Times',12)
        c.drawCentredString(309.75,51.939,str(self.source_pages-1+doc.page))


def create_annex(data,source_pages):
    path=QA/'仅内测增补页.pdf'
    story=[]
    for n,page in enumerate(data['pages']):
        if n:story.append(PageBreak())
        if page.get('title'):story.append(para(page['title'],'h1'))
        for block in page['blocks']:
            if block['type']=='h':story.append(para(block['text'],'h2'))
            elif block['type']=='p':story.append(para(block['text']))
            elif block['type']=='table':story.extend([para(block['caption'],'caption'),table(block)])
    AnnexDocument(path,source_pages).build(story)
    return path


def main():
    data=json.loads((ROOT/'编写源文件/内测增补.json').read_text(encoding='utf-8'))
    reader=PdfReader(SOURCE)
    assert len(reader.pages)==24
    header=header_fragment(reader)
    writer=PdfWriter();writer.clone_document_from_reader(reader)
    edits={}
    edits['cover']=edit_text_blocks(writer.pages[0],writer,remove=lambda x,y:170<x<450 and 318<y<343)
    assert edits['cover']['removed_blocks']>0

    # 概要重新排入原正文区域，原有运行结论与新增内测结果分别列出。
    edits['summary']=edit_text_blocks(writer.pages[2],writer,remove=lambda x,y:80<x<530 and 500<y<710)
    overview='本册汇集联枢多智能体协同运维系统的真实性、创新性与应用成效佐证，共16组证据（E01-E16），取自实际运行产生的平台响应、后台截图、事件日志、测试记录及项目讨论区的首次使用反馈。主要结论：7个智能体在梧桐平台全部审核通过并可被ADP发现；协调智能体平台累计调用32,620次（10月29日21:08官方查询页）；云端复合故障F10与执行者中断接管两例均在最终窗口完成30/30次请求、10个完整订单流程；向官方开源仓库提交2个PR、4个Issue，其中1个Issue获社区回复并转平台小组处理。本队暂无专利、软件著作权、论文、合作意向书或试点证明，本册不以其他材料替代。失败与未知记录按原值保留。'
    trial='新增E16记录10月30日按首次使用者路径开展的内测：完成配置准备与校验，部署入口5项、工作台3项选定测试全部通过，并检查未连接状态下的页面和接口表现。讨论区同时记录解释器选择、Docker环境检查和界面排障说明三类改进建议，详见附录C。'
    def summary(c):
        top=707.289
        for text in [overview,trial]:top=draw_at_top(c,para(text,'summary'),LEFT,top)
    overlay(writer.pages[2],summary)

    # 表1工程质量对照保留原格线与底色，接入新增证据。
    edits['score_table']=edit_text_blocks(writer.pages[3],writer,remove=lambda x,y:318.9<=x<510.3 and 455<y<480)
    def score(c):
        draw_mixed(c,'E06-E08、E14、E16',322.5,472.439)
        draw_mixed(c,'及问题记录',322.5,459.589)
        draw_mixed(c,'五、六',478.4,472.439,center=True)
        draw_mixed(c,'附录C',478.4,459.589,center=True)
    overlay(writer.pages[3],score)

    # 时间说明保持原三行区域，并说明新增E16的采集批次。
    edits['time_note']=edit_text_blocks(writer.pages[3],writer,remove=lambda x,y:80<x<530 and 235<y<281)
    def time_note(c):
        text='E01至E15沿用技术方案中的证据编号，采集于10月29日，涵盖源码、本地验证、平台注册、云端案例、安全检查与开源贡献。新增E16为10月30日首次使用内测，详见附录C。本文时间均为北京时间。'
        draw_at_top(c,para(text),LEFT,286.739)
    overlay(writer.pages[3],time_note)

    # 在续表2追加一行，原文字对象向下平移，不遮盖或重复原文。
    extra={'widths':[34,110.5,93.6,187.1],'rows':[['E16','首次使用测试与反馈','10月30日','配置校验与8项选定测试通过；完成未连接工作台交互检查。']]}
    row=table(extra,False)
    _,row_height=row.wrap(BODY_WIDTH,1000)
    edits['evidence_table']=edit_text_blocks(writer.pages[4],writer,shift=lambda x,y:-row_height if 80<x<530 and 280<y<530 else 0)
    def evidence_row(c):row.drawOn(c,85.10,HEIGHT-300.2008-row_height)
    overlay(writer.pages[4],evidence_row)

    # 附录B补项目仓库地址，开源时间按团队安排写为比赛结束后。
    repository_row=table({'widths':[233.776,191.38025],
        'rows':[['https://github.com/RoboSynth/multi-agent-interconnect','联枢项目源码仓库；比赛结束后公开。']]},False)
    _,repository_height=repository_row.wrap(BODY_WIDTH,1000)
    overlay(writer.pages[23],lambda c:repository_row.drawOn(c,85.10,HEIGHT-553.4007638-repository_height))

    # 目录只增加一个总入口；原有24页的页码和跳转位置保持。
    def toc(c):
        label='附录C 首次使用测试与反馈（E16）';y=114.639
        c.setFont('Hei',12);c.drawString(LEFT,y,label)
        end=LEFT+pdfmetrics.stringWidth(label,'Hei',12)
        page_number='24';c.setFont('Times',12)
        right_start=RIGHT-pdfmetrics.stringWidth(page_number,'Times',12)
        x=end+3
        while x<right_start-4:c.drawString(x,y,'.');x+=3.1
        c.drawRightString(RIGHT,y,page_number)
    overlay(writer.pages[1],toc)

    annex_path=create_annex(data,len(reader.pages))
    annex=PdfReader(annex_path)
    for page in annex.pages:
        page.merge_page(header)
        writer.add_page(page)
    writer.add_outline_item('附录C 首次使用测试与反馈（E16）',24)
    annotation=Link(rect=(LEFT,110,RIGHT,128),target_page_index=24)
    writer.add_annotation(1,annotation)
    snapshot=(ROOT/'原始记录/讨论区记录_20261030.json').read_bytes()
    writer.add_attachment('E16-内测讨论原始记录.json',snapshot)
    writer.add_metadata({'/Title':'联枢多智能体协同运维系统 佐证材料','/Author':'参赛团队','/Subject':'含E16首次使用测试与反馈'})
    OUTPUT.parent.mkdir(exist_ok=True)
    with OUTPUT.open('wb') as output:writer.write(output)
    result={'source_pages':24,'added_pages':len(annex.pages),'total_pages':len(writer.pages),'evidence_id':'E16',
            'source_pdf':SOURCE.relative_to(ROOT).as_posix(),'output_pdf':OUTPUT.relative_to(ROOT).as_posix(),
            'evidence_row_height':row_height,'edits':edits,'visual_review':'pending'}
    (QA/'生成记录.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 附录C 首次使用测试与反馈（E16）','']
    for page in data['pages']:
        for b in page['blocks']:
            if b['type'] in {'h','p'}:lines += [('## ' if b['type']=='h' else '')+b['text'],'']
            else:
                lines += [b['caption'],'','| '+' | '.join(b['headers'])+' |','| '+' | '.join(['---']*len(b['headers']))+' |']
                lines += ['| '+' | '.join(row)+' |' for row in b['rows']];lines.append('')
    (ROOT/'内测增补正文.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()

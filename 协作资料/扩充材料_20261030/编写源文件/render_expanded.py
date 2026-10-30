"""渲染扩充稿并生成逐页核对总览。"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
import os
import re
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('kinds',nargs='*')
parser.add_argument('--pages',help='只重渲染指定页，例如9或12-27')
parser.add_argument('--pdftoppm',default=os.getenv('MATERIAL_PDFTOPPM') or shutil.which('pdftoppm'))
args=parser.parse_args()
POP=args.pdftoppm
if not POP:raise SystemExit('请将Poppler加入PATH，或通过--pdftoppm指定pdftoppm路径。')
items=json.loads((ROOT/'核对记录'/'PDF生成记录.json').read_text(encoding='utf-8'))


def render(item):
    directory=ROOT/'核对记录'/'页面图'/item['kind']
    directory.mkdir(parents=True,exist_ok=True)
    selected=[]
    if args.pages:
        for part in args.pages.split(','):
            if '-' in part:
                a,b=map(int,part.split('-'));selected.extend(range(a,b+1))
            else:selected.append(int(part))
        assert all(1<=page<=item['pages'] for page in selected)
        for page in selected:
            subprocess.run([POP,'-r','110','-f',str(page),'-l',str(page),'-singlefile','-png',str(ROOT/item['pdf']),str(directory/f'page-{page:02}')],capture_output=True,check=True)
        for old in directory.glob('page-*.png'):
            if re.fullmatch(r'page-\d+\.png',old.name) and int(old.stem.split('-')[-1])>item['pages']:old.unlink()
    else:
        for old in directory.glob('page-*.png'):
            if re.fullmatch(r'page-\d+\.png',old.name):old.unlink()
        subprocess.run([POP,'-r','110','-png',str(ROOT/item['pdf']),str(directory/'page')],capture_output=True,check=True)
    files=sorted(directory.glob('page-*.png'))
    assert len(files)==item['pages']
    font=ImageFont.truetype(os.getenv('MATERIAL_UI_FONT','C:/Windows/Fonts/msyh.ttc'),20)
    for start in range(0,len(files),4):
        if selected and start//4 not in {(page-1)//4 for page in selected}:continue
        canvas=Image.new('RGB',(1100,1640),'#DFE5E9');draw=ImageDraw.Draw(canvas)
        for j,path in enumerate(files[start:start+4]):
            with Image.open(path) as source:image=source.convert('RGB')
            image.thumbnail((525,760))
            x=(j%2)*550+12;y=(j//2)*820+42
            draw.text((x,y-32),item['kind']+' '+path.stem,font=font,fill='#18354A')
            canvas.paste(image,(x,y))
        canvas.save(directory/f'overview-{start//4+1:02}.jpg',quality=90)
    return {'kind':item['kind'],'pages':len(files),'directory':str(directory)}


chosen=[x for x in items if not args.kinds or x['key'] in args.kinds or x['kind'] in args.kinds]
with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(render,chosen))
(ROOT/'核对记录'/'页面渲染.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))

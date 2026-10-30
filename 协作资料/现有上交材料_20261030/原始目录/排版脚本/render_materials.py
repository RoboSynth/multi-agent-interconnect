from pathlib import Path
import json, subprocess, concurrent.futures, os, shutil, re, sys
from PIL import Image, ImageOps, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[2]
QA=ROOT/'原始目录'/'排版核验'
poppler=os.getenv('MATERIAL_PDFTOPPM') or shutil.which('pdftoppm')
if not poppler:raise RuntimeError('Install Poppler or set MATERIAL_PDFTOPPM to its pdftoppm executable.')
POP=Path(poppler)
build=json.loads((QA/'document-build.json').read_text(encoding='utf-8'))

def render(item):
    names={'技术方案':'plan','技术报告':'report','佐证材料':'evidence'}
    d=QA/(names[item['kind']]+'-pages');d.mkdir(exist_ok=True)
    # 页数变化时Poppler会改变序号补零宽度，清除本脚本上次生成的图片。
    assert d.resolve().parent == QA.resolve()
    for old in d.iterdir():
        if old.is_file() and re.fullmatch(r'(?:page-\d+\.png|overview-\d+\.jpg)', old.name):
            old.unlink()
    p=subprocess.run([str(POP),'-r','110','-png',str(ROOT/item['path']),str(d/'page')],capture_output=True)
    if p.returncode:raise RuntimeError(p.stderr.decode('utf-8','replace'))
    files=sorted(d.glob('page-*.png'))
    assert len(files)==item['pages'],(len(files),item['pages'])
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',20)
    for start in range(0,len(files),4):
        subset=files[start:start+4];canvas=Image.new('RGB',(1000,1500),'#d9dfe4');draw=ImageDraw.Draw(canvas)
        for j,f in enumerate(subset):
            im=Image.open(f).convert('RGB'); im.thumbnail((480,700))
            x=(j%2)*500+10;y=(j//2)*750+38
            draw.text((x,y-30),item['kind']+' '+f.stem,font=font,fill='black');canvas.paste(im,(x,y))
        canvas.save(d/f'overview-{start//4+1}.jpg',quality=90)
    return {'kind':item['kind'],'pages':len(files),'directory':str(d.relative_to(ROOT))}

selected=set(sys.argv[1:])
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    rendered=list(pool.map(render,[x for x in build['files'] if not selected or x['kind'] in selected]))
index=QA/'render-index.json'
previous=json.loads(index.read_text(encoding='utf-8')) if index.exists() else []
by_kind={x['kind']:x for x in previous+rendered}
results=[by_kind[x['kind']] for x in build['files'] if x['kind'] in by_kind]
(QA/'render-index.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(rendered,ensure_ascii=False,indent=2))

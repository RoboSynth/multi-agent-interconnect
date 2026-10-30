from pathlib import Path
from pypdf import PdfReader
import json

ROOT=Path(__file__).resolve().parents[1]
NO_START='，。；：！？、）》】」』”’％'
NO_END='（《【「『“‘'
issues=[]
for path in (ROOT/'PDF').glob('*.pdf'):
    for number,page in enumerate(PdfReader(path).pages,1):
        for line in (page.extract_text() or '').splitlines():
            text=line.strip()
            if text and (text[0] in NO_START or text[-1] in NO_END):
                issues.append({'file':path.name,'page':number,'text':text})
(ROOT/'核对记录'/'中文行首行尾核对.json').write_text(json.dumps(issues,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(issues,ensure_ascii=False,indent=2))

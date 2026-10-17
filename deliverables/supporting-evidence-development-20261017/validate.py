"""Render exact PDF bytes and verify bounded text/data/metadata checks locally."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
from PIL import Image,ImageDraw

HERE=Path(__file__).resolve().parent
PDF=HERE/'supporting-evidence-development.pdf'

def executable(name):
    found=shutil.which(name)
    if found:return found
    p=Path('D:/16080/CodexData/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin')/(name+'.exe')
    if not p.exists():raise FileNotFoundError('Existing local renderer unavailable: '+name)
    return str(p)

def run(name,*args):
    return subprocess.run([executable(name),*map(str,args)],check=True,capture_output=True).stdout.decode('utf-8','replace')

def main():
    preview=HERE/'previews';preview.mkdir(exist_ok=True)
    info=run('pdfinfo',PDF)
    fonts=run('pdffonts',PDF)
    run('pdftotext','-enc','UTF-8','-layout',PDF,HERE/'extracted.txt')
    run('pdftoppm','-r','125','-png',PDF,preview/'page')
    text=(HERE/'extracted.txt').read_text(encoding='utf-8')
    pngs=sorted(preview.glob('page-*.png'))
    for first in range(0,len(pngs),6):
        sheet=Image.new('RGB',(912,908),'#e7ecee');draw=ImageDraw.Draw(sheet)
        for i,file in enumerate(pngs[first:first+6]):
            im=Image.open(file).convert('RGB');im.thumbnail((286,414))
            x=(i%3)*304+9;y=(i//3)*454+26
            sheet.paste(im,(x,y));draw.text((x,y-18),f'PAGE {first+i+1:02d}',fill='#173b50')
        sheet.save(preview/f'contact-{first//6+1:02d}.png')
    data=json.loads((HERE/'data.json').read_text(encoding='utf-8'))
    content=json.loads((HERE/'content.json').read_text(encoding='utf-8'))
    build=json.loads((HERE/'build-info.json').read_text(encoding='utf-8'))
    combined=text+'\n'+info+'\n'+json.dumps(content,ensure_ascii=False)+'\n'+json.dumps(data,ensure_ascii=False)
    patterns={
        'registered_namespace':r'(?i)\bBUPT\b',
        'complete_AIC':r'1\.2\.156\.\d+(?:\.[A-Z0-9]+){4,}',
        'known_accounts':r'(?i)Binah-Dev|RoboSynth',
        'absolute_windows_path':r'(?i)\b[A-Z]:[\\/]',
        'private_key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'authenticated_URI':r'(?i)(?:postgres(?:ql)?|amqps?)://[^\s/@:]+:[^\s/@]+@'
    }
    hits={k:len(re.findall(v,combined)) for k,v in patterns.items()}
    pages=[p for p in text.split('\f') if p.strip()]
    fontrows=[x for x in fonts.splitlines()[2:] if x.strip()]
    a=data['closed']['E1'];m=data['closed']['historical_comparison']
    checks={
        '12_pages_rendered':len(pages)==len(pngs)==build['page_count']==12,
        'cutoff_matches':content['cutoff_utc']==data['cutoff_utc']=='2026-10-17T12:50:41.317Z',
        'development_label_present':'非最终提交版' in text,
        'no_frame_overflow':not build['frame_overflow'] and min(build['page_body_min_y'])>=build['frame_bottom'],
        'fonts_embedded':bool(fontrows) and all('yes' in x for x in fontrows),
        'bounded_identity_pattern_zero':not any(hits.values()),
        'no_replacement_glyph':'\ufffd' not in text,
        'no_embedded_files_or_interactive_actions':all(x not in PDF.read_bytes() for x in [b'/EmbeddedFiles',b'/JavaScript',b'/Annots']),
        'PDF_below_10MiB':PDF.stat().st_size<10*1024*1024,
        '25_sources_indexed':len(data['sources'])==25 and all(s['id'] in text for s in data['sources']),
        'access_scope_separate':data['access']['native_start_tasks']==33 and data['access']['actual_access_records']==66 and data['amp']['log_types']['access']==84 and '不同' in text,
        'AMP_sum_exact':sum(data['amp']['log_types'].values())==data['amp']['unique_records']==1051,
        'E1_model_zero_and_segmented':a['actual_model_calls']==a['actual_model_tokens']==0 and a['uninterrupted_cases']==17 and a['controller_continuation_cases']==1,
        'old_M1_and_version_combination':m['historical_M1_observation_only'] and m['combined_versions'] and '九失败' in text,
        'full_tool_failure_preserved':not data['closed']['full_tool_M1_pilot']['initial_completed'][1] and 'unknown' in text,
        'backend_and_feedback_missing':data['unavailable']['platform_backend_visit_curve'] and data['unavailable']['human_interviews'] and data['unavailable']['public_issue_PR_links'],
        'screenshot_source_byte_match':hashlib.sha256((HERE/data['assets'][0]['relative_path']).read_bytes()).hexdigest()==data['assets'][0]['sha256']
    }
    result={'schema_version':'t93-validation/1.0','created_at':datetime.now(timezone.utc).isoformat(),'artifact_kind':'anonymous supporting-evidence development draft, not final submission','pdf':PDF.name,'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'pdf_bytes':PDF.stat().st_size,'page_count':len(pages),'rendered_pages':[str(x.relative_to(HERE)).replace('\\','/') for x in pngs],'checks':checks,'automatic_checks_passed':all(checks.values()),'pattern_hits':hits,'anonymity_scope':'PDF extracted text, PDF metadata, content/data text; embedded screenshot requires actual visual review, not OCR','pdfinfo':info,'pdffonts':fonts,'visual_review':{'status':'pending','pages_reviewed':[]},'resource_model_external_calls':False,'source_fingerprints':build['source_sha256'],'final_submission_ready':False}
    (HERE/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'automatic_checks_passed':result['automatic_checks_passed'],'page_count':len(pages),'checks':checks}))
    return 0 if result['automatic_checks_passed'] else 1

if __name__=='__main__':raise SystemExit(main())

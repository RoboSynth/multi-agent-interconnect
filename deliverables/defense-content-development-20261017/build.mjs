// Artifact Tool source entry. NOT EXECUTED: the supplied authoring runtime is unavailable.
// Syntax checks do not validate this API integration, layout, fonts or PowerPoint behavior.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const workspaceDir=path.dirname(fileURLToPath(import.meta.url));
const {SKILL_DIR,RUNTIME_PYTHON}=process.env;
if(!SKILL_DIR || !RUNTIME_PYTHON) throw new Error('Use load_workspace_dependencies first; set supplied SKILL_DIR and RUNTIME_PYTHON. No substitute runtime.');
let api;
try { api=await import('@oai/artifact-tool'); }
catch { throw new Error('Official @oai/artifact-tool runtime missing. No PPTX/PDF generated.'); }
const {Presentation,PresentationFile}=api;
const {applyPresentationChartFont,finalizePresentation}=await import(pathToFileURL(path.join(SKILL_DIR,'container_tools/artifact_tool_utils.mjs')).href);
const content=JSON.parse(await fs.readFile(path.join(workspaceDir,'content.json'),'utf8'));
const evidence=JSON.parse(await fs.readFile(path.join(workspaceDir,'evidence.json'),'utf8'));
const charts=JSON.parse(await fs.readFile(path.join(workspaceDir,'chart-data.json'),'utf8')).charts;
const C={paper:'#F7F6F2',ink:'#142734',muted:'#52636B',jade:'#087F8C',rust:'#C96A3A',line:'#CDD4D4',white:'#FFFFFF'};
const FONT='Microsoft YaHei';
const p=Presentation.create({slideSize:content.slide_size});
const box=(s,text,x,y,w,h,size=26,color=C.ink,bold=false)=>{
  const b=s.shapes.add({geometry:'textbox',name:`text-${s.id??''}-${x}-${y}`,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  b.text=text;b.text.style={typeface:FONT,fontSize:size,color,bold,autoFit:'none'};return b;
};
function table(s,def,x=80,y=238,w=1120,h=330){
  const values=[def.headers,...def.rows];
  const t=s.tables.add({rows:values.length,columns:def.headers.length,left:x,top:y,width:w,height:h,columnWidths:def.widths,values});
  t.borders.assign({style:'solid',fill:C.line,width:1});
  for(let r=0;r<values.length;r++) for(let c=0;c<def.headers.length;c++){
    const cell=t.getCell(r,c);cell.fill=r===0?C.ink:C.paper;
    cell.text.style={typeface:FONT,fontSize:r===0?25:23,color:r===0?C.white:C.ink,bold:r===0,autoFit:'none'};
  }
}
function dataChart(s,id,frame,{labels=true,legend=true}={}){
  const d=charts[id];
  const ch=s.charts.add('bar',{position:frame,categories:d.categories,series:d.series.map((a,i)=>({...a,fill:[C.jade,C.rust,'#8B9DA5'][i%3]})),barOptions:{direction:'column',grouping:'clustered'},hasLegend:legend&&d.series.length>1,legend:{position:'bottom',textStyle:{typeface:FONT,fontSize:17}},xAxis:{textStyle:{typeface:FONT,fontSize:18},line:{fill:C.line,width:1}},yAxis:{min:0,numberFormatCode:id.includes('recovery')?'0.0':'0',textStyle:{typeface:FONT,fontSize:17},majorGridlines:{fill:C.line,width:1}},dataLabels:{showValue:labels,position:'outEnd',textStyle:{typeface:FONT,fontSize:17,fill:C.ink}},chartFill:'none',plotAreaFill:'none'});
  applyPresentationChartFont(ch,{fontFamily:FONT});return ch;
}
function stepDiagram(s,items){
  const gap=32,w=256,x0=80,y=260;
  items.forEach((d,i)=>{const x=x0+i*(w+gap);box(s,String(i+1).padStart(2,'0'),x,y,w,58,48,C.jade,true);box(s,d.label,x,y+76,w,42,29,C.ink,true);box(s,d.text,x,y+132,w,108,25);});
}
for(const d of content.slides){
  const s=p.slides.add();s.background.fill=C.paper;
  box(s,d.title,80,d.layout==='cover'?130:52,1120,d.layout==='cover'?180:72,d.layout==='cover'?64:44,C.ink,true);
  if(d.layout==='cover'){
    box(s,d.statement,80,360,1050,72,34,C.jade);
    box(s,d.body.join('\n'),80,486,1080,100,25,C.muted);
  }else{
    box(s,d.statement,80,145,1120,70,29,C.jade);
    if(d.table){table(s,d.table);if(d.body?.length)box(s,d.body.join('\n'),80,588,1120,64,23,C.muted);}
    else if(d.layout==='timeline'||d.layout==='resume'){
      stepDiagram(s,d.steps);box(s,d.body.join('\n'),80,550,1120,96,24,C.muted);
    }else if(d.layout==='architecture'){
      table(s,{headers:['协调与协议','资源信任域','本域职责'],rows:d.domains.map((a,i)=>[i===0?d.coordinator:i===1?d.platform:'',a.title,a.text]),widths:[420,260,440]},80,238,1120,310);
      box(s,d.body.join('\n'),80,575,1120,74,24,C.muted);
    }else if(d.layout==='methods'){
      table(s,{headers:['方法','选择方式'],rows:d.methods.map(x=>[x.name,x.text]),widths:[330,790]},80,245,1120,250);
      box(s,d.body.join('\n'),80,538,1120,104,25);
    }else if(d.layout==='safety'){
      box(s,d.body.join('\n\n'),80,245,1120,282,27);
      box(s,d.equation,80,566,1120,65,34,C.jade,true);
    }else if(d.layout==='screenshot'){
      s.images.add({blob:new Uint8Array(await fs.readFile(path.join(workspaceDir,d.asset))),contentType:'image/png',fit:'contain',alt:'真实工作台：服务已恢复，原请求键遗失，仍需人工核对',position:{left:80,top:220,width:930,height:450}});
      box(s,d.body.join('\n\n'),1036,250,164,380,23,C.muted);
    }else if(d.layout==='three_charts'){
      const frames=[{left:60,top:264,width:576,height:280},{left:656,top:264,width:272,height:280},{left:940,top:264,width:272,height:280}];
      d.charts.forEach((id,i)=>{box(s,charts[id].title+(i===0?' / 秒':''),frames[i].left+20,222,frames[i].width,38,25,C.ink,true);dataChart(s,id,frames[i],{labels:i>0});});
      box(s,d.body.join('\n'),80,578,1120,78,24,C.muted);
    }else if(d.layout==='e1_platform'){
      dataChart(s,d.chart,{left:60,top:254,width:585,height:352});
      box(s,d.body.join('\n\n'),680,236,520,360,24);
      box(s,'E1-b各策略3次中位数 / UTF-8字节',80,620,560,35,20,C.muted);
    }else{
      box(s,d.body.join('\n\n'),80,260,1120,250,31);
      if(d.next)box(s,d.next,80,563,1120,86,26,C.jade,true);
    }
  }
  box(s,d.footnote??'',80,672,1080,31,16,C.muted);
  box(s,String(d.number).padStart(2,'0'),1160,672,45,31,16,C.muted);
  const locators=d.sources.map(id=>{const x=evidence.sources.find(x=>x.id===id);return `${id} 原项目根相对定位：${x.relative_path}\nSHA256：${x.sha256}\n范围：${x.scope}`;});
  s.speakerNotes.textFrame.setText(`用途：${d.purpose}\n\n${d.notes}\n\n证据截止：${content.cutoff_utc}\n\n${locators.join('\n\n')}`);
}
const staging=path.join(workspaceDir,'.build');
const out=path.join(workspaceDir,'output');await fs.mkdir(staging,{recursive:true});await fs.mkdir(out,{recursive:true});
const candidatePath=path.join(staging,'candidate.pptx');
await(await PresentationFile.exportPptx(p)).save(candidatePath);
const finalPath=path.join(out,'defense-development-v1.pptx');
await finalizePresentation({workspaceDir,candidatePath,finalPath,pythonExecutable:RUNTIME_PYTHON,integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],explicitTotalSlideCount:15,requiredNativeTableOwnerSlides:[3,5,6,8,14],requiredNativeChartOwnerSlides:[12,13],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:[FONT]},verifyArtifactToolImport:true,receiptPath:path.join(staging,'finalizer.json')});
// Render all final slides and open exact final bytes in native PowerPoint before delivery.
// PDF export and visual QA remain separate mandatory steps, not inferred from exportPptx success.
console.log(JSON.stringify({pptx:finalPath,pdf_generated:false,render_QA_complete:false,native_QA_complete:false}));

'use strict';
// Record the official public status/query UI. Private identity mapping is input only.
const fs=require('node:fs'),path=require('node:path');
const {startCapture}=require('./capture-session.cjs');

function statusMask(){
 const install=()=>{
  if(!document.documentElement||document.getElementById('status-privacy-css'))return;
  const style=document.createElement('style');style.id='status-privacy-css';
  style.textContent=`html{zoom:1.25} ::-webkit-scrollbar{display:none}
   #toolsAicInput{color:transparent!important;-webkit-text-fill-color:transparent!important;caret-color:transparent!important;text-shadow:none!important;background:#1f2937!important}
   #rankingRows td:first-child{color:transparent!important;-webkit-text-fill-color:transparent!important;background:#1f2937!important}
   .partner-card>*{visibility:hidden!important}.partner-card{background:#1f2937!important}
   header summary[title="Contributor"]{visibility:hidden!important}
   /* The platform popup computes its position without the 125% CSS zoom.
      Keep the entire original panel visible; do not alter its data. */
   #queryDialog{left:calc(50% - 195px)!important;top:100px!important}`;
  document.documentElement.appendChild(style);
 };new MutationObserver(install).observe(document,{childList:true,subtree:true});install();
}

async function main(){
 const [identityFile,outputDir,privateDir]=process.argv.slice(2);
 if(!privateDir)throw Error('Usage: node collect_v5_status.cjs private-identities.json empty-output-dir private-trace-dir');
 const ids=JSON.parse(fs.readFileSync(identityFile,'utf8').replace(/^\uFEFF/,''));
 const s=await startCapture({outputDir,privateDir,initScript:statusMask});
 const {page}=s,network=[],pending=[],observations=[];
 page.setDefaultNavigationTimeout(90000);
 const capturedAtUtc=new Date().toISOString();
 page.on('response',r=>{
  if(!r.url().includes('/api/rankings/top'))return;
  const n=network.length,receipt={url:r.url(),status:r.status(),receivedAtUtc:new Date().toISOString()};network.push(receipt);
  pending.push((async()=>{
   try{
    const body=await r.body();fs.mkdirSync(privateDir,{recursive:true});
    fs.writeFileSync(path.join(privateDir,`ranking-response-${n}.json`),body);
    receipt.bodySavedPrivately=true;
   }catch{receipt.bodySavedPrivately=false;}
  })());
 });
 let failure=null;
 try{
  await s.navigate('https://wt.ioa.pub/','Official Wutong public page');
  await page.getByRole('button',{name:'查询',exact:true}).waitFor();
  await page.waitForTimeout(1500);
  await s.click(page.getByRole('button',{name:'查询',exact:true}),'Open platform status and access statistics');
  const form=page.getByRole('search',{name:'按 AIC 查询状态及调用统计'});
  for(const alias of ['A01','A03']){
   await page.getByRole('searchbox',{name:'智能体 AIC'}).fill(ids[alias]);
   await s.click(form.getByRole('button',{name:'查询',exact:true}),'Query '+alias+' (identity field masked)');
   await page.locator('#toolsQueryResult').waitFor({state:'visible',timeout:40000});
   await page.evaluate(()=>window.scrollTo(0,0));
   const o=await page.evaluate(()=>({message:document.querySelector('#toolsQueryMessage').textContent,
    values:Object.fromEntries(['queryAlive','queryCaller','queryCallee','queryCallerExternal','queryCalleeExternal','queryStatsRange'].map(k=>[k,document.getElementById(k).textContent])),
    panelBox:(()=>{const r=document.getElementById('queryDialog').getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height};})()}));
   // A name missing in a failed query could fall back to the private AIC; redact it before export.
   for(const [a,v] of Object.entries(ids))o.message=o.message.replaceAll(v,a);
   o.alias=alias;o.observedAtUtc=new Date().toISOString();o.observedAtBeijing=new Date().toLocaleString('sv-SE',{timeZone:'Asia/Shanghai'})+' +08:00';
   o.screenshot='status-'+alias+'.png';observations.push(o);
   await s.holdScreenshot(o.screenshot,7);
  }
 }catch(e){
  fs.mkdirSync(privateDir,{recursive:true});fs.writeFileSync(path.join(privateDir,'capture-error-private.txt'),String(e.stack||e));
  failure={name:e.name,message:'Status capture did not complete; inspect private trace.'};
 }
 await Promise.allSettled(pending);
 const receipt={schema:'official-public-status-observation/1',capturedAtUtc,source:'https://wt.ioa.pub/',
  capture_kind:'live_public_UI',authenticated_management_backend:false,
  display_adaptation:'Original status panel repositioned to the page center because its built-in positioning clips at CSS zoom 125%; data and labels are unchanged.',
  statistics_source:'Official query UI; WutongCumulativeRanking.getStatistics uses /api/rankings/top segment aggregation; no displayed values replaced.',
  registry_inspection:'Authenticated registry navigation exposed My Agents only; no separate access monitor dashboard was identified.',
  official_requirement_boundary:'This is an official access-data query screenshot, not an authenticated management-dashboard screenshot. Organizer acceptance of this public statistics view is not inferred.',
  observations,network,error:failure};
 fs.writeFileSync(path.join(outputDir,'status-observation.json'),JSON.stringify(receipt,null,2)+'\n');
 await s.finish({scope:'Official public query access-data supplement',capture_kind:'live_public_UI',success:!failure});
 if(failure)throw Error(failure.message);
 console.log(JSON.stringify({observations:observations.map(o=>({alias:o.alias,time:o.observedAtBeijing,values:o.values})),network:network.length}));
}
main().catch(e=>{console.error(e.name+': '+e.message);process.exitCode=1;});

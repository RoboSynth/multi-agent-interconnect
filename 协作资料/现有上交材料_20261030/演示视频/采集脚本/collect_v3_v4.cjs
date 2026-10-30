'use strict';
const fs=require('fs'),path=require('path');
const {startCapture}=require('./capture-session.cjs');
const base=path.resolve(__dirname,'..'),cache=process.env.VIDEO_PRIVATE_DIR;
const origin=process.env.VIDEO_BRIDGE_ORIGIN||'http://127.0.0.1:8879';
if(!cache)throw new Error('VIDEO_PRIVATE_DIR required');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const mask=function(){
 const install=()=>{if(!document.documentElement||document.getElementById('video-privacy-css'))return;const style=document.createElement('style');style.id='video-privacy-css';style.textContent='html{zoom:1.25} ::-webkit-scrollbar{display:none}';document.documentElement.appendChild(style);};
 new MutationObserver(install).observe(document,{subtree:true,childList:true});install();
};
async function status(){const before=Date.now();const r=await fetch(origin+'/api/capture',{signal:AbortSignal.timeout(6000)});if(!r.ok)throw Error('Bridge HTTP '+r.status);const value=await r.json();return{value,before,after:Date.now()};}
async function waitCase(key){
 const end=Date.now()+20*60*1000;let lastLog=0;
 while(Date.now()<end){
  try{const s=await status();if(s.value.case===key&&s.value.phase==='ready_for_capture')return s;}catch{}
  if(Date.now()-lastLog>30000){console.log(JSON.stringify({waiting_for:key,utc:new Date().toISOString()}));lastLog=Date.now();}
  await sleep(750);
 }
 throw Error('Timed out before ready_for_capture: '+key);
}
async function capture(key,category){
 const ready=await waitCase(key);const dir=path.join(base,category);
 const s=await startCapture({outputDir:dir,privateDir:path.join(cache,category+'-browser'),initScript:mask,headless:true});
 const {page}=s;const receipt={case:key,category,bridge_view:'real engine / transport observer, identity fields anonymized by capture adapter',snapshots:[],approvals:[],clock_samples:[]};
 const snap=x=>{const epoch=Date.parse(x.value.observed_at_utc);receipt.clock_samples.push({local_before_utc:new Date(x.before).toISOString(),local_after_utc:new Date(x.after).toISOString(),server_observed_at_utc:x.value.observed_at_utc,round_trip_ms:x.after-x.before,estimated_server_minus_browser_host_ms:epoch-(x.before+x.after)/2,uncertainty_half_rtt_ms:(x.after-x.before)/2});};
 snap(ready);
 try{
  await s.navigate(origin,'same_run_observation_workbench');
  await page.getByRole('tab',{name:'证据与计划',exact:true}).waitFor();
  fs.writeFileSync(path.join(cache,category+'-browser','initial-aria-snapshot.yml'),await page.locator('body').ariaSnapshot());
  if(category==='V4-takeover')await s.click(page.getByRole('tab',{name:'操作与接续',exact:true}),'show_takeover_operations');
  await s.holdScreenshot('ready.png',1);
  const startBefore=Date.now();const response=await fetch(origin+'/api/capture/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({case:key}),signal:AbortSignal.timeout(10000)});
  receipt.start_request={before_utc:new Date(startBefore).toISOString(),after_utc:new Date().toISOString(),http_status:response.status};
  if(!response.ok)throw Error('Case start rejected: '+response.status);
  const end=Date.now()+17*60*1000;let lastSnapshot=0,lastViewChange=Date.now(),approvalNumber=0,viewIndex=category==='V4-takeover'?1:0;
  const tabs=['证据与计划','操作与接续','业务与记录'];
  while(Date.now()<end){
   const capture=await status();snap(capture);
   const startEvent=capture.value.events?.find(e=>e.event==='capture_case_started'&&e.case===key);
   if(startEvent&&!receipt.case_start_utc)receipt.case_start_utc=startEvent.captured_at_utc;
   if(capture.value.case!==key)throw Error('Case advanced before browser observed completion');
   if(Date.now()-lastSnapshot>1000){receipt.snapshots.push({observed_at_utc:capture.value.observed_at_utc,phase:capture.value.phase,connected:capture.value.connected,result:capture.value.result});lastSnapshot=Date.now();}
   const dialog=page.getByRole('dialog',{name:'确认高风险恢复操作',exact:true});
   if(await dialog.isVisible()){
    approvalNumber++;const imageName=`approval-${approvalNumber}.png`;
    const shown=Date.now();await s.holdScreenshot(imageName,2.2);
    const button=dialog.getByRole('button',{name:'批准此操作',exact:true});const id=await button.getAttribute('data-approval');
    const approvalText=await dialog.innerText();
    await s.click(button,`approve_real_pending_${approvalNumber}`);
    receipt.approvals.push({id,dialog_observed_utc:new Date(shown).toISOString(),clicked_utc:new Date().toISOString(),screenshot:imageName,text:approvalText,minimum_visible_hold_seconds:2.2});
    if(category==='V3-f10'&&approvalNumber===1){fs.copyFileSync(path.join(dir,imageName),path.join(base,'V6-safety','approval.png'));fs.writeFileSync(path.join(base,'V6-safety','approval-source.json'),JSON.stringify({case:key,source:'../V3-f10/'+imageName,capture:'genuine pending approval on the same cloud run',timestamp_utc:new Date().toISOString()},null,2));}
    await page.waitForTimeout(500);
   }
   if(capture.value.phase==='case_finished'||capture.value.phase==='case_failed'){
    receipt.final_capture=capture.value;
    for(const index of(category==='V3-f10'?[0,1,2]:[1,2])){await s.click(page.getByRole('tab',{name:tabs[index],exact:true}),`final_${['evidence','operations','results'][index]}`);await s.holdScreenshot(`final-${['evidence','operations','results'][index]}.png`,2);}
    break;
   }
   if(Date.now()-lastViewChange>10000 && !(await dialog.isVisible())){
    viewIndex=category==='V3-f10'?(viewIndex+1)%3:1;
    await s.click(page.getByRole('tab',{name:tabs[viewIndex],exact:true}),`progress_${['evidence','operations','results'][viewIndex]}`);
    lastViewChange=Date.now();
   }
   await page.waitForTimeout(650);
  }
  if(!receipt.final_capture)throw Error('Recording exceeded case observation deadline');
  const finished=await s.finish({category,case:key,status:'captured',run_outcome:receipt.final_capture.result,view:receipt.bridge_view,approval_mode:'real human-decision API, scripted visible hold >=2.2s'});
  receipt.recording=finished.timing;
  const started=receipt.final_capture.events?.find(e=>e.event==='capture_case_started'&&e.case===key);
  receipt.case_start_utc=receipt.case_start_utc??started?.captured_at_utc??null;
  const offset=receipt.clock_samples.reduce((a,b)=>a.round_trip_ms<b.round_trip_ms?a:b).estimated_server_minus_browser_host_ms;
  receipt.video_t0_to_server_case_start_seconds=receipt.case_start_utc?(Date.parse(receipt.case_start_utc)-offset-finished.timing.videoT0EpochMs)/1000:null;
  receipt.synchronization_note='Estimated cross-host alignment using the shortest measured HTTP round trip and server observed_at_utc; preserve RTT and 25 fps frame quantization uncertainty.';
  fs.writeFileSync(path.join(dir,'browser-run.json'),JSON.stringify(receipt,null,2));
  console.log(JSON.stringify({case:key,recorded:true,video:finished.videoProbe,approvals:approvalNumber}));
 }catch(e){receipt.error={name:e.name,message:e.message};await s.finish({category,case:key,status:'capture_failed',error:e.name});fs.writeFileSync(path.join(dir,'browser-run.json'),JSON.stringify(receipt,null,2));throw e;}
}
(async()=>{await capture('f10-m0-r1','V3-f10');await capture('e1a-after_applied-r1','V4-takeover');})().catch(e=>{console.error(e.message);process.exitCode=1;});

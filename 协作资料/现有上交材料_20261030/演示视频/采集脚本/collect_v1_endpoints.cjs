'use strict';
const fs=require('fs'),path=require('path');
const {startCapture}=require('./capture-session.cjs');
const {registryMask}=require('./browser-masks.cjs');
const base=path.resolve(__dirname,'..'),cache=process.env.VIDEO_PRIVATE_DIR;
if(!cache)throw Error('VIDEO_PRIVATE_DIR required');
(async()=>{
 const output=path.join(cache,'V1-endpoint-export');fs.mkdirSync(output,{recursive:true});
 const s=await startCapture({outputDir:output,privateDir:path.join(cache,'V1-endpoint-trace'),storageState:path.join(cache,'registry-auth.json'),initScript:registryMask});
 const {page}=s;
 async function showKey(area,key,label){
  const target=await area.evaluate((e,key)=>{
   const cs=getComputedStyle(e),scale=e.getBoundingClientRect().width/e.offsetWidth;
   const mirror=document.createElement('div');Object.assign(mirror.style,{position:'fixed',top:'0',left:'0',visibility:'hidden'});
   for(const p of ['font','letterSpacing','lineHeight','padding','border','boxSizing','whiteSpace','overflowWrap','wordBreak','tabSize'])mirror.style[p]=cs[p];
   mirror.style.width=e.offsetWidth+'px';const text=document.createTextNode(e.value);mirror.appendChild(text);document.body.appendChild(mirror);
   const index=e.value.indexOf('"'+key+'"');if(index<0)throw Error('Missing ACS field');const r=document.createRange();r.setStart(text,index);r.setEnd(text,index+key.length+2);
   const y=(r.getBoundingClientRect().top-mirror.getBoundingClientRect().top)/scale-parseFloat(cs.paddingTop);mirror.remove();return y;
  },key);
  for(let n=0;n<3;n++){const current=await area.evaluate(e=>e.scrollTop);if(Math.abs(current-target)<6)break;await s.wheel(area,(target-current)*1.25,label+'_'+n);}
  await page.evaluate(()=>window.__refreshPrivacyMasks?.());
 }
 try{
  await s.navigate('https://wt.ioa.pub/registry/#/my-agents/index','registered_agent_list');
  for(const [alias,name] of [['A01','跨域故障协调智能体'],['A03','跨域数据库协同智能体']]){
   const row=page.getByRole('row').filter({has:page.getByRole('cell',{name,exact:true})});await row.waitFor();await page.locator('.el-loading-mask').first().waitFor({state:'hidden'});
   await s.click(row.getByRole('button',{name:'详情',exact:true}),`open_${alias}_endpoint_detail`);
   const area=page.getByRole('textbox',{name:'ACS',exact:true});await area.waitFor();await page.locator('.el-loading-mask').first().waitFor({state:'hidden'});
   await s.scroll(area,`show_${alias}_ACS`);
   await showKey(area,'endPoints',`scroll_${alias}_endpoint_security`);await s.holdScreenshot(`${alias}-endpoint-security.png`,3);
   await showKey(area,'transport',`scroll_${alias}_endpoint_transport`);await s.holdScreenshot(`${alias}-endpoint-transport.png`,3);
   await s.click(page.getByRole('button',{name:'返回列表',exact:true}),`return_${alias}_list`);
  }
  const result=await s.finish({category:'V1',status:'captured',purpose:'supplementary endpoint security and transport close reading; original footage retained'});
  result.video='endpoints-video.webm';fs.writeFileSync(path.join(output,'actions.json'),JSON.stringify(result,null,2));
  for(const file of fs.readdirSync(output)){const to=file==='video.webm'?'endpoints-video.webm':file==='actions.json'?'endpoints-actions.json':file;fs.renameSync(path.join(output,file),path.join(base,'V1-registry',to));}
 }catch(e){await s.finish({category:'V1',status:'supplement_failed',error:e.name});throw e;}
})().catch(e=>{console.error(e.message);process.exitCode=1;});

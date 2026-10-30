'use strict';
const fs=require('node:fs'),path=require('node:path');
const {startCapture}=require('./capture-session.cjs');
const {storeMask}=require('./store-masks.cjs');
const base=path.resolve(__dirname,'..');
const cache=process.env.VIDEO_PRIVATE_DIR;
if(!cache)throw new Error('Set VIDEO_PRIVATE_DIR to the private cache outside deliverables.');
const target=path.join(base,'V2-discovery');
const sessionRoot=path.join(cache,'store-supplement',new Date().toISOString().replace(/[:.]/g,'-'));
const stage=path.join(sessionRoot,'prepared-export');
const aliases={
 '跨域故障协调智能体':'A01','跨域订单应用智能体':'A02','跨域数据库协同智能体':'A03',
 '跨域数据库备智能体':'A04','跨域入口运维智能体':'A05','跨域业务验证智能体':'A06','跨域接入体检智能体':'A07'
};
for(const name of ['store-video.webm','store-actions.json','store-observation.json']) {
 if(fs.existsSync(path.join(target,name)))throw new Error('Existing supplement would be overwritten: '+name);
}
(async()=>{
 const started=new Date().toISOString();
 const s=await startCapture({outputDir:stage,privateDir:path.join(sessionRoot,'private'),initScript:storeMask,headless:true});
 const {page}=s,queries=[],discoveryRequests=[];
 page.setDefaultNavigationTimeout(90000);
 page.on('response',response=>{
  const url=new URL(response.url());
  if(url.pathname.includes('/discovery/')&&url.pathname.endsWith('/discover')) {
   discoveryRequests.push({url:url.origin+url.pathname,status:response.status(),method:response.request().method(),observed_at_utc:new Date().toISOString()});
  }
 });
 try {
  await s.navigate('https://wt.ioa.pub/','platform_home');
  await page.getByRole('heading',{name:'智能体互联星图',exact:true}).waitFor();
  await page.mouse.move(1810,140);
  await s.holdScreenshot('store-home.png',2);
  await s.click(page.getByRole('button',{name:'Store',exact:true}),'open_store');
  await page.locator('#storeInput').waitFor();
  await page.locator('#storeField').selectOption('name');
  for(const [query,screenshot,hold] of [['跨域','store-search-cross-domain.png',4],['跨域订单','store-search-order.png',3],['跨域数据库','store-search-database.png',4]]) {
   const queryStarted=new Date().toISOString();
   await page.locator('#storeInput').fill(query);
   const observed=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/discover')&&r.request().method()==='POST',{timeout:30000});
   await s.click(page.getByRole('button',{name:'搜索',exact:true}),'search_'+query);
   const response=await observed;
   await page.locator('#storeCatalogTitle').filter({hasText:'查询结果'}).waitFor();
   await page.waitForTimeout(450);
   const current=await page.evaluate(()=>({
    search_field:document.querySelector('#storeField').value,
    match_mode:document.querySelector('#storeOp').value,
    query:document.querySelector('#storeInput').value,
    status:document.querySelector('#storeCatalogStatus').textContent,
    cards:[...document.querySelectorAll('#storeGrid .store-agent-card')].map(card=>({
     name:card.querySelector('.store-agent-name').textContent.trim(),
     status:card.querySelector('.store-alive').textContent.trim(),
     capability_label:card.querySelector('.store-agent-card-footer button').textContent.trim()
    }))
   }));
   current.cards=current.cards.map(card=>({alias:aliases[card.name]||'other-public-result',...(aliases[card.name]?{name:card.name}:{}),status:card.status,capability_label:card.capability_label}));
   queries.push({started_at_utc:queryStarted,observed_at_utc:new Date().toISOString(),response_status:response.status(),...current});
   await page.mouse.move(1810,140);
   await s.holdScreenshot(screenshot,hold);
  }
  const detail=page.getByRole('button',{name:'查看 跨域数据库备智能体 的详情',exact:true});
  if(await detail.count()!==1)throw new Error('A04 detail is not available in current search results; retain current observation.');
  await s.click(detail,'open_A04_detail');
  await page.locator('#storeAcsDialog[open]').waitFor();
  await page.locator('#storeAcsTitle').filter({hasText:'跨域数据库备智能体'}).waitFor();
  await page.waitForTimeout(400);
  await s.hover(page.locator('#storeAcsFacts dd').nth(2),'show_version');
  await page.waitForTimeout(800);
  await s.hover(page.locator('#storeAcsFacts dd').nth(3),'show_registration_enabled');
  await page.waitForTimeout(800);
  await s.holdScreenshot('store-A04-details.png',3);
  await s.scroll(page.locator('#storeCopyStatus'),'show_ACS_discovery_source');
  await page.mouse.move(1810,140);
  await s.holdScreenshot('store-A04-discovery-source.png',3);
  const detailData=await page.evaluate(()=>({
   name:document.querySelector('#storeAcsTitle').textContent,
   version:document.querySelectorAll('#storeAcsFacts dd')[2].textContent,
   registration_enabled:document.querySelectorAll('#storeAcsFacts dd')[3].textContent,
   skills:[...document.querySelectorAll('#storeAcsSkills .store-skill')].map(e=>({name:e.querySelector('h4').textContent,description:e.querySelector('p').textContent})),
   source_label:document.querySelector('#storeCopyStatus').textContent
  }));
  await s.click(page.locator('#storeAcsClose'),'close_A04_details');
  await page.waitForTimeout(1000);
  const receipt=await s.finish({category:'V2',status:'captured',capture_kind:'live_public_Store_UI',no_login:true,no_agent_task_dispatched:true,private_fields_masked_before_navigation:true});
  receipt.video='store-video.webm';
  const observation={source:'https://wt.ioa.pub/',capture_kind:'live_public_Store_UI',started_at_utc:started,ended_at_utc:new Date().toISOString(),
    started_at_beijing:new Date(started).toLocaleString('sv-SE',{timeZone:'Asia/Shanghai'})+' +08:00',
    separate_from_F10_capture:true,queries,detail:{alias:'A04',...detailData},discovery_http:discoveryRequests,
    privacy_masks:['provider names','AIC values','endpoint values','raw ACS and copy control','partner school logos and names','contributor control','unrelated popular-card names and descriptions'],
    status_values_unchanged:true,page_area_only_no_browser_chrome:true,login_used:false,agent_task_dispatched:false,
    note:'Current Store name-based queries are separate from the earlier skill-based ADP/describe run. An online badge is a platform observation, not an end-to-end business verification. Original private trace is excluded.'};
  fs.writeFileSync(path.join(stage,'store-actions.json'),JSON.stringify(receipt,null,2));
  fs.writeFileSync(path.join(stage,'store-observation.json'),JSON.stringify(observation,null,2));
  fs.renameSync(path.join(stage,'video.webm'),path.join(stage,'store-video.webm'));
  fs.unlinkSync(path.join(stage,'actions.json'));
  fs.writeFileSync(path.join(sessionRoot,'prepared.json'),JSON.stringify({stage,started,success:true},null,2));
  console.log(JSON.stringify({status:'prepared_for_visual_privacy_review',stage,video_duration:receipt.videoProbe.durationSeconds,queries:queries.map(x=>({query:x.query,count:x.cards.length,statuses:x.cards.map(a=>({alias:a.alias,status:a.status}))}))},null,2));
 }catch(error){
  fs.writeFileSync(path.join(sessionRoot,'failure-private.json'),JSON.stringify({name:error.name,message:error.message,queries,discoveryRequests},null,2));
  await s.finish({category:'V2',status:'failed',error_name:error.name});
  console.error('Supplement capture failed; private stage retained. '+error.name);
  process.exitCode=1;
 }
})().catch(error=>{console.error(error.name);process.exitCode=1;});

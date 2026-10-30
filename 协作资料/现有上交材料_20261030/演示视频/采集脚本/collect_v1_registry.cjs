'use strict';
const fs=require('fs'),path=require('path');
const {startCapture}=require('./capture-session.cjs');
const {registryMask}=require('./browser-masks.cjs');
const base=path.resolve(__dirname,'..'),cache=process.env.VIDEO_PRIVATE_DIR;
if(!cache)throw new Error('VIDEO_PRIVATE_DIR required');
const names={A01:'跨域故障协调智能体',A02:'跨域订单应用智能体',A03:'跨域数据库协同智能体',A04:'跨域数据库备智能体',A05:'跨域入口运维智能体',A06:'跨域业务验证智能体',A07:'跨域接入体检智能体'};
(async()=>{
 const s=await startCapture({outputDir:path.join(base,'V1-registry'),privateDir:path.join(cache,'V1-browser'),storageState:path.join(cache,'registry-auth.json'),initScript:registryMask,headless:true});
 const {page}=s, observations=[];
 const rowFor=alias=>page.getByRole('row').filter({has:page.getByRole('cell',{name:names[alias],exact:true})});
 const settle=async()=>{await page.locator('.el-loading-mask').first().waitFor({state:'hidden',timeout:45000});await page.waitForTimeout(700);};
 try{
  await s.navigate('https://wt.ioa.pub/registry/#/my-agents/index','my_agents');
  await rowFor('A01').waitFor({timeout:45000});await settle();
  for(const alias of ['A07','A06','A02','A01','A03','A04','A05']) {
   const row=rowFor(alias);const status=row.getByRole('cell',{name:'已通过',exact:true});
   if(await status.count()!==1)throw new Error('Expected approval status missing for '+alias);
   await s.scroll(row,`show_${alias}_approved`);
   await s.hover(status,`read_${alias}_approval_status`);
   await s.holdScreenshot(`${alias}-approved.png`,3);
   observations.push({alias,name:names[alias],status:await status.innerText(),observed_at_utc:new Date().toISOString()});
  }
  await page.mouse.move(1800,130);
  for(const alias of ['A01','A03']){
   await s.click(rowFor(alias).getByRole('button',{name:'详情',exact:true}),`open_${alias}_detail`);
   await page.getByRole('heading',{name:'审批信息',exact:true}).waitFor();await settle();
   await s.holdScreenshot(`${alias}-identity.png`,3);
   const area=page.getByRole('textbox',{name:'ACS',exact:true});await s.scroll(area,`show_${alias}_ACS`);
   await page.evaluate(()=>window.__refreshPrivacyMasks?.());
   await s.holdScreenshot(`${alias}-skills.png`,3);
   const acs=JSON.parse(await area.inputValue());
   observations.push({alias,detail_status:await page.getByRole('cell',{name:'已通过',exact:true}).innerText(),skills:acs.skills.map(x=>({id:x.id,name:x.name})),endpoint_transports:acs.endPoints?.map(x=>x.transport),identity_and_provider_redacted:true,observed_at_utc:new Date().toISOString()});
   // Real wheel events move the original disabled textarea; no value replacement.
   const endpointLine=(await area.inputValue()).split('\n').findIndex(l=>l.includes('"endPoints"'));
   const lineHeight=await area.evaluate(e=>parseFloat(getComputedStyle(e).lineHeight));
   await s.wheel(area,Math.max(0,(endpointLine-1)*lineHeight*1.25),`scroll_${alias}_endpoints`);
   await page.evaluate(()=>window.__refreshPrivacyMasks?.());
   await s.holdScreenshot(`${alias}-endpoints.png`,3);
   await s.click(page.getByRole('button',{name:'返回列表',exact:true}),`return_${alias}_to_list`);await rowFor('A01').waitFor();await settle();
  }
  fs.writeFileSync(path.join(base,'V1-registry','registry-observation.json'),JSON.stringify({capture_kind:'authenticated_current_registration_UI',observations,note:'Visible account names, AICs, ACS provider names and identity-bearing endpoint URL lines are CSS-masked. Approval state and skill fields are unmodified. Dates in screenshots use the platform session timezone.'},null,2));
  await s.finish({category:'V1',status:'captured',seven_approved:true,detail_roles:['A01','A03'],zoom:1.25});
 }catch(e){await s.finish({category:'V1',status:'failed',error:e.name});throw e;}
})().catch(e=>{console.error(e.message);process.exitCode=1;});

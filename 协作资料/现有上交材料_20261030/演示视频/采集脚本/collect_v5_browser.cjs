'use strict';
const fs=require('fs'),path=require('path');
const {startCapture}=require('./capture-session.cjs');
const {rankingMask}=require('./browser-masks.cjs');
const base=path.resolve(__dirname,'..');
const cache=process.env.VIDEO_PRIVATE_DIR;
if(!cache)throw new Error('Set VIDEO_PRIVATE_DIR to the private cache outside deliverables.');
(async()=>{
 const identities=JSON.parse(fs.readFileSync(path.join(cache,'private-identities.json'),'utf8').replace(/^\uFEFF/,''));
 const s=await startCapture({outputDir:path.join(base,'V5-access'),privateDir:path.join(cache,'V5-browser'),initScript:rankingMask,headless:true});
 const {page}=s;const records=[];
 try {
  await s.navigate('https://wt.ioa.pub/','platform_home');
  await s.click(page.getByRole('button',{name:'排行榜',exact:true}),'open_rankings');
  await page.locator('#rankingRows td[title]').first().waitFor({timeout:60000});
  await page.waitForTimeout(800);
  for(const [key,label,index] of [['caller','调用含内部',1],['callee','被调用含内部',2],['callerNonInternal','调用不含内部',3],['calleeNonInternal','被调用不含内部',4]]) {
   const button=page.locator(`button[data-rank-key="${key}"]`);
   await s.click(button,`sort_${key}_descending`);
   if(await button.locator('..').getAttribute('aria-sort')!=='descending')await s.click(button,`sort_${key}_descending_second_click`);
   await page.waitForTimeout(450);
   const data=await page.evaluate(({identities,index})=>{
    const rows=[...document.querySelectorAll('#rankingRows tr')];
    return Object.entries(identities).map(([alias,aic])=>{const n=rows.findIndex(r=>r.children[0]?.getAttribute('title')===aic);if(n<0)return{alias,present:false};const r=rows[n];return{alias,present:true,table_position:n+1,count:Number(r.children[index].textContent.replace(/,/g,'')),counts:[...r.children].slice(1).map(c=>Number(c.textContent.replace(/,/g,'')))};});
   },{identities,index});
   const candidates=data.filter(d=>d.present).sort((a,b)=>b.count-a.count||a.table_position-b.table_position);
   if(!candidates.length)throw new Error('No current team identities in loaded ranking table');
   const selected=candidates[0], row=page.locator('#rankingRows tr').filter({has:page.locator(`td[title="${identities[selected.alias]}"]`)});
   await s.scroll(row,`show_${selected.alias}_${key}`);
   await page.mouse.move(1800,140);
   await s.holdScreenshot(`${key}.png`,3);
   records.push({metric:key,label,selected_alias:selected.alias,selected_box:await row.boundingBox(),team:data,observed_at_utc:new Date().toISOString(),table_position_is_not_official_rank:true});
  }
  const windowText=await page.getByRole('heading',{name:'智能体调用排行榜'}).locator('..').innerText();
  fs.writeFileSync(path.join(base,'V5-access','ui-observation.json'),JSON.stringify({source:'https://wt.ioa.pub/',capture_kind:'live_public_UI',window_text:windowText,metric_ui:'one_table_four_sortable_columns',note:'The live page begins September 9; ranking-hourly.json requests begin September 24. Do not splice the counts as if the windows match.',records},null,2));
  await s.finish({category:'V5',status:'captured',ui:'four_sortable_columns',data_window:'actual_page_default_not_historical_query_window'});
 } catch(e){await s.finish({category:'V5',status:'failed',error:String(e.message).replace(/1\.2\.156\.[\w.]+/g,'[AIC]')});throw e;}
})().catch(e=>{console.error(e.message);process.exitCode=1;});

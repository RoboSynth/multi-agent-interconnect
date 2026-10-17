'use strict';
const $=id=>document.getElementById(id);
const statusNames={running:'排查中',awaiting_approval:'等待审批',completed:'业务已恢复',needs_attention:'需要处理',interrupted:'任务中断',pending:'等待',ok:'成功',unknown:'结果未知',applied:'已执行',skipped_already_applied:'已执行，跳过',rejected_stale_fence:'旧令牌已拒绝',failed:'失败',not_dispatched:'未下发',rejected:'已拒绝',tool_error:'工具错误'};
const factNames={container_state:'应用进程',route_version:'入口版本',read_only:'数据库只读',blocking_sessions:'阻塞会话',application_reachable:'应用可达',application_pool_revision:'连接池版本',application_read_only:'应用连接只读',application_error_codes:'近期错误'};
const causeNames={application_unavailable:'应用未运行',stale_route:'入口指向旧版本',database_read_only:'数据库只读',database_blocked:'数据库阻塞',healthy_or_other:'正常或待查原因'};
const eventNames={probe_selected:'选择探测',task_started:'下发任务',task_returned:'参与者返回',plan_adjusted:'调整恢复计划',approval_requested:'申请高风险操作',approval_granted:'操作获批',takeover:'参与者接管',original_request_unresolved:'原请求待核对'};
const originalResolutionNames={not_required:'没有待核对的原请求',resolved_receipt:'原请求结果已查清',unknown:'原请求结果仍待人工核对。',unknown_missing_key:'原请求键已遗失，请人工核对原订单。',unknown_receipt_missing:'暂未查到原请求回执，请人工核对原订单。',unknown_receipt_unavailable:'暂时无法查询原请求结果，请稍后核对。'};
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const text=value=>escapeHtml(typeof value==='object'?JSON.stringify(value):value);
let selectedId=null,lastApproval=null;
async function api(path,options={}){const response=await fetch(path,options);const data=await response.json();if(!response.ok)throw new Error(data.detail||'请求失败');return data;}
function error(message){$('error').textContent=message;$('error').hidden=!message;}
document.querySelectorAll('[role=tab]').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('[role=tab]').forEach(t=>{const active=t===tab;t.setAttribute('aria-selected',String(active));$(t.getAttribute('aria-controls')).hidden=!active;});}));
function updateOriginalHint(){const hasKey=Boolean($('original-key').value.trim());if(hasKey)$('original-unknown').checked=true;$('original-hint').hidden=!$('original-unknown').checked;$('original-hint').textContent=hasKey?'将使用原请求键核对下单结果。':'如果请求键已遗失，仍会排查并恢复服务；原订单需要人工核对。';}
$('original-unknown').addEventListener('change',updateOriginalHint);$('original-key').addEventListener('input',updateOriginalHint);
$('incident-form').addEventListener('submit',async event=>{event.preventDefault();error('');$('start').disabled=true;try{const data=await api('/api/incidents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symptom:$('symptom').value,original_request_key:$('original-key').value.trim()||null,original_request_unknown:$('original-unknown').checked})});selectedId=data.id;await refresh();}catch(e){error(e.message);$('start').disabled=false;}});
document.addEventListener('click',async event=>{const button=event.target.closest('button[data-approval]');if(!button)return;button.disabled=true;try{await api('/api/approvals/'+encodeURIComponent(button.dataset.approval),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approved:button.dataset.decision==='approve'})});$('approval-dialog').close();await refresh();}catch(e){error(e.message);button.disabled=false;}});
$('approval-later').addEventListener('click',()=>$('approval-dialog').close());
function renderRun(run){
 if(!run)return;
 $('incident-title').textContent=run.symptom;$('incident-id').textContent=run.id;$('incident-status').textContent=statusNames[run.status]||run.status;
 $('start').disabled=['running','awaiting_approval'].includes(run.status);if(run.error)error(run.error);
 $('hypotheses').innerHTML=(run.hypotheses||[]).map(h=>`<span class="hypothesis">${text(causeNames[h.cause]||h.cause)}</span>`).join('');
 $('facts').innerHTML=(run.facts||[]).map(f=>`<div class="fact"><div>${text(factNames[f.key]||f.key)}<small>${text(f.source)}</small></div><div class="fact-value">${text(f.value)}</div></div>`).join('')||'尚未收到证据。';
 $('events').innerHTML=(run.events||[]).slice(-24).map(e=>`<li>${text(eventNames[e.event]||e.event)} ${text(e.tool||'')}<small>${text(typeof e.reason==='string'?e.reason:(e.reason?.reason||''))} ${text(new Date(e.at).toLocaleTimeString())}</small></li>`).join('');
 $('approvals').innerHTML=(run.approvals||[]).filter(a=>a.status==='pending').map(a=>`<section class="approval"><h3>需要你批准：${text(a.tool)}</h3><p>${text(a.reason)}</p><p>操作参数：${text(a.args)}</p><button class="approve" data-approval="${text(a.id)}" data-decision="approve">批准此操作</button><button class="decline" data-approval="${text(a.id)}" data-decision="decline">拒绝</button></section>`).join('');
 const pendingApproval=(run.approvals||[]).find(a=>a.status==='pending');
 if(pendingApproval&&pendingApproval.id!==lastApproval){lastApproval=pendingApproval.id;$('approval-dialog-content').innerHTML=`<p>${text(pendingApproval.reason)}</p><p>操作：${text(pendingApproval.tool)}</p><p>参数：${text(pendingApproval.args)}</p><button class="approve" data-approval="${text(pendingApproval.id)}" data-decision="approve">批准此操作</button><button class="decline" data-approval="${text(pendingApproval.id)}" data-decision="decline">拒绝</button>`;$('approval-dialog').showModal();}
 if(!pendingApproval&&$('approval-dialog').open)$('approval-dialog').close();
 $('actions').innerHTML=(run.tasks||[]).filter(t=>t.kind==='act').map(t=>`<article class="action"><strong>${text(t.tool)}</strong>${text(statusNames[t.status]||t.status)}<small> ${text(statusNames[t.product?.operation?.state]||t.product?.operation?.state||'')}</small></article>`).join('')||'尚未提出修改。';
 $('takeovers').innerHTML=(run.events||[]).filter(e=>e.event.includes('takeover')||e.event.includes('resume')).map(e=>`<article class="action">${text(e.event)} ${text(e.reason)}</article>`).join('')||'尚未发生接管。';
 const summary=run.result?.order_observation;
 const serviceRecovered=run.result?.service_recovered??run.result?.business_recovered;
 const originalResolution=originalResolutionNames[run.result?.original_request_resolution]||(run.result?.manual_required?'原请求仍需人工核对。':'');
 $('business').innerHTML=summary?`<div class="business-facts"><span><strong>${text(run.result.business_recovered?'通过':'未通过')}</strong>业务验证</span><span><strong>${text(serviceRecovered?'已恢复':'待恢复')}</strong>服务状态</span><span><strong>${text(summary.completed_workflows)}</strong>完整订单流程</span><span><strong>${text(summary.unknown)}</strong>本轮验证中未确认的请求</span><span><strong>${text(summary.duration_seconds)}s</strong>观察窗口</span></div>${originalResolution?`<p class="resolution-note">${text(originalResolution)}</p>`:''}`:'业务验证尚未开始。';
 $('tasks').innerHTML=(run.tasks||[]).map(t=>`<tr><td>${text(t.tool)}<br><small>${text(t.logical_task_id)}</small></td><td>${text(t.kind)}</td><td>${text(statusNames[t.status]||t.status)}</td><td>${text(t.elapsed_ms==null?'—':t.elapsed_ms+' ms')}</td></tr>`).join('');
 const events=summary?.events||[];const maximum=Math.max(30,...events.map(e=>e.elapsed_seconds));
 $('order-chart').innerHTML=events.map(e=>{const x=10+e.elapsed_seconds/maximum*620;const y=e.outcome==='success'?25:e.outcome==='unknown'?60:95;const color=e.outcome==='success'?'#24715a':e.outcome==='unknown'?'#966414':'#ad4141';return `<circle cx="${x}" cy="${y}" r="3" fill="${color}"><title>${text(e.phase)} ${text(e.outcome)}</title></circle>`;}).join('');
 $('raw').textContent=JSON.stringify(run,null,2);
}
async function refresh(){try{const state=await api('/api/state');$('connection').textContent=state.connected?'参与者已连接':'参与者未连接';$('mode-note').textContent=state.mode==='local-aip-stdio'?'本地独立进程联调，使用 AIP 任务数据；平台发现与 AMQPS 另行验收。':state.mode==='unconfigured'?'先按部署文档启动本地业务和智能体，再发起排障。':'通过梧桐 AIP 群组协作。';$('artifacts').textContent=state.artifacts;
 $('participants').innerHTML=(state.participants||[]).map(p=>`<div class="participant">${text(p.name||p.role||'参与者')}<small>${text(p.aic||p.executor_aic||'')}</small></div>`).join('')||'<p class="empty">等待连接各资源域。</p>';
 const run=selectedId&&state.incident?.id!==selectedId?await api('/api/incidents/'+encodeURIComponent(selectedId)):state.incident;
 $('start').disabled=!state.connected||(run&&['running','awaiting_approval'].includes(run.status));if(state.connection_error)error(state.connection_error);else if(!run?.error)error('');renderRun(run);
 }catch(e){$('connection').textContent='服务连接中断';error(e.message);}}
refresh();setInterval(refresh,1200);

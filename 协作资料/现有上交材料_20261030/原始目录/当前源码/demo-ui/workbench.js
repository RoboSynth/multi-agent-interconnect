'use strict';
const $=id=>document.getElementById(id);
const statusNames={running:'排查中',awaiting_approval:'等待审批',completed:'业务已恢复',needs_attention:'需要处理',interrupted:'任务中断',pending:'等待',ok:'成功',unknown:'结果未知',applied:'已执行',skipped_already_applied:'已执行，跳过',rejected_stale_fence:'旧令牌已拒绝',failed:'失败',not_dispatched:'未下发',rejected:'已拒绝',tool_error:'工具错误'};
const factNames={container_state:'应用进程',route_version:'入口版本',read_only:'数据库只读',blocking_sessions:'阻塞会话',application_reachable:'应用可达',application_pool_revision:'连接池版本',application_read_only:'应用连接只读',application_error_codes:'近期错误',participant_reachable:'参与者可达状态',participant_heartbeat_status:'参与者心跳状态',participant_heartbeat_age_seconds:'距上次心跳秒数',participant_access_status:'参与者访问状态'};
const causeNames={application_unavailable:'应用未运行',stale_route:'入口指向旧版本',database_read_only:'数据库只读',database_blocked:'数据库阻塞',participant_unavailable:'参与者失联',healthy_or_other:'正常或待查原因'};
const eventNames={probe_selected:'选择探测',task_started:'下发任务',task_returned:'参与者返回',plan_adjusted:'调整恢复计划',approval_requested:'申请高风险操作',approval_granted:'操作获批',takeover:'参与者接管',original_request_unresolved:'原请求待核对',participant_unreachable:'参与者失联，转人工',participant_health_unconfirmed:'参与者状态待核实',participant_health_check_failed:'参与者证据不可用',independent_verification_failed:'独立业务验证未完成'};
const originalResolutionNames={not_required:'没有待核对的原请求',resolved_receipt:'原请求结果已查清',unknown:'原请求结果仍待人工核对。',unknown_missing_key:'原请求键已遗失，请人工核对原订单。',unknown_receipt_missing:'暂未查到原请求回执，请人工核对原订单。',unknown_receipt_unavailable:'暂时无法查询原请求结果，请稍后核对。'};
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const text=value=>escapeHtml(typeof value==='object'?JSON.stringify(value):value);
function factValue(f){if(!f.key.startsWith('participant_')||!f.value||typeof f.value!=='object')return f.value;if(f.key==='participant_heartbeat_age_seconds')return Number.isFinite(f.value.seconds)?f.value.seconds.toFixed(1)+' 秒':'未知';return {reachable:'可达',unreachable:'失联',unknown:'待核实',fresh:'有效',expired:'已过期',success:'记录到成功响应',error:'记录到错误响应'}[f.value.state]||f.value.state;}
function factSource(f){return f.source+(f.key.startsWith('participant_')&&f.observed_at?' · '+new Date(f.observed_at).toLocaleTimeString():'');}
let selectedId=null,lastApproval=null,renderedId=null;
async function api(path,options={}){const response=await fetch(path,options);const data=await response.json();if(!response.ok)throw new Error(data.detail||'请求失败');return data;}
function error(message){$('error').textContent=message;$('error').hidden=!message;}
document.querySelectorAll('[role=tab]').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('[role=tab]').forEach(t=>{const active=t===tab;t.setAttribute('aria-selected',String(active));$(t.getAttribute('aria-controls')).hidden=!active;});}));
function updateOriginalHint(){const hasKey=Boolean($('original-key').value.trim());if(hasKey)$('original-unknown').checked=true;$('original-hint').hidden=!$('original-unknown').checked;$('original-hint').textContent=hasKey?'将使用原请求键核对下单结果。':'如果请求键已遗失，仍会排查并恢复服务；原订单需要人工核对。';}
$('original-unknown').addEventListener('change',updateOriginalHint);$('original-key').addEventListener('input',updateOriginalHint);
$('incident-form').addEventListener('submit',async event=>{event.preventDefault();error('');$('start').disabled=true;try{const data=await api('/api/incidents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symptom:$('symptom').value,original_request_key:$('original-key').value.trim()||null,original_request_unknown:$('original-unknown').checked})});selectedId=data.id;await refresh();}catch(e){error(e.message);$('start').disabled=false;}});
document.addEventListener('click',async event=>{const button=event.target.closest('button[data-approval]');if(!button)return;button.disabled=true;try{await api('/api/approvals/'+encodeURIComponent(button.dataset.approval),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approved:button.dataset.decision==='approve'})});$('approval-dialog').close();await refresh();}catch(e){error(e.message);button.disabled=false;}});
$('approval-later').addEventListener('click',()=>$('approval-dialog').close());
function renderModel(run){
 $('model-usage').hidden=!run;if(!run){['model-source','model-calls','model-tokens','model-fallback'].forEach(id=>$(id).textContent='');$('model-fallback').hidden=true;return;}
 const pending=['running','awaiting_approval'].includes(run.status)&&run.model_calls==null;
 const calls=run.model_calls;
 const sourceNames={llm:'模型诊断',mixed:'模型与规则共同诊断',rules:calls>0?'规则回退':'规则诊断',llm_failed:'模型调用失败'};
 $('model-source').textContent=pending?'正在诊断，结束后统计':sourceNames[run.model_source]||'来源未记录';
 $('model-calls').textContent=calls==null?'待统计':calls+' 次';
 $('model-tokens').textContent=pending?'待统计':run.tokens==null?'未记录':String(run.tokens)+(run.token_usage_complete===false?'（仅已知部分）':run.token_usage_complete===true?'':'（完整性未记录）');
 const fallback=run.model_error?({HTTPStatusError:'模型服务返回错误，本次使用情况请结合实际来源查看。',ReadTimeout:'模型响应超时，本次使用情况请结合实际来源查看。',ValueError:'模型输出未通过校验，已保留规则回退记录。',ModelBudgetExceeded:'模型调用达到本次预算，已保留回退记录。'}[run.model_error]||'模型调用出现异常，原因类型：'+run.model_error):run.model_source==='mixed'?'部分步骤使用了规则回退。':run.model_source==='rules'&&calls>0?'模型输出未能用于诊断，本次采用规则回退。':'';
 $('model-fallback').textContent=fallback;$('model-fallback').hidden=!fallback;
}
const list=value=>Array.isArray(value)?value:[];
const riskNames={read:'只读',write:'修改',medium:'中风险',high:'高风险',low:'低风险'};
const approvalNames={pending:'等待审批',approved:'已批准',declined:'已拒绝',expired:'已过期'};
const outcomeNames={exited:'未运行',running:'运行中',v1:'旧版本 v1',v2:'当前版本 v2',reachable:'可达',unreachable:'不可达',ro:'只读',rw:'可读写',blocked:'存在阻塞',clear:'无阻塞'};
function recordedTime(value){if(!value)return '未记录';const date=new Date(value);return Number.isNaN(date.getTime())?String(value):date.toLocaleString('zh-CN',{hour12:false});}
function renderHypotheses(run){
 const confirmed=list(run.diagnosed_causes).includes('participant_unavailable')?'<p class="hypothesis">已确认：参与者失联</p>':'';
 $('hypotheses').innerHTML=confirmed+list(run.hypotheses).map(h=>{
  const predictions=h.predictions??h.expected_probes;
  const probes=Array.isArray(predictions)?predictions.map(p=>[p.tool,p.outcomes??p.expected]):Object.entries(predictions||{});
  return `<article class="hypothesis-detail"><h4>${text(causeNames[h.cause]||h.cause)}</h4>${list(h.because).length?`<ul class="hypothesis-reasons">${h.because.map(reason=>`<li>${text(reason)}</li>`).join('')}</ul>`:'<p class="record-note">依据未记录。</p>'}<dl class="probe-predictions">${probes.map(([tool,outcomes])=>`<div><dt>${text(tool)}</dt><dd>${text((Array.isArray(outcomes)?outcomes:[outcomes]).map(outcome=>outcomeNames[outcome]||outcome).join(' / '))}</dd></div>`).join('')}</dl>${probes.length?'':'<p class="record-note">探测预期未记录。</p>'}</article>`;
 }).join('')||'<p class="empty">尚未保存候选原因。</p>';
}
function comparableArgs(value){return JSON.stringify(value,(_,item)=>item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.entries(item).sort(([a],[b])=>a.localeCompare(b))):item);}
function planTask(run,node){
 const matches=list(run.tasks).filter(task=>task.tool===node.tool&&task.kind===(node.kind||'act')&&comparableArgs(task.args||{})===comparableArgs(node.args||{}));
 const operationId=node.id&&run.id?run.id+':'+node.id:null;
 const exact=operationId?matches.filter(task=>task.product?.operation?.operation_id===operationId):[];
 const candidates=exact.length?exact:matches.filter(task=>!operationId||!task.product?.operation?.operation_id);
 return {task:candidates.length===1?candidates[0]:null,ambiguous:candidates.length>1};
}
function renderPlan(run){
 const nodes=list(run.plan);
 $('plan').innerHTML=nodes.length?`<ol class="plan-list">${nodes.map(node=>{
  const {task,ambiguous}=planTask(run,node);
  const taskState=task?(statusNames[task.status]||task.status||'未记录'):ambiguous?'存在多个同类任务，无法唯一匹配':'尚无对应任务记录';
  const dependencies=list(node.depends_on).map(id=>{const dependency=nodes.find(other=>other.id===id);return dependency?dependency.tool+'（'+id+'）':id;});
  return `<li class="plan-step"><div class="record-heading"><strong>${text(node.tool)}</strong><span class="risk-label">${text(riskNames[node.risk]||node.risk||'风险未记录')}</span></div><p>${text(node.reason||'理由未记录。')}</p><dl class="record-details"><div><dt>步骤</dt><dd>${text(node.id||'未记录')}</dd></div><div><dt>资源</dt><dd>${text(node.resource||'未记录')}</dd></div><div><dt>依赖</dt><dd>${text(dependencies.length?dependencies.join('、'):'无已记录依赖')}</dd></div><div><dt>任务状态</dt><dd>${text(taskState)}</dd></div>${task?.product?.operation?.state?`<div><dt>资源域返回</dt><dd>${text(statusNames[task.product.operation.state]||task.product.operation.state)}</dd></div>`:''}</dl>${Object.keys(node.args||{}).length?`<details><summary>步骤参数</summary><pre>${text(node.args)}</pre></details>`:''}</li>`;
 }).join('')}</ol>`:'<p class="empty">尚未保存恢复计划。</p>';
 const selected=[...list(run.events)].reverse().find(event=>['probe_selected','tool_selected'].includes(event.event));
 $('probe-choice').innerHTML=selected?`最近一次${selected.event==='probe_selected'?'探测':'工具'}选择：<strong>${text(selected.tool)}</strong><small>${text(typeof selected.reason==='string'?selected.reason:selected.reason?.reason||'理由未记录')} · ${text(recordedTime(selected.at))}</small>`:'尚未记录探测选择。';
 $('planning-history').innerHTML=list(run.planning_history).map(entry=>`<li><p>${text(entry.reason||'选择理由未记录。')}</p>${entry.tool?`<strong>${text(entry.tool)}</strong>`:''}${list(entry.facts).length?`<p class="record-note">更新证据：${text(entry.facts.join('、'))}</p>`:''}${entry.status?`<p class="record-note">任务返回：${text(statusNames[entry.status]||entry.status)}</p>`:''}${list(entry.ranking).length?`<details><summary>候选探测排序</summary><div class="table-wrap"><table><thead><tr><th>探测</th><th>得分</th><th>区分度</th><th>预计秒数</th></tr></thead><tbody>${entry.ranking.map(row=>`<tr><td>${text(row.tool)}</td><td>${text(row.score??'未记录')}</td><td>${text(row.discrimination??'未记录')}</td><td>${text(row.median_seconds??'未记录')}</td></tr>`).join('')}</tbody></table></div></details>`:''}</li>`).join('');
}
function approvalButtons(approval){return approval.status==='pending'?`<button class="approve" data-approval="${text(approval.id)}" data-decision="approve">批准此操作</button><button class="decline" data-approval="${text(approval.id)}" data-decision="decline">拒绝</button>`:'';}
function renderApprovals(run){
 const approvals=list(run.approvals);
 $('approvals').innerHTML=approvals.map(approval=>`<section class="approval ${approval.status==='pending'?'approval-pending':'approval-history'}"><div class="record-heading"><h4>${text(approval.tool)}</h4><span class="approval-state">${text(approvalNames[approval.status]||approval.status||'状态未记录')}</span></div><p>${text(approval.reason||'申请理由未记录。')}</p><dl class="record-details"><div><dt>申请时间</dt><dd>${text(recordedTime(approval.requested_at))}</dd></div><div><dt>决定时间</dt><dd>${text(approval.decided_at?recordedTime(approval.decided_at):approval.status==='pending'?'尚未决定':'未记录')}</dd></div></dl><details><summary>操作参数</summary><pre>${text(approval.args??{})}</pre></details>${approvalButtons(approval)}</section>`).join('')||'<p class="empty">尚未申请高风险操作。</p>';
 const pending=approvals.find(approval=>approval.status==='pending');
 const key=pending?run.id+':'+pending.id:null;
 if($('approval-dialog').open&&key!==lastApproval)$('approval-dialog').close();
 if(pending&&key!==lastApproval){lastApproval=key;$('approval-dialog-content').innerHTML=`<p>${text(pending.reason)}</p><p>操作：${text(pending.tool)}</p><p>参数：${text(pending.args)}</p>${approvalButtons(pending)}`;$('approval-dialog').showModal();}
 if(!pending){lastApproval=null;$('approval-dialog-content').innerHTML='';}
}
function renderRun(run){
 renderModel(run);
 if(typeof window.renderWorkbenchAccess==='function')window.renderWorkbenchAccess(run?.access_reconciliation);
 if(renderedId!==(run?.id??null)){renderedId=run?.id??null;lastApproval=null;if($('approval-dialog').open)$('approval-dialog').close();$('approval-dialog-content').innerHTML='';}
 if(!run){$('incident-title').textContent='尚未发起事故';$('incident-id').textContent='输入业务症状，开始收集证据。';$('incident-status').textContent='等待任务';renderHypotheses({});renderPlan({});renderApprovals({});$('facts').innerHTML='尚未收到证据。';['events','tasks','order-chart','raw'].forEach(id=>$(id).textContent='');$('actions').innerHTML='尚未提出修改。';$('takeovers').innerHTML='尚未发生接管。';$('business').innerHTML='业务验证尚未开始。';return;}
 $('incident-title').textContent=run.symptom;$('incident-id').textContent=run.id;$('incident-status').textContent=statusNames[run.status]||run.status;
 $('start').disabled=['running','awaiting_approval'].includes(run.status);if(run.error)error(run.error);
 renderHypotheses(run);renderPlan(run);renderApprovals(run);
 $('facts').innerHTML=(run.facts||[]).map(f=>`<div class="fact"><div>${text(factNames[f.key]||f.key)}<small>${text(factSource(f))}</small></div><div class="fact-value">${text(factValue(f))}</div></div>`).join('')||'尚未收到证据。';
 $('events').innerHTML=(run.events||[]).slice(-24).map(e=>`<li>${text(eventNames[e.event]||e.event)} ${text(e.tool||'')}<small>${text(typeof e.reason==='string'?e.reason:(e.reason?.reason||''))} ${text(new Date(e.at).toLocaleTimeString())}</small></li>`).join('');
 $('actions').innerHTML=(run.tasks||[]).filter(t=>t.kind==='act').map(t=>`<article class="action"><strong>${text(t.tool)}</strong>${text(statusNames[t.status]||t.status)}<small> ${text(statusNames[t.product?.operation?.state]||t.product?.operation?.state||'')}</small></article>`).join('')||'尚未提出修改。';
 const participantAlerts=(run.participant_health||[]).map(p=>`<article class="action"><strong>${text(p.confirmed&&p.participant_state==='unreachable'?'参与者失联，需要人工处理':'参与者状态待核实，需要人工核对')}</strong><small>${text(p.aic)}</small></article>`).join('');
 $('takeovers').innerHTML=participantAlerts+(run.events||[]).filter(e=>e.event.includes('takeover')||e.event.includes('resume')).map(e=>`<article class="action">${text(e.event)} ${text(e.reason)}</article>`).join('')||'尚未发生接管。';
 const summary=run.result?.order_observation;
 const serviceRecovered=run.result?.service_recovered??run.result?.business_recovered;
 const originalResolution=originalResolutionNames[run.result?.original_request_resolution]||((run.original_request_unknown||run.original_request_key)&&run.result?.manual_required?'原请求仍需人工核对。':'');
 const serviceLabel=run.result?.participant_manual_required?(serviceRecovered?'当前健康':'待核实'):(serviceRecovered?'已恢复':'待恢复');
 const participantNote=run.result?.participant_manual_required?'<p class="resolution-note">业务健康与参与者状态分别判断，当前事件仍需人工处理。</p>':'';
 $('business').innerHTML=summary?`<div class="business-facts"><span><strong>${text(run.result.business_recovered?'通过':'未通过')}</strong>业务验证</span><span><strong>${text(serviceLabel)}</strong>服务状态</span><span><strong>${text(summary.completed_workflows)}</strong>完整订单流程</span><span><strong>${text(summary.unknown)}</strong>本轮验证中未确认的请求</span><span><strong>${text(summary.duration_seconds)}s</strong>观察窗口</span></div>${originalResolution?`<p class="resolution-note">${text(originalResolution)}</p>`:''}${participantNote}`:`业务验证尚未完成。${participantNote}`;
 $('tasks').innerHTML=(run.tasks||[]).map(t=>`<tr><td>${text(t.tool)}<br><small>${text(t.logical_task_id)}</small></td><td>${text(t.kind)}</td><td>${text(statusNames[t.status]||t.status)}</td><td>${text(t.elapsed_ms==null?'—':t.elapsed_ms+' ms')}</td></tr>`).join('');
 const events=summary?.events||[];const maximum=Math.max(30,...events.map(e=>e.elapsed_seconds));
 $('order-chart').innerHTML=events.map(e=>{const x=10+e.elapsed_seconds/maximum*620;const y=e.outcome==='success'?25:e.outcome==='unknown'?60:95;const color=e.outcome==='success'?'#24715a':e.outcome==='unknown'?'#966414':'#ad4141';return `<circle cx="${x}" cy="${y}" r="3" fill="${color}"><title>${text(e.phase)} ${text(e.outcome)}</title></circle>`;}).join('');
 $('raw').textContent=JSON.stringify(run,null,2);
}
async function refresh(){try{const state=await api('/api/state');$('connection').textContent=state.connected?'参与者已连接':'参与者未连接';$('mode-note').textContent=state.mode==='local-aip-stdio'?'本地独立进程联调，使用 AIP 任务数据；平台发现与 AMQPS 另行验收。':state.mode==='unconfigured'?'先按部署文档启动本地业务和智能体，再发起排障。':'通过梧桐 AIP 群组协作。';$('artifacts').textContent=state.artifacts;
 $('model-config').textContent=state.model_config?.enabled?'已启用模型：'+state.model_config.model+'。实际参与情况见本次诊断记录。':state.model&&state.model!=='rules'?'已配置模型：'+state.model+'。实际参与情况见本次诊断记录。':'规则诊断。可按部署说明启用本地模型。';
 $('participants').innerHTML=(state.participants||[]).map(p=>`<div class="participant">${text(p.name||p.role||'参与者')}<small>${text(p.aic||p.executor_aic||'')}</small></div>`).join('')||'<p class="empty">等待连接各资源域。</p>';
 const run=selectedId&&state.incident?.id!==selectedId?await api('/api/incidents/'+encodeURIComponent(selectedId)):state.incident;
 $('start').disabled=!state.connected||(run&&['running','awaiting_approval'].includes(run.status));if(state.connection_error)error(state.connection_error);else if(!run?.error)error('');renderRun(run);
 }catch(e){$('connection').textContent='服务连接中断';error(e.message);}}
refresh();setInterval(refresh,1200);

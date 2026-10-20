"""Aggregate actual terminal cells; retain failures and avoid physical-write claims."""
import csv
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

BATCH=Path(__file__).resolve().parent
RUN=BATCH/('matrix-combined' if (BATCH/'matrix-combined').exists() else 'matrix-r1')
OUTPUT=BATCH/'publication'
METHODS=['MR','M0','M1','M2v2']
SCENARIOS=['F01','F02','F06','F07','F10']

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def median(rows,key):
    values=[row[key] for row in rows if row.get(key) is not None]
    return round(statistics.median(values),3) if values else None

def confirmed(row):
    return row['status']=='completed' and row['continuous_recovery_confirmed'] is True

def has_comparable_receipt_states(operation):
    for key in ['before','after']:
        value=operation.get(key)
        if value is None or (isinstance(value,dict) and set(value)=={'value'} and value['value'] is None):
            return False
    return True

def main():
    rows=json.loads((RUN/'results.json').read_text(encoding='utf-8'))
    expected={(s,m,r) for s in SCENARIOS for m in METHODS for r in range(1,4)}
    cells=[(row['scenario'],row['method'],row['repeat']) for row in rows]
    if len(rows)!=60 or len(set(cells))!=60 or set(cells)!=expected:
        raise RuntimeError('Report requires exactly the 60 planned terminal cells')
    if any(row['workload_seed']!=[101,202,303][row['repeat']-1]
           or row['precondition_pool_rebuilds']!=(row['repeat']-1)%3 for row in rows):
        raise RuntimeError('A terminal row lost its original seed or connection-pool precondition index')
    summary={}
    incidents={row['incident_id']:json.loads((RUN/'incidents'/f"{row['incident_id']}.json").read_text(encoding='utf-8')) for row in rows}
    for method in METHODS:
        group=[row for row in rows if row['method']==method]
        good=[row for row in group if confirmed(row)]
        tasks=[task for row in group for task in incidents[row['incident_id']]['tasks']]
        acts=[task for task in tasks if task['kind']=='act']
        operations=[(task.get('product') or {}).get('operation') or {} for task in acts]
        applied=[operation for operation in operations if operation.get('state')=='applied']
        comparable=[operation for operation in applied if has_comparable_receipt_states(operation)]
        model_requests=[request for row in group for request in incidents[row['incident_id']].get('model_requests',[])]
        summary[method]={
            'cells':len(group),'recovery_confirmed':len(good),'unconfirmed':len(group)-len(good),
            'strict_continuous_acceptance_passed':len(good),
            'fault_observed':sum(row['fault_observed'] is True for row in group),
            'median_seconds_all_terminal':median(group,'seconds'),'median_seconds_confirmed_only':median(good,'seconds'),
            'median_recovery_observed_seconds_confirmed_only':median(good,'recovery_observed_seconds'),
            'probes':sum(row['probes'] for row in group),
            'cross_domain_observation_calls':sum(row['cross_organization_calls'] for row in group),
            'median_declared_resource_domains_contacted':median(group,'resource_organizations_contacted'),
            'sensitive_blocking_session_observations':sum(row['sensitive_observations'] for row in group),
            'weighted_probe_cost':sum(row['weighted_probe_cost'] for row in group),
            'action_attempts':sum(row['modification_attempts'] for row in group),
            'successful_action_tasks':sum(row['modifications'] for row in group),
            'unrelated_high_privilege_attempts':sum(row['unnecessary_high_privilege_calls'] for row in group),
            'unrelated_successful_action_tasks':sum(row['unnecessary_modifications'] for row in group),
            'rejected_actions':sum(row['rejected_actions'] for row in group),
            'skipped_runbook_actions':sum(row['runbook_skipped_actions'] for row in group),
            'action_operation_states':dict(Counter(((task.get('product') or {}).get('operation') or {}).get('state','not_present') for task in acts)),
            'applied_receipts_equal_before_after':sum(operation['before']==operation['after'] for operation in comparable),
            'applied_receipts_unequal_before_after':sum(operation['before']!=operation['after'] for operation in comparable),
            'applied_receipts_without_comparable_before_after':len(applied)-len(comparable),
            'repeated_action_tool_attempts_within_incident':sum(sum(count-1 for count in Counter(
                task['tool'] for task in incidents[row['incident_id']]['tasks'] if task['kind']=='act').values()) for row in group),
            'model_calls':sum(row['model_calls'] for row in group),'max_model_calls_per_incident':max(row['model_calls'] for row in group),
            'model_failures':sum(row['model_failures'] for row in group),'disclosed_rule_fallbacks':sum(row['model_fallbacks'] for row in group),
            'model_request_wall_seconds_sum':round(sum(request.get('seconds',0) or 0 for request in model_requests),3),
            'model_request_wall_seconds_median':median(model_requests,'seconds'),
            'tokens':sum(row['tokens'] for row in group),
            'diagnosis_exact_matches':sum(row['diagnosis_exact_match'] is True for row in group),
        }
    bycell={(row['scenario'],row['method'],row['repeat']):row for row in rows}
    pairs=[]
    for scenario in SCENARIOS:
        for repeat in range(1,4):
            fixed=bycell[(scenario,'M0',repeat)]
            ranked=bycell[(scenario,'M2v2',repeat)]
            pairs.append({'scenario':scenario,'repeat':repeat,'both_confirmed':confirmed(fixed) and confirmed(ranked),
                'M0_seconds':fixed['seconds'],'M2v2_seconds':ranked['seconds'],
                'elapsed_ratio':round(ranked['seconds']/fixed['seconds'],6),
                'M0_recovery_observed_seconds':fixed['recovery_observed_seconds'],
                'M2v2_recovery_observed_seconds':ranked['recovery_observed_seconds'],
                'recovery_observed_ratio':round(ranked['recovery_observed_seconds']/fixed['recovery_observed_seconds'],6)
                    if confirmed(fixed) and confirmed(ranked) and fixed['recovery_observed_seconds'] else None,
                'M0_weighted_probe_cost':fixed['weighted_probe_cost'],'M2v2_weighted_probe_cost':ranked['weighted_probe_cost'],
                'M0_sensitive_observations':fixed['sensitive_observations'],'M2v2_sensitive_observations':ranked['sensitive_observations']})
    goodpairs=[pair for pair in pairs if pair['both_confirmed']]
    ratios=[pair['M2v2_seconds']/pair['M0_seconds'] for pair in goodpairs]
    median_ratio=round(statistics.median(ratios),6) if ratios else None
    observed_ratios=[pair['M2v2_recovery_observed_seconds']/pair['M0_recovery_observed_seconds']
                     for pair in goodpairs if pair['recovery_observed_ratio'] is not None]
    ratio_of_medians=round(summary['M2v2']['median_seconds_confirmed_only']/summary['M0']['median_seconds_confirmed_only'],6) if len(goodpairs)==15 else None
    mr504=[]
    mr_strict_verification_failures=[]
    mr_zero_success_verification_failures=[]
    zero_discrimination_stops=[]
    for row in rows:
        if row['method']!='M2v2' or confirmed(row):
            continue
        state=incidents[row['incident_id']]
        zero_rankings=[entry['ranking'] for entry in state.get('planning_history',[])
            if entry.get('ranking') and all(item.get('discrimination')==0 for item in entry['ranking'])]
        if zero_rankings:
            zero_discrimination_stops.append({'scenario':row['scenario'],'repeat':row['repeat'],
                'incident_id':row['incident_id'],'last_zero_ranking':zero_rankings[-1],
                'candidate_prediction_tool_sets':[list(h.get('predictions',{})) for h in state['hypotheses']],
                'actions_attempted':row['modification_attempts'],'status':row['status']})
    for row in rows:
        if row['method']!='MR' or confirmed(row):
            continue
        state=incidents[row['incident_id']]
        checks=[fact['value'] for task in state['tasks'] if task['tool']=='incident.verification'
            for fact in (task.get('product') or {}).get('facts',[]) if fact['key']=='order_observation']
        if checks and checks[-1].get('passed') is False and checks[-1].get('success',0)==0:
            mr_zero_success_verification_failures.append({'scenario':row['scenario'],'repeat':row['repeat'],
                'incident_id':row['incident_id'],
                'http_statuses':dict(Counter(event.get('http_status','not_available') for event in checks[-1].get('events',[]))),
                'final_verification':{key:value for key,value in checks[-1].items() if key not in {'events','state'}}})
        if checks and checks[-1].get('passed') is False and checks[-1].get('success',0)>0:
            mr_strict_verification_failures.append({'scenario':row['scenario'],'repeat':row['repeat'],
                'incident_id':row['incident_id'],'recovery_observed_seconds':row['recovery_observed_seconds'],
                'non_success_events':[{**event,'request_key_length':len(event.get('request_key',''))}
                    for event in checks[-1].get('events',[]) if event.get('outcome')!='success'],
                'max_operation_key_length':max((len(intent.get('operation_key','')) for intent in
                    checks[-1].get('state',{}).get('pending',[])+checks[-1].get('state',{}).get('completed',[])),default=0),
                'final_verification':{key:value for key,value in checks[-1].items() if key not in {'events','state'}}})
        categories=[fact['value'] for fact in state['facts'] if fact['key']=='symptom_category']
        statuses=[event.get('http_status') for fact in state['facts'] if fact['key']=='symptom_observation'
                  for event in fact['value'].get('events',[])]
        if 504 in statuses and 'write_error' in categories:
            mr504.append({'scenario':row['scenario'],'repeat':row['repeat'],'incident_id':row['incident_id'],
                          'http_statuses':statuses,'symptom_categories':categories,'error':row['error']})
    result={'status':'ALL_60_TERMINAL_CELLS_RECORDED','scope':'local-aip-stdio/native; no Wutong identities or paid API',
        'primary_metric':'strict acceptance: coordinator completed plus continuous 30-second / 10-complete-workflow confirmation; not physical repair success rate',
        'methods':summary,'paired_M2v2_vs_M0':{'confirmed_pairs':len(goodpairs),'median_paired_elapsed_ratio':median_ratio,
            'median_paired_recovery_observed_ratio':round(statistics.median(observed_ratios),6) if observed_ratios else None,
            'M0_weighted_probe_cost_on_confirmed_pairs':sum(pair['M0_weighted_probe_cost'] for pair in goodpairs),
            'M2v2_weighted_probe_cost_on_confirmed_pairs':sum(pair['M2v2_weighted_probe_cost'] for pair in goodpairs),
            'M0_sensitive_observations_on_confirmed_pairs':sum(pair['M0_sensitive_observations'] for pair in goodpairs),
            'M2v2_sensitive_observations_on_confirmed_pairs':sum(pair['M2v2_sensitive_observations'] for pair in goodpairs),
            'ratio_of_method_medians':ratio_of_medians,'criterion':1.3,
            'criterion_met':len(goodpairs)==15 and median_ratio<=1.3 and ratio_of_medians<=1.3},
        'MR_gateway_504_classification_failures':mr504,
        'MR_failed_final_verification_with_some_successful_requests':mr_strict_verification_failures,
        'MR_failed_final_verification_with_zero_successful_requests':mr_zero_success_verification_failures,
        'M2v2_failed_zero_discrimination_stops':zero_discrimination_stops,
        'failure_classes':dict(Counter(row['error'].split(':',1)[0] or row['status'] for row in rows if not confirmed(row))),
        'limitations':['seconds includes final domain verification, not pure repair latency',
            'Observation costs count declared resource domains, not verified separate legal companies',
            'Successful action tasks and applied operation receipts do not prove distinct physical mutations',
            'Before/after receipt comparisons refer to returned payload values; no uniform actual_changed metric exists',
            'MR classifies 502 but not 504 as entry errors; its affected failures are implementation defects, not proof of scheduling value',
            'Five existing fault families with three seeds; not evidence of generalization to unseen fault families',
            'All-cell low observation cost can result from early failed termination; compare cost on confirmed pairs separately',
            'MR final verification inherits pending intents from the initial quick symptom check; receipt resolution consumes slots in its fixed 30-request window, unlike the fresh M0 state',
            'One local small model and one Windows machine; no platform M2v2 matrix in this batch'],
        'recorded_at':datetime.now(timezone.utc).isoformat()}
    if (RUN/'continuation.json').exists():
        result['continuation']=json.loads((RUN/'continuation.json').read_text(encoding='utf-8'))
        result['attempt_accounting']={'unique_planned_cells':60,'terminal_cells':60,'actual_attempts':61,
            'executor_interrupted_attempts':1,'interrupted_attempt_is_algorithm_failure':False,
            'cost_totals_scope':'60 terminal attempts only; excludes the incomplete interrupted attempt',
            'complete_all_attempt_token_total':None,
            'incomplete_attempt_cost':'Partial incident/task/model evidence retained; complete token and time cost not reconstructable from terminal rows'}
    save(OUTPUT/'summary.json',result)
    save(OUTPUT/'results.json',rows)
    save(OUTPUT/'paired-M2v2-M0.json',pairs)
    save(OUTPUT/'failed-cases.json',[row for row in rows if not confirmed(row)])
    for name,data in [('results.csv',rows),('paired-M2v2-M0.csv',pairs)]:
        with (OUTPUT/name).open('w',newline='',encoding='utf-8-sig') as stream:
            writer=csv.DictWriter(stream,fieldnames=data[0].keys());writer.writeheader();writer.writerows(data)
    text=['# P5 本地 60 格实际结果','',
        '5 场景 × MR/M0/M1/M2v2 × 3 次。全部真实终态按原计划保留；本批使用独立 Windows 原生资源和本地 Qwen3-1.7B Q8_0，未占用云端身份。','',
        '60个唯一计划格、61次实际尝试：第30次被工具会话中断，保留原始partial事故/任务记录，接续只执行剩余31格。中断不计为算法失败。下表模型调用、token、动作和耗时汇总只覆盖60个终态，不含中断尝试的未完整成本；没有编造61次尝试的总token。','',
        '| 方法 | 严格持续验收通过 | 已通过例中位耗时（秒，含最终验证） | 业务首次恢复中位（秒） | 观察调用 | 敏感会话观察 | 加权观察成本 | 无关高权限尝试 | 模型调用 | token |',
        '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for method in METHODS:
        item=summary[method]
        text.append(f"| {method} | {item['recovery_confirmed']}/15 | {item['median_seconds_confirmed_only']} | {item['median_recovery_observed_seconds_confirmed_only']} | {item['probes']} | {item['sensitive_blocking_session_observations']} | {item['weighted_probe_cost']} | {item['unrelated_high_privilege_attempts']} | {item['model_calls']} | {item['tokens']} |")
    ratio_description=str(ratio_of_medians) if ratio_of_medians is not None else '未计算（未取得全部15个成功配对）'
    text+=['',f"M2v2/M0 的 {len(goodpairs)} 个成功配对：逐配对耗时比中位数 {median_ratio}，两方法中位耗时比 {ratio_description}；目标 ≤1.3，实际判定为 {result['paired_M2v2_vs_M0']['criterion_met']}。这里耗时包含最终约30秒独立业务验证，不能当成纯修复延迟。",'',
        f"同一批配对的业务首次恢复时间比中位数为 {result['paired_M2v2_vs_M0']['median_paired_recovery_observed_ratio']}。它从故障注入开始计时，单独报告，避免约30秒固定验证窗口掩盖实际修复等待。",'',
        f"MR 有 {len(mr504)} 例遇到 Windows Nginx 504，却被当前症状分类当成写错误；这些失败及无关动作必须作为已冻结实现的缺陷披露，不能拿它们证明证据驱动机制的优越性。",'',
        f"另有 {len(mr_strict_verification_failures)} 个 MR 未通过例在最终验证中已有成功请求，仍未满足完整30秒/10流程的严格门槛（明细见摘要）。它们不等于完全没有业务恢复。已核对的F06/F07首例各为29成功请求、1 unknown、9个完整流程：唯一unknown是验证第1次查询初始quick探测遗留pending intent的回执，HTTP404；request_key长54、operation_key长61，后续全200，因此不是云端长key/422问题。原失败判定保留。",'',
        '主表统计的是“协调者完成＋严格30秒/10完整流程验收通过”，不能直接称物理修好率。MR继承quick探测的pending intent，固定30次请求中还要完成回执查询；M0从新状态开始，没有这个额外请求槽位，因此这里存在方法相关的测量限制。未来公平比较需保留原未知请求，分别衡量原intent收敛及之后新的30秒健康窗口；本批不改测量实现或旧判定。','',
        'MR的F10三例在最终验证中均为0成功、30 unknown（503/404反复），与F06/F07的29成功/1回执404属于不同失败，不把它们都解释为验收窗口限制。M1其余9个未通过例均记录ModelBudgetExceeded，受本机小模型和预定token预算限制。','',
        f"M2v2 有 {len(zero_discrimination_stops)} 个未恢复例记录了剩余探测区分度全为0后停止。已查明的表锁例中，模型给出了阻塞候选，但候选分别只预测自己的工具；当前区分度计算需要两个候选都预测同一个工具，因而与稀疏预测契约不匹配。完整候选、排序和失败记录已保留，本批未中途修算法。",'',
        '无关高权限列是工具尝试次数，拒绝、跳过和成功任务另列机器摘要；不等于已经造成相同次数的实际资源修改。资源域数量也不等于已核实的法律组织数。','',
        '原始 modifications / unnecessary_modifications 分别为成功动作任务数及无关成功动作任务数。摘要另列 applied 回执前后值相同、不同、无法比较的数量，以及同一事故内同一动作工具的重复尝试；这些仍不能替代统一的实际资源变更次数。db.restore_writes 的 false→false 属于幂等回执，不按真实改变计。','',
        f"表中成本包括每方法全部15次尝试，提前失败也会少做观察，不能直接把较低总成本当作收益。在双方均恢复的 {len(goodpairs)} 个配对上，M0/M2v2 加权观察成本分别为 {result['paired_M2v2_vs_M0']['M0_weighted_probe_cost_on_confirmed_pairs']}/{result['paired_M2v2_vs_M0']['M2v2_weighted_probe_cost_on_confirmed_pairs']}；这只描述已恢复的子集。",'',
        '本批没有新增故障家族，因此不能据此声称“剧本外故障泛化”；原历史45格保持不变。原始事故、工作负载、日志、注入和源码冻结副本保留在本机同批目录。']
    if 'continuation' in result:
        text+=['','原执行器在29个终态后被工具会话中断，第30格记为 interrupted attempt。冻结源码不变，外置接续执行器按原索引/种子/连接池预置和轮转只跑剩余31格。上表为60个唯一格的终态；被中断尝试另存，不算算法失败，也没有覆盖原29条。']
    (OUTPUT/'README.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    experiment=json.loads((RUN/'experiment.json').read_text(encoding='utf-8'))
    save(OUTPUT/'source-bindings.json',{'source_sha256':experiment['source_sha256'],
        'method_definition_ids':experiment['method_definition_ids'],'sampling':experiment['sampling'],
        'budgets':experiment['budgets'],'held_out_instances':experiment['held_out_instances'],
        'local_model_artifact':experiment.get('local_model_artifact'),
        'bound_plan_sha256':hashlib.sha256((BATCH/'bound-plan.json').read_bytes()).hexdigest(),
        'result_sha256':hashlib.sha256((RUN/'results.json').read_bytes()).hexdigest(),
        'result_role':'60 unique terminal rows combined from preserved r1 and continued r2' if RUN.name=='matrix-combined' else 'single original batch',
        'continuation':result.get('continuation')})
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()

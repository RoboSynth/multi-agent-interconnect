import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const project = path.resolve(here, '../..');
const teamRoot = path.resolve(project, '../team-repository-multi-agent-interconnect');
const read = async rel => JSON.parse(await fs.readFile(path.join(project, rel), 'utf8'));
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const content = JSON.parse(await fs.readFile(path.join(here, 'content.json'), 'utf8'));
let frozen;
try { frozen=JSON.parse(await fs.readFile(path.join(here,'evidence.json'),'utf8')); }
catch(error) { if(error.code!=='ENOENT') throw error; }
const previous = await read('artifacts/technical-report-draft-20261017/evidence.json');
const image = await read('artifacts/new7-image-build-20261017/image-proof.json');
const cycle2 = await read('eval/results/platform/T07-scheduled-partial3-cycle2-20261017/summary.json');
if (image.captured_at !== content.cutoff_utc || !image.passed || !cycle2.healthy_business.passed) {
  throw new Error('Closed source facts or cutoff no longer match this development draft');
}
const sourceList = [
  ['S01','docs/高分方案_需求架构创新与任务_20261017.md','方案第3、4、7、10.2节。设计要求，不当作实测结果。'],
  ['S02','docs/P0完成审计_20261017.md','仅顶部本轮补证更新。下方初审历史不当作最新事实。'],
  ['S03','eval/results/local/M1-full-tools-pilot-20261017/report.md','首次完整工具M1，F01三方法各一次，M1失败保留。'],
  ['S04','eval/results/local/M1-full-tools-pilot-v2-20261017/report.md','共享route guard修复后，F01三方法各一次复验。'],
  ['S05','eval/results/platform/workbench-partial3-20261017/results.json','旧三参与域的只读启动及指定范围凭据扫描。'],
  ['S06','output/playwright/f12-cold-ui-20261017/results.json','真实UI、隔离冷容器、缺键与receipt404两分支。'],
  ['S07','eval/results/platform/container-postgres-mcp-20261017-order-fix-v2/results.json','真实三旧域ADP、生命周期与PG MCP观察。'],
  ['S08','integration/incident/high-score-registration-20261017/review-status-and-public-aic-20261017T120745Z.json','只引用已批准7、详情核实5、领证0的数量；不复制身份内容。'],
  ['S09','docs/contributions/README.md','四Issue与SDK PR审阅草稿，未发布。'],
  ['S10','eval/results/local/E1-native-20261017/analysis/summary.json','18例最终及独立核验，模型0，不能宣称正式ADP接管。'],
  ['S11','eval/results/local/E1-native-20261017/analysis/segmentation.json','A8连续加1控制器续验、B9连续，原中断保留。'],
  ['S12','output/database-bridge-20261017T085554Z/results.json','真实Postgres MCP stdio及受控动作，非平台群组。'],
  ['S13','output/docker-mcp-bridge-20261017T094625Z/results.json','真实第三方Docker MCP，早于当前scope补丁。'],
  ['S14','output/docker-scope-offline-20261017/results.json','精确project/service/name守卫与稳定状态适配，仅离线。'],
  ['S15','docs/evaluation.md','方法定义、1rps计时与组合版本边界。'],
  ['S16','eval/results/local/model-fairness-comparison-20261017/primary-rows.json','历史观察版M1，45主格的声明组合，不是单次统一冻结。'],
  ['S17','eval/results/platform/T07-scheduled-partial3-cycle2-20261017/summary.json','周期2自然触发，三旧域健康巡检，非故障恢复。'],
  ['S18','artifacts/new7-image-build-20261017/image-proof.json','断网/只读/无env无挂载临时probe。未启动新版身份。'],
  ['S19','docs/开发进度_高分方案.md','本轮最新开发与验收边界摘要。']
];
const sources = [];
for (const [id, relative_path, scope] of sourceList) {
  const bytes = await fs.readFile(path.join(project, relative_path));
  const original=frozen?.sources?.find(x=>x.id===id);
  if(original && original.sha256!==sha(bytes)) throw new Error(`Frozen original changed: ${id} ${relative_path}`);
  let team_copy={exists:false,same_bytes:false};
  try {
    const teamBytes=await fs.readFile(path.join(teamRoot,relative_path));
    team_copy={exists:true,relative_path,same_bytes:sha(teamBytes)===sha(bytes),sha256:sha(teamBytes)};
  } catch(error) { if(error.code!=='ENOENT') throw error; }
  sources.push({id,locator_basis:'original-development-project-root-relative',relative_path,sha256:sha(bytes),scope,team_copy});
}
const scenarios = previous.model_comparison.by_scenario;
const methods=['M0','M1','M2'];
const chartData = {
  schema_version:'incident-defense-charts/1.0',
  cutoff_utc:content.cutoff_utc,
  charts:{
    historical_recovery_medians:{
      title:'恢复估计中位数',unit:'秒',source_ids:['S15','S16'],
      categories:scenarios.map(x=>x.scenario),
      series:methods.map(name=>({name,values:scenarios.map(x=>x.methods[name].median_observed_seconds)})),
      limitations:['每格3次，1rps采样估计','历史M1仅自由观察','四场景v2与F06-v3组合，不是一次同源码冻结']
    },
    historical_probe_totals:{
      title:'探测总数',unit:'次',source_ids:['S15','S16'],categories:methods,
      series:[{name:'探测',values:methods.map(m=>previous.model_comparison.totals[m].probes)}],
      limitations:['总数来自45主格的组合版本','失败F06-v2另存，不从历史档案删除']
    },
    historical_model_tokens:{
      title:'模型token总数',unit:'token',source_ids:['S15','S16'],categories:methods,
      series:[{name:'token',values:methods.map(m=>previous.model_comparison.totals[m].tokens)}],
      limitations:['不是E1模型数据','M0没有模型调用']
    },
    E1_information_and_wire_bytes:{
      title:'E1-b交接字节中位数',unit:'UTF-8字节',source_ids:['S10','S11'],
      categories:['从头','完整历史','恢复包'],
      series:[
        {name:'完整IFC',values:[1084,4594,5223]},
        {name:'信息量',values:[325,3835,2388]}
      ],
      limitations:['每策略3次','恢复包兼容字段重复编码，实际wire更大','实际模型调用与token均0']
    }
  }
};
const evidence = {
  schema_version:'incident-defense-evidence/1.0',
  cutoff_utc:content.cutoff_utc,
  status:'closed_facts_frozen_format_outputs_not_generated',
  source_locator_notice:'Source paths and SHA refer to original development-project evidence. Do not assume identical paths or bytes exist in a team copy. team_copy is a read-only observation at preparation time, not a future guarantee.',
  public_derived_target:'deliverables/defense-content-development-20261017/',
  sources,
  data:{
    historical_comparison:{recorded_primary_cells:45,combined_versions:true,historical_M1_observation_only:true,preserved_F06_v2_failures:9,actual_model_calls:[0,99,114],model_tokens:[0,57335,122372],probe_counts:[108,99,99]},
    full_tool_M1_pilot:{scenario:'F01',transport:'local-aip-stdio',cases_per_method_per_revision:1,initial_completed:[true,false,true],initial_route_mcp_modify_invocations_M1:1,initial_M1_effect:'unknown',shared_guard_revision_completed:[true,true,true],M1_unnecessary_high_action:'db.restore_writes',formal_45_matrix:false},
    E1:{cases:18,final_checks_passed:18,independent_checks_passed:18,uninterrupted_cases:17,controller_continuation_cases:1,db_modify_invocations:18,duplicate_db_calls:0,old_fence_rejected:18,actual_model_calls:0,actual_model_tokens:0,formal_ADP_takeover_verified:false},
    platform:{participant_domain_roles:['application','database','verification'],identity_generation:'old-compatible',healthy_inspection_cycles:2,cycle1:{duration_seconds:30.003,requests:30,complete_flows:10},cycle2:{duration_seconds:cycle2.healthy_business.duration_seconds,requests:cycle2.healthy_business.requests,complete_flows:cycle2.healthy_business.completed_workflows,natural_trigger:cycle2.natural_scheduler_trigger,resource_recovery_actions:cycle2.resource_recovery_action_count,approval_count:cycle2.approval_count},resource_credential_count_in_checked_startup:0,accepted_as_24h:false},
    new7:{registry_approved:7,detail_public_identifiers_verified:5,certificates_issued:0,user_deferred_certificates:true,new_identity_consumers_started:false,image_offline_build_exit:image.build_exit_code,image_offline_probe_exit:image.temporary_probe_exit_code,fixed_source_hash_count:image.fixed_source_count,formal_target_preflight_run:false,formal_45_matrix_run:false},
    F12:{real_UI:true,transport:'local-aip-stdio',same_machine_cold_containers:true,missing_key:{service_recovered:true,original_request_resolved:false,status:'needs_attention',resolution:'manual',duration_seconds:30.016,complete_flows:10},receipt_404:{service_recovered:true,original_request_resolved:false,receipt_remains_404:true,replacement_original_key_created:false,duration_seconds:30,complete_flows:10}},
    contributions:{issue_drafts:4,public_issue_or_PR_published:false}
  },
  anonymity:{people:false,schools:false,full_AIC:false,organization_accounts:false,absolute_paths:false,provider:false,credentials:false,raw_logs:false},
  excluded_claims:['新版七角色已上线','正式平台接管通过','新正式45格已通过','单进程连续18例E1','E1模型token节省','24小时或7天连续在线','同机冷部署等于新机器T96','草稿等于已发布Issue或PR']
};
await fs.mkdir(path.join(here,'assets'),{recursive:true});
const screenshotRel='output/playwright/f12-cold-ui-20261017/unknown-missing-key.png';
const screenshot=await fs.readFile(path.join(project,screenshotRel));
await fs.writeFile(path.join(here,'assets/f12-unknown-missing-key.png'),screenshot);
evidence.assets=[{path:'assets/f12-unknown-missing-key.png',source_relative_path:screenshotRel,sha256:sha(screenshot),review:'Viewed at full size; no people, school, accounts, full AIC, secrets or absolute file paths visible.'}];
await fs.writeFile(path.join(here,'chart-data.json'),JSON.stringify(chartData,null,2)+'\n');
await fs.writeFile(path.join(here,'evidence.json'),JSON.stringify(evidence,null,2)+'\n');
const speech=['# 匿名答辩开发稿逐页讲稿','',`证据截止：${content.cutoff_utc}。本文件为内容准备稿，PPTX/PDF因官方演示runtime缺失尚未生成。`, ''];
for (const slide of content.slides) {
  speech.push(`## ${String(slide.number).padStart(2,'0')} ${slide.title.replaceAll('\n','')}`,'',slide.statement,'');
  speech.push(...(slide.body??[]).map(x=>x+'\n'));
  if(slide.steps) speech.push(slide.steps.map(x=>`${x.label}：${x.text}`).join('。')+'。','');
  if(slide.methods) speech.push(slide.methods.map(x=>`${x.name}：${x.text}`).join('。')+'。','');
  if(slide.table) speech.push(...slide.table.rows.map(row=>row.join('：')+'。\n'));
  if(slide.equation) speech.push(slide.equation,'');
  if(slide.next) speech.push(slide.next,'');
  speech.push(slide.notes,'','证据：'+slide.sources.map(id=>{const s=sources.find(s=>s.id===id);return `${id} ${s.relative_path}`;}).join('；'),'');
}
await fs.writeFile(path.join(here,'speaker-script.md'),speech.join('\n'));
console.log(JSON.stringify({slides:content.slides.length,sources:sources.length,charts:Object.keys(chartData.charts).length,asset_count:evidence.assets.length,cutoff_utc:content.cutoff_utc,pptx_generated:false,pdf_generated:false}));

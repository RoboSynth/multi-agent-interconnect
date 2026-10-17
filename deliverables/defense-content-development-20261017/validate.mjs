import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';

const here=path.dirname(fileURLToPath(import.meta.url));
const read=async p=>JSON.parse(await fs.readFile(path.join(here,p),'utf8'));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const c=await read('content.json'),e=await read('evidence.json'),d=await read('chart-data.json');
const checks=[];
const check=(name,passed,scope)=>checks.push({name,passed,scope});
check('exact_15_slides',c.slides.length===15&&c.slides.every((s,i)=>s.number===i+1),'Includes cover.');
check('cutoff_fixed',c.cutoff_utc==='2026-10-17T12:50:41.317Z'&&c.cutoff_utc===e.cutoff_utc&&c.cutoff_utc===d.cutoff_utc,'Latest closed image proof; excludes later cycles.');
check('page_purposes_and_notes',c.slides.every(s=>s.purpose&&s.notes&&s.statement&&s.sources.length),'Content coverage only, not visual layout.');
check('notes_locators',new Set(e.sources.map(s=>s.id)).size===19&&c.slides.every(s=>s.sources.every(id=>e.sources.some(x=>x.id===id))),'Original-project locators and SHA, not guaranteed team paths.');
check('origin_and_copy_scope',e.sources.every(s=>s.locator_basis==='original-development-project-root-relative'&&/^[a-f0-9]{64}$/.test(s.sha256)&&typeof s.team_copy.exists==='boolean'),'Team byte comparison is explicit, missing evidence stays missing.');
const m=e.data.historical_comparison;
check('historical_45_version_boundary',m.recorded_primary_cells===45&&m.combined_versions&&m.historical_M1_observation_only&&m.preserved_F06_v2_failures===9,'No renaming old M1 or single-freeze claim.');
const h=d.charts.historical_recovery_medians;
check('editable_chart_data',Object.keys(d.charts).length===4&&h.categories.length===5&&h.series.length===3&&h.series.every(s=>s.values.length===5),'4 literal datasets. No chart object exported yet.');
check('historical_probe_and_tokens',JSON.stringify(d.charts.historical_probe_totals.series[0].values)==='[108,99,99]'&&JSON.stringify(d.charts.historical_model_tokens.series[0].values)==='[0,57335,122372]','Probe reduction = 9/108 = 8.333%, rounds to 8.3%.');
const a=e.data.E1;
check('E1_segmented_and_zero_models',a.cases===18&&a.final_checks_passed===18&&a.independent_checks_passed===18&&a.uninterrupted_cases+a.controller_continuation_cases===18&&a.actual_model_calls===0&&a.actual_model_tokens===0&&a.duplicate_db_calls===0&&!a.formal_ADP_takeover_verified,'17 continuous + 1 controller continuation. Local AIP stdio.');
const wire=d.charts.E1_information_and_wire_bytes.series;
check('E1_information_not_wire_savings',JSON.stringify(wire[0].values)==='[1084,4594,5223]'&&JSON.stringify(wire[1].values)==='[325,3835,2388]'&&wire[0].values[2]>wire[0].values[1],'No claimed wire or model-token savings.');
const pilot=e.data.full_tool_M1_pilot;
check('full_tool_M1_failure_retained',pilot.cases_per_method_per_revision===1&&pilot.initial_completed[1]===false&&pilot.initial_route_mcp_modify_invocations_M1===1&&pilot.initial_M1_effect==='unknown'&&pilot.shared_guard_revision_completed.every(Boolean)&&pilot.M1_unnecessary_high_action==='db.restore_writes'&&!pilot.formal_45_matrix,'F01 only. Initial failure and extra high action retained.');
check('platform_partial_short_run',e.data.platform.healthy_inspection_cycles===2&&e.data.platform.identity_generation==='old-compatible'&&!e.data.platform.accepted_as_24h&&e.data.platform.cycle2.natural_trigger&&e.data.platform.cycle2.complete_flows===10,'Two healthy cycles; not new7, 24h or fault recovery.');
check('new7_offline_only',e.data.new7.registry_approved===7&&e.data.new7.certificates_issued===0&&e.data.new7.user_deferred_certificates&&!e.data.new7.new_identity_consumers_started&&!e.data.new7.formal_target_preflight_run&&!e.data.new7.formal_45_matrix_run,'Image build/probe does not imply deployed roles.');
check('F12_manual_intent',e.data.F12.missing_key.service_recovered&&!e.data.F12.missing_key.original_request_resolved&&e.data.F12.missing_key.duration_seconds===30.016&&e.data.F12.missing_key.complete_flows===10&&e.data.F12.receipt_404.receipt_remains_404&&!e.data.F12.receipt_404.replacement_original_key_created,'Values rechecked against original cases.0/cases.1 and receipt HTTP status.');
const texts=[JSON.stringify(c),JSON.stringify(e),JSON.stringify(d),await fs.readFile(path.join(here,'speaker-script.md'),'utf8')].join('\n');
const forbidden=[/BUPT/i,/Binah-Dev|RoboSynth/i,/1\.2\.156\.\d+(?:\.[A-Z0-9]+){4,}/i,/\b[A-Za-z]:[\\/]/,/file:\/\//,/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/];
check('anonymous_text_scope',forbidden.every(r=>!r.test(texts)),'Four text sources only. Screenshot has separate manual observation; no finished PPTX/PDF exists to scan.');
const asset=await fs.readFile(path.join(here,e.assets[0].path));
check('unchanged_reviewed_screenshot',sha(asset)===e.assets[0].sha256,'One actual view_image inspection this session, unchanged source bytes.');
for(const f of ['prepare.mjs','build.mjs','validate.mjs']){
  try {execFileSync(process.execPath,['--check',path.join(here,f)],{encoding:'utf8',stdio:'pipe'});check(`syntax_${f}`,true,'Node parser only. No module execution, API or render validation.');}
  catch {check(`syntax_${f}`,false,'Parser failed.');}
}
const issues=checks.filter(x=>!x.passed).map(x=>x.name);
const result={schema_version:'incident-defense-validation/1.0',status:issues.length?'content_check_failed':'CONTENT_SOURCE_READY_FORMAT_BLOCKED',cutoff_utc:c.cutoff_utc,content_checks_passed:issues.length===0,checks,issues,format_outputs:{pptx_generated:false,pdf_generated:false,artifact_tool_executed:false,slides_rendered:0,visual_QA:'not_run',native_PowerPoint_QA:'not_run',editable_objects_verified:false},runtime_blocker:{tool:'load_workspace_dependencies not in current ALL_TOOLS',package:'@oai/artifact-tool not resolvable; no bundle found in bounded known-cache inspection',substitute_installed:false},asset_review:{performed:true,method:'view_image full-size observation',images:1,not_OCR:true},final_submission_ready:false};
await fs.writeFile(path.join(here,'validation.json'),JSON.stringify(result,null,2)+'\n');
const payload=['README.md','content.json','speaker-script.md','chart-data.json','evidence.json','prepare.mjs','build.mjs','validate.mjs','validation.json','assets/f12-unknown-missing-key.png'];
const files=[];
for(const relative_path of payload){const bytes=await fs.readFile(path.join(here,relative_path));files.push({source_relative_path:relative_path,target_relative_path:'deliverables/defense-content-development-20261017/'+relative_path,bytes:bytes.length,sha256:sha(bytes)});}
await fs.writeFile(path.join(here,'source-ready.json'),JSON.stringify({schema_version:'incident-source-ready/1.0',status:result.status,source_directory:'artifacts/defense-development-20261017/',target_directory:'deliverables/defense-content-development-20261017/',cutoff_utc:c.cutoff_utc,payload_count:files.length,format_outputs_generated:false,original_report_unchanged:true,backend_or_team_modified:false,files},null,2)+'\n');
console.log(JSON.stringify({status:result.status,checks:checks.length,issues,payload_count:files.length,pptx:false,pdf:false}));
if(issues.length)process.exitCode=1;

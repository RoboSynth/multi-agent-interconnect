"""Project-local preparation from closed public projections. No resource/network calls."""
from pathlib import Path
import hashlib
import json
import shutil

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[1]
CUTOFF='2026-10-17T12:50:41.317Z'

def load(rel):
    return json.loads((PROJECT/rel).read_text(encoding='utf-8'))

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    frozen=load('artifacts/defense-development-20261017/evidence.json')
    historical=load('artifacts/technical-report-draft-20261017/evidence.json')
    assert frozen['cutoff_utc']==CUTOFF
    old={s['id']:s for s in frozen['sources']}
    sources=[]
    def prior(id,label,sid):
        s=old[sid]
        sources.append({'id':id,'label':label,'locator_basis':'original-development-project-root-relative','relative_path':s['relative_path'],'sha256':s['sha256'],'capture_basis':'frozen anonymized source index; current file is not assumed unchanged','scope':s['scope']})
    def actual(id,label,rel,scope):
        sources.append({'id':id,'label':label,'locator_basis':'original-development-project-root-relative','relative_path':rel,'sha256':digest(PROJECT/rel),'capture_basis':'closed original read in this preparation','scope':scope})
    prior('E01','正式三旧域兼容复验','S07')
    prior('E02','T07自然周期2','S17')
    prior('E03','F12真实工作台两分支','S06')
    prior('E04','历史45主格原始摘要','S16')
    prior('E05','完整工具M1首次F01验收','S03')
    prior('E06','共享guard修复后的F01复验','S04')
    prior('E07','本地E1最终与独立核验','S10')
    prior('E08','E1控制器中断与续验边界','S11')
    prior('E09','真实Postgres MCP','S12')
    actual('E10','真实阻塞会话守卫','output/database-blocker-bridge-20261017T091119Z/results.json','只提取拒绝/终止/重放的状态，不复制会话或身份内容。')
    prior('E11','真实Docker MCP','S13')
    prior('E12','Docker精确scope离线验证','S14')
    prior('E13','新版镜像断网临时验证','S18')
    actual('E14','33任务66双端access对账','eval/results/local/scheduling-native-20261017/access-reconciliation.json','逐任务对账计数，非平台后台访问量。')
    actual('E15','本地六类AMP聚合','eval/results/local/local-amp-report.json','六类聚合计数，非平台入库或任务RTT。')
    actual('E16','Fluent Bit六类路由','output/fluent-bit-local-20261017T093249Z/results.json','本地synthetic fixture，Kafka连接/平台入库未验收。')
    for i,(file,label) in enumerate([
        ('01-task-result-order.md','任务回执乱序Bug草稿'),
        ('02-mq-endpoint-docs.md','MQ端点文档改进草稿'),
        ('03-group-access.md','群组统计功能建议草稿'),
        ('04-discovery-alive.md','ADP筛选文档改进草稿'),
        ('PR-sdk-resumable.md','SDK PR审阅说明')],17):
        actual(f'E{i:02d}',label,'docs/contributions/'+file,'本地未发布草稿，不代表已提交、合并或社区采纳。')
    prior('E22','T93材料要求及数据口径','S01')
    actual('E23','28组历史素材盘点','artifacts/report-preparation-20261017/inventory.json','盘点时点早于本稿截止，旧pending不作为最新结论；只引用索引。')
    actual('E24','冻结匿名聚合输入','artifacts/defense-development-20261017/evidence.json','只读复用截止12:50:41.317Z已闭合数据，不复制整份原始记录。')
    actual('E25','历史逐次数据的匿名聚合输入','artifacts/technical-report-draft-20261017/evidence.json','历史M1仅自由观察，组合版本；这里只提取数值和版本标识。')
    access=load('eval/results/local/scheduling-native-20261017/access-reconciliation.json')
    amp=load('eval/results/local/local-amp-report.json')
    route=load('output/fluent-bit-local-20261017T093249Z/results.json')
    blocker=load('output/database-blocker-bridge-20261017T091119Z/results.json')
    safe={
        'schema_version':'t93-supporting-data/1.0','cutoff_utc':CUTOFF,
        'closed':frozen['data'],
        'historical_model':historical['model_comparison'],
        'E1b':historical['E1a_E1b']['E1b'],
        'access':{k:access[k] for k in ['native_start_tasks','expected_access_records','actual_access_records','missing_records','extra_records','passed']},
        'amp':{'unique_records':amp['unique_records'],'log_types':amp['log_types'],'invalid_records':amp['invalid_records'],'platform_ingestion_verified':False},
        'fluent_bit':{'routes_observed':route['routes_observed'],'log_ids_preserved':route['log_ids_preserved'],'synthetic_local_fixture':route['synthetic_local_fixture'],'kafka_connected':route['kafka_connected'],'platform_ingestion_tested':route['platform_ingestion_tested'],'passed':route['passed']},
        'blocker':{'passed':blocker['passed'],'without_approval':blocker['checks']['without_approval']['status'],'non_blocking_target':blocker['checks']['non_blocking_target']['status'],'controlled_termination':blocker['checks']['controlled_termination']['operation']['state'],'waiter_released':blocker['checks']['waiter_released']['completed'],'duplicate':blocker['checks']['duplicate']['operation']['state']},
        'source_policy':'Only selected fields and anonymous aggregates. No original messages, identity values, credentials, personal/provider data or raw logs copied.',
        'source_locator_notice':'Relative paths and SHA identify original development-project evidence at the stated capture, not guaranteed same-path files in a team copy.',
        'sources':sources,
        'unavailable':{'platform_backend_screenshot':True,'platform_backend_visit_curve':True,'public_issue_PR_links':True,'human_interviews':True,'independent_user_feedback':True,'new_machine_T96':True,'new7_formal_45_matrix':True,'formal_platform_takeover':True,'continuous_24h':True}
    }
    assert safe['access']['passed'] and safe['blocker']['passed'] and safe['fluent_bit']['passed']
    assert sum(safe['amp']['log_types'].values())==safe['amp']['unique_records']
    (HERE/'assets').mkdir(exist_ok=True)
    screenshot='output/playwright/f12-cold-ui-20261017/unknown-missing-key.png'
    target=HERE/'assets/f12-unknown-missing-key.png'
    shutil.copyfile(PROJECT/screenshot,target)
    safe['assets']=[{'relative_path':'assets/f12-unknown-missing-key.png','source_relative_path':screenshot,'sha256':digest(target),'review_basis':'Actual image inspected this session; final embedded page also requires visual QA.'}]
    (HERE/'data.json').write_text(json.dumps(safe,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'sources':len(sources),'assets':len(safe['assets']),'cutoff_utc':CUTOFF,'raw_logs_copied':False}))

if __name__=='__main__':main()

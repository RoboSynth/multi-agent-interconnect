from pathlib import Path
import json

HERE=Path(__file__).resolve().parent
path=HERE/'PLAN_expanded.json'
pages=json.loads(path.read_text(encoding='utf-8'))
pages[-1]['blocks'][2]['text']='先在运维教学和实验环境使用现有订单系统，讲清入口、数据库、应用连接与业务结果的关系。试点接入有明确负责人和审批流程的资源，按固定故障案例验收。新增资源时补齐工具描述、权限规则、状态检查和操作记录。'
pages[-1]['blocks'][3]['text']='下一步先修复测试准备对象和启动问题，整理两套代码差异，再扩充中断、接管版本和原请求结果测试。在同一故障、负载和统计时段下，对比预设规则、检查评分和模型辅助方式的恢复时间、检查次数与工具成本。跨主机接管需统一操作记录和接管版本的管理，再部署验收。'
path.write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

path=HERE/'REPORT_expanded.json'
pages=json.loads(path.read_text(encoding='utf-8'))
for page in pages:
    blocks=page['blocks']
    for i in range(len(blocks)-1):
        if blocks[i]['type']=='diagram' and blocks[i+1]['type']=='note' and 'ledger.py:55–140' in blocks[i+1]['text']:
            blocks[i]['caption']+='\n'+blocks[i+1]['text']
            del blocks[i+1]
            break
path.write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

path=HERE/'expand_evidence.py'
source=path.read_text(encoding='utf-8').replace('按该次页面显示区间','9月9日00:00至10月29日22:00')
path.write_text(source,encoding='utf-8')

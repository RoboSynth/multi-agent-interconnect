"""Summarize preserved runs without reclassifying or overwriting their outcomes."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def classify(directory):
    s = load(directory / 'summary.json')
    if 'total_cases' in s:
        return {'suite': '故障恢复', 'checks': s['total_cases'], 'passed': s['passed_cases'],
                'failed': s['total_cases'] - s['passed_cases'], 'fatal': s['fatal_error'],
                'cleanup': s['processes_stopped'] and not s['ports_still_open'],
                'outcomes': s['actual_outcome_counts']}
    if s.get('suite') == 'consistency':
        return {'suite': '并发一致性', 'checks': s['total'], 'passed': s['passed'],
                'failed': len(s['failed']), 'fatal': s['setup_error'],
                'cleanup': s['processes_stopped'] and s['test_ports_closed'],
                'aip_requests': s['requests']}
    return {'suite': '协议与边界', 'checks': s['checks'], 'passed': s['passed'],
            'failed': s['failed'], 'fatal': s['fatal'],
            'cleanup': s['all_child_processes_exited'], 'http_requests': s['requests']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--final', nargs=3, required=True, help='Protocol, consistency, resilience directories')
    parser.add_argument('--audit', required=True)
    args = parser.parse_args()
    final = [Path(p).resolve() for p in args.final]
    audit_path = Path(args.audit).resolve()
    output = audit_path.parent
    runs = []
    for directory in sorted((ROOT / 'artifacts').iterdir()):
        if not (directory / 'summary.json').exists():
            continue
        row = {'directory': str(directory), 'selected_final': directory.resolve() in final,
               **classify(directory)}
        if (directory / 'HARNESS_REVIEW.json').exists():
            row['harness_review'] = load(directory / 'HARNESS_REVIEW.json')
        runs.append(row)
    selected = [r for r in runs if r['selected_final']]
    audit = load(audit_path)
    bundle = {'created_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'runs': runs, 'final_directories': [str(p) for p in final],
              'independent_audit': str(audit_path),
              'prior_audit_preserved': str(ROOT / 'artifacts' / 'campaign-20261017-final-v1' / 'AUDIT.json'),
              'total_check_executions': sum(r['checks'] for r in runs),
              'final_checks': sum(r['checks'] for r in selected),
              'final_passed': sum(r['passed'] for r in selected),
              'final_failed': sum(r['failed'] for r in selected),
              'current_services_sha256': hashlib.sha256((ROOT / 'services.py').read_bytes()).hexdigest()}
    (output / 'CAMPAIGN.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 跨系统故障协作：大量测试结果', '', f'生成时间：{bundle["created_at"]}', '',
             '## 最终版本复测', '',
             '| 测试方向 | 场景/断言数 | 符合预期 | 失败 | 清理声明 |',
             '|---|---:|---:|---:|---|']
    for row in selected:
        lines.append(f'| {row["suite"]} | {row["checks"]} | {row["passed"]} | {row["failed"]} | {row["cleanup"]} |')
    lines += ['', '场景与断言不是独立故障种类；重复和种子变化用于检查稳定性。',
              '符合预期包含应当阻断或转人工的情况，不代表全部自动恢复。', '',
              '## 发现并修复的问题', '',
              '1. 部分不完整的 Start 及非法业务 JSON 导致 HTTP 500：补充任务 ID 生成与受控输入拒绝。',
              '2. 在途任务覆盖取消终态：业务等待结束和异常分支均保留已有终态。取消不承诺撤销已提交的业务动作。',
              '3. 不同会话可读取或取消同一任务：增加任务与会话、声明发送方的一致性检查。这不是密码学身份认证。',
              '4. 输入拒绝初版的 Accepted→Rejected 历史不符协议：改为从无直接创建 Rejected。', '',
              '原始一致性套件有30项断言误报：重复Complete允许增加审计历史，业务状态/产物/修改次数应保持。'
              '已独立核对原始响应并纠正断言；原始结果、HARNESS_REVIEW.json和源码快照均保留。', '',
              '## 首轮及中间轮次记录', '',
              '| 目录 | 阶段 | 检查数 | 符合预期 | 原始失败数 |',
              '|---|---|---:|---:|---:|']
    for row in runs:
        lines.append(f'| {Path(row["directory"]).name} | {"最终" if row["selected_final"] else "早期/中间"} | '
                     f'{row["checks"]} | {row["passed"]} | {row["failed"]} |')
    lines += ['', '首轮韧性测试曾出现一次端口连接成功的清理疑点；原始summary仍保留失败gate，'
              '后续显式绑定不同源端口的复查及独立审计单独保留，不将原记录改写为通过。', '',
              '最终独立审计v1曾短暂观察到一个已记录退出的进程编号仍活跃；历史原因无法追溯证明。'
              'v1完整保留，v2复查该编号已不存在、各实验端口明确拒绝连接，未终止任何不属于实验的进程。', '',
              '独立审计仍有两项非关键证据限制：一致性与韧性归档中的AIP响应保留了JSON和关联ID，'
              '没有逐条保存数字HTTP状态码。客户端执行时检查状态，但归档无法独立重建其精确数值。', '',
              '## 能够支持的结论', '',
              '- 已知的地址错误、模拟数据库暂停及其组合能够在本机真实服务间闭环恢复。',
              '- 处理智能体退出并有同能力替代者时，动态发现可继续；固定寻址可能阻断。',
              '- 并发修改依靠版本检查避免重复写入；不认识的故障停止并转人工。',
              '- 底层应用或数据库进程真正退出时，目前会阻断；人工重启后的验证不算自动恢复能力。', '',
              '## 证据边界', '',
              '采用官方 ACPs SDK v2.2.0、本机独立进程、HTTP 和 SQLite；未调用付费API。'
              '诊断仍是规则，本地目录不等于官方ADP，尚未接入梧桐、mTLS、正式AIC或大模型。'
              '测试不证明行业创新性、未知故障诊断能力、跨组织隔离或真实生产性能。', '',
              '## 最终证据目录', '']
    lines += [f'- {p}' for p in final]
    lines += ['', f'独立审计：{audit_path}', '',
              f'累计检查执行数（含早期失败和复测）：{bundle["total_check_executions"]}。', '']
    (output / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({k: v for k, v in bundle.items() if k != 'runs'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

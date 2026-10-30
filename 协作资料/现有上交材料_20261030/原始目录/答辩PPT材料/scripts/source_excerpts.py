"""Export exact short excerpts without changing source files."""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repo", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
sdk = "vendor/ACPs-community/acps-sdk/acps_sdk/aip/"
selections = [
    (sdk + "resumable/ledger.py", 128, 141, "ledger_128-141_接管版本.md", "为同一协调任期生成递增的接管版本，并拒绝过期任期。"),
    (sdk + "resumable/ledger.py", 213, 222, "ledger_213-222_已执行跳过.md", "检查fence与参数摘要；已执行的操作返回缓存结果，避免再次发出修改。"),
    (sdk + "_task_order.py", 16, 26, "task_order_16-26_状态合并.md", "保留终态，按发送方状态时间阻止迟到结果回退状态。"),
    ("acps_mcp_bridge/policy.py", 70, 88, "policy_70-88_写入与审批检查.md", "校验参数与风险类型，并要求写入控制字段和高风险审批。"),
]
dest = args.output / "1-开源改造/代码片段"
dest.mkdir(parents=True, exist_ok=True)
for path, start, end, filename, purpose in selections:
    content = (args.repo / path).read_text(encoding="utf-8-sig").splitlines()
    excerpt = content[start - 1:end]
    assert len(excerpt) == end - start + 1 <= 20
    text = f"# {Path(filename).stem}\n\n源文件：`{path}`，第 {start}–{end} 行。\n\n{purpose}\n\n```python\n" + "\n".join(excerpt) + "\n```\n"
    (dest / filename).write_text(text, encoding="utf-8")
print(f"Exported {len(selections)} source excerpts, each at most 20 lines.")

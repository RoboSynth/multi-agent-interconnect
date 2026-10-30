"""Read-only source inventory. All paths are supplied by the operator.

Usage: python source_inventory.py --repo REPO --cache PRIVATE_CACHE --output OUTPUT
The cache must contain upstream-3985c13.zip, pr13.diff and pr14.diff.
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

UPSTREAM = "3985c1330209f075c124669cc9d31f0e75448140"
SKIP = {"__pycache__", ".git", ".venv", "node_modules", "dist", "build", ".pytest_cache"}


def eligible(path):
    return not any(p in SKIP or p.endswith(".egg-info") for p in path.parts) and path.suffix not in {".pyc", ".pyo"}


def lf(data):
    return data.replace(b"\r\n", b"\n")


def lines(path):
    return len(lf(path.read_bytes()).splitlines())


def git(*args, cwd=None):
    result = subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=cwd, capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout.decode("utf-8", errors="replace")


def kind(path):
    if "tests" in path.parts or path.name.startswith("test_"):
        return "测试"
    if "examples" in path.parts:
        return "示例"
    return "运行时" if path.suffix == ".py" and path.parts[0] == "acps_sdk" else "文档"


def purpose(path):
    names = {
        "_task_order.py": "按发送方状态时间合并任务结果并保护终态",
        "access_status.py": "从结构化任务结果提取访问状态",
        "aip_group_leader.py": "接入状态排序、事件监听和群组访问记录",
        "aip_group_partner.py": "接入群组访问记录及任务处理异常结果",
        "aip_group_auth.py": "为幂等群组权限请求增加有限重试与超时控制",
        "aip_group_runtime.py": "调整参与者与群组运行时清理顺序",
        "group_access.py": "按任务首次Start记录访问并贯穿关联标识",
        "_message_tap.py": "增加按任务或会话选择关联标识的辅助函数",
        "durable_access.py": "用持久化outbox保留进程中断后的未确认访问结果",
        "message_emitter.py": "按解析后的文件路径串行写入消息记录",
        "journal.py": "持久保存意图、尝试和原始任务事件",
        "ledger.py": "按操作标识保存效果并检查fence与不确定结果",
        "partner.py": "将任务接续参数接入资源侧账本执行",
        "takeover.py": "发现并确认备用参与者后推进接管版本",
        "resumable_group_demo.py": "演示可接续群组任务的用法",
        "test_resumable.py": "覆盖账本幂等、接管和结果持久化",
        "test_task_ordering.py": "覆盖迟到状态与合法较新状态合并",
        "test_message_emitter_concurrency.py": "覆盖并发消息写入",
    }
    if path.name in names:
        return names[path.name]
    if path.as_posix() == "acps_sdk/amp/__init__.py":
        return "导出持久访问日志及完整性异常接口"
    if path.suffix == ".md":
        return "说明新增接口、使用条件与验证范围"
    if path.name == "__init__.py" and "resumable" in path.parts:
        return "导出可接续任务组件"
    if kind(path) == "测试":
        return "补充相关功能回归用例"
    return "见该文件差异及代码位置；未按文件名推定功能"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, cache, output = args.repo.resolve(), args.cache.resolve(), args.output.resolve()
    dest = output / "1-开源改造"
    dest.mkdir(parents=True, exist_ok=True)
    comparison = Path(tempfile.mkdtemp(prefix="source-compare-", dir=cache))
    upstream = comparison / "upstream-sdk-lf"
    current = comparison / "current-sdk-lf"
    upstream.mkdir(exist_ok=True)
    current.mkdir(exist_ok=True)
    archive = cache / "upstream-3985c13.zip"
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            parts = Path(info.filename).parts
            if len(parts) < 3 or parts[1] != "acps-sdk" or info.is_dir():
                continue
            relative = Path(*parts[2:])
            if ".." in relative.parts or not eligible(relative):
                continue
            target = upstream / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(lf(z.read(info)))
    source_sdk = repo / "vendor/ACPs-community/acps-sdk"
    for path in source_sdk.rglob("*"):
        relative = path.relative_to(source_sdk)
        if path.is_file() and eligible(relative):
            target = current / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(lf(path.read_bytes()))
    upstream_files = {p.relative_to(upstream): p for p in upstream.rglob("*") if p.is_file()}
    current_files = {p.relative_to(current): p for p in current.rglob("*") if p.is_file()}
    prs, pr_summary = {}, {}
    for number in (13, 14):
        patch = cache / f"pr{number}.diff"
        pr_tree = comparison / f"pr{number}-sdk"
        shutil.copytree(upstream, pr_tree, dirs_exist_ok=True)
        apply = subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "-p2", str(patch)], cwd=pr_tree, capture_output=True)
        if apply.returncode:
            raise RuntimeError(f"PR{number} could not be reconstructed against the normalized upstream SDK")
        rows = []
        for line in git("apply", "--numstat", str(patch)).splitlines():
            added, removed, name = line.split("\t", 2)
            if not name.startswith("acps-sdk/"):
                continue
            relative = Path(name.removeprefix("acps-sdk/"))
            prs.setdefault(relative, []).append((number, pr_tree / relative))
            rows.append({"path": relative.as_posix(), "added": int(added), "removed": int(removed)})
        pr_summary[str(number)] = {"files": len(rows), "added": sum(r["added"] for r in rows), "removed": sum(r["removed"] for r in rows), "paths": rows}
    changes, unchanged, bindings = [], [], []
    for relative in sorted(set(upstream_files) | set(current_files)):
        before, after = upstream_files.get(relative), current_files.get(relative)
        if after:
            raw = (source_sdk / relative).read_bytes()
            bindings.append({"path": "vendor/ACPs-community/acps-sdk/" + relative.as_posix(), "sha256": hashlib.sha256(raw).hexdigest(), "physical_lines": lines(after)})
        if before and after and before.read_bytes() == after.read_bytes():
            if kind(relative) == "运行时":
                unchanged.append({"path": relative.as_posix(), "lines": lines(after)})
            continue
        diff = git("diff", "--no-index", "--numstat", "--no-renames", str(before) if before else "/dev/null", str(after) if after else "/dev/null")
        entries = [row.split("\t", 2) for row in diff.splitlines() if row]
        if len(entries) != 1:
            raise RuntimeError(f"Unexpected diff for {relative}")
        added, removed, _ = entries[0]
        related = prs.get(relative, [])
        exact = [n for n, p in related if after and p.exists() and lf(p.read_bytes()) == after.read_bytes()]
        status = "当前文件与" + "/".join(f"#{n}" for n in exact) + "内容一致" if exact else "同路径已有PR；当前文件仍有后续差异" if related else "未在PR13/14中找到"
        changes.append({"路径": relative.as_posix(), "类别": "新增" if not before else "删除" if not after else "修改", "新增行": int(added), "删除行": int(removed), "文件类型": kind(relative), "改动目的": purpose(relative), "对应PR": "/".join(f"#{n}" for n, _ in related) or "无", "是否已提交上游": status})
    with (dest / "改造清单.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(changes[0])); writer.writeheader(); writer.writerows(changes)
    modules = {
        "acps_mcp_bridge": "身份、策略、审批、审计与MCP调用桥接",
        "acps-mcp-bridge": "早期桥接演示入口，单列不当作当前核心模块",
        "incident": "事故协调、候选选择、故障观察与恢复流程",
        "business": "订单业务及观察负载",
        "domains": "各资源域执行体、描述与受控工具",
        "eval": "场景评估与结果统计",
        "ops": "部署后巡检、接入体检和运行维护",
        "integration": "真实平台接入探测与接管集成",
        "deploy": "部署、服务入口与云端采集",
        "工作台": "工作台服务及静态界面（表内仅计Python）",
        "tools": "打包、分析及开发辅助工具",
        "tests": "仓库公共测试；不重复分摊到业务模块",
        "根目录其他Python": "运行、验证和压力脚本",
    }
    module_rows = []
    for module, responsibility in modules.items():
        if module == "工作台":
            paths = [repo / "workbench_server.py", repo / "demo_server.py"]
        elif module == "根目录其他Python":
            paths = [p for p in repo.glob("*.py") if p.name not in {"workbench_server.py", "demo_server.py"}]
        else:
            paths = list((repo / module).rglob("*.py"))
        paths = sorted(p for p in paths if p.is_file() and eligible(p.relative_to(repo)))
        module_rows.append({"模块": module, "职责": responsibility, ".py文件数": len(paths), "行数": sum(lines(p) for p in paths), "其中测试行数": sum(lines(p) for p in paths if "tests" in p.relative_to(repo).parts or p.name.startswith("test_"))})
        for path in paths:
            bindings.append({"path": path.relative_to(repo).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "physical_lines": lines(path)})
    with (dest / "项目自研模块.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(module_rows[0])); writer.writeheader(); writer.writerows(module_rows)
    receipt = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(), "source_base_commit": git("rev-parse", "HEAD", cwd=repo).strip(),
        "source_includes_working_tree": True, "upstream_commit": UPSTREAM,
        "upstream_archive_url": f"https://codeload.github.com/AIP-PUB/ACPs-community/zip/{UPSTREAM}",
        "upstream_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "line_method": "physical lines including comments and blank lines; CRLF normalized to LF; generated artifacts excluded",
        "changed_files": len(changes), "added": sum(r["新增行"] for r in changes), "removed": sum(r["删除行"] for r in changes),
        "unchanged_runtime_files": len(unchanged), "unchanged_runtime_lines": sum(r["lines"] for r in unchanged),
        "unchanged_runtime": unchanged, "pr_diffs": pr_summary, "modules": module_rows,
        "source_files": bindings,
    }
    (dest / "统计依据.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("changed_files", "added", "removed", "unchanged_runtime_files", "unchanged_runtime_lines")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

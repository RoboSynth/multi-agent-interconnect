"""Publish an explicit four-case preparation selection, with path-only projections."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
ROOT = HERE / "publication-checkout"
DEST = ROOT / "evidence/access-validation-prep-20261019"
SOURCE = "a4d71e83444228a71499a75c932a2b9e7ba678f1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    summary = json.loads((HERE / "plan-preparation/prepared-summary.json").read_bytes())
    validation = json.loads((HERE / "plan-preparation/validation-result.json").read_bytes())
    assert summary["source_commit"] == validation["source_commit"] == SOURCE
    assert validation["prepared_summary_sha256"] == sha((HERE / "plan-preparation/prepared-summary.json").read_bytes())
    assert summary["plan_count"] == 4 and not validation["real_project_or_platform_or_model_or_faults_executed"]
    selection = json.loads((HERE / "plan-preparation/publication-files.json").read_bytes())
    assert selection["prepared_summary_sha256"] == validation["prepared_summary_sha256"]
    names = set(selection["files"])
    assert len(names) == selection["file_count"] == 25
    for name, digest in selection["files"].items():
        assert (name in {"run_authorized.py", "run_f10.py", "test_batch_guards.py"}
                or name.startswith("plan-preparation/") and Path(name).suffix in {".json", ".md", ".log", ".py"})
        assert ".." not in Path(name).parts and not Path(name).is_absolute()
        assert sha((HERE / name).read_bytes()) == digest
    names.update({"plan-preparation/publication-files.json", "review/four-case-preparation-review.md"})
    roots = [("source-checkout", HERE / "checkout"), ("publication-checkout", ROOT),
             ("batch", HERE), ("account-home", Path.home())]
    replacements = {}
    for label, path in roots:
        variants = {str(path), path.as_posix()}
        variants.update(value.encode("gbk", errors="replace").decode("utf-8", errors="replace") for value in list(variants))
        for raw in variants:
            replacements[raw] = "[" + label + "]"
            replacements[json.dumps(raw, ensure_ascii=True)[1:-1]] = "[" + label + "]"

    def project(value):
        for old, new in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
            value = value.replace(old, new)
        labels = "|".join(re.escape("[" + label + "]") for label, _ in roots)
        return re.sub(r"(?:" + labels + r")([^\s\"'<>]*)",
                      lambda match: re.sub(re.escape(chr(92)) + r"+(?=[A-Za-z_.-])", "/", match.group()), value)

    def walk(value):
        if isinstance(value, str):
            return project(value)
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return value

    # This destination contains only the explicit uncommitted publication copy;
    # original evidence remains in HERE and prior scan receipts are preserved.
    DEST.mkdir(parents=True, exist_ok=True)
    bindings = []
    for name in sorted(names):
        source, target = HERE / name, DEST / name
        raw = source.read_bytes()
        if source.suffix == ".py":
            published = raw
        elif source.suffix == ".json":
            original = json.loads(raw)
            projected = walk(original)
            published = (json.dumps(projected, ensure_ascii=False, indent=2) + "\n").encode() if projected != original else raw
        else:
            decoded = raw.decode("utf-8-sig")
            projected = project(decoded)
            published = projected.encode("utf-8") if projected != decoded else raw
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(published)
        bindings.append(dict(path=name, original_sha256=sha(raw), published_sha256=sha(published),
                             original_bytes=len(raw), published_bytes=len(published), path_projection_applied=raw != published))
    receipt = dict(schema_version="four-case-preparation-publication/1", prepared_at_utc=datetime.now(timezone.utc).isoformat(),
                   status="PREPARED_NOT_AUTHORIZED_NOT_EXECUTED", source_commit=SOURCE,
                   batch_plans_sha256=summary["batch_plans_sha256"],
                   prepared_summary_original_sha256=sha((HERE / "plan-preparation/prepared-summary.json").read_bytes()),
                   real_fault_executions=0, identities_started=0, authorization_generated=False,
                   hash_semantics="Embedded hashes bind local originals; this manifest maps originals to the published path projections.",
                   private_inputs_published=False, originals_modified=False, files=bindings,
                   publisher_sha256=sha(Path(__file__).read_bytes()))
    (DEST / "publication-bindings.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DEST / "README.md").write_text("""# 接入日志恢复：四例复验准备

本批已准备并完成文件与模拟验证，尚未授权或运行。旧 12 例授权已经用于上一批，不能用于本批。

- 源码固定为 `a4d71e83444228a71499a75c932a2b9e7ba678f1`；发布本资料不改变执行源码。
- 新独立项目 `incident-pilot-access-validation-20261019`，端口 60881/60882/60888/60890。
- 共 4 例：F10/M0 复合故障 1 次，E1-a 在观察后、修改前、已应用后三个中断点各 1 次；模型调用为 0。
- E1-a 停止自有数据库 worker 后，用原身份、原日志路径和原 journal 在断网临时容器中恢复接入日志，随后复原正常 worker 和资源。
- 每例尝试由官方 SDK 正常关闭本例所有权可核实的群组及其队列、交换机、ACL，检查六项关闭条件，并独立检查 30 秒 / 10 个完整订单流程。
- 串行保留失败。清理条件不满足时停止后续例；批末按已登记 ID、项目、服务、镜像、创建和启动时间停止本批进程，保留卷和记录。

运行前须重新确认七身份没有其他消费者，并将本次明确授权绑定到总计划 SHA、源码、执行辅助文件、配置、镜像和启动/恢复/清理范围。默认入口仅校验文件；缺授权的实际 `--execute` 已验证为拒绝。

查看[具体范围和四份计划摘要](plan-preparation/run-scope.md)、[验证结果](plan-preparation/validation-result.json)和[独立审阅](review/four-case-preparation-review.md)。[发布映射](publication-bindings.json)保留原始字节与路径投影的哈希对应关系。

这些脚本记录本机冻结批次的准备和执行入口，依赖未公开的私有配置布局。队友应按仓库接手指南，用自己的平台身份重新生成部署与计划；不能直接复用本批身份或凭据。

如果失败后新数据库容器缺少对应子例的恢复 ID 收据，末停会报告失败并保留登记。旧 22 例的 18 通过 / 4 失败、旧 12 例的 11 通过 / 1 失败及其日志缺口保持原判。本批不证明 Kafka/Monitor 入库、新机器部署或长期稳定性。
""", encoding="utf-8")
    tooling = DEST / "tooling"
    tooling.mkdir(exist_ok=True)
    (tooling / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(files=len(bindings), path_projections=sum(item["path_projection_applied"] for item in bindings),
                          batch_plans_sha256=summary["batch_plans_sha256"])))


if __name__ == "__main__":
    main()

"""Opt-in symptom-driven runbook; resource-domain safeguards still apply."""
from .free_tools import ToolStep
from incident.coordinator.planner import PlanNode, blocking_root_pid


class RunbookStep(ToolStep):
    def action_node(self):
        node = super().action_node()
        return PlanNode(node.id, node.tool, node.kind, node.resource,
                        "MR 按症状执行固定剧本（仍受资源域守卫约束）", node.args, risk=node.risk)


class BlindRunbookSelector:
    method = "MR"
    observation_tools = {"incident.symptom_check"}

    def __init__(self):
        self.phase = "symptom"
        self.pending = []
        self.entry_script_ran = False
        self.write_script_ran = False

    async def __call__(self, state, planner, available):
        while True:
            if self.pending:
                tool = self.pending.pop(0)
                if tool == "db.terminate_blocker":
                    pid = blocking_root_pid(planner.value("blocking_sessions", []))
                    if pid is None:
                        planner.history.append({"reason": "MR 无可安全定位的阻塞PID，跳过结束会话", "tool": tool,
                                                "runbook_action_skipped": True})
                        continue
                    args = {"pid": pid}
                elif tool == "application.pool_rebuild":
                    revision = planner.value("application_pool_revision")
                    if type(revision) is not int:
                        raise RuntimeError("MR cannot safely rebuild without the current revision")
                    args = {"expected_revision": revision}
                else:
                    args = {}
                kind = "observe" if tool in {"application.status", "db.blocking_sessions"} else "act"
                planner.history.append({"reason": "MR 固定剧本下一步；观察仅提供PID或revision前置参数",
                                        "tool": tool, "kind": kind})
                return RunbookStep(tool, kind, args)
            if self.phase == "symptom":
                self.phase = "choose"
                planner.history.append({"reason": "MR 只按公共入口症状分支", "tool": "incident.symptom_check"})
                return RunbookStep("incident.symptom_check", "observe")
            if self.phase == "choose":
                symptom = planner.value("symptom_category")
                if symptom == "entry_error" and not self.entry_script_ran:
                    self.entry_script_ran = True
                    self.pending = ["ops.restart", "ops.route_rollback"]
                    self.phase = "symptom"
                    continue
                if symptom == "write_error" and not self.write_script_ran:
                    self.write_script_ran = True
                    # Read blocking sessions only to locate a safe target;
                    # never invent a PID or bypass the domain's policy.
                    self.pending = ["db.restore_writes", "db.blocking_sessions", "db.terminate_blocker",
                                    "application.status", "application.pool_rebuild"]
                    # Re-check after either script, like a written runbook; each
                    # script still runs at most once, so the loop is bounded.
                    self.phase = "symptom"
                    continue
                self.phase = "verify"
            planner.history.append({"reason": "MR 剧本结束，完整30秒独立业务验证", "tool": "incident.verification"})
            return RunbookStep("incident.verification", "verify")

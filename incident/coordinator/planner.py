"""Deterministic D/(C+0.2T) ranking and explicit resource dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from .hypothesis import Hypothesis


@dataclass
class Probe:
    tool: str
    fact_key: str
    cost: float = 1.0
    median_seconds: float = 1.0


PROBES = [Probe("ops.containers", "container_state"),
          Probe("ops.route_status", "route_version"),
          Probe("application.status", "application_reachable"),
          Probe("db.read_only_status", "read_only"),
          Probe("db.blocking_sessions", "blocking_sessions", 1.5)]


def category(key, value):
    if key == "read_only":
        return "ro" if value is True else "rw" if value is False else "unknown"
    if key == "blocking_sessions":
        return "blocked" if value else "clear"
    if key == "application_reachable":
        return "reachable" if value else "unreachable"
    return str(value)


def blocking_root_pid(rows):
    """Resolve waiter -> blocker edges; never mistake a waiter for its blocker."""
    if not isinstance(rows, list):
        return None
    waiting, blocking, direct = set(), set(), set()
    valid = lambda pid: type(pid) is int and pid > 0
    for row in rows:
        if isinstance(row, dict) and "blocking_pids" in row:
            pid, parents = row.get("pid"), row["blocking_pids"]
            if not valid(pid) or not isinstance(parents, list) or any(not valid(parent) for parent in parents):
                return None
            if parents:
                waiting.add(pid)
                blocking.update(parents)
        else:
            # Retain the original adapter format that explicitly lists blockers.
            pid = row.get("pid") if isinstance(row, dict) else row
            if not valid(pid):
                return None
            direct.add(pid)
    roots = blocking - waiting
    if blocking:
        return min(roots) if roots else None
    return min(direct) if direct else None


def rank_probes(hypotheses: list[Hypothesis], probes: list[Probe]):
    pairs = list(combinations(hypotheses, 2))
    rows = []
    for probe in probes:
        distinguished = sum(bool(a.predictions.get(probe.tool)) and bool(b.predictions.get(probe.tool))
            and set(a.predictions[probe.tool]).isdisjoint(b.predictions[probe.tool]) for a, b in pairs)
        d = distinguished / len(pairs) if pairs else 0.0
        if probe.cost <= 0 or probe.median_seconds < 0:
            raise ValueError("probe cost must be positive and time nonnegative")
        rows.append({"tool": probe.tool, "score": d / (probe.cost + 0.2 * probe.median_seconds),
                     "discrimination": d, "median_seconds": probe.median_seconds})
    return sorted(rows, key=lambda r: (-r["score"], r["median_seconds"], r["tool"]))


@dataclass
class PlanNode:
    id: str
    tool: str
    kind: str
    resource: str
    reason: str
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    risk: str = "read"


class EvidencePlanner:
    def __init__(self):
        self.facts: dict[str, dict] = {}
        self.history: list[dict] = []
        self.observed: set[str] = set()
        self.completed: set[str] = set()
        self.confirmed_conflicts: set[tuple] = set()
        self.pending_conflict = None

    def update(self, tool, facts):
        self.observed.add(tool)
        for fact in facts:
            self.facts[fact["key"]] = fact
        if tool == "db.read_only_status" and self.pending_conflict is not None:
            if self.read_only_conflict() == self.pending_conflict:
                self.confirmed_conflicts.add(self.pending_conflict)
            self.pending_conflict = None
        self.history.append({"reason": "接收参与者观察，更新证据", "tool": tool,
                             "facts": [f["key"] for f in facts]})

    def value(self, key, default=None):
        return self.facts.get(key, {}).get("value", default)

    def read_only_conflict(self):
        app, database = self.value("application_read_only"), self.value("read_only")
        if type(app) is bool and type(database) is bool and app != database:
            return (app, database, self.value("application_pool_revision"))
        return None

    def candidates(self, hypotheses):
        return [h for h in hypotheses if not any(
            p.tool in h.predictions and p.fact_key in self.facts
            and category(p.fact_key, self.value(p.fact_key)) not in h.predictions[p.tool]
            for p in PROBES)]

    def required_probe(self, available=None):
        conflict = self.read_only_conflict()
        if conflict and conflict not in self.confirmed_conflicts and (
                available is None or "db.read_only_status" in available):
            self.pending_conflict = conflict
            self.history.append({"reason": "应用连接与数据库只读证据冲突，补充数据库侧探测", "tool": "db.read_only_status"})
            return "db.read_only_status"
        if ("db.restore_writes" in self.completed and "application.pool_rebuild" not in self.completed
                and type(self.value("application_pool_revision")) is not int
                and (available is None or "application.status" in available)):
            self.history.append({"reason": "重建连接前先确认当前连接池 revision", "tool": "application.status"})
            return "application.status"
        return None

    def next_probe(self, hypotheses, available=None):
        required = self.required_probe(available)
        if required is not None:
            return required
        probes = [p for p in PROBES if p.tool not in self.observed
                  and (available is None or p.tool in available)]
        ranked = rank_probes(self.candidates(hypotheses) or hypotheses, probes)
        if not ranked:
            return None
        self.history.append({"reason": "按假设区分度与成本选择下一次观察", "ranking": ranked})
        return ranked[0]["tool"]

    def actions(self):
        nodes = []
        conflict = self.read_only_conflict()
        if conflict and conflict not in self.confirmed_conflicts:
            return nodes
        if self.value("container_state") == "exited" and "ops.restart" not in self.completed:
            nodes.append(PlanNode("restart", "ops.restart", "act", "application",
                                  "应用进程未运行", risk="high"))
        if self.value("route_version") == "v1" and "ops.route_rollback" not in self.completed:
            nodes.append(PlanNode("route", "ops.route_rollback", "act", "gateway",
                                  "入口仍指向旧版本", risk="write"))
        if self.value("read_only") is True and "db.restore_writes" not in self.completed:
            nodes.append(PlanNode("restore-writes", "db.restore_writes", "act", "database",
                                  "数据库观察确认只读", risk="high"))
        blockers = self.value("blocking_sessions", [])
        if blockers and "db.terminate_blocker" not in self.completed:
            # Only the diagnosed blocking session is selected, never all sessions.
            pid = blocking_root_pid(blockers)
            if pid is not None:
                nodes.append(PlanNode("unblock", "db.terminate_blocker", "act", "database",
                                      "阻塞链中确认的实验应用根会话", {"pid": pid}, risk="high"))
        stale_pool = conflict in self.confirmed_conflicts and self.value("read_only") is False and self.value("application_read_only") is True
        if ("db.restore_writes" in self.completed or stale_pool) and "application.pool_rebuild" not in self.completed:
            revision = self.value("application_pool_revision")
            if type(revision) is int:
                nodes.append(PlanNode("pool", "application.pool_rebuild", "act", "application",
                                      "数据库已恢复读写，应用需建立新连接", {"expected_revision": revision},
                                      depends_on=["restore-writes"] if "db.restore_writes" in self.completed else [], risk="write"))
            else:
                self.observed.discard("application.status")
        return nodes

    def action_completed(self, node):
        self.completed.add(node.tool)
        # Facts describing modified resources must be re-observed. Keep other
        # domains' evidence so compound faults continue after the first repair.
        invalidations = {"ops.restart": ["container_state", "application_reachable"],
            "ops.route_rollback": ["route_version"], "db.restore_writes": ["read_only"],
            "db.terminate_blocker": ["blocking_sessions"], "application.pool_rebuild": ["application_reachable", "application_pool_revision", "application_read_only"]}
        for key in invalidations.get(node.tool, []):
            self.facts.pop(key, None)
            self.observed.difference_update(p.tool for p in PROBES if p.fact_key == key)
        self.history.append({"reason": node.reason + "；修改后重新观察相关状态", "tool": node.tool})

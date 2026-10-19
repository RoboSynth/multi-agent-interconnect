"""Opt-in per-incident ranking. Historical EvidencePlanner stays unchanged."""
from dataclasses import replace

from .planner import EvidencePlanner, PROBES, category, rank_probes


class IncidentPlanner(EvidencePlanner):
    # These are declared resource organizations, not verified legal entities.
    # Read-only blocking-session inspection exposes session/SQL metadata.
    probes = [replace(probe, cost=2 if probe.tool == "db.blocking_sessions" else 1)
              for probe in PROBES]

    def candidates(self, hypotheses):
        fault_confirmed = (self.value("container_state") == "exited" or self.value("route_version") == "v1"
                           or self.value("read_only") is True
                           or bool(self.value("blocking_sessions", [])))
        result = []
        for hypothesis in hypotheses:
            if fault_confirmed and hypothesis.cause == "healthy_or_other":
                continue
            contradicted = False
            for probe in self.probes:
                if probe.tool not in hypothesis.predictions or probe.fact_key not in self.facts:
                    continue
                value = self.value(probe.fact_key)
                # Missing/unknown evidence cannot disprove a possible cause.
                if value is None:
                    continue
                observed = category(probe.fact_key, value)
                if observed == "unknown":
                    continue
                if observed not in hypothesis.predictions[probe.tool]:
                    contradicted = True
                    break
            if not contradicted:
                result.append(hypothesis)
        return result

    def next_probes(self, hypotheses, available=None, *, maximum=3):
        required = self.required_probe(available)
        if required is not None:
            return [required]
        probes = [probe for probe in self.probes if probe.tool not in self.observed
                  and (available is None or probe.tool in available)]
        ranked = rank_probes(self.candidates(hypotheses), probes)
        self.history.append({"reason": "按跨域成本排序；无区分度且无前置观察时停止", "ranking": ranked})
        # One outstanding task per resource partner. Both transports select
        # one active partner per prefix; never overlap two ops/db requests.
        selected, domains = [], set()
        for row in ranked:
            domain = row["tool"].split(".")[0]
            if row["discrimination"] > 0 and domain not in domains:
                selected.append(row["tool"])
                domains.add(domain)
            if len(selected) == maximum:
                break
        return selected

    def next_probe(self, hypotheses, available=None):
        selected = self.next_probes(hypotheses, available, maximum=1)
        return selected[0] if selected else None

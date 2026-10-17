"""Official AMP emitters shared by every identity, with local periodic tasks."""
from __future__ import annotations
import asyncio
from contextlib import suppress
from pathlib import Path
import statistics
import time

from acps_sdk.amp import (AccessEmitter, AuditEmitter, AuditBody, AuditActor, AuditAction,
    AuditTarget, AuditResult, CertificateAuditSigner, HeartbeatEmitter, MessageEmitter,
    MetricsEmitter, MetricsBody, LoadMetrics, WindowMetrics, SystemEmitter)


class RuntimeMetrics:
    def __init__(self):
        self.started = time.monotonic()
        self.active = 0
        self.samples = []

    def record(self, elapsed_ms, success):
        self.samples.append((time.monotonic(), elapsed_ms, bool(success)))
        self.samples = [s for s in self.samples if s[0] >= time.monotonic() - 300]

    def sample(self):
        recent = [s for s in self.samples if s[0] >= time.monotonic() - 300]
        windows = []
        if recent:
            latencies = sorted(s[1] for s in recent)
            windows.append(WindowMetrics(window="PT5M", request_total=len(recent),
                success_rate=100 * sum(s[2] for s in recent) / len(recent),
                avg_latency_ms=statistics.mean(latencies),
                p50_latency_ms=statistics.median(latencies),
                p95_latency_ms=latencies[min(len(latencies)-1, int(len(latencies)*.95))]))
        return MetricsBody(uptime_seconds=time.monotonic()-self.started,
            load_metrics=LoadMetrics(active_tasks=self.active, queued_tasks=0), window_metrics=windows)


class AmpRuntime:
    def __init__(self, directory, name, aic, *, cert=None, key=None):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        if not name.replace("-", "").replace("_", "").isalnum():
            raise ValueError("AMP name must be a simple identifier")
        self.aic, self.name = aic, name
        signer = None
        if cert and key:
            signer = CertificateAuditSigner(private_key_pem=Path(key).read_text(encoding="utf-8"),
                                            cert_pem=Path(cert).read_text(encoding="utf-8"))
        self.signed_audit = signer is not None
        filename = lambda kind: path / f"amp_{kind}_{name}.jsonl"
        self.heartbeat = HeartbeatEmitter(filename("heartbeat"), aic)
        self.sampler = RuntimeMetrics()
        self.metrics = MetricsEmitter(filename("metrics"), aic, self.sampler)
        self.system = SystemEmitter(filename("system"), aic)
        self.audit = AuditEmitter(filename("audit"), aic, signer=signer)
        self.access = AccessEmitter(filename("access"), aic)
        self.message = MessageEmitter(filename("message"), aic)
        self.tasks = []

    async def start(self):
        if self.tasks:
            return
        await self.system.emit({"event": "process_started", "name": self.name,
                                "signed_audit": self.signed_audit})
        self.tasks = [asyncio.create_task(self.heartbeat.run_periodic(15)),
                      asyncio.create_task(self.metrics.run_periodic(30))]

    async def close(self):
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            with suppress(asyncio.CancelledError):
                await task
        self.tasks = []
        await self.system.emit({"event": "process_stopped", "name": self.name})

    def audit_event(self, event):
        """Adapter for gateway and coordinator audit dictionaries."""
        incident_id = str(event.get("incident_id", "unknown"))
        status = event.get("status", "unknown")
        outcome = "success" if status in ("ok", "applied", "approved", "success", "skipped_already_applied") else (
                  "failure" if status in ("rejected", "tool_error", "failure") else "unknown")
        return self.audit.emit_sync(AuditBody(
            actor=AuditActor(id=str(event.get("caller_aic", self.aic)), type="agent"),
            action=AuditAction(name=str(event.get("tool", event.get("event", "incident_event"))), type="incident"),
            target=AuditTarget(type="operation", id=str(event.get("operation_id", incident_id))),
            result=AuditResult(status=outcome, reason=str(event.get("reason", ""))[:300] or None)),
            trace_id=incident_id, correlation_id=event.get("logical_task_id"))

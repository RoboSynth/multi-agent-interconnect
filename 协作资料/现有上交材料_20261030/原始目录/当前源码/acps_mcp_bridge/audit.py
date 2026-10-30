"""Bridge audit events use the official AMP emitter and certificate signer."""
from pathlib import Path


class AmpAuditSink:
    def __init__(self, emitter):
        self.emitter = emitter

    @classmethod
    def from_certificate(cls, log_file, aic, cert_path, key_path):
        from acps_sdk.amp.emitter import AuditEmitter
        from acps_sdk.amp.signer import CertificateAuditSigner
        signer = CertificateAuditSigner(private_key_pem=Path(key_path).read_text(),
                                        cert_pem=Path(cert_path).read_text())
        return cls(AuditEmitter(Path(log_file), aic, signer=signer))

    async def __call__(self, event):
        from acps_sdk.amp.models import AuditBody, AuditActor, AuditAction, AuditTarget, AuditResult
        status = "success" if event["status"] == "ok" else "unknown" if event["status"] == "unknown" else "failure"
        return await self.emitter.emit(AuditBody(
            actor=AuditActor(id=event["caller_aic"], type="agent"),
            action=AuditAction(name=event["tool"], type="mcp_bridge"),
            target=AuditTarget(type="resource_domain", id=event["operation_id"] or event["tool"]),
            result=AuditResult(status=status, reason=event["operation_state"] or event["status"])),
            trace_id=event["incident_id"], correlation_id=event["logical_task_id"])

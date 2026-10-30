"""Local AIC ownership and cooperative handoff; never kill another consumer.

The first-byte locks deliberately match platform_resume_experiment.coordinator_lock.
Metadata is diagnostic: only an OS-held lock proves local exclusion. There is no
TTL-based stealing, and another computer still needs a human exclusivity check.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = ROOT / "artifacts/new7-platform-healthy-plan-20261018/ownership"


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


class LeaseBusy(RuntimeError):
    pass


class LeaseQuarantined(RuntimeError):
    pass


class AicLease:
    """All-or-none locks in AIC order, held across the entire consumer lifetime."""
    def __init__(self, aics, *, purpose, directory=DEFAULT_DIRECTORY, owner=None):
        if (isinstance(aics, str) or not aics or len(set(aics)) != len(aics)
                or any(not isinstance(aic, str) or not aic.strip() or aic != aic.strip() for aic in aics)):
            raise ValueError("Lease requires distinct exact AIC strings")
        if not isinstance(purpose, str) or not purpose.strip():
            raise ValueError("Lease purpose is required")
        self.aics, self.directory = sorted(aics), Path(directory)
        self.owner = dict(owner or {})
        self.owner.update(pid=os.getpid(), hostname=socket.gethostname(), purpose=purpose,
                          lease_id=uuid.uuid4().hex, started_at=now())
        self.streams = []

    def _base(self, aic):
        return self.directory / hashlib.sha256(aic.encode()).hexdigest()

    def acquire(self):
        if self.streams:
            raise RuntimeError("Lease already acquired")
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            for aic in self.aics:
                base = self._base(aic)
                stream = base.with_suffix(".lock").open("a+b")
                try:
                    if stream.seek(0, os.SEEK_END) == 0:
                        stream.write(b"0")
                        stream.flush()
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as error:
                    stream.close()
                    raise LeaseBusy("An AIC is still owned by another local consumer") from error
                self.streams.append((aic, stream))
                if base.with_suffix(".quarantine.json").exists():
                    raise LeaseQuarantined("Remote cleanup is unresolved; identities remain quarantined")
            for aic, _ in self.streams:
                save(self._base(aic).with_suffix(".owner.json"), {**self.owner, "aic": aic, "status": "held"})
            return self
        except BaseException:
            self.release()
            raise

    def quarantine(self, reason, *, evidence=None):
        if len(self.streams) != len(self.aics):
            raise RuntimeError("Only the full lease holder may quarantine identities")
        for aic, _ in self.streams:
            path = self._base(aic).with_suffix(".quarantine.json")
            previous = load(path) if path.exists() else None
            save(path, dict(aic=aic, owner=self.owner, quarantined_at=now(), reason=reason,
                            evidence=evidence, previous=previous))

    def release(self):
        for aic, stream in reversed(self.streams):
            try:
                path = self._base(aic).with_suffix(".owner.json")
                if path.exists() and load(path).get("lease_id") == self.owner["lease_id"]:
                    save(path, {**load(path), "status": "released", "released_at": now()})
            except (ValueError, OSError):
                # Diagnostic metadata must never prevent releasing later locks.
                pass
            finally:
                stream.close()
        self.streams.clear()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *error):
        self.release()


class ExperimentOwnership:
    def __init__(self, lease):
        self.lease = lease
        self.cleanup_receipt = None

    def mark_cleanup_verified(self, receipt):
        # A business H00 result alone cannot prove remote ACL/MQ cleanup.
        required = {"resource_restored", "h00_passed", "consumers_closed", "remote_groups_closed"}
        if not isinstance(receipt, dict) or any(receipt.get(key) is not True for key in required):
            raise ValueError("Cleanup receipt must confirm resources, H00, consumers and remote groups")
        self.cleanup_receipt = receipt


@asynccontextmanager
async def experiment_lease(aics, *, purpose, control_directory=None, directory=DEFAULT_DIRECTORY,
                           timeout=180, poll_seconds=.25):
    """Request idle pause BEFORE waiting for AICs; finally resume only after cleanup.

    The caller must start/close all experiment consumers inside this context and
    explicitly certify remote cleanup. Existing frozen runners do not use it.
    """
    if timeout <= 0 or poll_seconds <= 0:
        raise ValueError("Handoff timeout and polling interval must be positive")
    token, control, paused, entered = uuid.uuid4().hex, None, False, False
    request = None
    reservation = None
    lease = AicLease(aics, purpose=purpose, directory=directory)
    deadline = time.monotonic() + timeout
    try:
        if control_directory is not None:
            control = Path(control_directory)
            state = load(control / "host.json")
            if state.get("status") != "running" or set(state.get("aics", [])) != set(aics):
                raise ValueError("Managed host must be running with the exact selected AIC set")
            # Serialize controllers without holding any of the consumers' AICs.
            reservation = AicLease(["handoff:"+str(control.resolve())], purpose=purpose,
                                   directory=control / "controllers")
            reservation.acquire()
            request = dict(action="stop_when_idle", request_id=token, host_session=state["session_id"],
                           owner=lease.owner, requested_at=now(), aics=sorted(aics))
            save(control / "handoff-request.json", request)
            while True:
                state = load(control / "host.json")
                if state.get("session_id") != request["host_session"]:
                    raise RuntimeError("Managed host changed during handoff")
                if state.get("status") == "quarantined":
                    raise LeaseQuarantined("Managed host could not confirm consumer cleanup")
                if state.get("status") == "paused" and state.get("request_id") == token:
                    if state.get("consumers_closed") is not True or state.get("lease_released") is not True:
                        raise RuntimeError("Pause acknowledgement lacks consumer close or lease release")
                    paused = True
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("Idle pause was not confirmed; no consumer was stopped by the requester")
                await asyncio.sleep(poll_seconds)
        while True:
            try:
                lease.acquire()
                break
            except LeaseBusy:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Exclusive identities were not released within the handoff window")
                await asyncio.sleep(poll_seconds)
        ownership = ExperimentOwnership(lease)
        entered = True
        try:
            yield ownership
        finally:
            if ownership.cleanup_receipt is None:
                lease.quarantine("experiment cleanup was not fully verified", evidence={"request_id": token})
            lease.release()
            if paused and ownership.cleanup_receipt is not None:
                save(control / "handoff-result.json", dict(request_id=token, host_session=request["host_session"],
                    action="resume", cleanup_receipt=ownership.cleanup_receipt, finished_at=now()))
            elif paused:
                save(control / "handoff-result.json", dict(request_id=token, host_session=request["host_session"],
                    action="quarantine", reason="experiment cleanup was not fully verified", finished_at=now()))
    finally:
        lease.release()
        # Cancel a pending pause when no experiment started. The host can finish
        # a graceful drain, then resume; no abandoned request is left to steal it.
        if request is not None and not entered:
            save(control / "handoff-result.json", dict(request_id=token, host_session=request["host_session"],
                action="cancel", reason="handoff not acquired", finished_at=now()))
        if reservation is not None:
            reservation.release()

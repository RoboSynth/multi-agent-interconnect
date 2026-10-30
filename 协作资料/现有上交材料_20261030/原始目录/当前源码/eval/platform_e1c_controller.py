"""E1-c only: resume an owned stopped Linux worker, never restart it."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import sqlite3
import time

from eval.platform_resume_experiment import Controller, DB_SERVICES, digest, local, save


def request_sha256(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def ledger_snapshot(path, operation_id, resource_domain):
    """Read only the state/fence columns; do not initialize or mutate a ledger."""
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT state,coordinator_term,takeover_version FROM operations "
            "WHERE resource_domain=? AND operation_id=?", (resource_domain, operation_id)).fetchone()
        fence = connection.execute("SELECT coordinator_term,takeover_version FROM operation_fences "
            "WHERE resource_domain=?", (resource_domain,)).fetchone()
        return {"operation_id": operation_id, "state": row[0] if row else None,
                "operation_fence": dict(zip(("coordinator_term", "takeover_version"), row[1:])) if row else None,
                "active_fence": dict(zip(("coordinator_term", "takeover_version"), fence)) if fence else None}
    finally:
        connection.close()


# The pidfd pins the original kernel process even if it exits between the last
# /proc check and signaling. All command arguments are fixed public worker args.
PROCESS_CODE = r"""
import json,os,signal,sys,time
from pathlib import Path
expected=json.loads(sys.argv[1]); resume=sys.argv[2]=='continue'
identity=expected['process_identity']; pid=identity['pid']
if type(pid) is not int or pid<=1 or type(identity['linux_start_ticks']) is not int or identity['linux_start_ticks']<=0:
    raise ValueError('invalid Linux process identity')
fd=os.pidfd_open(pid)
try:
    base=Path('/proc')/str(pid)
    raw=(base/'stat').read_text(); fields=raw.rpartition(')')[2].split()
    actual={'pid':int(raw.split(' ',1)[0]),'linux_start_ticks':int(fields[19])}
    argv=(base/'cmdline').read_bytes().rstrip(b'\0').decode('utf-8').split('\0')
    command=expected['command']
    if (actual!=identity or not argv or Path(argv[0]).name!=command[0] or argv[1:]!=command[1:]):
        raise ValueError('owned process identity/command changed')
    state=fields[0]
    if resume and state not in ('T','t'):
        raise ValueError('owned process is not stopped')
    result={'process_identity':actual,'state':state,'cmdline':argv,'stat':raw,'signal_sent':False}
    if resume:
        expiry=expected.get('approval_expires_at')
        if 'approval_expires_at' in expected and (type(expiry) is not int or expiry<=time.time()+5):
            raise ValueError('original approval no longer valid before signal')
        signal.pidfd_send_signal(fd,signal.SIGCONT)
        result['signal_sent']=True
    print(json.dumps(result))
finally:
    os.close(fd)
"""


class RevivalController(Controller):
    """Reuse E1 ownership/start/restore; collect adds a same-process revival."""
    revival_wait_seconds = 30

    def __init__(self, plan, output):
        if plan.get("case") != "E1-c" or plan.get("crash_point") != "before_modification":
            raise ValueError("RevivalController requires the exact E1-c before_modification case")
        super().__init__(plan, output)
        self.revival_metrics = {"status": "not_started", "process_snapshots": [], "signals_sent": 0}

    def owned_worker(self, item, service, *, experiment=False, running=True):
        super().owned_worker(item, service, experiment=experiment, running=running)
        if experiment and service == DB_SERVICES[0] and item["HostConfig"].get("Init") is not True:
            raise ValueError("E1-c primary requires init:true and a non-PID1 Python worker")

    def _workers(self):
        records = self.inspect()
        self.assert_stable_others(records)
        self.owned_database(records, experiment=True)
        if any(records[name]["Id"] != self.experimental[name] or
               records[name]["State"]["StartedAt"] != self.experimental_started[name] for name in DB_SERVICES):
            raise ValueError("E1-c workers were replaced or restarted")
        return records

    def _traces(self, records, *, wait=False):
        paths = {role: "/state/experiments/" + self.plan["experiment_id"] + "/" + role + ".jsonl"
                 for role in ("primary", "backup")}
        code = ("import json,time;from pathlib import Path;paths=json.loads(__import__('sys').argv[1]);"
                "deadline=time.monotonic()+float(__import__('sys').argv[2])\n"
                "while True:\n"
                " data={k:Path(p).read_text(encoding='utf-8') for k,p in paths.items()}\n"
                " events=[json.loads(line) for line in data['primary'].splitlines()]\n"
                " if any(e.get('event')=='experiment_stale_request_result' for e in events) or time.monotonic()>=deadline:break\n"
                " time.sleep(0.1)\n"
                "print(json.dumps(data))")
        text = self.command(self.target.docker + ["exec", records[DB_SERVICES[1]]["Id"], "python", "-c", code,
            json.dumps(paths), str(self.revival_wait_seconds if wait else 0)])
        raw = json.loads(text)
        result = {}
        for role in paths:
            path = self.output / (role + "-trace.jsonl")
            path.write_text(raw[role], encoding="utf-8")
            initial = self.output / ("pre-revival-" + role + "-trace.jsonl")
            if not initial.exists():
                initial.write_text(raw[role], encoding="utf-8")
            result[role] = [json.loads(line) for line in raw[role].splitlines()]
        return result

    def _identity(self, events, *, primary=True):
        identity = events[0].get("process_identity")
        if (not isinstance(identity, dict) or set(identity) != {"pid", "linux_start_ticks"}
                or type(identity["pid"]) is not int or identity["pid"] < (2 if primary else 1)
                or type(identity["linux_start_ticks"]) is not int or identity["linux_start_ticks"] <= 0):
            raise ValueError("A real non-PID1 Linux process/start identity is required")
        return identity

    def _startup(self, traces):
        identities = {}
        for role, events in traces.items():
            starts = [event for event in events if event.get("event") == "experiment_worker_start"]
            expected = dict(experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"],
                executor_aic=self.plan["identities"]["database" if role == "primary" else "database-backup"],
                worker_role=role, armed=role == "primary", transport="wutong-amqps",
                bundle_manifest_sha256=digest(local(self.plan["bundle"]) / "worker-source-manifest.json"))
            if len(starts) != 1 or any(starts[0].get(k) != v for k, v in expected.items()):
                raise ValueError("E1-c startup trace differs from frozen manifest/identity")
            identities[role] = self._identity(starts, primary=role == "primary")
        return identities

    def _marker(self, events, name, identity, payload=None):
        found = [event for event in events if event.get("event") == name]
        if len(found) != 1:
            raise ValueError("Expected one exact E1-c marker: " + name)
        expected = dict(experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"],
            executor_aic=self.plan["identities"]["database"], transport="wutong-amqps",
            operation_id=self.plan["operation_id"], tool="db.restore_writes", process_identity=identity,
            crash_point="before_modification", AIP_product_submitted=False)
        if payload is not None:
            expected.update(logical_task_id=payload["logical_task_id"], request_sha256=request_sha256(payload), fence=payload["fence"])
        if any(found[0].get(k) != v for k, v in expected.items()):
            raise ValueError("E1-c marker does not bind the exact stopped request/process")
        return found[0]

    def _counts(self, traces):
        from acps_mcp_bridge.experiment import operation_counts
        counts = operation_counts([self.output / (role + "-trace.jsonl") for role in traces],
            experiment_id=self.plan["experiment_id"], incident_id=self.plan["incident_id"])
        expected = [{"executor_aic": self.plan["identities"]["database-backup"], "operation_id": self.plan["operation_id"],
                     "invocations": 1, "returned": 1, "returned_errors": 0, "without_return": 0}]
        if counts["operations"] != expected:
            raise ValueError("E1-c requires zero primary and exactly one successful backup modifying MCP call")
        return counts

    def _ledger(self, records):
        code = ("import json,sqlite3;from pathlib import Path\n" + inspect.getsource(ledger_snapshot) +
            "\nc=json.loads(Path('/domain/bridge.json').read_text());p=Path(c['ledger_path']);"
            "p=p if p.is_absolute() else Path('/domain')/p;"
            "print(json.dumps(ledger_snapshot(p,__import__('sys').argv[1],c.get('ledger_domain','db'))))")
        return json.loads(self.command(self.target.docker + ["exec", records[DB_SERVICES[1]]["Id"],
            "python", "-c", code, self.plan["operation_id"]]))

    def _process(self, records, identity, *, resume=False, approval_expires_at=None):
        # Recheck the immutable container/start/mount contract immediately before
        # the in-container pidfd+command guard; docker exec targets the exact ID.
        current = self._workers()
        if any(current[s]["Id"] != records[s]["Id"] for s in DB_SERVICES):
            raise ValueError("Worker ownership changed before process inspection")
        expected = {"process_identity": identity, "command": current[DB_SERVICES[0]]["Config"]["Cmd"]}
        if approval_expires_at is not None:
            expected["approval_expires_at"] = approval_expires_at
        result = json.loads(self.command(self.target.docker + ["exec", current[DB_SERVICES[0]]["Id"],
            "python", "-c", PROCESS_CODE, json.dumps(expected), "continue" if resume else "inspect"]))
        if result.get("process_identity") != identity or (resume and result.get("signal_sent") is not True):
            raise ValueError("Process probe did not confirm the exact intended process/signal")
        self.revival_metrics["process_snapshots"].append(result)
        if result.get("signal_sent"):
            self.revival_metrics["signals_sent"] += 1
        save(self.output / "e1c-process-snapshots.json", self.revival_metrics["process_snapshots"])
        return result

    def collect(self, payload):
        self.revival_metrics["status"] = "checking_stopped_primary"
        try:
            if (payload.get("kind"), payload.get("tool"), payload.get("incident_id"), payload.get("operation_id")) != (
                    "act", "db.restore_writes", self.plan["incident_id"], self.plan["operation_id"]):
                raise ValueError("E1-c collect requires the exact original modifying request")
            records = self._workers()
            traces = self._traces(records)
            identity = self._startup(traces)["primary"]
            suspended = self._marker(traces["primary"], "experiment_worker_suspended", identity, payload)
            if suspended.get("ledger_state") != "received":
                raise ValueError("Primary did not stop after durable received and before modification")
            if any(e.get("event") in {"experiment_worker_revived", "experiment_stale_request_result"} for e in traces["primary"]):
                raise ValueError("Primary was already revived before the controller's owned signal")
            self._counts(traces)
            ledger = self._ledger(records)
            old = payload["fence"]
            fields = ("coordinator_term", "takeover_version")
            for fence in (old, ledger.get("active_fence"), ledger.get("operation_fence")):
                if not isinstance(fence, dict) or set(fence) != set(fields) or any(type(fence[k]) is not int or fence[k] < 0 for k in fields):
                    raise ValueError("E1-c requires explicit nonnegative old/active/operation fences")
            if (ledger.get("operation_id") != self.plan["operation_id"] or ledger.get("state") != "applied"
                    or ledger["active_fence"] != ledger["operation_fence"]
                    or tuple(ledger["active_fence"][k] for k in fields) <= tuple(old[k] for k in fields)):
                raise ValueError("Backup applied state and advanced fence must precede revival")
            self.revival_metrics["ledger_before_revival"] = ledger
            if self._process(records, identity).get("state") not in {"T", "t"}:
                raise ValueError("Primary is not actually Linux-stopped")
            approval = payload.get("approval")
            expiry = approval.get("expires_at") if isinstance(approval, dict) else None
            if type(expiry) is not int or expiry <= time.time() + 5:
                raise ValueError("Original approval must remain valid across the same-request revival")
            self._process(records, identity, resume=True, approval_expires_at=expiry)
            before = traces
            traces = self._traces(records, wait=True)
            if any(traces[role][:len(events)] != events for role, events in before.items()):
                raise ValueError("Durable worker traces changed their pre-revival history")
            if self._startup(traces)["primary"] != identity:
                raise ValueError("Primary process identity changed across revival")
            self._marker(traces["primary"], "experiment_worker_suspended", identity, payload)
            revived = self._marker(traces["primary"], "experiment_worker_revived", identity, payload)
            result = self._marker(traces["primary"], "experiment_stale_request_result", identity, payload)
            if (revived.get("ledger_state"), result.get("status"), result.get("operation_state"), result.get("result_operation_id")) != (
                    "applied", "rejected", "rejected_stale_fence", self.plan["operation_id"]):
                raise ValueError("Same-process original request did not return rejected_stale_fence")
            names = [event.get("event") for event in traces["primary"]]
            if not names.index("experiment_worker_suspended") < names.index("experiment_worker_revived") < names.index("experiment_stale_request_result"):
                raise ValueError("E1-c lifecycle trace is out of order")
            counts = self._counts(traces)
            if self._ledger(records) != ledger:
                raise ValueError("Stale primary changed the durable operation/fence")
            if self._process(records, identity).get("state") in {"T", "t", "Z", "X"}:
                raise ValueError("Revived original process is not live")
            self.revival_metrics.update(status="completed", same_process=True, old_request_sha256=request_sha256(payload),
                old_fence=old, stale_request_state="rejected_stale_fence", replay_attempts=1,
                rejected_stale_fence=1, counts=counts)
            save(self.output / "mcp-operation-counts.json", counts)
            return dict(self.revival_metrics)
        except Exception as error:
            self.revival_metrics.update(status="failed", error_class=type(error).__name__)
            raise
        finally:
            save(self.output / "e1c-revival-metrics.json", self.revival_metrics)

    def restore(self):
        errors = []
        proof = {"resume_before_restore": "not_needed", "parent_restore": "not_attempted"}
        try:
            if self.switched and hasattr(self, "experimental"):
                records = self._workers()
                traces = self._traces(records)
                identity = self._startup(traces)["primary"]
                stopped = [e for e in traces["primary"] if e.get("event") == "experiment_worker_suspended"]
                if stopped:
                    self._marker(traces["primary"], "experiment_worker_suspended", identity)
                    snapshot = self._process(records, identity)
                    if snapshot["state"] in {"T", "t"}:
                        self._process(records, identity, resume=True)
                        proof["resume_before_restore"] = "same_owned_process_continued"
                    else:
                        proof["resume_before_restore"] = "owned_process_not_stopped"
        except Exception as error:
            proof.update(resume_before_restore="failed", resume_error_class=type(error).__name__)
            errors.append(error)
        try:
            super().restore()
            proof["parent_restore"] = "completed" if self.switched else "not_needed"
        except Exception as error:
            proof.update(parent_restore="failed", parent_error_class=type(error).__name__)
            errors.append(error)
        finally:
            save(self.output / "e1c-restore.json", proof)
        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("E1-c resume and parent restoration failed", errors)

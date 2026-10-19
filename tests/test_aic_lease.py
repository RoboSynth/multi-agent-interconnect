import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ops.aic_lease import AicLease, LeaseBusy, LeaseQuarantined, experiment_lease, load, save
from ops.domain_entry import run_managed
from ops.longrun_host import ComposeConsumers, close_owned_server
from ops.schedule import Scheduler


class LeaseTests(unittest.TestCase):
    def test_all_or_none_lock_and_diagnostic_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            with AicLease(["b"], purpose="holder", directory=temporary):
                with self.assertRaises(LeaseBusy):
                    AicLease(["a", "b"], purpose="contender", directory=temporary).acquire()
                with AicLease(["a"], purpose="released-partial", directory=temporary) as lease:
                    owner = load(Path(temporary) / (hashlib.sha256(b"a").hexdigest()+".owner.json"))
                    self.assertEqual(owner["lease_id"], lease.owner["lease_id"])
                    self.assertEqual(owner["purpose"], "released-partial")
            with AicLease(["a", "b"], purpose="after-release", directory=temporary):
                pass

    def test_quarantine_survives_os_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            with AicLease(["a", "b"], purpose="experiment", directory=temporary) as lease:
                lease.quarantine("ACL unknown")
            with self.assertRaises(LeaseQuarantined):
                AicLease(["a", "b"], purpose="resume", directory=temporary).acquire()


class HandoffTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_server_error_quarantines_and_always_releases_lease(self):
        async def failing_server():
            raise RuntimeError("SDK close unknown")
        task = asyncio.create_task(failing_server())
        server, lease = Mock(), Mock()
        with self.assertRaisesRegex(RuntimeError, "SDK close unknown"):
            await close_owned_server(task, server, lease)
        lease.quarantine.assert_called_once()
        lease.release.assert_called_once()
        self.assertTrue(server.should_exit)

    async def test_outer_cancellation_waits_for_domain_cleanup_and_preserves_its_error(self):
        for fail in (False, True):
            entered, cleaning, allow_close, stop = (asyncio.Event() for _ in range(4))
            async def domain():
                try:
                    entered.set()
                    await asyncio.Event().wait()
                finally:
                    cleaning.set()
                    await allow_close.wait()
                    if fail:
                        raise RuntimeError("SDK final close unknown")
            managed = asyncio.create_task(run_managed(domain(), stop))
            await entered.wait()
            managed.cancel()
            await asyncio.wait_for(cleaning.wait(), 1)
            self.assertFalse(managed.done())
            allow_close.set()
            with self.assertRaisesRegex(RuntimeError, "SDK final close unknown") if fail else self.assertRaises(asyncio.CancelledError):
                await managed

    async def test_pause_closes_consumer_before_waiting_for_lease_and_resumes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory, control = Path(temporary)/"leases", Path(temporary)/"control"
            holder = AicLease(["a", "b"], purpose="longrun", directory=directory).acquire()
            save(control / "host.json", dict(status="running", session_id="host", aics=["a", "b"]))
            async def host():
                while not (control/"handoff-request.json").exists():
                    await asyncio.sleep(.001)
                request = load(control/"handoff-request.json")
                holder.release()  # models transport + owned domain close first
                save(control/"host.json", dict(status="paused", session_id="host", request_id=request["request_id"],
                    aics=["a", "b"], consumers_closed=True, lease_released=True))
            task = asyncio.create_task(host())
            async with experiment_lease(["a", "b"], purpose="test", directory=directory,
                                         control_directory=control, timeout=2, poll_seconds=.001) as ownership:
                with self.assertRaises(LeaseBusy):
                    AicLease(["a"], purpose="concurrent", directory=directory).acquire()
                ownership.mark_cleanup_verified(dict(resource_restored=True, h00_passed=True,
                    consumers_closed=True, remote_groups_closed=True, evidence="test receipt"))
            await task
            self.assertEqual(load(control/"handoff-result.json")["action"], "resume")
            with AicLease(["a", "b"], purpose="resumed", directory=directory):
                pass

    async def test_unknown_cleanup_blocks_reuse_even_when_h00_passed(self):
        with tempfile.TemporaryDirectory() as temporary:
            async with experiment_lease(["a"], purpose="test", directory=temporary) as ownership:
                with self.assertRaises(ValueError):
                    ownership.mark_cleanup_verified(dict(resource_restored=True, h00_passed=True,
                        consumers_closed=True, remote_groups_closed=False))
            with self.assertRaises(LeaseQuarantined):
                AicLease(["a"], purpose="next-case", directory=temporary).acquire()

    async def test_pause_timeout_cancels_request_and_does_not_touch_holder(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory, control = Path(temporary)/"leases", Path(temporary)/"control"
            save(control/"host.json", dict(status="running", session_id="host", aics=["a"]))
            with AicLease(["a"], purpose="longrun", directory=directory):
                with self.assertRaises(TimeoutError):
                    async with experiment_lease(["a"], purpose="test", directory=directory,
                                                control_directory=control, timeout=.01, poll_seconds=.001):
                        self.fail("must not enter before idle close")
                self.assertEqual(load(control/"handoff-result.json")["action"], "cancel")

    async def test_scheduler_does_not_dispatch_while_host_drains(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save(root/"control/host.json", dict(status="draining"))
            scheduler = Scheduler(dict(directory=str(root/"schedule"), workbench_url="http://127.0.0.1:8877",
                longrun_control_directory=str(root/"control")))
            scheduler.request = AsyncMock()
            await scheduler.run_job("inspect")
            scheduler.request.assert_not_awaited()

    async def test_signal_adapter_waits_for_existing_cleanup_and_propagates_failure(self):
        for fail in (False, True):
            stop, entered = asyncio.Event(), asyncio.Event()
            closed = []
            async def domain():
                try:
                    entered.set()
                    await asyncio.Event().wait()
                finally:
                    closed.append(True)
                    if fail:
                        raise RuntimeError("SDK close unknown")
            managed = asyncio.create_task(run_managed(domain(), stop))
            await entered.wait()
            stop.set()
            if fail:
                with self.assertRaisesRegex(RuntimeError, "SDK close unknown"):
                    await managed
            else:
                await managed
            self.assertEqual(closed, [True])

    async def test_owned_container_replacement_is_never_stopped(self):
        consumers = ComposeConsumers(type("Target", (), {})())
        consumers.owned = {"application-agent": "original"}
        consumers.inventory = AsyncMock(return_value={"application-agent": {"Id": "replacement"}})
        consumers.command = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "replaced"):
            await consumers.stop()
        consumers.command.assert_not_awaited()

    async def test_nonzero_owned_consumer_exit_cannot_acknowledge_close(self):
        consumers = ComposeConsumers(type("Target", (), {"docker": ["docker"]})())
        consumers.owned = {"application-agent": "original"}
        rows = {"application-agent": {"Id": "original", "State": {"Running": False, "ExitCode": 137}}}
        consumers.inventory = AsyncMock(return_value=rows)
        consumers.command = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "normally"):
            await consumers.stop()

    async def test_wsl_command_passes_session_without_relying_on_windows_environment_forwarding(self):
        target = type("Target", (), {"wsl_distro": "Ubuntu"})()
        consumers = ComposeConsumers(target, session="owned-session")
        result = type("Result", (), {"returncode": 0, "stdout": "ok"})()
        with patch("ops.longrun_host.subprocess.run", return_value=result) as run:
            self.assertEqual(await consumers.command(["wsl.exe", "-d", "Ubuntu", "--exec", "docker", "info"]), "ok")
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ["wsl.exe", "-d", "Ubuntu", "--exec", "env"])
        self.assertIn("INCIDENT_MANAGED_SESSION=owned-session", command)
        self.assertEqual(command[-2:], ["docker", "info"])


if __name__ == "__main__":
    unittest.main()

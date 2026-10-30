"""Offline F12 target, session ownership and exact-route cleanup checks."""
from copy import deepcopy
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]
import httpx
from eval.inject import Injector, main
from eval.targets import DockerTarget, DOMAIN_SOURCE_FILES
from test_eval_platform import profile, inspected, domain_proof


class Fixture:
    def __init__(self, directory):
        self.path, self.value, _ = profile(directory)
        self.value["ports"]["reply_drop"] = 38190
        self.path.write_text(json.dumps(self.value), encoding="utf-8")
        self.target = DockerTarget.from_file(self.path, root=directory)
        self.original = b"set $order_upstream app-v2:8000;\r\n"
        self.target.route_file.write_bytes(self.original)
        self.records = inspected(self.target)
        for row in self.records:
            row["State"]["Running"] = True
        self.proxies = []
        self.calls = []
        self.http_calls = []
        self.after_create_error = None
        self.stop_error = None
        self.render = {"services": {"reply-drop": {
            "image": "unit-existing-app", "command": ["python", "-m", "business.fault_reply_proxy"],
            "environment": {"FAULT_UPSTREAM": "http://app-v2:8000", "FAULT_REPLY_DELAY": "60"},
            "networks": {"default": None},
            "ports": [{"host_ip": "127.0.0.1", "published": "38190", "target": 8090, "protocol": "tcp"}]}},
            "networks": {"default": {"name": self.target.project+"_default"}}}

    def command(self, args, **kwargs):
        args = list(map(str, args))
        self.calls.append((args, kwargs))
        if args[-3:] == ["config", "--format", "json"]:
            return json.dumps(self.render)
        if args[-3:] == ["ps", "-a", "-q"]:
            return "baseline"
        if "inspect" in args:
            index = args.index("inspect")
            if args[index-1] == "image":
                return json.dumps([{"Id": "sha256:unit-image"}])
            ids = args[index+1:]
            return json.dumps(self.records+self.proxies if ids == ["baseline"] else
                [row for row in self.records+self.proxies if row["Id"] in ids])
        if "ps" in args and "--filter" in args:
            return " ".join(row["Id"] for row in self.proxies)
        if "run" in args:
            name = args[args.index("--name")+1]
            label = args[args.index("--label")+1].split("=", 1)[1]
            self.proxies.append({"Id": "owned-proxy-id", "Name": "/"+name, "Image": "sha256:unit-image",
                "Config": {"Labels": {"incident-pilot": "true", "com.docker.compose.project": self.target.project,
                    "com.docker.compose.service": "reply-drop", "incident-pilot.f12.session": label}},
                "HostConfig": {"PortBindings": {"8090/tcp": [{"HostIp": "127.0.0.1", "HostPort": "38190"}]}},
                "NetworkSettings": {"Networks": {self.target.project+"_default": {}}}, "Mounts": [],
                "State": {"Running": True, "StartedAt": "2026-10-19T01:00:00Z"}})
            if self.after_create_error:
                raise self.after_create_error
            return "owned-proxy-id\n"
        if "stop" in args:
            if self.stop_error:
                raise self.stop_error
            self.proxies[0]["State"]["Running"] = False
            return args[-1]
        if args[-3:] in (["nginx", "nginx", "-t"], ["nginx", "-s", "reload"]):
            return ""
        raise AssertionError("Unmocked external command: "+repr(args))

    def get(self, url):
        self.http_calls.append(url)
        relay = ":38190/" in url or b"reply-drop" in self.target.route_file.read_bytes()
        headers = {"via": "1.1 incident-pilot-relay"} if relay else {}
        return httpx.Response(200, json={"ok": True, "api_version": "v2"}, headers=headers, request=httpx.Request("GET", url))

    def injector(self, stack):
        stack.enter_context(patch("eval.inject.DockerTarget.from_file", return_value=self.target))
        stack.enter_context(patch("eval.inject.run_command", side_effect=self.command))
        domains = domain_proof()
        stack.enter_context(patch("eval.inject.Injector.runtime_domain", side_effect=lambda _, service, **kw: deepcopy(domains[service])))
        client = stack.enter_context(patch("eval.inject.httpx.Client"))
        client.return_value.__enter__.return_value.get.side_effect = self.get
        stack.enter_context(patch("eval.inject.time.sleep"))
        stack.enter_context(patch("eval.inject.time.monotonic", side_effect=itertools.count()))
        return Injector(target_config=self.path)


class F12TargetTests(unittest.TestCase):
    def setUp(self):
        from contextlib import ExitStack
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.fixture = Fixture(directory)

    def test_schema_three_and_four_ports_and_explicit_url(self):
        fixture = self.fixture
        self.assertEqual(fixture.target.reply_drop_url, "http://127.0.0.1:38190")
        fixture.value["ports"].pop("reply_drop")
        fixture.path.write_text(json.dumps(fixture.value), encoding="utf-8")
        old = DockerTarget.from_file(fixture.path, root=fixture.path.parent)
        with self.assertRaisesRegex(ValueError, "reply_drop"):
            _ = old.reply_drop_url
        for port in (True, 38088, 0):
            fixture.value["ports"]["reply_drop"] = port
            fixture.path.write_text(json.dumps(fixture.value), encoding="utf-8")
            with self.assertRaises(ValueError):
                DockerTarget.from_file(fixture.path, root=fixture.path.parent)

    def test_route_and_access_implementations_cannot_use_old_image_attestation(self):
        required = {"domains/ops/route_mcp.py", "domains/ops/policy.yaml", "domains/ops/policy.native.yaml",
            "vendor/ACPs-community/acps-sdk/acps_sdk/amp/durable_access.py", "incident/amp_setup.py"}
        self.assertTrue(required <= set(DOMAIN_SOURCE_FILES))
        fixture = self.fixture
        fixture.injector(self.stack)
        incomplete = {name: "unit-hash" for name in DOMAIN_SOURCE_FILES if name not in required}
        with self.assertRaisesRegex(ValueError, "All fixed domain source fingerprints"), \
                patch("eval.inject.run_command") as command:
            Injector(target_config=fixture.path, expected_sources=incomplete)
        command.assert_not_called()
        for name in sorted(required):
            stale = domain_proof()
            stale["ops-agent"]["source_sha256"][name] = "old-image-file"
            with self.subTest(name=name), patch("eval.inject.Injector.runtime_domain", side_effect=lambda _, service, **kw: deepcopy(stale[service])):
                with self.assertRaisesRegex(ValueError, "image source differs"):
                    Injector(target_config=fixture.path)

    def test_same_session_restores_exact_bytes_and_stops_only_owned_id(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        injector.apply("F12")
        self.assertIn(b"reply-drop", fixture.target.route_file.read_bytes())
        injector.restore("F12")
        injector.restore("F12")
        self.assertEqual(fixture.target.route_file.read_bytes(), fixture.original)
        self.assertEqual([args for args, _ in fixture.calls if "stop" in args], [["docker", "stop", "owned-proxy-id"]])
        started = next(args for args, _ in fixture.calls if "run" in args)
        for flag in ("--no-deps", "--service-ports", "--use-aliases"):
            self.assertIn(flag, started)
        self.assertEqual(started[started.index("--pull")+1], "never")
        self.assertFalse(any("rm" in args or "down" in args or "build" in args for args, _ in fixture.calls))
        self.assertTrue(injector.f12_proof["route_restored"])
        self.assertTrue(injector.f12_proof["proxy_stopped"])
        self.assertEqual(injector.f12_proof["original_route_sha256"], hashlib.sha256(fixture.original).hexdigest())
        f12_calls = [kwargs for _, kwargs in fixture.calls if "env" in kwargs]
        self.assertTrue(f12_calls)
        self.assertTrue(all(not any(key.startswith("COMPOSE_") or key == "APP_ADMIN_TOKEN" for key in kwargs["env"]) for kwargs in f12_calls))

    def test_target_env_and_baseline_changes_fail_before_start(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        fixture.target.env_file.write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            injector.apply("F12")
        injector.restore("F12")
        self.assertFalse(any("run" in args or "stop" in args for args, _ in fixture.calls))
        self.assertEqual(fixture.target.route_file.read_bytes(), fixture.original)

    def test_restarted_baseline_refuses_before_start(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        fixture.records[1]["State"]["StartedAt"] = "2026-10-19T01:01:00Z"
        with self.assertRaisesRegex(ValueError, "identity changed"):
            injector.apply("F12")
        self.assertFalse(any("run" in args for args, _ in fixture.calls))

    def test_wrong_proxy_render_image_network_port_or_mount_fails_closed(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        original = deepcopy(fixture.render)
        changes = [lambda s: s["ports"][0].update(host_ip="0.0.0.0"),
            lambda s: s.update(volumes=[{"type": "bind", "source": "/private", "target": "/private"}]),
            lambda s: s.update(networks={"default": {"aliases": ["postgres"]}}),
            lambda s: s["environment"].update(FAULT_UPSTREAM="http://other:8000"),
            lambda s: s.update(image=None)]
        for change in changes:
            fixture.render = deepcopy(original)
            change(fixture.render["services"]["reply-drop"])
            with self.subTest(change=change), self.assertRaises(ValueError):
                injector.apply("F12")
        self.assertFalse(any("run" in args or "stop" in args for args, _ in fixture.calls))
        fixture.render = original
        with patch.object(injector, "_f12_command", wraps=injector._f12_command) as command:
            real = command._mock_wraps
            command.side_effect = lambda args: json.dumps([{"Id": "wrong-image"}]) if "image" in args else real(args)
            with self.assertRaisesRegex(ValueError, "image differs"):
                injector.apply("F12")

    def test_running_proxy_is_not_adopted_or_stopped_even_by_finally(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        fixture.proxies = [{"Id": "external", "Config": {"Labels": {"incident-pilot": "true",
            "com.docker.compose.project": fixture.target.project, "com.docker.compose.service": "reply-drop",
            "incident-pilot.f12.session": "external-session"}}, "State": {"Running": True}}]
        with self.assertRaisesRegex(ValueError, "cannot be adopted"):
            injector.apply("F12")
        injector.restore("F12")
        self.assertFalse(any("run" in args or "stop" in args for args, _ in fixture.calls))

    def test_failed_create_discovers_only_session_container_and_preserves_error(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        fixture.after_create_error = RuntimeError("create failed after owned container start")
        with self.assertRaisesRegex(RuntimeError, "create failed"):
            injector.apply("F12")
        self.assertFalse(fixture.proxies[0]["State"]["Running"])
        self.assertEqual(fixture.target.route_file.read_bytes(), fixture.original)
        injector.restore("F12")

    def test_failed_route_apply_restores_exact_original_and_original_exception(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        route = injector.route
        def broken(target, **kwargs):
            if target == "reply-drop":
                fixture.target.route_file.write_bytes(b"partial\n")
                raise RuntimeError("initial route reload failure")
            return route(target, **kwargs)
        with patch.object(injector, "route", side_effect=broken):
            with self.assertRaisesRegex(RuntimeError, "initial route reload failure"):
                injector.apply("F12")
        self.assertEqual(fixture.target.route_file.read_bytes(), fixture.original)
        self.assertFalse(fixture.proxies[0]["State"]["Running"])

    def test_restore_route_failure_still_stops_proxy_and_both_errors_are_traceable(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        with patch.object(injector, "route", side_effect=RuntimeError("route error")):
            with self.assertRaises(ExceptionGroup) as caught:
                injector.apply("F12")
        self.assertEqual(len(caught.exception.exceptions), 2)
        self.assertFalse(fixture.proxies[0]["State"]["Running"])
        self.assertNotIn("route_restored", injector.f12_proof)

    def test_initial_route_and_stop_errors_retain_full_exception_chain(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        fixture.stop_error = RuntimeError("owned stop failure")
        with patch.object(injector, "route", side_effect=RuntimeError("route reload failure")):
            with self.assertRaises(ExceptionGroup) as caught:
                injector.apply("F12")
        self.assertEqual(str(caught.exception.exceptions[0]), "route reload failure")
        self.assertEqual(str(caught.exception.exceptions[1]), "owned stop failure")
        self.assertEqual(str(caught.exception.exceptions[1].__context__), "route reload failure")
        self.assertFalse(injector.f12_proof["proxy_stopped"])
        self.assertNotIn("route_restored", injector.f12_proof)

    def test_unready_proxy_uses_explicit_port_and_restores_without_routing(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        original_get = fixture.get
        def get(url):
            response = original_get(url)
            if ":38190/" in url:
                response.headers.pop("via", None)
            return response
        client = self.stack.enter_context(patch("eval.inject.httpx.Client"))
        client.return_value.__enter__.return_value.get.side_effect = get
        with self.assertRaisesRegex(RuntimeError, "not ready"):
            injector.apply("F12")
        self.assertEqual(sum(":38190/health" in url for url in fixture.http_calls), 30)
        self.assertFalse(any(":8090/" in url for url in fixture.http_calls))
        self.assertEqual(fixture.target.route_file.read_bytes(), fixture.original)
        self.assertFalse(fixture.proxies[0]["State"]["Running"])

    def test_wsl_command_removes_resource_and_compose_overrides_without_exposing_values(self):
        fixture = self.fixture
        target = DockerTarget(fixture.target.project, "Ubuntu-22.04", fixture.target.compose_files,
            fixture.target.env_file, fixture.target.route_file, fixture.target.ports)
        injector = object.__new__(Injector)
        injector.target = target
        command = target.docker+["image", "inspect", "unit-image"]
        with patch.dict(os.environ, {"APP_ADMIN_TOKEN": "offline-value", "COMPOSE_FILE": "other.yml", "WSLENV": "APP_ADMIN_TOKEN"}), \
                patch("eval.inject.run_command", return_value="[]") as run:
            injector._f12_command(command)
        args = run.call_args.args[0]
        self.assertEqual(args[:5], ["wsl.exe", "-d", "Ubuntu-22.04", "--exec", "env"])
        self.assertIn("REPLY_DROP_PORT", args)
        self.assertIn("COMPOSE_PROFILES", args)
        self.assertEqual(args[-4:], ["docker", "image", "inspect", "unit-image"])
        self.assertNotIn("offline-value", args)
        self.assertFalse({"APP_ADMIN_TOKEN", "COMPOSE_FILE", "WSLENV"} & run.call_args.kwargs["env"].keys())

    def test_replaced_proxy_identity_is_never_stopped(self):
        fixture = self.fixture
        injector = fixture.injector(self.stack)
        injector.apply("F12")
        fixture.proxies[0]["State"]["StartedAt"] = "2026-10-19T01:02:00Z"
        with self.assertRaisesRegex(ValueError, "identity changed"):
            injector.restore("F12")
        self.assertFalse(any("stop" in args for args, _ in fixture.calls))

    def test_cli_explicit_f12_mutation_rejected_before_injector_construction(self):
        for action in ("apply", "restore"):
            with self.subTest(action=action), patch("sys.argv", ["inject.py", "F12", action, "--target-config", "target.json"]), \
                    patch("eval.inject.Injector") as constructor:
                with self.assertRaisesRegex(ValueError, "in-process"):
                    main()
                constructor.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Synthetic original evidence and MockTransport; no service or real key is used."""
import asyncio
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from eval import receipt_reconciliation as tool

ORDER_ID = "eddf78ef-38a9-4c36-851c-f38a7235a5eb"


class ReceiptReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.intent = {"request_key": "synthetic-original", "operation_key": "synthetic-original-cancel",
                       "item": "book", "quantity": 2, "phase": "resolve", "resume_phase": "create",
                       "unknown_key": "synthetic-original", "was_unknown": True}
        self.trace = [{"request_key": self.intent["request_key"], "phase": "create", "method": "POST",
                       "path": "/orders", "http_status": 503, "outcome": "unknown"}]

    def fixture(self, intent=None, trace=None):
        intent, trace = deepcopy(intent or self.intent), deepcopy(trace or self.trace)
        summary = {"state": {"pending": [intent], "completed": []}, "unresolved_intents": 1,
                   "requests": len(trace), **{outcome: sum(row["outcome"] == outcome for row in trace)
                   for outcome in ("success", "failed", "unknown")}}
        (self.root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (self.root / "requests.jsonl").write_text("\n".join(json.dumps(row) for row in trace), encoding="utf-8")
        manifest = {"schema_version": 1, "base_url": "http://127.0.0.1:38088", "entries": [{"label": "synthetic-case",
                    **{kind: {"path": name, "sha256": tool.sha((self.root / name).read_bytes())}
                       for kind, name in (("summary", "summary.json"), ("trace", "requests.jsonl"))}}]}
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def receipt(self, kind="create"):
        return {"order_api_version": "v2", "operation_key": self.intent["request_key"] if kind == "create" else self.intent["operation_key"],
                "operation_kind": kind, "outcome": "committed", "order_id": ORDER_ID,
                "order": {"id": ORDER_ID, "request_key": self.intent["request_key"], "item": "book", "quantity": 2,
                          "status": "CREATED" if kind == "create" else "CANCELLED"}}

    def observe(self, body=None, *, status=200, handler=None, prepared=None):
        prepared = prepared or tool.prepare(self.fixture())
        requests = []
        def respond(request):
            requests.append(request)
            return handler(request) if handler else httpx.Response(status, json=body)
        result = asyncio.run(tool.run(prepared, self.root / "output", transport=httpx.MockTransport(respond)))
        return result, requests

    def cancellation(self, *, submitted):
        intent = dict(self.intent, phase="cancel" if not submitted else "resolve", order_id=ORDER_ID, was_unknown=submitted)
        for field in ("resume_phase", "unknown_key"):
            intent.pop(field)
        trace = [{"request_key": intent["request_key"], "phase": "create", "method": "POST", "path": "/orders", "outcome": "success", "http_status": 200},
                 {"request_key": intent["request_key"], "phase": "query", "method": "GET", "path": "/orders/" + ORDER_ID, "outcome": "success", "http_status": 200}]
        if submitted:
            intent.update(resume_phase="cancel", unknown_key=intent["operation_key"])
            trace.append({"request_key": intent["request_key"], "phase": "cancel", "method": "POST", "path": "/orders/" + ORDER_ID + "/cancel", "outcome": "unknown", "http_status": 503})
        return tool.prepare(self.fixture(intent, trace))

    def test_default_describe_never_constructs_http_client_or_writes_output(self):
        manifest = self.fixture()
        before = set(self.root.iterdir())
        with patch.object(tool.httpx, "AsyncClient", side_effect=AssertionError("network forbidden")), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(tool.main(["--manifest", str(manifest)]), 0)
        self.assertEqual(json.loads(output.getvalue())["maximum_GETs"], 1)
        self.assertEqual(set(self.root.iterdir()), before)

    def test_changed_source_or_summary_trace_disagreement_is_rejected(self):
        manifest = self.fixture()
        (self.root / "summary.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sha256"):
            tool.prepare(manifest)
        forged = dict(self.intent, unknown_key="different-key")
        with self.assertRaisesRegex(ValueError, "unknown_key"):
            tool.prepare(self.fixture(forged))

    def test_arbitrary_key_or_successful_post_is_not_an_unknown_intent(self):
        fake_trace = [dict(self.trace[0], request_key="unrelated-key")]
        with self.assertRaisesRegex(ValueError, "no_trace"):
            tool.prepare(self.fixture(trace=fake_trace))
        successful = [dict(self.trace[0], outcome="success", http_status=200)]
        with self.assertRaisesRegex(ValueError, "missing_order_id"):
            tool.prepare(self.fixture(trace=successful))
        wrong_path = [dict(self.trace[0], path="/arbitrary")]
        with self.assertRaisesRegex(ValueError, "method_path"):
            tool.prepare(self.fixture(trace=wrong_path))

    def test_continuous_summary_counts_fault_window_and_replays_full_original_trace(self):
        warmup = [dict(self.trace[0], request_key="synthetic-warmup", outcome="success", http_status=200)]
        manifest_path = self.fixture(trace=warmup + self.trace)
        summary_path = self.root / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary.update(requests=1, success=0, unknown=1, requests_per_second=1,
                       http_timeout_seconds=.8, observation_deadline_exhausted=True)
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["entries"][0]["summary"]["sha256"] = tool.sha(summary_path.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(tool.describe(tool.prepare(manifest_path))["maximum_GETs"], 1)
        summary["unknown"] = 0
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        manifest["entries"][0]["summary"]["sha256"] = tool.sha(summary_path.read_bytes())
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "counts_mismatch"):
            tool.prepare(manifest_path)

    def test_wrong_committed_receipt_bindings_remain_unknown(self):
        changes = [{"operation_key": "other-key"}, {"operation_kind": "cancel"}, {"outcome": "unknown"},
                   {"order_id": "not-a-uuid"}, {"order": {"id": ORDER_ID, "request_key": self.intent["request_key"], "item": "book", "quantity": 2, "status": "CANCELLED"}},
                   {"order": {"id": ORDER_ID, "request_key": self.intent["request_key"], "item": "pen", "quantity": 2, "status": "CREATED"}},
                   {"order": {"id": ORDER_ID, "request_key": self.intent["request_key"], "item": "book", "quantity": True, "status": "CREATED"}},
                   {"order_api_version": "v1"}]
        prepared = tool.prepare(self.fixture())
        async def check():
            for change in changes:
                with self.subTest(change=change):
                    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=dict(self.receipt(), **change)))) as client:
                        rows = await tool.observe(prepared, client)
                    self.assertEqual(rows[0]["status"], "unknown")
                    self.assertFalse(rows[0]["operation_commit_confirmed"])
        asyncio.run(check())

    def test_create_commit_is_one_get_but_does_not_complete_workflow(self):
        prepared = tool.prepare(self.fixture())
        before = {path: Path(path).read_bytes() for path in prepared["inputs"]}
        result, requests = self.observe(self.receipt(), prepared=prepared)
        self.assertEqual([(r.method, r.url.path) for r in requests], [("GET", "/receipts/synthetic-original")])
        row = result["intents"][0]
        self.assertTrue(row["operation_commit_confirmed"])
        self.assertFalse(row["workflow_terminal_confirmed"])
        self.assertTrue(row["manual_required"])
        self.assertTrue(result["original_inputs_unchanged"])
        self.assertEqual(before, {path: Path(path).read_bytes() for path in prepared["inputs"]})
        rendered = (self.root / "output/result.json").read_text(encoding="utf-8")
        self.assertNotIn(self.intent["request_key"], rendered)
        self.assertNotIn(ORDER_ID, rendered)

    def test_404_is_one_get_unknown_and_never_retried(self):
        result, requests = self.observe({"outcome": "unknown"}, status=404)
        self.assertEqual(len(requests), 1)
        self.assertEqual(result["intents"][0]["reason"], "receipt_not_found_execution_not_disproved")
        self.assertEqual(result["intents"][0]["status"], "unknown")

    def test_unsent_cancel_is_not_submitted_and_causes_no_request(self):
        prepared = self.cancellation(submitted=False)
        result, requests = self.observe(handler=lambda request: self.fail("unsent cancel must not query"), prepared=prepared)
        self.assertEqual(requests, [])
        self.assertEqual(result["actual_GET_attempts"], 0)
        self.assertEqual(result["intents"][0]["status"], "not_submitted")

    def test_cancel_requires_original_create_key_content_and_known_order_id(self):
        prepared = self.cancellation(submitted=True)
        invalid = self.receipt("cancel")
        invalid["order"] = dict(invalid["order"], request_key="other-create-key")
        wrong_identity = self.receipt("cancel")
        wrong_identity["order_id"] = "eac7cb60-6708-43eb-a586-fe677f6d71f1"
        wrong_identity["order"] = dict(wrong_identity["order"], id=wrong_identity["order_id"])
        async def check():
            for body, accepted in [(invalid, False), (wrong_identity, False), (self.receipt("cancel"), True)]:
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as client:
                    row = (await tool.observe(prepared, client))[0]
                self.assertEqual(row["workflow_terminal_confirmed"], accepted)
        asyncio.run(check())

    def test_redirect_timeout_invalid_json_each_get_once(self):
        prepared = tool.prepare(self.fixture())
        async def check():
            for kind in ("redirect", "timeout", "invalid-json"):
                count = []
                def respond(request):
                    count.append(request)
                    if kind == "timeout":
                        raise httpx.ReadTimeout("synthetic", request=request)
                    if kind == "redirect":
                        return httpx.Response(302, headers={"location": "https://unknown.invalid/"})
                    return httpx.Response(200, content=b"not-json")
                result = await tool.run(prepared, self.root / kind, transport=httpx.MockTransport(respond))
                row = result["intents"][0]
                self.assertEqual(len(count), 1)
                self.assertEqual(row["status"], "unknown")
        asyncio.run(check())

    def test_run_disables_environment_proxy_and_redirects(self):
        prepared = tool.prepare(self.fixture())
        factory = httpx.AsyncClient
        options = []
        def client_factory(**kwargs):
            options.append(kwargs)
            return factory(**kwargs)
        with patch.object(tool.httpx, "AsyncClient", side_effect=client_factory):
            asyncio.run(tool.run(prepared, self.root / "client-options",
                transport=httpx.MockTransport(lambda request: httpx.Response(404, json={}))))
        self.assertEqual(len(options), 1)
        self.assertIs(options[0]["trust_env"], False)
        self.assertIs(options[0]["follow_redirects"], False)

    def test_total_deadline_cancels_slow_get_and_continues_next_intent(self):
        prepared = tool.prepare(self.fixture())
        second = dict(prepared["jobs"][0], label="synthetic-second", operation_key="synthetic-second")
        prepared["jobs"].append(second)
        calls, cancelled = [], []
        async def respond(request):
            calls.append(request)
            if request.url.path.endswith("synthetic-original"):
                try:
                    await asyncio.sleep(1)
                finally:
                    cancelled.append(True)
            return httpx.Response(404, json={})
        with patch.object(tool, "TOTAL_DEADLINE_SECONDS", .01):
            result = asyncio.run(tool.run(prepared, self.root / "total-deadline", transport=httpx.MockTransport(respond)))
        self.assertEqual(len(calls), 2)
        self.assertEqual(cancelled, [True])
        self.assertEqual(result["actual_GET_attempts"], 2)
        self.assertEqual(result["intents"][0]["reason"], "receipt_total_deadline_exceeded")
        self.assertEqual(result["intents"][1]["reason"], "receipt_not_found_execution_not_disproved")

    def test_target_output_and_source_change_protections(self):
        for value in ("http://localhost:38088", "https://127.0.0.1:38088", "http://127.0.0.1:38088/path",
                      "http://user@127.0.0.1:38088", "http://example.com:38088", "http://127.0.0.1:38088?x=1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tool.local_base_url(value)
        prepared = tool.prepare(self.fixture())
        existing = self.root / "existing"
        existing.mkdir()
        with self.assertRaises(FileExistsError):
            asyncio.run(tool.run(prepared, existing))
        (self.root / "requests.jsonl").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "before_run"):
            asyncio.run(tool.run(prepared, self.root / "changed-output"))

    def test_midrun_source_change_is_saved_as_failed_preservation(self):
        def respond(request):
            (self.root / "requests.jsonl").write_text("synthetic concurrent edit", encoding="utf-8")
            return httpx.Response(404, json={})
        result, requests = self.observe(handler=respond)
        self.assertEqual(len(requests), 1)
        self.assertFalse(result["original_inputs_unchanged"])
        self.assertFalse(json.loads((self.root / "output/result.json").read_text(encoding="utf-8"))["original_inputs_unchanged"])


if __name__ == "__main__":
    unittest.main()

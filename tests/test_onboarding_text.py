"""Public text requests through the real adapter, with no broker or network."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "vendor/ACPs-community/acps-sdk")]

from acps_sdk.aip import StructuredDataItem, TaskCommand, TaskCommandType, TextDataItem
from domains.onboarding.check import OnboardingPartner
from domains.onboarding.text import prepare_text_request, readable_result
from incident.platform_worker import DomainExecutorAdapter

CALLER = "1.2.156.3088.1.1.34C2.478BDF.3GF546.0JU4"
SERVICE = "1.2.156.3088.1.1.34C2.478BDF.3GF547.0JU5"
TARGET = "1.2.156.3088.1.1.34C2.478BDF.3GF548.0JU6"


class OnboardingTextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.document = json.loads((ROOT / "integration/incident/application.approved.acs.json").read_text(encoding="utf-8"))
        self.target = self.document["aic"]
        self.discover = AsyncMock(return_value=self.document)
        self.executor = OnboardingPartner(SERVICE, discovery_url="https://unused.invalid", allowed_callers=[],
            discover=self.discover, public_metadata_service=True)
        self.client = SimpleNamespace(_identity_binding_enabled=True, partner_aic=SERVICE, group_id="test-group",
            _group_info=SimpleNamespace(leader=SimpleNamespace(aic=CALLER)), set_command_handler=Mock(),
            reject_task=AsyncMock(), accept_task=AsyncMock(), start_working=AsyncMock(),
            submit_for_completion=AsyncMock(), send_task_result=AsyncMock())
        self.amp = SimpleNamespace(audit_event=Mock())

    def bind(self, *, public=True, executor=None):
        return DomainExecutorAdapter(executor or self.executor, SERVICE, [CALLER], self.amp,
                                     public_metadata_service=public).bind_partner(self.client)

    def command(self, text, *, items=None):
        return TaskCommand(id="test-command", sentAt="2026-10-20T00:00:00Z", senderRole="leader", senderId=CALLER,
            sessionId="text-session", groupId="test-group", taskId="text-task", command=TaskCommandType.Start,
            mentions=[SERVICE], dataItems=items if items is not None else [TextDataItem(text=text)])

    def result_items(self):
        return self.client.submit_for_completion.await_args.args[2][0].dataItems

    async def test_plain_text_checks_one_aic_and_returns_structured_and_readable_result(self):
        result = await self.bind()(self.command(f"请检查 {self.target} 的公开元数据。"), True)
        self.discover.assert_awaited_once_with(self.target)
        self.assertEqual(result["status"], "ok")
        items = self.result_items()
        self.assertIsInstance(items[0], StructuredDataItem)
        self.assertEqual(items[0].data, result)
        self.assertIsInstance(items[1], TextDataItem)
        self.assertIn("结果：通过", items[1].text)
        self.assertIn("不代表目标运行可达", items[1].text)

    async def test_no_target_returns_help_without_discovery(self):
        result = await self.bind()(self.command("你好，请介绍一下怎么体检"), True)
        self.assertEqual(result["reason"], "target_aic_required")
        self.assertIn("请提供一个目标 AIC", self.result_items()[1].text)
        self.discover.assert_not_awaited()

    async def test_multiple_targets_return_help_without_discovery(self):
        result = await self.bind()(self.command(f"检查 {self.target} 和 {TARGET}"), True)
        self.assertEqual(result["reason"], "single_target_aic_required")
        self.discover.assert_not_awaited()

    async def test_active_intent_returns_read_only_refusal_without_discovery(self):
        result = await self.bind()(self.command(f"深度探测 {self.target} 并修复配置"), True)
        self.assertEqual(result["reason"], "read_only_metadata_check_required")
        self.assertIn("只接受公开元数据检查", self.result_items()[1].text)
        self.discover.assert_not_awaited()

    async def test_original_json_text_and_structured_ifc_keep_one_item(self):
        for structured in (False, True):
            with self.subTest(structured=structured):
                self.client.submit_for_completion.reset_mock()
                payload = dict(incident_id="existing", logical_task_id="existing-task", kind="observe",
                    tool="aip.onboarding.check", args=dict(target_aic=self.target, deep=False))
                items = [StructuredDataItem(data=payload)] if structured else [TextDataItem(text=json.dumps(payload))]
                result = await self.bind()(self.command("", items=items), True)
                self.assertEqual(result["incident_id"], "existing")
                self.assertEqual(len(self.result_items()), 1)
                self.assertIsInstance(self.result_items()[0], StructuredDataItem)

    async def test_private_onboarding_and_other_domains_still_reject_plain_text(self):
        for public, executor in ((False, self.executor), (True, Mock())):
            with self.subTest(public=public, onboarding=isinstance(executor, OnboardingPartner)):
                result = await self.bind(public=public, executor=executor)(self.command(f"检查 {self.target}"), True)
                self.assertEqual(result["reason"], "invalid_ifc_schema")
        self.discover.assert_not_awaited()
        self.client.submit_for_completion.assert_not_awaited()

    async def test_malformed_json_and_multiple_items_still_reject(self):
        cases = [[TextDataItem(text='{"target_aic": "' + self.target + '"')],
                 [TextDataItem(text=self.target), TextDataItem(text="检查")]]
        for items in cases:
            with self.subTest(items=len(items)):
                result = await self.bind()(self.command("", items=items), True)
                self.assertEqual(result["reason"], "invalid_ifc_schema")
        self.discover.assert_not_awaited()

    def test_normalization_only_produces_read_only_check_and_stable_identity(self):
        request, result = prepare_text_request(f"检查 {TARGET.lower()}. {TARGET}", session_id="s", task_id="t", executor_aic=SERVICE)
        self.assertIsNone(result)
        self.assertEqual(request["kind"], "observe")
        self.assertEqual(request["args"], dict(target_aic=TARGET, deep=False))
        self.assertEqual(request, prepare_text_request(TARGET, session_id="s", task_id="t", executor_aic=SERVICE)[0])

    def test_dangerous_and_oversized_text_never_normalizes_to_a_check(self):
        for intent in ("重启", "修改", "执行命令", "连通性", "ping", "deep check", "SQL update", "mtls"):
            with self.subTest(intent=intent):
                _, result = prepare_text_request(intent + " " + TARGET, session_id="s", task_id="t", executor_aic=SERVICE)
                self.assertEqual(result["reason"], "read_only_metadata_check_required")
        _, result = prepare_text_request("x" * 2001 + TARGET, session_id="s", task_id="t", executor_aic=SERVICE)
        self.assertEqual(result["reason"], "text_too_long")

    def test_query_failure_does_not_claim_target_fault(self):
        self.assertIn("不表示目标配置有误", readable_result(dict(status="tool_error")))


if __name__ == "__main__":
    unittest.main()

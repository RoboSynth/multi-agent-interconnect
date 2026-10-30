from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import daily_report as helper
import prepare_stage8_timer as timer

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
AICS = ["fixture-team-" + str(index) for index in range(7)]
SCHEMA = {"includes_internal_calls": True, "rows_pointer": "/data/internal",
          "aic_pointer": "/identity/aic", "rank_pointer": "/rank", "count_pointer": "/calls"}
NOW = datetime(2026, 10, 19, 16, 0, tzinfo=timezone.utc)
OFFICIAL_SCHEMA = {"includes_internal_calls": True, "boards": {"caller": "/caller", "callee": "/callee"},
                  "aic_pointer": "/aic", "rank_pointer": None, "rank_from_list_order": True,
                  "count_descending_required": True, "count_pointer": "/count",
                  "access_count_pointer": "/accessCount", "message_count_pointer": "/messageCount"}


def official_payload():
    def row(aic, count):
        return dict(aic=aic, count=count, accessCount=count, messageCount=0, extra="DO_NOT_SAVE_RAW_ROW")
    return {"caller": [row("OTHER_TEAM_DO_NOT_SAVE", 100), row(AICS[0], 10)],
            "callee": [row("OTHER_TEAM_DO_NOT_SAVE", 100),
                       *[row(aic, 10-index) for index, aic in enumerate(AICS[1:])]],
            "timeRange": {"startAt": helper.START_AT, "endAt": "2026-10-20T01:00:00+08:00"}}


def payload(aics=AICS):
    return {"data": {"internal": [
        {"identity": {"aic": "OTHER_TEAM_DO_NOT_SAVE"}, "rank": 1,
         "calls": 999, "other_team_metadata": "PRIVATE_OTHER_BODY"},
        *[{"identity": {"aic": aic}, "rank": index+2, "calls": index,
           "unexpected_payload": "DO_NOT_SAVE_RAW_ROW"} for index, aic in enumerate(aics)]]}}


class DailyReportTests(unittest.TestCase):
    def settings(self, root):
        (root/"schedule").mkdir()
        (root/"amp").mkdir()
        for index, aic in enumerate(AICS):
            record = {"aic": aic, "timestamp": (NOW-timedelta(seconds=5)).isoformat(),
                      "log_id": "hb-"+str(index), "log_type": "heartbeat", "body": {}}
            (root/"amp"/("amp_heartbeat_"+str(index)+".jsonl")).write_text(json.dumps(record)+"\n")
        return {"schedule_directory": str(root/"schedule"), "amp_directory": str(root/"amp"),
                "evidence_root": str(root/"evidence"), "expected_aics": AICS,
                "online_since": (NOW-timedelta(hours=3)).isoformat(), "leaderboard_schema": SCHEMA}

    def test_retains_only_projected_team_fields(self):
        result = helper.team_projection(payload(), SCHEMA, AICS)
        self.assertEqual(result["rank_status"], "all_team_present")
        self.assertEqual(len(result["entries"]), 7)
        self.assertEqual(set(result["entries"][0]), {"aic", "rank", "matched_calls"})
        self.assertNotIn("OTHER_TEAM", json.dumps(result))
        self.assertNotIn("DO_NOT_SAVE_RAW_ROW", json.dumps(result))

    def test_real_schema_unions_two_boards_without_inventing_a_combined_rank(self):
        result = helper.team_projection(official_payload(), OFFICIAL_SCHEMA, AICS)
        self.assertEqual(result["rank_status"], "all_team_present")
        self.assertEqual(len(result["entries"]), 7)
        coordinator = next(row for row in result["entries"] if row["aic"] == AICS[0])
        self.assertEqual((coordinator["board"], coordinator["rank"]), ("caller", 2))
        self.assertTrue(all(row["board"] == "callee" for row in result["entries"] if row["aic"] != AICS[0]))
        self.assertEqual(coordinator["access_calls"], 10)
        self.assertNotIn("OTHER_TEAM", json.dumps(result))
        self.assertNotIn("DO_NOT_SAVE_RAW_ROW", json.dumps(result))

    def test_real_schema_keeps_two_distinct_role_ranks_for_the_same_team_aic(self):
        value = official_payload()
        value["callee"].append(dict(aic=AICS[0], count=1, accessCount=1, messageCount=0))
        result = helper.team_projection(value, OFFICIAL_SCHEMA, AICS)
        rows = [row for row in result["entries"] if row["aic"] == AICS[0]]
        self.assertEqual([(row["board"], row["rank"]) for row in rows], [("caller", 2), ("callee", 8)])

    def test_real_schema_changed_count_order_fails_instead_of_assigning_wrong_positions(self):
        value = official_payload()
        value["callee"].reverse()
        with self.assertRaisesRegex(helper.ReportError, "order_changed"):
            helper.team_projection(value, OFFICIAL_SCHEMA, AICS)

    def test_standard_ascii_aic_ties_are_sorted_before_per_board_rank_assignment(self):
        aics = ["1.2.156.3088.1.BUPT." + char for char in "ABCDEFG"]
        def row(aic):
            return dict(aic=aic, count=7, accessCount=7, messageCount=0)
        value = {"caller": [row(aics[2]), row(aics[0]), row(aics[1])],
                 "callee": [row(aics[6]), row(aics[3]), row(aics[5]), row(aics[4])]}
        result = helper.team_projection(value, OFFICIAL_SCHEMA, aics)
        self.assertEqual(result["rank_status"], "all_team_present")
        self.assertEqual([(entry["aic"], entry["rank"]) for entry in result["entries"]],
                         [(aics[index], index+1) for index in range(3)] +
                         [(aics[index], index-2) for index in range(3, 7)])
        self.assertIn("AIC lexical order", result["rank_order"])

    def test_official_query_uses_fixed_start_next_shanghai_hour_and_top_200(self):
        self.assertEqual(helper.ranking_window(NOW),
            {"startAt": helper.START_AT, "endAt": "2026-10-20T01:00:00+08:00", "n": 200})

    def test_stage8_timer_is_absolute_two_hours_after_actual_logging_start_and_never_early(self):
        text = timer.render("2026-10-20T00:00:00.123456+08:00")
        self.assertIn("OnCalendar=2026-10-19 18:00:01 UTC", text)
        self.assertIn("Persistent=true", text)
        self.assertIn("Unit=incident-stage8-check.service", text)
        service = (Path(__file__).resolve().parents[1] / "incident-stage8-check.service").read_text()
        self.assertIn("--minimum-runtime-hours 2 --require-team-ranked", service)
        self.assertNotIn("--require-all-team-ranked", service)
        self.assertIn("Type=oneshot", service)

    def test_unknown_schema_is_rejected_without_echoing_payload(self):
        for response in ({"wrong": payload()}, {"data": {"internal": {}}}):
            with self.subTest(response_type=type(response).__name__):
                with self.assertRaisesRegex(helper.ReportError, "leaderboard_schema_mismatch"):
                    helper.team_projection(response, SCHEMA, AICS)
        with self.assertRaisesRegex(helper.ReportError, "not_confirmed"):
            helper.team_projection(payload(), {**SCHEMA, "includes_internal_calls": False}, AICS)

    def test_duplicate_and_boolean_rank_are_not_rank_evidence(self):
        duplicate = payload()
        duplicate["data"]["internal"].append(duplicate["data"]["internal"][1])
        with self.assertRaisesRegex(helper.ReportError, "duplicate"):
            helper.team_projection(duplicate, SCHEMA, AICS)
        boolean = payload()
        boolean["data"]["internal"][1]["rank"] = True
        with self.assertRaisesRegex(helper.ReportError, "positive_integer"):
            helper.team_projection(boolean, SCHEMA, AICS)

    def test_reuses_real_local_status_and_shanghai_daily_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, path, receipt = helper.report(self.settings(root), REPO, now=NOW,
                minimum_runtime_hours=2, require_all_team_ranked=True, fetch=payload)
            self.assertEqual(code, 0)
            self.assertEqual(path.parent.name, "longrun-20261020")
            local = json.loads((path.parent/receipt["local_status_file"]).read_text())
            self.assertEqual(local["schema_version"], "longrun-status/1")
            self.assertEqual(len(local["heartbeat_agents"]), 7)
            self.assertFalse(local["platform_ingestion_verified"])
            self.assertIsNone(local["actual_process_uptime_seconds"])
            all_text = "\n".join(p.read_text() for p in path.parent.glob("*.json"))
            self.assertNotIn("OTHER_TEAM", all_text)
            self.assertNotIn("DO_NOT_SAVE_RAW_ROW", all_text)

    def test_schema_failure_writes_safe_receipt_but_no_raw_or_rank_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, path, receipt = helper.report(self.settings(root), REPO, now=NOW,
                fetch=lambda: {"unrecognized": "OTHER_TEAM_DO_NOT_SAVE"})
            self.assertEqual(code, 1)
            self.assertEqual(receipt["reason"], "leaderboard_schema_mismatch")
            self.assertEqual(list(path.parent.glob("leaderboard*.json")), [])
            self.assertNotIn("OTHER_TEAM", path.read_text())

    def test_real_schema_report_records_actual_query_window_and_platform_window(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.settings(root)
            config["leaderboard_schema"] = OFFICIAL_SCHEMA
            code, path, receipt = helper.report(config, REPO, now=NOW, minimum_runtime_hours=2,
                require_all_team_ranked=True, fetch=official_payload)
            self.assertEqual(code, 0)
            self.assertEqual(receipt["query_window"], helper.ranking_window(NOW))
            rank = json.loads((path.parent / receipt["leaderboard_file"]).read_text())
            self.assertEqual(rank["observed_at"], NOW.isoformat())
            self.assertEqual(rank["platform_time_range"], official_payload()["timeRange"])
            self.assertNotIn("OTHER_TEAM", json.dumps(rank))

    def test_optional_require_all_mode_still_rejects_missing_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.settings(root)
            config["leaderboard_schema"] = OFFICIAL_SCHEMA
            value = official_payload()
            value["callee"].pop()
            code, _, receipt = helper.report(config, REPO, now=NOW, minimum_runtime_hours=2,
                require_all_team_ranked=True, fetch=lambda: value)
            self.assertEqual(code, 3)
            self.assertEqual(receipt["rank_status"], "partial_team_present")

    def test_stage8_team_access_passes_with_partial_presence_and_lists_missing_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.settings(root)
            config["leaderboard_schema"] = OFFICIAL_SCHEMA
            value = official_payload()
            value["callee"].pop()
            code, path, receipt = helper.report(config, REPO, now=NOW, minimum_runtime_hours=2,
                require_team_ranked=True, fetch=lambda: value)
            self.assertEqual(code, 0)
            self.assertEqual(receipt["ranking_acceptance"], "passed")
            self.assertEqual(receipt["rank_status"], "partial_team_present")
            rank = json.loads((path.parent / receipt["leaderboard_file"]).read_text())
            self.assertEqual(rank["missing_team_aics"], [AICS[-1]])
            self.assertTrue(rank["team_access_ranked"])

    def test_stage8_message_only_presence_does_not_prove_positive_access_ranking(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.settings(root)
            config["leaderboard_schema"] = OFFICIAL_SCHEMA
            value = official_payload()
            for board in ("caller", "callee"):
                for row in value[board]:
                    row.update(accessCount=0, messageCount=row["count"])
            code, _, receipt = helper.report(config, REPO, now=NOW, minimum_runtime_hours=2,
                require_team_ranked=True, fetch=lambda: value)
            self.assertEqual(code, 3)
            self.assertEqual(receipt["rank_status"], "all_team_present")
            self.assertEqual(receipt["ranking_acceptance"], "team_access_not_visible")
            self.assertFalse(receipt["team_access_ranked"])

    def test_before_two_hours_does_not_query_and_reports_waiting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.settings(root)
            config["online_since"] = (NOW-timedelta(minutes=30)).isoformat()
            def must_not_query():
                raise AssertionError("must wait before leaderboard query")
            code, _, receipt = helper.report(config, REPO, now=NOW, minimum_runtime_hours=2,
                require_team_ranked=True, fetch=must_not_query)
            self.assertEqual(code, 3)
            self.assertEqual(receipt["rank_status"], "waiting_for_minimum_runtime")
            self.assertEqual(receipt["ranking_acceptance"], "waiting_for_minimum_runtime")

    def test_valid_empty_team_ranking_is_not_successful_stage8(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, _, receipt = helper.report(self.settings(root), REPO, now=NOW,
                require_all_team_ranked=True, fetch=lambda: payload([]))
            self.assertEqual(code, 3)
            self.assertEqual(receipt["rank_status"], "team_not_present")

    def test_explicit_seven_roots_copy_only_logs_and_cleanup_private_view(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.settings(root)
            config.pop("amp_directory")
            roots = []
            for index, aic in enumerate(AICS):
                directory = root/("source-"+str(index))
                directory.mkdir()
                (directory/"key.pem").write_text("DO_NOT_COPY_PRIVATE_KEY")
                source = root/"amp"/("amp_heartbeat_"+str(index)+".jsonl")
                (directory/source.name).write_bytes(source.read_bytes())
                roots.append(str(directory))
            config["amp_directories"] = roots
            before = {p: p.read_bytes() for directory in roots for p in Path(directory).glob("*")}
            seen = []
            from ops.longrun_status import status
            def inspect_then_status(schedule, amp, **kwargs):
                seen.append(amp)
                self.assertEqual(len(list(amp.rglob("amp_*.jsonl"))), 7)
                self.assertEqual(list(amp.rglob("*.pem")), [])
                return status(schedule, amp, **kwargs)
            code, path, receipt = helper.report(config, REPO, now=NOW,
                fetch=payload, local_status=inspect_then_status)
            self.assertEqual(code, 0)
            self.assertEqual(receipt["amp_input_roots"], 7)
            self.assertFalse(seen[0].exists())
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            local = json.loads((path.parent/receipt["local_status_file"]).read_text())
            self.assertEqual(len(local["heartbeat_agents"]), 7)

    def test_copy_failure_cleans_temporary_view_and_retains_error_class_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.settings(root)
            config.pop("amp_directory")
            roots = []
            for index in range(7):
                directory = root/("source-"+str(index)); directory.mkdir()
                (directory/"amp_heartbeat_fixture.jsonl").write_text("{}\n")
                roots.append(str(directory))
            config["amp_directories"] = roots
            targets = []
            def fail_copy(source, target):
                targets.append(target)
                raise PermissionError("DO_NOT_ECHO_LOG_CONTENT_OR_PATH")
            with patch.object(helper.shutil, "copyfile", side_effect=fail_copy):
                code, path, receipt = helper.report(config, REPO, now=NOW, fetch=payload)
            self.assertEqual(code, 1)
            self.assertEqual(receipt["error_class"], "PermissionError")
            self.assertNotIn("DO_NOT_ECHO", path.read_text())
            self.assertFalse(targets[0].parent.parent.exists())


if __name__ == "__main__":
    unittest.main()

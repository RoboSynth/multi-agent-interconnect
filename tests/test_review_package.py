"""Anonymous exports must fail closed and preserve measured numerical data."""
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.package_review import (
    png_text, repair_links, safe_name, sanitize_text, scan_text, text_decode, transform,
)

POLICY = {
    "terms": [
        {"value": "REVIEW_PERSON_42", "replacement": "Anonymous Contributor", "category": "person_name"},
        {"value": "sample-owner-42", "replacement": "project-team", "category": "github_account"},
        {"value": "Example Research School", "replacement": "Research Organization", "category": "school_name"},
    ],
    "path_prefixes": [],
}


class ReviewPackageTests(unittest.TestCase):
    def test_encoded_names_are_detected_and_removed(self):
        value = "REVIEW_PERSON_42"
        escaped = "".join("\\u%04x" % ord(c) for c in value)
        self.assertIn("person_name", scan_text(escaped, POLICY))
        cleaned, _ = sanitize_text(escaped, POLICY)
        self.assertFalse(scan_text(cleaned, POLICY))
        # Normal JSON encoding uses literal ASCII; non-ASCII variants are also supported.
        text, _ = sanitize_text(json.dumps({"person": value}), POLICY)
        self.assertFalse(scan_text(text, POLICY))

    def test_paths_are_redacted_without_changing_measurements(self):
        path = "C:" + "\\" + "Users" + "\\" + "fixture-user" + "\\run"
        data = json.dumps({"path": path, "elapsed": 1.275452, "passed": 15}).encode()
        exported, _, _ = transform("result.json", data, POLICY)
        value = json.loads(exported)
        self.assertEqual(value["elapsed"], 1.275452)
        self.assertEqual(value["passed"], 15)
        self.assertNotIn("fixture-user", value["path"])
        self.assertFalse(scan_text(exported.decode(), POLICY))

    def test_short_name_does_not_rewrite_substrings_in_identifiers(self):
        policy = {"terms": [{"value": "lisi", "replacement": "contact",
                            "category": "example_person_name", "whole_word": True}]}
        output, _ = sanitize_text("collision lisi@example.invalid", policy)
        self.assertEqual(output, "collision contact@example.invalid")
        self.assertFalse(scan_text(output, policy))

    def test_acronyms_do_not_match_across_ordinary_word_spacing(self):
        policy = {"terms": [{"value": "DUT", "replacement": "ORGX", "category": "school_name"}]}
        self.assertFalse(scan_text("Shared utilities", policy))

    def test_unicode_escaped_workspace_prefix_is_removed(self):
        policy = {"terms": [], "path_prefixes": ["D:/项目"]}
        data = json.dumps({"file": "D:/项目/result.json"}, ensure_ascii=True).encode()
        output, _, _ = transform("capture.json", data, policy)
        self.assertFalse(scan_text(output.decode(), policy))
        self.assertEqual(json.loads(output)["file"], "X:/workspace/result.json")

    def test_legacy_windows_log_encoding_is_explicit(self):
        output, _, mode = transform("native.txt", "运行成功".encode("gb18030"), POLICY)
        self.assertEqual(output.decode("utf-8"), "运行成功")
        self.assertEqual(mode, "full_text_legacy_windows_codepage")

    def test_provider_is_neutral_and_schema_description_is_not_rewritten(self):
        data = {"provider": {"name": "Example Research School"}, "success": 30}
        output, _, _ = transform("agent.json", json.dumps(data).encode(), POLICY)
        self.assertEqual(json.loads(output)["provider"]["name"], "Incident Pilot Project")
        self.assertEqual(json.loads(output)["success"], 30)
        schema = {"provider": {"name": {"type": "string"}}}
        output, _, _ = transform("schema.json", json.dumps(schema).encode(), POLICY)
        self.assertEqual(json.loads(output), schema)

    def test_team_links_use_nonlive_placeholder_and_official_links_remain(self):
        text = "https://github.com/sample-owner-42/project https://github.com/official-org/sdk"
        output, _ = sanitize_text(text, POLICY)
        self.assertIn("https://example.invalid/project-source/project", output)
        self.assertIn("https://github.com/official-org/sdk", output)

    def test_paths_and_private_files_cannot_enter_archive(self):
        for value in ("../other.txt", "private/account.json", ".git/config",
                      "runtime/data.json", "key.pem", "records.sqlite"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                safe_name(value)

    def test_utf16_logs_decode_and_unknown_binary_fails(self):
        self.assertEqual(text_decode("hello".encode("utf-16")), "hello")
        with self.assertRaises(UnicodeDecodeError):
            text_decode(b"\x81\xff\x80")

    def test_png_text_is_scanned_and_exif_fails(self):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        data = b"\x89PNG\r\n\x1a\n" + chunk(b"tEXt", b"Author\0REVIEW_PERSON_42") + chunk(b"IEND", b"")
        self.assertIn("person_name", scan_text(png_text(data), POLICY))
        with self.assertRaises(ValueError):
            transform("figure.png", data, POLICY)
        with self.assertRaises(ValueError):
            png_text(b"\x89PNG\r\n\x1a\n" + chunk(b"eXIf", b"opaque"))

    def test_cross_archive_links_and_missing_history_are_explicit(self):
        packages = {
            "code": {"docs/report.md": b"[data](../evidence/run/result.json)"},
            "evidence": {
                "evidence/run/result.json": b"{}",
                "README.md": b"[old](docs/missing.md)",
            },
        }
        repair_links(packages)
        self.assertIn(b"../../review-evidence/evidence/run/result.json", packages["code"]["docs/report.md"])
        self.assertNotIn(b"](docs/missing.md)", packages["evidence"]["README.md"])


if __name__ == "__main__":
    unittest.main()

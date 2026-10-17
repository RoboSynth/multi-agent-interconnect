"""Hidden properties and failed extraction must not produce a clean audit."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.material_scan import scan


class MaterialScanTests(unittest.TestCase):
    def test_split_school_markers_and_explicit_personal_terms(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"content.txt"
            path.write_text("某大\n学，Ｓａｍｐｌｅ　Ｔｅａｃｈｅｒ", encoding="utf-8")
            result = scan([path], forbidden_terms=["Sample Teacher"])
        self.assertFalse(result["machine_checks_passed"])
        self.assertEqual({row["category"] for row in result["findings"]}, {"school_marker", "forbidden_term_1"})
        self.assertNotIn("Sample Teacher", str(result["findings"]))

    def test_pdf_properties_are_scanned_when_page_text_is_clean(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"report.pdf"
            path.write_bytes(b"fixture")
            outputs = [b"Anonymous content", b"Author: sample@example.com", b""]
            with patch("eval.material_scan.subprocess.run", side_effect=[subprocess.CompletedProcess([], 0, stdout=value) for value in outputs]) as run:
                result = scan([path], poppler_dir=folder)
            self.assertEqual(run.call_count, 3)
        self.assertEqual(result["findings"][0]["section"], "pdf_properties")
        self.assertFalse(result["machine_checks_passed"])

    def test_missing_unsupported_and_empty_extraction_are_not_zero_hit_success(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder)/"image.png"
            image.write_bytes(b"image")
            result = scan([Path(folder)/"missing.txt", image])
            self.assertEqual(result["hits"], 0)
            self.assertEqual(len(result["errors"]), 2)
            self.assertFalse(result["machine_checks_passed"])
            pdf = Path(folder)/"report.pdf"
            pdf.write_bytes(b"fixture")
            with patch("eval.material_scan.subprocess.run", return_value=subprocess.CompletedProcess([], 0, stdout=b"")):
                self.assertFalse(scan([pdf], poppler_dir=folder)["machine_checks_passed"])

    def test_clean_text_pass_is_bounded_and_fingerprinted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"content.md"
            path.write_text("十个订单流程完成，原请求仍待核对。", encoding="utf-8")
            result = scan([path])
        self.assertTrue(result["machine_checks_passed"])
        self.assertEqual(len(result["files"][0]["sha256"]), 64)
        self.assertFalse(result["final_submission_anonymity_proven"])
        self.assertFalse(scan([])["machine_checks_passed"])


if __name__ == "__main__":
    unittest.main()

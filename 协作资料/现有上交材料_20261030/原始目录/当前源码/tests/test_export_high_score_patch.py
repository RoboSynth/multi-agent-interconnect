"""Exporter checks use temporary fixtures, never the real baseline/export tree."""
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "tools/export_high_score_patch.py"
spec = importlib.util.spec_from_file_location("source_exporter", SCRIPT)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class SourceExport(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="incident-export-test-")
        self.root = Path(self.temp.name) / "project"
        self.baseline = Path(self.temp.name) / "baseline"
        for root in (self.root, self.baseline):
            path = root / exporter.SDK_PREFIX / "acps_sdk/aip/example.py"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"old = 1\r\n")

    def tearDown(self):
        self.temp.cleanup()

    def put(self, name, content=b"print('source')\n"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def test_allowlist_excludes_private_environments_runtimes_and_results(self):
        self.put("business/order.py")
        self.put("demo-ui/workbench.js")
        self.put("demo-ui/app.js")
        for name in (".dockerignore", "deploy/.dockerignore", "deploy/Dockerfile.agent", "deploy/Dockerfile.docker-mcp"):
            self.put(name)
        for name in ("business/private/credentials.json", "business/runtime/state.json", "business/.env",
                     "deploy/.env.example", "deploy/native-runtime.json", "deploy/client.pem", "deploy/client.key",
                     "eval/results/run.json", "integration/private/key.py", "tools/runtime/unsafe.py", ".venv/site.py",
                     "artifacts/task.py", "tests/__pycache__/unsafe.py"):
            self.put(name)
        selected = {path.as_posix() for path in exporter.source_paths(self.root)}
        self.assertEqual(selected, {"business/order.py", "demo-ui/workbench.js", ".dockerignore", "deploy/.dockerignore",
                                    "deploy/Dockerfile.agent", "deploy/Dockerfile.docker-mcp"})

    def test_archive_is_byte_reproducible_and_contains_no_live_tree(self):
        self.put("business/order.py")
        self.put("eval/results/do-not-ship.json", b'{"secret":"not for export"}')
        entries1, patch1, manifest1 = exporter.prepare_export(self.root, self.baseline)
        entries2, patch2, manifest2 = exporter.prepare_export(self.root, self.baseline)
        first, second = exporter.deterministic_zip(entries1), exporter.deterministic_zip(entries2)
        self.assertEqual(first, second)
        self.assertEqual(patch1, patch2)
        self.assertEqual(manifest1, manifest2)
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertNotIn("eval/results/do-not-ship.json", archive.namelist())
            self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()))

    @unittest.skipUnless(shutil.which("git"), "git unavailable for isolated patch application check")
    def test_patch_applies_exact_bytes_including_no_final_newline(self):
        target = exporter.SDK_PREFIX / "acps_sdk/aip/example.py"
        changed = b"new = 2\nfinal = 3"
        (self.root / target).write_bytes(changed)
        self.put((exporter.SDK_PREFIX / "acps_sdk/aip/new.py").as_posix(), b"added = True\n")
        patch, changes = exporter.sdk_patch(self.root, self.baseline)
        patch_file = Path(self.temp.name) / "sdk.patch"
        patch_file.write_bytes(patch)
        applied = subprocess.run(["git", "-c", "core.autocrlf=false", "-C", str(self.baseline), "apply", str(patch_file)], capture_output=True, text=True)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual((self.baseline / target).read_bytes(), changed)
        self.assertEqual(len(changes), 2)


if __name__ == "__main__":
    unittest.main()

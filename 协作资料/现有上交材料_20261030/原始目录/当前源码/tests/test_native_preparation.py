"""Offline preparation boundaries using synthetic files and stubbed transports."""
from contextlib import contextmanager, redirect_stdout
import io
import json
import ntpath
from pathlib import Path
import shutil
import types
import unittest
from unittest import mock
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load_tool(name):
    path = ROOT / "tools" / (name + ".py")
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


@contextmanager
def fixture_directory():
    base = ROOT / "artifacts/native-preparation-20261018/fixtures"
    base.mkdir(parents=True, exist_ok=True)
    directory = base / uuid.uuid4().hex
    directory.mkdir()
    try:
        yield directory
    finally:
        if directory.resolve().parent != base.resolve() or directory.is_symlink():
            raise AssertionError("Fixture cleanup escaped its artifact directory")
        shutil.rmtree(directory)


class DatabasePreparationTests(unittest.TestCase):
    def test_import_does_not_create_alias_or_start_process(self):
        with mock.patch("subprocess.run", side_effect=AssertionError("Unexpected process")), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("Unexpected process")):
            load_tool("prepare_native_database")

    def test_existing_cluster_missing_any_identity_fails_before_writes_or_alias(self):
        for missing in ("postgres-superuser", "application", "database"):
            with self.subTest(missing=missing), fixture_directory() as root:
                module = load_tool("prepare_native_database")
                private = root / "runtime/private"
                private.mkdir(parents=True)
                data = root / "selected-data"
                data.mkdir()
                (data / "PG_VERSION").write_text("16", encoding="utf-8")
                deploy = root / "deploy"
                deploy.mkdir()
                runtime_file = deploy / "native-runtime.json"
                runtime_file.write_text(json.dumps({"pgdata": str(data)}), encoding="utf-8")
                for role in module.ENVIRONMENT:
                    if role != missing:
                        (private / (role + ".env")).write_text("synthetic=unchanged\n", encoding="utf-8")
                before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
                with mock.patch.multiple(module, ROOT=root, PRIVATE=private), \
                     mock.patch.object(module, "native_root", side_effect=AssertionError("Alias must not be touched")), \
                     mock.patch.object(module.secrets, "token_urlsafe", side_effect=AssertionError("No new password")), \
                     mock.patch.object(module.subprocess, "run", side_effect=AssertionError("No resources")), \
                     mock.patch.object(module.subprocess, "Popen", side_effect=AssertionError("No resources")):
                    with self.assertRaisesRegex(RuntimeError, "missing identity env files: " + missing):
                        module.prepare()
                self.assertEqual(before, {path.relative_to(root): path.read_bytes()
                    for path in root.rglob("*") if path.is_file()})

    def test_existing_selected_paths_and_identity_bytes_survive_preparation(self):
        with fixture_directory() as root:
            module = load_tool("prepare_native_database")
            private = root / "runtime/private"
            private.mkdir(parents=True)
            data, binaries = root / "selected-data", root / "selected-bin"
            data.mkdir()
            (data / "PG_VERSION").write_text("16", encoding="utf-8")
            (root / "deploy").mkdir()
            (root / "business/order_app").mkdir(parents=True)
            (root / "business/order_app/schema.sql").write_text("-- synthetic schema", encoding="utf-8")
            saved = {"postgres_bin": str(binaries), "pgdata": str(data), "nginx_bin": "chosen/nginx.exe",
                     "nginx_prefix": "chosen/prefix", "custom_setting": {"retain": True}}
            runtime_file = root / "deploy/native-runtime.json"
            runtime_file.write_text(json.dumps(saved), encoding="utf-8")
            for role, values in module.ENVIRONMENT.items():
                (private / (role + ".env")).write_text("# retain fixture bytes\nPGHOST=127.0.0.1\nPGPORT=55432\n"
                    "PGDATABASE=orders\nPGUSER=" + values["PGUSER"] + "\nPGPASSWORD=synthetic-password\n", encoding="utf-8")
            identities = {path.name: path.read_bytes() for path in private.iterdir()}
            commands = []

            def run(command, **kwargs):
                commands.append(command)
                self.assertEqual(Path(command[0]).parent, binaries)
                if Path(command[0]).name == "pg_ctl.exe":
                    self.assertEqual(command[-1], str(data))
                    return types.SimpleNamespace(returncode=0)
                self.assertEqual(Path(command[0]).name, "psql.exe")
                return types.SimpleNamespace(returncode=0, stdout="1\n", stderr="")

            with mock.patch.multiple(module, ROOT=root, PRIVATE=private), \
                 mock.patch.object(module, "native_root", return_value=root), \
                 mock.patch.object(module.secrets, "token_urlsafe", side_effect=AssertionError("No password replacement")), \
                 mock.patch.object(module.subprocess, "run", side_effect=run), \
                 mock.patch.object(module.subprocess, "Popen", side_effect=AssertionError("No server start")), \
                 redirect_stdout(io.StringIO()):
                module.prepare()
            self.assertGreater(len(commands), 1)
            self.assertEqual(json.loads(runtime_file.read_text(encoding="utf-8")), saved)
            self.assertEqual(identities, {path.name: path.read_bytes() for path in private.iterdir()})
            summary = json.loads((root / "runtime/database-setup.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["data_directory"], str(data))

    def test_new_cluster_adds_only_missing_runtime_path_defaults(self):
        with fixture_directory() as root:
            module = load_tool("prepare_native_database")
            (root / "deploy").mkdir()
            (root / "runtime").mkdir()
            (root / "business/order_app").mkdir(parents=True)
            (root / "business/order_app/schema.sql").write_text("-- synthetic schema", encoding="utf-8")
            runtime_file = root / "deploy/native-runtime.json"
            runtime_file.write_text('{"nginx_prefix":"retain-prefix","custom_setting":7}', encoding="utf-8")
            commands = []

            def run(command, **kwargs):
                commands.append(command)
                return types.SimpleNamespace(returncode=0, stdout="1\n", stderr="")

            with mock.patch.multiple(module, ROOT=root, PRIVATE=root / "runtime/private"), \
                 mock.patch.object(module, "native_root", return_value=root), \
                 mock.patch.object(module.secrets, "token_urlsafe", return_value="synthetic-generated-password"), \
                 mock.patch.object(module.subprocess, "run", side_effect=run), \
                 mock.patch.object(module.subprocess, "Popen", side_effect=AssertionError("No server start")), \
                 redirect_stdout(io.StringIO()):
                module.prepare()
            self.assertEqual(Path(commands[0][0]).name, "initdb.exe")
            runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
            self.assertEqual(runtime["pgdata"], str(root / "runtime/pgdata"))
            self.assertEqual(runtime["postgres_bin"], str(root / "tools/runtime/pgsql/bin"))
            self.assertEqual(runtime["nginx_prefix"], "retain-prefix")
            self.assertEqual(runtime["custom_setting"], 7)
            self.assertFalse((root / "runtime/private/initdb-password.txt").exists())


class NativeRootTests(unittest.TestCase):
    @contextmanager
    def aliases(self, module, temporary, targets):
        original_resolve = Path.resolve
        original_lexists = module.os.path.lexists
        commands = []

        def resolve(path, *args, **kwargs):
            if path in targets:
                return targets[path]
            return original_resolve(path, *args, **kwargs)

        def create(command, **kwargs):
            self.assertEqual(command[:3], ["powershell.exe", "-NoProfile", "-Command"])
            self.assertTrue(kwargs["check"])
            text = command[3]
            start = "New-Item -ItemType Junction -Path '"
            self.assertTrue(text.startswith(start) and text.endswith("' | Out-Null"))
            alias, target = text[len(start):-len("' | Out-Null")].split("' -Target '")
            alias, target = Path(alias.replace("''", "'")), Path(target.replace("''", "'"))
            self.assertNotIn(alias, targets)
            targets[alias] = target
            commands.append(command)
            return types.SimpleNamespace(returncode=0)

        windows = types.SimpleNamespace(name="nt", path=types.SimpleNamespace(
            normcase=ntpath.normcase, lexists=lambda path: Path(path) in targets or original_lexists(path)))
        with mock.patch.object(module, "os", windows), \
             mock.patch.object(module.tempfile, "gettempdir", return_value=str(temporary)), \
             mock.patch.object(Path, "resolve", resolve), \
             mock.patch.object(module.subprocess, "run", side_effect=create), \
             mock.patch.object(module.subprocess, "Popen", side_effect=AssertionError("No resources")):
            yield commands

    def test_two_checkouts_get_separate_stable_ascii_aliases(self):
        with fixture_directory() as base:
            first, second, temporary = base / "检出甲", base / "检出乙", base / "aliases"
            for path in (first, second, temporary):
                path.mkdir()
            module = load_tool("prepare_native_database")
            targets = {}
            with self.aliases(module, temporary, targets) as commands:
                with mock.patch.object(module, "ROOT", first):
                    one = module.native_root()
                with mock.patch.object(module, "ROOT", second):
                    two = module.native_root()
                with mock.patch.object(module, "ROOT", first / ".." / first.name):
                    self.assertEqual(module.native_root(), one)
                self.assertNotEqual(one, two)
                self.assertTrue(one.name.isascii() and two.name.isascii())
                self.assertEqual(len(commands), 2)
                self.assertEqual(targets[one], first)
                self.assertEqual(targets[two], second)

    def test_matching_legacy_alias_is_reused_without_writes(self):
        with fixture_directory() as base:
            root, temporary = base / "检出甲", base / "aliases"
            root.mkdir()
            temporary.mkdir()
            saved = root / "saved-runtime.json"
            identity = root / "identity.env"
            saved.write_bytes(b'{"pgdata":"keep-selected-data"}')
            identity.write_bytes(b"synthetic=preserve\n")
            before = saved.read_bytes(), identity.read_bytes()
            legacy = temporary / "incident-pilot-runtime-01a148fe"
            module = load_tool("prepare_native_database")
            with self.aliases(module, temporary, {legacy: root}) as commands, \
                 mock.patch.object(module, "ROOT", root):
                self.assertEqual(module.native_root(), legacy)
                self.assertFalse(commands)
            self.assertEqual((saved.read_bytes(), identity.read_bytes()), before)

    def test_other_checkout_legacy_alias_is_not_changed(self):
        with fixture_directory() as base:
            root, other, temporary = base / "检出甲", base / "检出乙", base / "aliases"
            for path in (root, other, temporary):
                path.mkdir()
            legacy = temporary / "incident-pilot-runtime-01a148fe"
            legacy.mkdir()
            marker = legacy / "owner.txt"
            marker.write_bytes(b"other checkout unchanged")
            module = load_tool("prepare_native_database")
            targets = {legacy: other}
            with self.aliases(module, temporary, targets) as commands, \
                 mock.patch.object(module, "ROOT", root):
                alias = module.native_root()
                self.assertNotEqual(alias, legacy)
                self.assertEqual(targets[legacy], other)
                self.assertEqual(targets[alias], root)
                self.assertEqual(len(commands), 1)
            self.assertEqual(marker.read_bytes(), b"other checkout unchanged")

    def test_wrong_project_hash_alias_is_rejected_without_overwrite(self):
        with fixture_directory() as base:
            root, other, temporary = base / "检出甲", base / "检出乙", base / "aliases"
            for path in (root, other, temporary):
                path.mkdir()
            module = load_tool("prepare_native_database")
            targets = {}
            with self.aliases(module, temporary, targets) as commands, \
                 mock.patch.object(module, "ROOT", root):
                alias = module.native_root()
                targets[alias] = other
                commands.clear()
                with self.assertRaisesRegex(RuntimeError, "alias does not target this project"):
                    module.native_root()
                self.assertFalse(commands)
                self.assertEqual(targets[alias], other)


def archive_bytes(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as package:
        for name, content in entries.items():
            package.writestr(name, content)
    return stream.getvalue()


class RuntimeDownloadTests(unittest.TestCase):
    def install_fixture(self, root, payload, *, cached=False):
        module = load_tool("download_native_runtime")
        destination = root / "runtime"
        destination.mkdir()
        archive = destination / "nginx-1.30.6.zip"
        if cached:
            archive.write_bytes(payload)
        return module, destination, archive

    def test_valid_new_archive_is_verified_then_promoted_and_extracted(self):
        with fixture_directory() as root:
            payload = archive_bytes({"nginx-1.30.6/nginx.exe": b"synthetic executable"})
            module, destination, archive = self.install_fixture(root, payload)
            with mock.patch.object(module, "DEST", destination), \
                 mock.patch.object(module.urllib.request, "urlopen", return_value=io.BytesIO(payload)) as request:
                result = module.install(("nginx-1.30.6.zip", "https://fixture.invalid/runtime.zip"))
            request.assert_called_once()
            self.assertEqual(archive.read_bytes(), payload)
            self.assertEqual((destination / "nginx-1.30.6/nginx.exe").read_bytes(), b"synthetic executable")
            self.assertEqual(result["extracted_members"], 1)
            self.assertEqual(list(destination.glob("*.download")), [])

    def test_valid_cached_archive_reuses_bytes_without_network(self):
        with fixture_directory() as root:
            payload = archive_bytes({"nginx-1.30.6/nginx.exe": b"synthetic executable"})
            module, destination, archive = self.install_fixture(root, payload, cached=True)
            with mock.patch.object(module, "DEST", destination), \
                 mock.patch.object(module.urllib.request, "urlopen", side_effect=AssertionError("No network")):
                module.install(("nginx-1.30.6.zip", "https://fixture.invalid/runtime.zip"))
            self.assertEqual(archive.read_bytes(), payload)
            self.assertTrue((destination / "nginx-1.30.6/nginx.exe").is_file())

    def test_postgresql_required_commands_are_extracted_without_pgadmin(self):
        with fixture_directory() as root:
            entries = {"pgsql/bin/" + name: b"synthetic executable" for name in
                ("postgres.exe", "pg_ctl.exe", "initdb.exe", "psql.exe", "pg_isready.exe")}
            entries["pgsql/pgAdmin 4/unused.exe"] = b"exclude this optional application"
            payload = archive_bytes(entries)
            module = load_tool("download_native_runtime")
            destination = root / "runtime"
            with mock.patch.object(module, "DEST", destination), \
                 mock.patch.object(module.urllib.request, "urlopen", return_value=io.BytesIO(payload)):
                result = module.install(("postgresql-16.15.zip", "https://fixture.invalid/runtime.zip"))
            self.assertEqual(result["extracted_members"], 5)
            self.assertTrue((destination / "pgsql/bin/postgres.exe").is_file())
            self.assertFalse((destination / "pgsql/pgAdmin 4/unused.exe").exists())

    def test_bad_cached_archive_fails_clearly_and_preserves_original_without_network(self):
        with fixture_directory() as root:
            payload = b"PK\x03\x04truncated fixture"
            module, destination, archive = self.install_fixture(root, payload, cached=True)
            with mock.patch.object(module, "DEST", destination), \
                 mock.patch.object(module.urllib.request, "urlopen", side_effect=AssertionError("No network")):
                with self.assertRaisesRegex(RuntimeError, "preserved nginx-1.30.6.zip"):
                    module.install(("nginx-1.30.6.zip", "https://fixture.invalid/runtime.zip"))
            self.assertEqual(archive.read_bytes(), payload)
            self.assertEqual(list(destination.iterdir()), [archive])

    def test_invalid_downloads_are_retained_without_canonical_cache_or_extraction(self):
        valid = archive_bytes({"nginx-1.30.6/nginx.exe": b"CRC_MARKER_CONTENT"})
        cases = {
            "truncated": b"PK\x03\x04truncated fixture",
            "missing-entry": archive_bytes({"nginx-1.30.6/readme.txt": b"not executable"}),
            "crc": valid.replace(b"CRC_MARKER_CONTENT", b"X" * len(b"CRC_MARKER_CONTENT"), 1),
            "escape": archive_bytes({"nginx-1.30.6/nginx.exe": b"fixture", "../escape.txt": b"reject"}),
        }
        for name, payload in cases.items():
            with self.subTest(case=name), fixture_directory() as root:
                module, destination, archive = self.install_fixture(root, payload)
                with mock.patch.object(module, "DEST", destination), \
                     mock.patch.object(module.urllib.request, "urlopen", return_value=io.BytesIO(payload)):
                    with self.assertRaisesRegex(RuntimeError, "Runtime archive validation failed; preserved"):
                        module.install(("nginx-1.30.6.zip", "https://fixture.invalid/runtime.zip"))
                self.assertFalse(archive.exists())
                retained = list(destination.glob("*.download"))
                self.assertEqual(len(retained), 1)
                self.assertEqual(retained[0].read_bytes(), payload)
                self.assertEqual(list(destination.iterdir()), retained)
                self.assertFalse((root / "escape.txt").exists())


if __name__ == "__main__":
    unittest.main()

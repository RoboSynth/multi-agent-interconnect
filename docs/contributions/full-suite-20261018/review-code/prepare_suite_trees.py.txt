"""Prepare fresh local SDK copies and offline TLS fixtures; never install or run pytest.

Default is a read-only plan. --prepare creates a new trees/ directory once.
All generated keys remain local to that directory. No registered identity is used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import venv

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIGINAL = ROOT / "artifacts/upstream-public-submission-20261018"
LOCKED = HERE / "locked-dependencies"
GIT = (Path(sys.base_prefix).parent / "native/git/cmd/git.exe").resolve()
BRANCHES = {
    "resumable": ("branch-resumable", "30f8840785a1b02a661e0fbb335a8dcd9bb038d0"),
    "message-emitter": ("branch-message-emitter", "ddf2094ef2ea7b687a8966e43302ab07d23b9950"),
}
PARTNER = "demo-partner/partners/online/beijing_food"
LEADER = "demo-leader/leader/atr"
FIXTURES = (PARTNER + "/server.pem", PARTNER + "/server.key", PARTNER + "/client.pem", PARTNER + "/client.key",
            PARTNER + "/trust-bundle.pem", LEADER + "/client.pem", LEADER + "/client.key", LEADER + "/trust-bundle.pem")
# AIC-shaped synthetic identifiers avoid weakening the SDK identity parser.
PARTNER_CN = "1.2.156.3088.1.1.TESTCA.TEST01.TEST01.0001"
LEADER_CN = "1.2.156.3088.1.1.TESTCA.TEST01.TEST02.0002"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def run_git(directory, *arguments):
    assert GIT.is_file() and GIT.is_absolute()
    directory = Path(directory).resolve()
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    result = subprocess.run([str(GIT), "-C", str(directory), "-c", "core.autocrlf=false",
        "-c", "safe.directory=" + str(directory), *arguments],
        env=env, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError("Local Git operation failed: " + " ".join(arguments[:2]) + ": exit " + str(result.returncode))
    return result.stdout


def sdk_sources(tree):
    names = run_git(tree, "ls-files", "-z", "--", "acps-sdk/").decode().split("\0")
    return {name: sha((tree / name).read_bytes()) for name in names if name}


def baseline():
    records = {}
    for name, (folder, commit) in BRANCHES.items():
        tree = ORIGINAL / folder
        assert run_git(tree, "rev-parse", "HEAD").decode().strip() == commit
        assert not run_git(tree, "status", "--porcelain=v1", "--untracked-files=all")
        assert all(not (tree / relative).exists() for relative in FIXTURES)
        records[name] = dict(commit=commit, source=tree, sdk_source_sha256=sdk_sources(tree))
    return records


def isolate_imports():
    # Imported packages come only from the reviewed independent dependency target.
    base = Path(sys.base_prefix)
    stdlib = base / "Lib"
    sys.path[:] = [str(LOCKED), str(stdlib), str(base / "DLLs"), str(base / ("python" + str(sys.version_info.major) + str(sys.version_info.minor) + ".zip"))]
    installed = {dist.metadata["Name"].lower().replace("_", "-"): dist.version
                 for dist in importlib.metadata.distributions(path=[str(LOCKED)])}
    audit_raw = (HERE / "locked-dependency-audit.json").read_bytes()
    audit = json.loads(audit_raw)
    assert audit["status"] == "ISOLATED_LOCKED_DEPENDENCY_GRAPH_VALIDATED" and not audit["problems"]
    assert installed == audit["installed_distributions"] and len(installed) == 36
    for name in ("cryptography", "pytest", "pytest-asyncio", "anyio", "pydantic", "aio-pika", "httpx", "jcs", "pyjwt"):
        assert name in installed, "Independent dependency target incomplete: " + name
    assert installed["pytest"] == "9.0.2" and installed["pytest-asyncio"] == "1.4.0"
    return installed, sha(audit_raw)


def make_tls():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Offline SDK test fixture"),
                         x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic SDK suite CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
            encipher_only=None, decipher_only=None), critical=True).sign(ca_key, hashes.SHA256()))
    pem = lambda cert: cert.public_bytes(serialization.Encoding.PEM)
    leaves = {}
    for role, cn in (("partner-server", PARTNER_CN), ("partner-client", PARTNER_CN), ("leader-client", LEADER_CN)):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Offline SDK test fixture"),
                          x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(ca.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=2)).add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                x509.UniformResourceIdentifier("acps://" + cn)]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True,
                data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=None, decipher_only=None), critical=True).sign(ca_key, hashes.SHA256()))
        leaves[role] = (pem(cert), key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
            dict(common_name=cn, certificate_sha256=sha(pem(cert)), public_key_sha256=sha(key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)),
                valid_from_utc=cert.not_valid_before_utc.isoformat(), valid_until_utc=cert.not_valid_after_utc.isoformat(),
                extended_key_usage=["serverAuth", "clientAuth"], SAN=["localhost", "127.0.0.1", "acps://" + cn]))
    assert leaves["partner-server"][2]["public_key_sha256"] != leaves["partner-client"][2]["public_key_sha256"]
    files = {PARTNER + "/server.pem": leaves["partner-server"][0], PARTNER + "/server.key": leaves["partner-server"][1],
        PARTNER + "/client.pem": leaves["partner-client"][0], PARTNER + "/client.key": leaves["partner-client"][1],
        PARTNER + "/trust-bundle.pem": pem(ca), LEADER + "/client.pem": leaves["leader-client"][0],
        LEADER + "/client.key": leaves["leader-client"][1], LEADER + "/trust-bundle.pem": pem(ca)}
    assert set(files) == set(FIXTURES)
    return files, dict(test_only=True, registered_platform_identity_used=False, CA_private_key_persisted=False,
        CA_certificate_sha256=sha(pem(ca)), leaves={role: row[2] for role, row in leaves.items()},
        expected_fixture_paths=list(FIXTURES), private_keys_publication_allowed=False)


def make_interpreter():
    target = HERE / "runtime-venv"
    assert not target.exists()
    venv.EnvBuilder(with_pip=False, symlinks=False, system_site_packages=False).create(target)
    site = target / "Lib/site-packages"
    # ASCII execution line is valid even if Windows reads .pth using the local codepage.
    pth = ("import sys; sys.path.insert(0, " + json.dumps(str(LOCKED.resolve()), ensure_ascii=True) + ")\n").encode("ascii")
    (site / "sdk-suite-locked-dependencies.pth").write_bytes(pth)
    config = (target / "pyvenv.cfg").read_text(encoding="utf-8")
    assert "include-system-site-packages = false" in config.lower()
    executable = target / "Scripts/python.exe"
    assert executable.is_file()
    return dict(executable=str(executable), base_executable=str(Path(getattr(sys, "_base_executable", sys.executable))),
        include_system_site_packages=False, with_pip=False,
        pth_sha256=sha(pth), pth_encoding="ASCII JSON-escaped absolute dependency path", locked_dependency_path=str(LOCKED.resolve()),
        official_child_uses_same_interpreter_without_sys_executable_override=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    originals = baseline()
    if not args.prepare:
        print(json.dumps(dict(status="READONLY_FULL_SUITE_PREPARATION_PLAN", branches={name: row["commit"] for name, row in originals.items()},
            output="trees/<branch>", independent_dependencies="locked-dependencies", synthetic_leaf_certificates=3,
            synthetic_CA_certificates=1, expected_fixture_files_per_tree=8, pytest_executed=False)))
        return
    assert not (HERE / "trees").exists() and not (HERE / "prepared-trees.json").exists() and not (HERE / "runtime-venv").exists(), "Existing preparation must be preserved"
    installed, audit_sha = isolate_imports()
    output = HERE / "trees"
    output.mkdir()
    # Exclusive marker preserves a partial attempt and prevents accidental retries.
    (HERE / "preparation-start.json").write_bytes(encoded(dict(started_at_utc=datetime.now(timezone.utc).isoformat(),
        helper_sha256=sha(Path(__file__).read_bytes()), commits={name: row["commit"] for name, row in originals.items()})))
    interpreter = make_interpreter()
    branches = {}
    for name, row in originals.items():
        target = output / name
        run_git(row["source"], "clone", "--local", "--no-hardlinks", "--no-checkout", str(row["source"]), str(target))
        run_git(target, "checkout", "--detach", row["commit"])
        assert sdk_sources(target) == row["sdk_source_sha256"]
        fixture_bytes, public_metadata = make_tls()
        for relative, data in fixture_bytes.items():
            path = target / relative
            assert path.resolve().is_relative_to(target.resolve()) and not path.exists()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
            if path.suffix == ".key":
                path.chmod(0o600)
        assert sdk_sources(target) == row["sdk_source_sha256"]
        assert sdk_sources(row["source"]) == row["sdk_source_sha256"]
        assert not run_git(row["source"], "status", "--porcelain=v1", "--untracked-files=all")
        branches[name] = dict(commit=row["commit"], tree=target.relative_to(HERE).as_posix(),
            sdk_source_sha256=row["sdk_source_sha256"], original_source_bytes_unchanged=True,
            fresh_SDK_source_bytes_exact=True, public_TLS_metadata=public_metadata)
    receipt = dict(status="FRESH_LOCAL_OFFICIAL_BRANCH_COPIES_AND_SYNTHETIC_TLS_FIXTURES_PREPARED", branches=branches, interpreter=interpreter,
        dependency_versions=installed, dependency_source="locked-dependencies only", locked_dependency_audit_sha256=audit_sha,
        native_Git_executable=str(GIT), Git_global_or_system_config_used=False,
        helper_sha256=sha(Path(__file__).read_bytes()),
        original_branches_modified=False, SDK_source_or_tests_modified=False, network_calls=0, pytest_executed=False,
        platform_identity_or_resource_credentials_read=False, synthetic_fixture_private_keys_local_only=True,
        completed_at_utc=datetime.now(timezone.utc).isoformat())
    (HERE / "prepared-trees.json").write_bytes(encoded(receipt))
    print(json.dumps(dict(status=receipt["status"], branches=list(branches), expected_fixture_files_per_tree=8, pytest_executed=False)))


if __name__ == "__main__":
    main()

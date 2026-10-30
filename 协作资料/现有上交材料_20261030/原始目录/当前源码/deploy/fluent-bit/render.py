"""Render six official AMP topic routes for local stdout or configured Kafka."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

KINDS = ("audit", "heartbeat", "metrics", "access", "message", "system")
COLLECTION_ROLES = ("coordinator", "application", "database", "database-backup", "ops", "verification", "onboarding")
ROOT = Path(__file__).resolve().parents[2]
TLS_FILES = ("ssl.ca.location", "ssl.certificate.location", "ssl.key.location")
ENV_REFERENCE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def parse_kinds(value=None):
    """Select a nonempty subset of the six AMP kinds, kept in canonical order.

    A staged rollout can first send only heartbeat and access, then widen the
    selection; every kind keeps its own offset database, so adding a kind later
    starts that kind at new lines when Read_From_Head is false and that kind has
    no existing offset. Existing offsets always resume without resetting others.
    """
    if value is None or value == "all":
        return KINDS
    items = value.split(",") if isinstance(value, str) else list(value)
    items = [item.strip() for item in items]
    if not items or any(item not in KINDS for item in items) or len(set(items)) != len(items):
        raise ValueError("kinds.invalid")
    return tuple(kind for kind in KINDS if kind in items)


def source_id(directory):
    """One stable owner/state identity for relative, absolute and Windows aliases."""
    normalized = os.path.normcase(str(Path(directory).resolve()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _kafka_fields(kafka, *, check_environment=True):
    if not isinstance(kafka, dict) or not isinstance(kafka.get("brokers"), str):
        raise ValueError("kafka.brokers_required")
    brokers = kafka["brokers"]
    if (not brokers or any(word in brokers.upper() for word in ("REPLACE", "TODO", "<"))
            or any(char.isspace() for char in brokers) or "://" in brokers or "@" in brokers
            or any(not item for item in brokers.split(","))):
        raise ValueError("kafka.invalid_brokers")
    properties = kafka.get("rdkafka")
    if not isinstance(properties, dict) or not isinstance(properties.get("security.protocol"), str):
        raise ValueError("kafka.security_protocol_required")
    protocol = properties["security.protocol"].lower()
    if protocol not in {"ssl", "sasl_ssl", "plaintext", "sasl_plaintext"}:
        raise ValueError("kafka.invalid_security_protocol")
    for key, value in properties.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_.]+", key) or not isinstance(value, str) or "\n" in value or "\r" in value:
            raise ValueError("kafka.invalid_property")
        if "password" in key and not ENV_REFERENCE.fullmatch(value):
            raise ValueError("kafka.password_requires_environment_reference")
        if check_environment and any(not os.environ.get(name) for name in ENV_REFERENCE.findall(value)):
            raise ValueError("kafka.environment_reference_unset")
    if protocol in {"ssl", "sasl_ssl"} and not properties.get("ssl.ca.location"):
        raise ValueError("kafka.explicit_tls_ca_required")
    if bool(properties.get("ssl.certificate.location")) != bool(properties.get("ssl.key.location")):
        raise ValueError("kafka.client_certificate_and_key_must_be_paired")
    if protocol.startswith("sasl_") and any(not properties.get(key) for key in ("sasl.mechanism", "sasl.username", "sasl.password")):
        raise ValueError("kafka.sasl_fields_required")
    return protocol, properties


def validate_kafka(kafka):
    """Validate metadata/path presence only; never open TLS material or connect."""
    protocol, properties = _kafka_fields(kafka)
    checked = []
    for key in TLS_FILES:
        if key in properties:
            value = ENV_REFERENCE.sub(lambda match: os.environ[match[1]], properties[key])
            if not Path(value).is_absolute() or not Path(value).is_file():
                raise ValueError("kafka.tls_file_missing_or_not_absolute:" + key)
            checked.append(key)
    return {"security_protocol": protocol, "tls_files_checked": checked}


def check(log_directory, parser_file, *, mode="stdout", kafka=None, kinds=KINDS):
    """Pure preflight: no native_path/subst, writes, subprocesses or network."""
    kinds = parse_kinds(kinds)
    errors, counts = [], {}
    directory = Path(log_directory).resolve()
    if not directory.is_dir():
        errors.append("logs.directory_missing")
    for kind in kinds:
        counts[kind] = sum(path.is_file() for path in directory.glob(f"amp_{kind}_*.jsonl")) if directory.is_dir() else 0
        if not counts[kind]:
            errors.append("logs.missing_kind:" + kind)
    if not Path(parser_file).is_file():
        errors.append("parser.file_missing")
    kafka_report = None
    if mode == "kafka":
        try:
            kafka_report = validate_kafka(kafka)
        except ValueError as error:
            errors.append(str(error))
    elif mode != "stdout":
        errors.append("mode.invalid")
    return {"status": "FLUENT_BIT_FILE_PREFLIGHT", "passed": not errors, "source_id": source_id(directory),
            "mode": mode, "kinds": list(kinds), "log_files_by_kind": counts, "errors": errors, "kafka": kafka_report,
            "kafka_connection_tested": False, "platform_ingestion_tested": False}


@contextmanager
def source_owner(directory):
    """Nonblocking OS lock per input path, independent of output/state overrides."""
    owners = ROOT / "runtime/fluent-bit-owners"
    owners.mkdir(parents=True, exist_ok=True)
    stream = (owners / (source_id(directory) + ".lock")).open("a+b")
    try:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("source.already_owned") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def collection_sources(sources):
    """Validate the seven explicit local paths without reading log contents."""
    if not isinstance(sources, dict) or set(sources) != set(COLLECTION_ROLES):
        raise ValueError("collection.seven_roles_required")
    result = {}
    for role in COLLECTION_ROLES:
        if not isinstance(sources[role], (str, Path)) or not str(sources[role]):
            raise ValueError("collection.invalid_source:" + role)
        directory = Path(sources[role]).resolve()
        if not directory.is_dir() or any(char in str(directory) for char in (",", "\r", "\n")):
            raise ValueError("collection.invalid_source:" + role)
        result[role] = directory
    if len({source_id(directory) for directory in result.values()}) != len(COLLECTION_ROLES):
        raise ValueError("collection.duplicate_canonical_source")
    return result


@contextmanager
def collection_owner(sources):
    """Acquire a stable lock order and release prior locks if acquisition fails."""
    directories = collection_sources(sources).values()
    with ExitStack() as owners:
        for directory in sorted(directories, key=source_id):
            owners.enter_context(source_owner(directory))
        yield


def check_collection(sources, parser_file, *, mode="stdout", kafka=None, kinds=KINDS):
    try:
        checked = collection_sources(sources)
    except ValueError as error:
        return {"status": "FLUENT_BIT_COLLECTION_PREFLIGHT", "passed": False, "errors": [str(error)],
                "kafka_connection_tested": False, "platform_ingestion_tested": False}
    reports = {role: check(directory, parser_file, mode=mode, kafka=kafka, kinds=kinds) for role, directory in checked.items()}
    return {"status": "FLUENT_BIT_COLLECTION_PREFLIGHT", "passed": all(item["passed"] for item in reports.values()),
            "sources": reports, "errors": [], "kafka_connection_tested": False, "platform_ingestion_tested": False}


def native_path(value):
    resolved = Path(value).resolve()
    if os.name != "nt" or resolved.as_posix().isascii():
        return resolved.as_posix()
    if not resolved.is_relative_to(ROOT):
        raise ValueError("Windows Fluent Bit needs an ASCII path outside the project; select an ASCII log/state path")
    settings = ROOT / "deploy/native-runtime.json"
    drive = json.loads(settings.read_text(encoding="utf-8-sig")).get("native_drive", "P:") if settings.exists() else "P:"
    if not re.fullmatch(r"[D-Z]:", drive, re.I):
        raise ValueError("Select a registered native data drive for Fluent Bit")
    alias = Path(drive + "/")
    if not alias.exists():
        subprocess.run(["subst.exe", drive, str(ROOT)], capture_output=True, check=True, timeout=5)
    if not alias.samefile(ROOT):
        raise ValueError("Native drive points to another workspace")
    return (alias / resolved.relative_to(ROOT)).as_posix()


def _render_paths(inputs, parser_file, *, mode, kafka, read_from_head):
    if mode not in {"stdout", "kafka"}:
        raise ValueError("mode.invalid")
    if mode == "kafka":
        _kafka_fields(kafka, check_environment=False)
    lines = ["[SERVICE]", "    Flush 1", "    Daemon Off", "    Grace 1", "    Log_Level info",
             "    Parsers_File " + parser_file, ""]
    for kind, filename, database in inputs:
        lines.extend(["[INPUT]", "    Name tail", f"    Tag amp.{kind}",
            "    Path " + filename, "    Parser amp_json", "    DB " + database,
            "    Read_From_Head " + ("True" if read_from_head else "False"),
            "    Refresh_Interval 1", "    Buffer_Max_Size 1M", "    Skip_Long_Lines Off", ""])
    for kind in (kind for kind in KINDS if any(row[0] == kind for row in inputs)):
        lines.extend(["[OUTPUT]", "    Name " + ("kafka" if mode == "kafka" else "stdout"), f"    Match amp.{kind}"])
        if mode == "kafka":
            lines.extend(["    Brokers " + kafka["brokers"], f"    Topics amp.{kind}", "    Workers 1",
                "    rdkafka.log.connection.close false", "    rdkafka.request.required.acks 1",
                "    rdkafka.allow.auto.create.topics false"])
            if kind == "audit":
                lines.append("    timestamp_key _fb_ts")
            for key, value in kafka["rdkafka"].items():
                lines.append(f"    rdkafka.{key} {value}")
        else:
            # Keep human-readable stdout records intact across six routes.
            lines.append("    Workers 0")
        lines.append("")
    return "\n".join(lines)


def _render(sources, parser_file, *, mode, kafka, read_from_head, kinds=KINDS):
    if mode not in {"stdout", "kafka"}:
        raise ValueError("mode.invalid")
    if mode == "kafka":
        validate_kafka(kafka)
    parser = native_path(parser_file)
    inputs = []
    for log_directory, state_directory in sources:
        for kind in parse_kinds(kinds):
            filename = native_path(Path(log_directory) / f"amp_{kind}_*.jsonl")
            if os.name == "nt":
                # Windows Tail globbing needs backslashes; config loading does not.
                filename = filename.replace("/", "\\")
            inputs.append((kind, filename, native_path(Path(state_directory) / f"amp-{kind}.db")))
    return _render_paths(inputs, parser, mode=mode, kafka=kafka, read_from_head=read_from_head)


def render(log_directory, state_directory, parser_file, *, mode="stdout", kafka=None, read_from_head=False,
           kinds=KINDS):
    return _render([(log_directory, state_directory)], parser_file,
                   mode=mode, kafka=kafka, read_from_head=read_from_head, kinds=kinds)


def render_collection(sources, state_root, parser_file, *, mode="stdout", kafka=None, read_from_head=True,
                      kinds=KINDS):
    checked = collection_sources(sources)
    inputs = [(directory, Path(state_root) / source_id(directory) / mode)
              for directory in checked.values()]
    return _render(inputs, parser_file, mode=mode, kafka=kafka, read_from_head=read_from_head, kinds=kinds)


def render_collection_paths(sources, state_paths, parser_file, *, mode="stdout", kafka=None, read_from_head=True,
                            kinds=KINDS):
    """Render Linux mount paths without host IO; validate Kafka on the host first.

    state_paths maps each role to a flat DB template with one ``{kind}`` token.
    TLS locations in kafka must already refer to the container's read-only mounts.
    """
    def linux_path(value):
        if (not isinstance(value, str) or not value.startswith("/")
                or any(char in value for char in ("\\", ",", "\r", "\n", "\x00"))
                or ".." in PurePosixPath(value).parts):
            raise ValueError("collection.invalid_linux_path")
        return str(PurePosixPath(value))
    if (not isinstance(sources, dict) or set(sources) != set(COLLECTION_ROLES)
            or not isinstance(state_paths, dict) or set(state_paths) != set(COLLECTION_ROLES)):
        raise ValueError("collection.seven_roles_required")
    paths = {role: linux_path(sources[role]) for role in COLLECTION_ROLES}
    if len(set(paths.values())) != len(COLLECTION_ROLES):
        raise ValueError("collection.duplicate_linux_source")
    inputs = []
    for role in COLLECTION_ROLES:
        template = state_paths[role]
        if not isinstance(template, str) or template.count("{kind}") != 1 or "{" in template.replace("{kind}", "") or "}" in template.replace("{kind}", ""):
            raise ValueError("collection.invalid_database_template")
        for kind in parse_kinds(kinds):
            inputs.append((kind, paths[role] + f"/amp_{kind}_*.jsonl", linux_path(template.replace("{kind}", kind))))
    if len({database for _, _, database in inputs}) != len(inputs):
        raise ValueError("collection.duplicate_database")
    if mode == "kafka":
        _kafka_fields(kafka, check_environment=False)
        for key in TLS_FILES:
            if key in kafka["rdkafka"]:
                linux_path(kafka["rdkafka"][key])
    return _render_paths(inputs, linux_path(parser_file), mode=mode, kafka=kafka, read_from_head=read_from_head)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--log-directory", type=Path)
    inputs.add_argument("--collection-sources", type=Path, help="JSON object mapping the seven roles to local log directories")
    locations = parser.add_mutually_exclusive_group()
    locations.add_argument("--state-directory", type=Path)
    locations.add_argument("--state-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=["stdout", "kafka"], default="stdout")
    parser.add_argument("--kafka-settings", type=Path)
    parser.add_argument("--read-from-head", action="store_true")
    parser.add_argument("--kinds", default="all",
                        help="Comma-separated AMP kinds to route, e.g. heartbeat,access; default all six")
    parser.add_argument("--check", action="store_true", help="Read-only field/path check; never render or run")
    parser.add_argument("--executable", type=Path, help="Internal foreground runner; holds the input owner lock until exit")
    args = parser.parse_args(argv)
    kinds = parse_kinds(args.kinds)
    if args.check and args.executable:
        parser.error("--check cannot run --executable")
    if args.collection_sources:
        if args.kafka_settings and args.mode != "kafka":
            raise ValueError("collection.kafka_settings_require_kafka_mode")
        sources = json.loads(args.collection_sources.read_text(encoding="utf-8-sig"))
        settings = json.loads(args.kafka_settings.read_text(encoding="utf-8-sig")) if args.kafka_settings else None
        report = check_collection(sources, Path(__file__).with_name("parsers.conf"), mode=args.mode, kafka=settings,
                                  kinds=kinds)
        if args.check or not report["passed"]:
            print(json.dumps(report))
            return 0 if report["passed"] else 1
        if not args.state_root:
            parser.error("Collection rendering requires --state-root")
        state = args.state_root.resolve()
        output = args.output or state / ("collection-" + args.mode + ".conf")
        if args.executable and not args.executable.is_file():
            raise ValueError("executable.file_missing")
        def prepare_collection():
            config = render_collection(sources, state, Path(__file__).with_name("parsers.conf"), mode=args.mode,
                                       kafka=settings, read_from_head=args.read_from_head, kinds=kinds)
            for directory in collection_sources(sources).values():
                (state / source_id(directory) / args.mode).mkdir(parents=True, exist_ok=True)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(config, encoding="utf-8")
            count = len(collection_sources(sources)) * len(kinds)
            print(json.dumps(dict(report, status="FLUENT_BIT_COLLECTION_PREPARED", kinds=list(kinds),
                                  inputs=count, offset_databases=count)))
        if args.executable:
            with collection_owner(sources):
                prepare_collection()
                return subprocess.run([str(args.executable.resolve()), "-c", str(output.resolve())]).returncode
        prepare_collection()
        return 0
    settings = json.loads(args.kafka_settings.read_text(encoding="utf-8-sig")) if args.kafka_settings else None
    report = check(args.log_directory, Path(__file__).with_name("parsers.conf"), mode=args.mode, kafka=settings,
                   kinds=kinds)
    if args.check or not report["passed"]:
        print(json.dumps(report))
        return 0 if report["passed"] else 1
    directory = args.log_directory.resolve()
    state = args.state_root.resolve() / report["source_id"] / args.mode if args.state_root else args.state_directory
    if state is None:
        parser.error("Rendering requires --state-directory or --state-root")
    output = args.output or (state / ("fluent-bit-" + args.mode + ".conf") if args.state_root else None)
    if output is None:
        parser.error("Rendering with --state-directory requires --output")
    if args.executable and not args.executable.is_file():
        raise ValueError("executable.file_missing")

    def prepare():
        config = render(directory, state, Path(__file__).with_name("parsers.conf"),
                        mode=args.mode, kafka=settings, read_from_head=args.read_from_head, kinds=kinds)
        state.mkdir(parents=True, exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(config, encoding="utf-8")
        print(json.dumps(dict(report, status="FLUENT_BIT_CONFIG_PREPARED", output=str(output.resolve()),
                              routes=["amp." + kind for kind in kinds])))

    if args.executable:
        with source_owner(directory):
            prepare()
            return subprocess.run([str(args.executable.resolve()), "-c", str(output.resolve())]).returncode
    prepare()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        # Paths, broker details and private settings must not leak in errors.
        print(json.dumps({"status": "failed", "error_class": type(error).__name__}))
        raise SystemExit(1)

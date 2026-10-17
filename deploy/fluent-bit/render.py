"""Render six official AMP topic routes for local stdout or configured Kafka."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

KINDS = ("audit", "heartbeat", "metrics", "access", "message", "system")
ROOT = Path(__file__).resolve().parents[2]


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


def render(log_directory, state_directory, parser_file, *, mode="stdout", kafka=None, read_from_head=False):
    path = native_path
    lines = ["[SERVICE]", "    Flush 1", "    Daemon Off", "    Grace 1", "    Log_Level info",
             "    Parsers_File " + path(parser_file), ""]
    for kind in KINDS:
        tail_path = path(Path(log_directory) / f"amp_{kind}_*.jsonl")
        if os.name == "nt":
            # Windows Tail's file globbing needs backslashes, even though the
            # parser/config file loader accepts forward slashes.
            tail_path = tail_path.replace("/", "\\")
        lines.extend(["[INPUT]", "    Name tail", f"    Tag amp.{kind}",
            "    Path " + tail_path, "    Parser amp_json",
            "    DB " + path(Path(state_directory) / f"amp-{kind}.db"),
            "    Read_From_Head " + ("True" if read_from_head else "False"),
            "    Refresh_Interval 1", "    Buffer_Max_Size 1M", "    Skip_Long_Lines Off", ""])
    if mode == "kafka":
        if not kafka or not kafka.get("brokers") or not kafka.get("rdkafka", {}).get("security.protocol"):
            raise ValueError("Kafka brokers and confirmed security.protocol must be supplied explicitly")
        if any(value in str(kafka["brokers"]) for value in ("REPLACE", "TODO", "<", "\n", "\r")):
            raise ValueError("Kafka broker configuration is still a placeholder")
        protocol = kafka["rdkafka"]["security.protocol"].lower()
        if protocol not in {"ssl", "sasl_ssl", "plaintext", "sasl_plaintext"}:
            raise ValueError("Unknown Kafka security.protocol")
        for key, value in kafka.get("rdkafka", {}).items():
            if not re.fullmatch(r"[a-zA-Z0-9_.]+", key) or not isinstance(value, str) or "\n" in value or "\r" in value:
                raise ValueError("Invalid Kafka property")
            if "password" in key and not re.fullmatch(r"\$\{[A-Z_][A-Z0-9_]*\}", value):
                raise ValueError("Kafka passwords must be environment references, not stored in rendered config")
    for kind in KINDS:
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-directory", type=Path, required=True)
    parser.add_argument("--state-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["stdout", "kafka"], default="stdout")
    parser.add_argument("--kafka-settings", type=Path)
    parser.add_argument("--read-from-head", action="store_true")
    args = parser.parse_args()
    args.state_directory.mkdir(parents=True, exist_ok=True)
    settings = json.loads(args.kafka_settings.read_text(encoding="utf-8-sig")) if args.kafka_settings else None
    config = render(args.log_directory, args.state_directory, Path(__file__).with_name("parsers.conf"),
                    mode=args.mode, kafka=settings, read_from_head=args.read_from_head)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(config, encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "mode": args.mode, "routes": ["amp." + kind for kind in KINDS],
                      "kafka_connection_tested": False}))


if __name__ == "__main__":
    main()

"""Recover only an existing domain access journal, without connecting to AIP or tools."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from acps_sdk.amp import DurableAccessEmitter


def fingerprint(path):
    if not path.exists():
        return {"exists": False, "bytes": 0, "sha256": None}
    raw = path.read_bytes()
    return {"exists": True, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def recover(config_path, *, expected_aic, expected_name, expected_directory, state_root):
    """Require the original identity/path and journal; never create a replacement intent."""
    config_path = Path(config_path)
    raw_config = config_path.read_bytes()
    config = json.loads(raw_config.decode("utf-8-sig"))
    platform = config["platform"]
    if (not expected_aic or not expected_name.replace("-", "").replace("_", "").isalnum()
            or config["executor_aic"] != expected_aic or platform["name"] != expected_name
            or platform["amp_directory"] != str(expected_directory)):
        raise ValueError("Recovery identity, name or original directory differs from the explicit scope")
    directory, state = Path(expected_directory), Path(state_root).resolve()
    if not directory.is_absolute() or not directory.resolve().is_relative_to(state):
        raise ValueError("Access recovery must remain in its owned state root")
    emitter = DurableAccessEmitter(directory / ("amp_access_" + expected_name + ".jsonl"), expected_aic)
    if emitter.journal_path.is_symlink() or not emitter.journal_path.is_file():
        raise ValueError("Original access journal is missing; do not fabricate one")
    # Opening the normal emitter may initialize a brand-new journal. Recovery
    # must first prove that this original database already has its owner/schema.
    with closing(sqlite3.connect(emitter.journal_path.as_uri() + "?mode=ro", uri=True, timeout=0)) as connection:
        owner = connection.execute("SELECT aic, log_path FROM owner").fetchall()
        columns = [row[1] for row in connection.execute("PRAGMA table_info(attempts)")]
        if owner != [(expected_aic, os.path.normcase(str(emitter._log_file)))]:
            raise ValueError("Original access journal owner does not match")
        if columns != ["event_key", "log_id", "intent", "record", "written"]:
            raise ValueError("Original access journal schema does not match")
    before = fingerprint(emitter._log_file)
    journal_before = fingerprint(emitter.journal_path)
    try:
        emitter.start_sync()
    finally:
        emitter.close_sync()
    rows = [json.loads(line) for line in emitter._log_file.read_bytes().splitlines()] if emitter._log_file.exists() else []
    return {"schema_version": "domain-access-recovery/1", "status": "recovered",
            "aic": expected_aic, "name": expected_name,
            "config_sha256": hashlib.sha256(raw_config).hexdigest(),
            "log_before": before, "log_after": fingerprint(emitter._log_file),
            "journal_before": journal_before, "journal_after": fingerprint(emitter.journal_path),
            "unique_access_ids": len({row["log_id"] for row in rows}),
            "access_rows": len(rows),
            "unconfirmed_outcomes": sum(((row.get("body") or {}).get("error") or {}).get("code") == "OutcomeUnconfirmed" for row in rows),
            "business_or_platform_actions": 0,
            "scope": "original domain journal only; existing immutable records replayed, unknown outcomes retained"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--expected-aic", required=True)
    parser.add_argument("--expected-name", required=True)
    parser.add_argument("--expected-directory", required=True)
    parser.add_argument("--state-root", type=Path, default=Path("/state"))
    args = parser.parse_args(argv)
    try:
        result = recover(args.config, expected_aic=args.expected_aic, expected_name=args.expected_name,
                         expected_directory=args.expected_directory, state_root=args.state_root)
    except Exception as error:
        print(json.dumps({"status": "failed", "error_class": type(error).__name__}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

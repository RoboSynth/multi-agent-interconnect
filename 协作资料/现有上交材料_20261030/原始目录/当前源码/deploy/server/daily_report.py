"""Record local longrun status and only this team's verified leaderboard fields."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://wt.ioa.pub/internal/matched-stats/top"
START_AT = "2026-09-24T00:00:00+08:00"
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")


class ReportError(ValueError):
    pass


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ReportError("timestamp_timezone_required")
    return result.astimezone(timezone.utc)


def pointer(value, path):
    """Resolve an explicitly configured RFC6901 pointer, never infer a schema."""
    if path == "":
        return value
    if not isinstance(path, str) or not path.startswith("/"):
        raise ReportError("invalid_json_pointer")
    try:
        for token in path[1:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            value = value[int(token)] if isinstance(value, list) else value[token]
        return value
    except (ValueError, TypeError, KeyError, IndexError):
        raise ReportError("leaderboard_schema_mismatch") from None


def validate_schema(schema):
    if not isinstance(schema, dict) or schema.get("includes_internal_calls") is not True:
        raise ReportError("internal_board_schema_not_confirmed")
    if "boards" in schema:
        boards = schema["boards"]
        if (not isinstance(boards, dict) or set(boards) != {"caller", "callee"}
                or any(not isinstance(path, str) or not path.startswith("/") for path in boards.values())):
            raise ReportError("internal_caller_callee_boards_required")
        for path in boards.values():
            validate_schema({key: value for key, value in schema.items() if key != "boards"} | {"rows_pointer": path})
        return
    if not isinstance(schema.get("rows_pointer"), str) or not isinstance(schema.get("aic_pointer"), str):
        raise ReportError("leaderboard_schema_not_configured")
    if not schema["aic_pointer"]:
        raise ReportError("aic_pointer_must_select_a_field")
    if (not isinstance(schema.get("rank_pointer"), str)
            and schema.get("rank_from_list_order") is not True):
        raise ReportError("rank_schema_not_configured")


def team_projection(payload, schema, aics):
    validate_schema(schema)
    if "boards" in schema:
        boards = {board: team_projection(payload,
            {key: value for key, value in schema.items() if key != "boards"} | {"rows_pointer": path}, aics)
            for board, path in schema["boards"].items()}
        entries = [dict(board=board, **row) for board, result in boards.items() for row in result["entries"]]
        seen = {row["aic"] for row in entries}
        missing = sorted(set(aics)-seen)
        return {"rank_status": ("all_team_present" if not missing else
                                "partial_team_present" if seen else "team_not_present"),
                "entries": entries, "missing_team_aics": missing, "includes_internal_calls": True,
                "raw_response_saved": False,
                "rank_order": boards["caller"]["rank_order"],
                "basis": "union of exact team AICs in internal caller/callee top-200 lists; separate board ranks"}
    rows = pointer(payload, schema["rows_pointer"])
    if not isinstance(rows, list):
        raise ReportError("leaderboard_schema_mismatch")
    if schema.get("count_descending_required") is True:
        counts = [pointer(row, schema["count_pointer"]) for row in rows]
        if any(type(value) is not int or value < 0 for value in counts) or counts != sorted(counts, reverse=True):
            raise ReportError("leaderboard_count_order_changed")
        for row in rows:
            aic = pointer(row, schema["aic_pointer"])
            if not isinstance(aic, str) or not aic:
                raise ReportError("leaderboard_schema_mismatch")
        # The official page orders ties by aic.localeCompare. Lexical order
        # agrees for standard uppercase ASCII AICs; do not inherit API tie order.
        rows = sorted(rows, key=lambda row: (-pointer(row, schema["count_pointer"]),
                                             pointer(row, schema["aic_pointer"])))
    team, records, seen = set(aics), [], set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ReportError("leaderboard_schema_mismatch")
        aic = pointer(row, schema["aic_pointer"])
        if not isinstance(aic, str) or not aic:
            raise ReportError("leaderboard_schema_mismatch")
        if aic not in team:
            continue
        if aic in seen:
            raise ReportError("duplicate_team_aic_in_selected_board")
        rank = (pointer(row, schema["rank_pointer"])
                if isinstance(schema.get("rank_pointer"), str) else index)
        if type(rank) is not int or rank < 1:
            raise ReportError("leaderboard_rank_not_positive_integer")
        record = {"aic": aic, "rank": rank}
        if schema.get("count_pointer") is not None:
            count = pointer(row, schema["count_pointer"])
            if type(count) is not int or count < 0:
                raise ReportError("leaderboard_count_not_nonnegative_integer")
            record["matched_calls"] = count
        for source, output in (("access_count_pointer", "access_calls"), ("message_count_pointer", "message_calls")):
            if schema.get(source) is not None:
                value = pointer(row, schema[source])
                if type(value) is not int or value < 0:
                    raise ReportError("leaderboard_count_not_nonnegative_integer")
                record[output] = value
        records.append(record)
        seen.add(aic)
    missing = sorted(team-seen)
    return {"rank_status": ("all_team_present" if not missing else
                            "partial_team_present" if records else "team_not_present"),
            "entries": sorted(records, key=lambda row: row["rank"]),
            "missing_team_aics": missing, "includes_internal_calls": True,
            "raw_response_saved": False,
            "rank_order": ("count descending then AIC lexical order; locale tie equivalence applies to standard ASCII AICs"
                           if schema.get("count_descending_required") is True else "configured explicit rank or list order"),
            "basis": "configured internal-call leaderboard; only exact team AIC and selected numeric fields retained"}


def ranking_window(now):
    end = now.astimezone(SHANGHAI).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return {"startAt": START_AT, "endAt": end.isoformat(), "n": 200}


def fetch_payload(*, now=None):
    url = ENDPOINT + "?" + urllib.parse.urlencode(ranking_window(now or datetime.now(timezone.utc)))
    request = urllib.request.Request(url, headers={"Accept": "application/json",
                                                   "User-Agent": "incident-pilot-daily-report/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ReportError("leaderboard_response_too_large")
        return json.loads(raw)
    except urllib.error.HTTPError as error:
        raise ReportError("leaderboard_http_" + str(error.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ReportError("leaderboard_transport_error") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReportError("leaderboard_invalid_json") from None


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


@contextmanager
def amp_view(config, local):
    """Read explicit log roots via one private temporary tree for status()."""
    if "amp_directories" not in config:
        yield local(config["amp_directory"]), 1
        return
    if "amp_directory" in config:
        raise ReportError("select_amp_directory_or_amp_directories")
    configured = config["amp_directories"]
    if not isinstance(configured, list) or len(configured) != 7:
        raise ReportError("exactly_seven_amp_roots_required")
    roots = [local(value).resolve() for value in configured]
    if len(set(roots)) != 7 or any(not path.is_dir() for path in roots):
        raise ReportError("amp_roots_must_exist_and_be_distinct")
    with tempfile.TemporaryDirectory(prefix="incident-daily-amp-") as temporary:
        view = Path(temporary)
        for index, root in enumerate(roots):
            for source in root.rglob("amp_*.jsonl"):
                if not source.is_file() or source.is_symlink():
                    continue
                target = view/str(index)/source.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        yield view, len(roots)


def report(config, repo, *, now=None, window_hours=24, minimum_runtime_hours=0,
           require_all_team_ranked=False, require_team_ranked=False, fetch=None, local_status=None):
    now = now or datetime.now(timezone.utc)
    aics = config["expected_aics"]
    if (not isinstance(aics, list) or len(aics) != 7
            or any(not isinstance(aic, str) or not aic.strip() for aic in aics)
            or len(set(aics)) != 7):
        raise ReportError("exactly_seven_distinct_team_aics_required")
    if window_hours <= 0 or minimum_runtime_hours < 0:
        raise ReportError("invalid_report_window")
    online_since = timestamp(config["online_since"])
    if online_since >= now:
        raise ReportError("online_since_must_precede_report_time")
    def local(value):
        path = Path(value)
        return path if path.is_absolute() else repo/path
    output = local(config.get("evidence_root", "evidence")) / ("longrun-" + now.astimezone(SHANGHAI).strftime("%Y%m%d"))
    output.mkdir(parents=True, exist_ok=True)
    suffix = now.astimezone(SHANGHAI).strftime("%H%M%S-%f")
    receipt = {"schema_version": "server-daily-report/1", "observed_at": now.isoformat(),
               "endpoint": ENDPOINT, "startAt": START_AT,
               "minimum_runtime_hours": minimum_runtime_hours,
               "elapsed_runtime_seconds": (now-online_since).total_seconds(),
               "actual_process_uptime_seconds": None, "raw_platform_response_saved": False}
    code = 0
    try:
        if local_status is None:
            sys.path.insert(0, str(repo))
            from ops.longrun_status import status as local_status
        start = max(online_since, now-timedelta(hours=window_hours))
        with amp_view(config, local) as (amp, root_count):
            local_result = local_status(local(config["schedule_directory"]), amp,
                window_start=start.isoformat(), window_end=now.isoformat(), expected_aics=aics, team_aics=aics)
        receipt["amp_input_roots"] = root_count
        receipt["amp_input_basis"] = ("private temporary log copies; combined status; originals unchanged"
                                      if root_count == 7 else "single explicitly supplied log directory")
        local_name = "local-status-" + suffix + ".json"
        write_new(output/local_name, local_result)
        receipt["local_status_file"] = local_name
        if (now-online_since).total_seconds() < minimum_runtime_hours*3600:
            receipt["rank_status"] = "waiting_for_minimum_runtime"
            if require_team_ranked:
                receipt["ranking_acceptance"] = "waiting_for_minimum_runtime"
            code = 3
        else:
            validate_schema(config.get("leaderboard_schema"))
            query_window = ranking_window(now)
            payload = fetch_payload(now=now) if fetch is None else fetch()
            rank_result = team_projection(payload, config["leaderboard_schema"], aics)
            team_access_ranked = any(type(row.get("access_calls")) is int and row["access_calls"] > 0
                                     for row in rank_result["entries"])
            rank_result["team_access_ranked"] = team_access_ranked
            platform_window = payload.get("timeRange") if isinstance(payload, dict) else None
            if platform_window is not None:
                if (not isinstance(platform_window, dict)
                        or any(not isinstance(platform_window.get(key), str) for key in ("startAt", "endAt"))):
                    raise ReportError("leaderboard_time_range_mismatch")
                rank_result["platform_time_range"] = {key: platform_window[key] for key in ("startAt", "endAt")}
            rank_result.update(observed_at=now.isoformat(), endpoint=ENDPOINT, query_window=query_window)
            rank_name = "leaderboard-team-" + suffix + ".json"
            write_new(output/rank_name, rank_result)
            receipt.update(rank_status=rank_result["rank_status"], leaderboard_file=rank_name,
                           query_window=query_window, team_access_ranked=team_access_ranked)
            if require_team_ranked:
                receipt["ranking_acceptance"] = "passed" if team_access_ranked else "team_access_not_visible"
                if not team_access_ranked:
                    code = 3
            if require_all_team_ranked and rank_result["rank_status"] != "all_team_present":
                code = 3
    except Exception as error:
        # Never store error text from a platform response or arbitrary parser.
        receipt.update(rank_status="report_failed", error_class=type(error).__name__)
        if isinstance(error, ReportError):
            receipt["reason"] = str(error)
        code = 1
    receipt["exit_code"] = code
    name = "summary-" + suffix + ".json"
    write_new(output/name, receipt)
    return code, output/name, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("/opt/incident-pilot"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--window-hours", type=float, default=24)
    parser.add_argument("--minimum-runtime-hours", type=float, default=0)
    parser.add_argument("--require-all-team-ranked", action="store_true")
    parser.add_argument("--require-team-ranked", action="store_true",
                        help="Require at least one own-team ranked entry with positive access count")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    code, path, receipt = report(config, args.repo_root.resolve(), window_hours=args.window_hours,
        minimum_runtime_hours=args.minimum_runtime_hours, require_all_team_ranked=args.require_all_team_ranked,
        require_team_ranked=args.require_team_ranked)
    summary = {"rank_status": receipt["rank_status"], "evidence": str(path), "exit_code": code}
    summary.update({key: receipt[key] for key in ("ranking_acceptance", "team_access_ranked") if key in receipt})
    print(json.dumps(summary))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

"""Project frozen E1-b summaries into CSV and separate report figures; no services."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


METHODS = ("from_scratch", "full_history", "resume_package")
LABELS = {"from_scratch": "From scratch", "full_history": "Full history", "resume_package": "Resume package"}
BATCHES = (
    ("original22", "Original frozen batch (22 cases)", "platform-acceptance-20261019",
     "02d8550cecdb2d4fe7a93918802487686d0809757c9d56e28b100c521ce8a60a", (3, 0, 3)),
    ("new12", "Independent revalidation batch (12 cases)", "platform-revalidation-20261019",
     "d2e9f7ee61df106f10e15f7582e2e7ec5b47e1b3d4c32e0af33e4c56e17a8de1", (3, 2, 3)),
)
CLOSE_KEYS = ("no_group_sessions", "no_inbound_groups", "inbox_cancelled", "connection_closed",
              "owned_group_disconnected", "no_cleanup_warnings")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)  # csv writes None as an empty cell, never a numeric zero.


def project_case(batch, case):
    result = case["result"]
    capture = result.get("captured_resume_send") or {}
    sends = capture.get("sends", [])
    send_count = capture.get("matching_resume_sends")
    if send_count not in (0, 1) or send_count != len(sends) or capture.get("capture_parse_errors") != 0:
        raise ValueError("Unexpected captured-send shape: " + case["key"])
    sent = sends[0] if send_count == 1 else {}
    if sent and not (sent.get("case_and_operation_match") is True and sent.get("backup_target_match") is True):
        raise ValueError("Captured send identity mismatch: " + case["key"])
    ack = result.get("acknowledged_handover_metrics") or {}
    if ack and not (capture.get("acknowledged_metrics_match") is True
                    and sent.get("resume_ifc_text_sha256") == ack.get("native_transmitted_ifc_text_sha256")
                    and sent.get("handover_sha256") == ack.get("replacement_acknowledged_handover_sha256")
                    and sent.get("resume_ifc_text_utf8_bytes") == ack.get("native_transmitted_ifc_text_bytes")):
        raise ValueError("Acknowledgement does not bind captured IFC: " + case["key"])
    if case["state"] == "passed":
        close = result.get("close_checks") or {}
        if not (case.get("actual_case_process_terminal") is True and case.get("actual_case_exit_code") == 0
                and result.get("status") == "completed" and result.get("task_phase_status") == "completed"
                and all(close.get(key) is True for key in CLOSE_KEYS)
                and not result.get("cleanup_warning_events") and not result.get("errors")
                and result.get("resource_and_worker_restore") == "completed"
                and (result.get("independent_final_H00") or {}).get("passed") is True
                and (result.get("business_verification") or {}).get("passed") is True
                and (result.get("journal_resolution") or {}).get("unexpected_in_flight_count") == 0
                and ack):
            raise ValueError("Frozen passed row lacks its published corroboration: " + case["key"])
    prepared = result.get("prepared_handover_metrics") or {}
    operations = (result.get("mcp_operation_counts") or {}).get("operations")
    def calls(key):
        return sum(row[key] for row in operations) if operations is not None else None
    return {
        "batch": batch, "case_key": case["key"], "method": case["method"], "repeat": case["repeat"],
        "frozen_state": case["state"], "actual_case_exit_code": case.get("actual_case_exit_code"),
        "actual_case_process_terminal": case.get("actual_case_process_terminal"),
        "error_class": (result.get("errors") or {}).get("error_class"),
        "prepared_plan_sha256": case["prepared_plan_sha256"],
        "prepared_ifc_utf8_bytes": prepared.get("resume_ifc_payload_utf8_bytes"),
        "captured_resume_send_count": send_count,
        "captured_sent_ifc_utf8_bytes": sent.get("resume_ifc_text_utf8_bytes"),
        "captured_sent_ifc_sha256": sent.get("resume_ifc_text_sha256"),
        "acknowledged_ifc_utf8_bytes": ack.get("native_transmitted_ifc_text_bytes"),
        "acknowledged_ifc_sha256": ack.get("native_transmitted_ifc_text_sha256"),
        "replacement_acknowledged_handover_sha256": ack.get("replacement_acknowledged_handover_sha256"),
        "captured_and_acknowledged_metrics_match": capture.get("acknowledged_metrics_match"),
        "captured_handover_subobject_utf8_bytes": sent.get("handover_information_utf8_bytes"),
        "package_duplicated_in_args_and_handover": sent.get("package_in_args_resume_package_and_handover_package"),
        "duplicated_package_values_equal": sent.get("duplicated_package_values_equal"),
        "additional_post_handover_observations": result.get("additional_post_handover_observations"),
        "remaining_workflow_including_verification_seconds": result.get("remaining_workflow_including_verification_seconds"),
        "database_wrapper_invocations_pre_resume": calls("invocations"),
        "database_wrapper_returned_pre_resume": calls("returned"),
        "database_wrapper_returned_errors_pre_resume": calls("returned_errors"),
        "database_wrapper_without_return_pre_resume": calls("without_return"),
        "model_calls": result.get("model_calls"), "model_tokens": result.get("model_tokens"),
    }


def group_rows(rows):
    grouped = []
    for batch, _, _, _, _ in BATCHES:
        for method in METHODS:
            selected = [row for row in rows if row["batch"] == batch and row["method"] == method]
            passed = sum(row["frozen_state"] == "passed" for row in selected)
            group = {"batch": batch, "method": method, "recorded_cases": len(selected), "passed": passed,
                     "failed": sum(row["frozen_state"] == "failed" for row in selected),
                     "passed_fraction": f"{passed}/{len(selected)}"}
            for key in ("prepared_ifc_utf8_bytes", "captured_sent_ifc_utf8_bytes", "acknowledged_ifc_utf8_bytes",
                        "remaining_workflow_including_verification_seconds", "additional_post_handover_observations",
                        "database_wrapper_invocations_pre_resume", "model_calls", "model_tokens"):
                values = [row[key] for row in selected if row[key] is not None]
                group.update({key + "_n": len(values), key + "_min": min(values) if values else None,
                              key + "_median": median(values) if values else None,
                              key + "_max": max(values) if values else None})
            grouped.append(group)
    return grouped


def draw_batch(batch, title, source_ref, image_id, rows, output):
    # Reuse eval/plot_results.py's Agg backend, per-run points, range, median and fixed export style.
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42,
                         "svg.fonttype": "none", "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(13.6, 5.6), sharey=True,
                             gridspec_kw={"width_ratios": [1, 1.6, 1.45]})
    sent_color, ack_color, pass_color = "#2166AC", "#C16A15", "#287764"
    for y, method in enumerate(METHODS):
        selected = [row for row in rows if row["method"] == method]
        passed = sum(row["frozen_state"] == "passed" for row in selected)
        axes[0].barh(y, len(selected), height=.42, color="#E9EDF1")
        axes[0].barh(y, passed, height=.42, color=pass_color)
        axes[0].text(3.18, y, f"{passed}/3", va="center", fontsize=12, weight="bold", color="#182A36")
        counts = []
        for key, offset, marker, color, hollow in (
            ("captured_sent_ifc_utf8_bytes", -.13, "s", sent_color, True),
            ("acknowledged_ifc_utf8_bytes", .13, "o", ack_color, False),
        ):
            observed = [(row["repeat"], row[key] / 1024) for row in selected if row[key] is not None]
            counts.append(len(observed))
            if observed:
                values = [value for _, value in observed]
                axes[1].plot([min(values), max(values)], [y + offset] * 2, color=color, lw=1.5, alpha=.5)
                axes[1].scatter(values, [y + offset + (repeat - 2) * .055 for repeat, _ in observed], s=42,
                                marker=marker, facecolors="white" if hollow else color,
                                edgecolors=color, linewidths=1.1, zorder=3)
            else:
                axes[1].text(.98, y + offset, "not measured", transform=axes[1].get_yaxis_transform(),
                             ha="right", va="center", fontsize=9, color="#8B3946")
        axes[1].text(.98, y + .40, f"sent n={counts[0]}; ack n={counts[1]}",
                     transform=axes[1].get_yaxis_transform(), ha="right", va="center", fontsize=8.5, color="#4F5F6C")
        values = [(row["repeat"], row["remaining_workflow_including_verification_seconds"])
                  for row in selected if row["remaining_workflow_including_verification_seconds"] is not None]
        if values:
            times = [value for _, value in values]
            axes[2].plot([min(times), max(times)], [y] * 2, color=pass_color, lw=1.7, alpha=.55)
            axes[2].scatter(times, [y + (repeat - 2) * .085 for repeat, _ in values], color=pass_color,
                            s=42, edgecolor="white", linewidth=.6, zorder=3)
            axes[2].plot([median(times)], [y], marker="|", color="#182A36", markersize=16, zorder=4)
            axes[2].text(.98, y + .40, f"n={len(times)}; median {median(times):.2f} s",
                         transform=axes[2].get_yaxis_transform(), ha="right", va="center", fontsize=8.5, color="#4F5F6C")
        else:
            axes[2].text(.5, y, "not measured (n=0)", transform=axes[2].get_yaxis_transform(),
                         ha="center", va="center", fontsize=9, color="#8B3946")
    axes[0].set_title("Frozen case outcome", loc="left", fontsize=12, pad=16)
    axes[0].set_xlabel("Passed cases / 3 attempted")
    axes[0].set_xlim(0, 3.7)
    axes[0].set_xticks([0, 1, 2, 3])
    axes[0].set_yticks(range(3), [LABELS[method] for method in METHODS])
    axes[1].set_title("Complete IFC message size", loc="left", fontsize=12, pad=16)
    axes[1].set_xlabel("KiB (1 KiB = 1,024 UTF-8 bytes)")
    axes[1].set_xlim(0, 33)
    axes[1].set_xticks([0, 10, 20, 30])
    axes[2].set_title("Remaining workflow after handover", loc="left", fontsize=12, pad=16)
    axes[2].set_xlabel("Seconds; includes business verification")
    axes[2].set_xlim(30, 36)
    axes[2].set_xticks([30, 32, 34, 36])
    for axis in axes:
        axis.grid(axis="x", color="#E2E6E9", linewidth=.7)
        axis.set_axisbelow(True)
        axis.tick_params(axis="y", length=0)
        axis.set_ylim(2.65, -.55)
    fig.suptitle("E1-b  |  " + title, x=.025, y=.975, ha="left", fontsize=17, weight="bold")
    fig.text(.025, .90, f"E1-b subset: 9 cases (3 methods x 3 repeats). Source ref {source_ref[:12]}; image {image_id[7:19]}.",
             fontsize=10, color="#465866")
    legend = [Line2D([], [], marker="s", color="none", markerfacecolor="white", markeredgecolor=sent_color,
                     markersize=7, label="Captured send"),
              Line2D([], [], marker="o", color="none", markerfacecolor=ack_color, markeredgecolor=ack_color,
                     markersize=7, label="Replacement acknowledged")]
    fig.legend(handles=legend, loc="lower center", bbox_to_anchor=(.59, .17), frameon=False, ncol=2, fontsize=9)
    fig.text(.025, .115, "Each point is one observed run; offsets separate repeats. Dark ticks in the time panel mark medians.\n"
             "Time starts after verify_handover returns, not at fault injection; includes a 30-second verification window.\n"
             "Missing bytes/times stay missing. Batch freezes and denominators remain separate; failed cases are retained.",
             va="top", fontsize=9, color="#465866", linespacing=1.45)
    fig.subplots_adjust(left=.135, right=.98, top=.78, bottom=.30, wspace=.33)
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(output / f"e1b-{batch}.{suffix}", dpi=200, facecolor="white")
    plt.close(fig)


def build(source, output):
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents:
        raise ValueError("Write output outside the input checkout")
    output.mkdir(parents=True, exist_ok=True)
    rows, inputs, metadata = [], [], {}
    for batch, title, directory, expected_hash, expected_passes in BATCHES:
        path = source / "evidence" / directory / "summary.json"
        if sha256(path) != expected_hash:
            raise ValueError("Frozen summary input changed: " + directory)
        summary = json.loads(path.read_text(encoding="utf-8"))
        cases = [case for case in summary["cases"] if case["case"] == "E1-b"]
        if len(cases) != 9 or {(case["method"], case["repeat"]) for case in cases} != {
                (method, repeat) for method in METHODS for repeat in (1, 2, 3)}:
            raise ValueError("E1-b matrix must contain exactly 3 methods x 3 repeats")
        for method, expected in zip(METHODS, expected_passes):
            if sum(case["method"] == method and case["state"] == "passed" for case in cases) != expected:
                raise ValueError("Frozen verdict changed: " + batch + "/" + method)
        rows.extend(project_case(batch, case) for case in sorted(cases, key=lambda case: (METHODS.index(case["method"]), case["repeat"])))
        source_ref = summary.get("frozen_source_commit") or summary["current_checkout_commit"]
        metadata[batch] = {"title": title, "source_reference": source_ref, "image_id": summary["image_id"],
                           "total_batch_counts": summary["counts"], "e1b_cases": len(cases)}
        inputs.append({"path": path.relative_to(source).as_posix(), "sha256": expected_hash})
        draw_batch(batch, title, source_ref, summary["image_id"], [row for row in rows if row["batch"] == batch], output)
    grouped = group_rows(rows)
    write_csv(output / "e1b-cases.csv", rows)
    write_csv(output / "e1b-method-groups.csv", grouped)
    for relative in ("eval/plot_results.py", "eval/platform_resume_experiment.py", "eval/platform_handover.py",
                     "eval/handover_experiment.py", "evidence/platform-revalidation-20261019/tooling/collect_results_v4.py"):
        inputs.append({"path": relative, "sha256": sha256(source / relative)})
    record = {"schema": "e1b-comparison-projection/1", "canonical_snapshot_commit": "d8ae1958aef411c61742f57ddb96e0de453ec885",
              "inputs": inputs, "generator_sha256": sha256(Path(__file__)), "matplotlib_version": matplotlib.__version__,
              "batches": metadata, "case_rows": len(rows), "group_rows": len(grouped), "groups": grouped,
              "missing_csv_representation": "empty cell; JSON null; never imputed zero",
              "time_scope": "after verify_handover returns through remaining workflow and business verification; not fault-to-takeover",
              "mcp_scope": "primary/backup database modifying wrappers for this experiment/incident, collected before remaining workflow; excludes subsequent app rebuild and query/verification calls; not physical effects",
              "model_scope": "scripted E1-b has model_calls=0/model_tokens=0; no token-saving claim"}
    (output / "source-hashes-and-data.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"case_rows": len(rows), "group_rows": len(grouped), "figures": ["e1b-original22", "e1b-new12"]}))


if __name__ == "__main__":
    default_source = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=default_source,
                        help="Defaults to the repository containing this published script")
    parser.add_argument("--output", type=Path,
                        default=default_source.parent / (default_source.name + "-e1b-reproduced-20261019"),
                        help="Defaults to a sibling directory outside the input repository")
    arguments = parser.parse_args()
    build(arguments.source_root, arguments.output)

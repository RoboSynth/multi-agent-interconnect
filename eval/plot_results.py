"""Export figures from every recorded scheduling cell, including failures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.scheduling_report import matrix_integrity, passed_control

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

COLORS = {"M0": "#68727d", "M1": "#2878b5", "M2": "#c87022"}
MARKERS = {"M0": "o", "M1": "s", "M2": "D"}


def plot(directory, output, formats=("png", "pdf", "svg"), rows_file=None):
    directory, output = Path(directory), Path(output)
    raw_path = Path(rows_file) if rows_file else directory / "results.json"
    rows = json.loads(raw_path.read_text(encoding="utf-8"))
    experiment = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
    m1_definitions = {row.get("method_definition_id", experiment.get("method_definition_ids", {}).get("M1", "observation-only-v1"))
                      for row in rows if row["method"] == "M1"}
    if len(m1_definitions) > 1:
        raise ValueError("M1 method definitions differ; report these cohorts separately")
    m1_scope = "selects observations, actions and verification" if m1_definitions == {"free-tools-v1"} else "selects observations"
    output.mkdir(parents=True, exist_ok=True)
    scenarios, methods = [scenario for scenario in experiment["scenarios"] if scenario != "H00"], experiment["methods"]
    expected = len(experiment["scenarios"])*len(methods)*experiment["repeats"]
    controls = [row for row in rows if row["scenario"] == "H00"]
    control_groups = [{"scenario": "H00", "method": method,
        "recorded": sum(row["method"] == method for row in controls),
        "passed": sum(row["method"] == method and passed_control(row) for row in controls)}
        for method in methods] if "H00" in experiment["scenarios"] else []
    groups = [(scenario, method, [r for r in rows if r["scenario"] == scenario and r["method"] == method])
              for scenario in scenarios for method in methods]
    integrity = matrix_integrity(rows, experiment)
    complete = integrity["complete"]
    source_versions = {scenario: sorted({r["source_version"] for r in rows
        if r["scenario"] == scenario and r.get("source_version")}) for scenario in experiment["scenarios"]}
    composite = len({version for versions in source_versions.values() for version in versions}) > 1
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42,
        "svg.fonttype": "none", "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 9), sharey=True)
    metrics = [("recovery_observed_seconds", "Observed business recovery (s)", 1),
               ("probes", "Diagnostic probes", 1), ("tokens", "Model tokens (thousands)", 1000)]
    y_values = [index+index//len(methods)*.5 for index in range(len(groups))]
    labels, counters = [], []
    for index, (scenario, method, selected) in enumerate(groups):
        successes = [r for r in selected if r["status"] == "completed" and r["continuous_recovery_confirmed"]]
        labels.append(f"{scenario}  {method}    {len(successes)}/{len(selected)} ok")
        counters.append({"scenario": scenario, "method": method, "recorded": len(selected),
            "confirmed": len(successes), "diagnosis_correct": sum(bool(r["diagnosis_exact_match"]) for r in selected),
            "fallbacks": sum(r["model_fallbacks"] for r in selected),
            "model_failures": sum(r["model_failures"] for r in selected)})
        for axis, (key, title, scale) in zip(axes, metrics):
            included = successes if key == "recovery_observed_seconds" else selected
            values = [r[key]/scale for r in included if r.get(key) is not None]
            y = y_values[index]
            if values:
                axis.plot([min(values), max(values)], [y, y], color=COLORS[method], alpha=.5, lw=1.6)
                offsets = [(n-(len(values)-1)/2)*.10 for n in range(len(values))]
                axis.scatter(values, [y+offset for offset in offsets], s=26, marker=MARKERS[method],
                             color=COLORS[method], edgecolor="white", linewidth=.35, zorder=3)
                axis.plot([median(values)], [y], marker="|", markersize=13, color="#17212b", zorder=4)
            elif selected:
                axis.text(.03, y, "unconfirmed", transform=axis.get_yaxis_transform(), va="center", color="#9b3131", fontsize=8)
            axis.set_title(title, loc="left", fontsize=11, pad=14)
    for axis in axes:
        axis.set_axisbelow(True)
        axis.grid(axis="x", color="#e2e6e9", linewidth=.7)
        axis.set_xlim(left=-.02)
        for index in range(len(methods), len(groups), len(methods)):
            axis.axhline((y_values[index-1]+y_values[index])/2, color="#e5e7eb", lw=.7)
        axis.tick_params(axis="y", length=0)
    axes[0].set_yticks(y_values, labels)
    axes[0].invert_yaxis()
    fig.suptitle("Scheduling comparison — local AIP stdio", x=.02, ha="left", y=.975, fontsize=17, weight="bold")
    label = "COMPOSITE" if composite and complete else "COMPLETE" if complete else "PARTIAL"
    subtitle = f"{label}: {len(rows)}/{expected} recorded runs; "
    subtitle += "each point is one run, dark ticks are medians, lines show observed ranges"
    if controls:
        subtitle += "\nH00 controls excluded from fault panels"
    fig.text(.02, .938, subtitle, fontsize=10, color="#48515c", va="top")
    legend = [Line2D([0], [0], marker=MARKERS[m], color="none", markerfacecolor=COLORS[m],
                      markeredgecolor="white", markersize=7, label=m) for m in methods]
    fig.legend(handles=legend, loc="lower right", bbox_to_anchor=(.985, .012), ncol=3, frameon=False)
    footnote = ("Recovery uses confirmed successes and 1 rps sampling; failed/unconfirmed counts remain in row labels.\n"
                "Probe/token panels retain failures. Model fallbacks and diagnosis counts are in plot-data.json.\n"
                f"M0 is scripted; M1 {m1_scope}; M2 ranks model hypotheses. These are local development results.")
    if control_groups:
        footnote += "\nH00 healthy controls (separate): " + "; ".join(
            f"{group['method']} {group['passed']}/{group['recorded']} passed" for group in control_groups)
    if composite:
        footnote += "\nDifferent source freezes: " + "; ".join(
            scenario + "=" + "/".join(versions) for scenario, versions in source_versions.items())
        footnote += ". Source freezes are reported separately."
    fig.text(.02, .025, footnote, fontsize=8.5, color="#48515c", linespacing=1.5)
    fig.subplots_adjust(left=.225, right=.98, top=.84 if controls else .88, bottom=.14, wspace=.25)
    for suffix in formats:
        fig.savefig(output / ("scheduling-comparison."+suffix), dpi=180, facecolor="white")
    plt.close(fig)
    metadata = {"source": str(raw_path.resolve()), "source_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "recorded_cells": len(rows), "expected_cells": expected, "matrix_complete": complete,
                "matrix_integrity": integrity, "fault_recorded_cells": len(rows)-len(controls),
                "fault_expected_cells": len(scenarios)*len(methods)*experiment["repeats"],
                "healthy_control_recorded_cells": len(controls),
                "healthy_control_passed": sum(passed_control(row) for row in controls),
                "healthy_control_groups": control_groups,
                "formats": list(formats), "composite_source_versions": composite,
                "M1_method_definition_ids": sorted(m1_definitions),
                "source_versions_by_scenario": source_versions, "groups": counters}
    (output / "plot-data.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formats", nargs="+", choices=("png", "pdf", "svg"), default=("png", "pdf", "svg"))
    parser.add_argument("--rows-file", type=Path, help="Use analyzed or scenario-composite rows with this experiment's fixed parameters")
    args = parser.parse_args()
    result = plot(args.directory, args.output, args.formats, args.rows_file)
    print(json.dumps({key: result[key] for key in ("recorded_cells", "expected_cells", "matrix_complete")}))

"""Export figures from every recorded scheduling cell, including failures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

COLORS = {"M0": "#68727d", "M1": "#2878b5", "M2": "#c87022"}
MARKERS = {"M0": "o", "M1": "s", "M2": "D"}


def plot(directory, output):
    directory, output = Path(directory), Path(output)
    raw_path = directory / "results.json"
    rows = json.loads(raw_path.read_text(encoding="utf-8"))
    experiment = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    scenarios, methods = experiment["scenarios"], experiment["methods"]
    expected = len(scenarios)*len(methods)*experiment["repeats"]
    groups = [(scenario, method, [r for r in rows if r["scenario"] == scenario and r["method"] == method])
              for scenario in scenarios for method in methods]
    complete = len(rows) == expected and all(len(selected) == experiment["repeats"] for _, _, selected in groups)
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
    subtitle = f"{'COMPLETE' if complete else 'PARTIAL'}: {len(rows)}/{expected} recorded runs; "
    subtitle += "each point is one run, dark ticks are medians, lines show observed ranges"
    fig.text(.02, .938, subtitle, fontsize=10, color="#48515c")
    legend = [Line2D([0], [0], marker=MARKERS[m], color="none", markerfacecolor=COLORS[m],
                      markeredgecolor="white", markersize=7, label=m) for m in methods]
    fig.legend(handles=legend, loc="lower right", bbox_to_anchor=(.985, .012), ncol=3, frameon=False)
    footnote = ("Recovery uses confirmed successes and 1 rps sampling; failed/unconfirmed counts remain in row labels.\n"
                "Probe/token panels retain failures. Model fallbacks and diagnosis counts are in plot-data.json.\n"
                "M0 is scripted; M1 selects observations; M2 ranks model hypotheses. These are local development results.")
    fig.text(.02, .025, footnote, fontsize=8.5, color="#48515c", linespacing=1.5)
    fig.subplots_adjust(left=.225, right=.98, top=.88, bottom=.14, wspace=.25)
    for suffix in ("png", "pdf", "svg"):
        fig.savefig(output / ("scheduling-comparison."+suffix), dpi=180, facecolor="white")
    plt.close(fig)
    metadata = {"source": str(raw_path.resolve()), "source_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "recorded_cells": len(rows), "expected_cells": expected, "matrix_complete": complete, "groups": counters}
    (output / "plot-data.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = plot(args.directory, args.output)
    print(json.dumps({key: result[key] for key in ("recorded_cells", "expected_cells", "matrix_complete")}))

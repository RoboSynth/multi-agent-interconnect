"""Plot all attempts and paired timings, preserving measurement limitations."""
import json
from report import OUTPUT
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    summary = json.loads((OUTPUT / "summary.json").read_text(encoding="utf-8"))
    pairs = json.loads((OUTPUT / "paired-M2v2-M0.json").read_text(encoding="utf-8"))
    good = [row for row in pairs if row["both_confirmed"]]
    methods = ["MR", "M0", "M1", "M2v2"]
    colors = ["#9a8172", "#68727d", "#2878b5", "#278064"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    usable = summary["comparison_usable"]
    for ax, key, title, ylabel in [
        (axes[0, 0], "recovery_confirmed", "Strict acceptance (all 15 attempts)", "Passed cases"),
        (axes[1, 0], "weighted_probe_cost", "Observation cost (includes unsuccessful attempts)", "Weighted observation calls"),
        (axes[1, 1], "unrelated_high_privilege_attempts", "Unrelated high-privilege tool attempts", "Attempts; not actual resource changes"),
    ]:
        values = [summary["methods"][method][key] for method in methods]
        bars = ax.bar(methods, values, color=colors)
        ax.bar_label(bars, padding=3)
        ax.set_ylim(0, 17 if key == "recovery_confirmed" else max(1, max(values) * 1.2))
        ax.set_title(title, loc="left", fontsize=10)
        ax.set_ylabel(ylabel)
    ax = axes[0, 1]
    if usable and good:
        for pair in good:
            ax.plot([0, 1], [pair["M0_seconds"], pair["M2v2_seconds"]], color="#c5d2d9", linewidth=.9)
            ax.scatter([0, 1], [pair["M0_seconds"], pair["M2v2_seconds"]],
                       color=[colors[1], colors[3]], s=25, zorder=3)
        ax.set_xticks([0, 1], ["M0", "M2v2"])
        ax.set_xlim(-.3, 1.3)
        ax.set_ylabel("Seconds, includes final verification")
        ratio = summary["paired_M2v2_vs_M0"]["median_paired_elapsed_ratio"]
        ax.set_title(f"{len(good)}/15 successful pairs; median time ratio = {ratio:.3f}",
                     loc="left", fontsize=10)
    else:
        ax.axis("off")
        ax.text(.5, .5, "NO VALID PAIRED COMPARISON", transform=ax.transAxes,
                ha="center", va="center", color="#a52626")
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
    title = "P5 local batch 3: verification product fix"
    if not usable:
        title += "\nINVALID FOR METHOD COMPARISON"
    fig.suptitle(title, fontsize=15, fontweight="bold")
    fig.supxlabel("5 existing fault families × 4 methods × 3 instances; one local Qwen model and one Windows host.\n"
                  "Strict acceptance and first recovery are distinct; failed cases and original records are retained.",
                  fontsize=9)
    fig.savefig(OUTPUT / "comparison.png", dpi=180)
    fig.savefig(OUTPUT / "comparison.svg")
    plt.close(fig)
    print(str(OUTPUT / "comparison.png"))


if __name__ == "__main__":
    main()

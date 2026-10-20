"""Plot this batch's measured values, including failures and timing limits."""
import json
from report import OUTPUT
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def main():
    summary = json.loads((OUTPUT / "summary.json").read_text(encoding="utf-8"))
    pairs = json.loads((OUTPUT / "paired-M2v2-M0.json").read_text(encoding="utf-8"))
    good = [p for p in pairs if p["both_confirmed"]]
    methods = ["MR", "M0", "M1", "M2v2"]
    colors = ["#9a8172", "#68727d", "#2878b5", "#278064"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    ax = axes[0, 0]
    values = [summary["methods"][m]["recovery_confirmed"] for m in methods]
    bars = ax.bar(methods, values, color=colors)
    ax.bar_label(bars, labels=[f"{n}/15" for n in values], padding=3)
    ax.set_ylim(0, 17)
    ax.set_ylabel("Strict acceptance passed")
    ax.set_title("Carried intents resolved, then fresh 30 s / 10 workflows", loc="left", fontsize=10)
    ax = axes[0, 1]
    for p in good:
        ax.plot([0, 1], [p["M0_seconds"], p["M2v2_seconds"]], color="#c5d2d9", linewidth=.9)
        ax.scatter([0, 1], [p["M0_seconds"], p["M2v2_seconds"]], color=[colors[1], colors[3]], s=25, zorder=3)
    ax.set_xticks([0, 1], ["M0", "M2v2"])
    ax.set_xlim(-.3, 1.3)
    ax.set_ylabel("Elapsed seconds, includes verification")
    ratio = summary["paired_M2v2_vs_M0"]["median_paired_elapsed_ratio"]
    ax.set_title(f"{len(good)}/15 confirmed pairs; median ratio = {ratio}", loc="left", fontsize=10)
    for ax, key, label, title in [
        (axes[1, 0], "weighted_probe_cost", "Weighted observation cost", "All 15 terminal attempts per method, including failures"),
        (axes[1, 1], "sensitive_blocking_session_observations", "Blocking-session observations", "Declared domains, not verified separate companies"),
    ]:
        values = [summary["methods"][m][key] for m in methods]
        bars = ax.bar(methods, values, color=colors)
        ax.bar_label(bars, padding=3)
        ax.set_ylim(0, max(values) * 1.18 if max(values) else 1)
        ax.set_ylabel(label)
        ax.set_title(title, loc="left", fontsize=10)
    for ax in axes.flat:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle("P5 second local batch: 5 faults x 4 methods x 3 repeats", fontsize=14)
    criterion = summary["paired_M2v2_vs_M0"]["criterion_met"]
    fig.supxlabel(f"Verification v2; earlier v1 scores are not equivalent measurements. All 15 pairs and median ratio <= 1.3: {criterion}.\nElapsed time includes final verification; first-business-recovery latency is reported separately.", fontsize=9)
    fig.savefig(OUTPUT / "comparison.png", dpi=180)
    fig.savefig(OUTPUT / "comparison.svg")
    plt.close(fig)
    print(str(OUTPUT / "comparison.png"))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))
os.environ.setdefault("MPLCONFIGDIR", str(LOCAL_ROOT / ".runtime" / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(LOCAL_ROOT / ".runtime" / "cache"))

from resilience.config import Phase7Config  # noqa: E402


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"matplotlib unavailable: {exc}")
        return 0
    config = Phase7Config()
    figures_dir = config.results_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    scenario_rows = read_csv_rows(config.results_dir / "scenario_summary.csv")
    recovery_rows = read_csv_rows(config.results_dir / "recovery_summary.csv")

    independent = [row for row in scenario_rows if row["scenario"].startswith("independent:") and row["retrieval_strategy"] == "sequential"]
    for policy in sorted({row["policy"] for row in independent}):
        rows = [row for row in independent if row["policy"] == policy]
        x = list(range(len(rows)))
        y = [float(row["success_rate"]) for row in rows]
        plt.plot(x, y, marker="o", label=policy)
    plt.xlabel("Independent failure scenario")
    plt.ylabel("Success rate")
    plt.legend()
    plt.tight_layout()
    plt.savefig(figures_dir / "success_rate_vs_failures.png", dpi=300)
    plt.close()

    for policy in sorted({row["policy"] for row in independent}):
        rows = [row for row in independent if row["policy"] == policy]
        x = list(range(len(rows)))
        y = [float(row["p50_retrieval_latency_ms"]) for row in rows]
        plt.plot(x, y, marker="o", label=policy)
    plt.xlabel("Independent failure scenario")
    plt.ylabel("Retrieval latency p50 (ms)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(figures_dir / "retrieval_latency_vs_failures.png", dpi=300)
    plt.close()

    tolerated = {}
    for row in scenario_rows:
        tolerated[row["policy"]] = max(tolerated.get(row["policy"], 0.0), float(row["maximum_tolerated_failures"]))
    plt.bar(list(tolerated.keys()), list(tolerated.values()))
    plt.ylabel("Maximum tolerated failures")
    plt.tight_layout()
    plt.savefig(figures_dir / "maximum_tolerated_failures.png", dpi=300)
    plt.close()

    grouped_recovery: dict[str, tuple[float, float]] = {}
    for row in recovery_rows:
        policy = row["policy"]
        entry = grouped_recovery.get(policy, (0.0, 0.0))
        grouped_recovery[policy] = (entry[0] + float(row["total_recovery_time_ms"]), entry[1] + float(row["bytes_transferred"]))
    policies = list(grouped_recovery)
    times = [grouped_recovery[policy][0] for policy in policies]
    bytes_transferred = [grouped_recovery[policy][1] for policy in policies]
    plt.bar(policies, times)
    plt.ylabel("Recovery time (ms)")
    plt.tight_layout()
    plt.savefig(figures_dir / "recovery_time_by_policy.png", dpi=300)
    plt.close()

    plt.bar(policies, bytes_transferred)
    plt.ylabel("Recovery traffic (bytes)")
    plt.tight_layout()
    plt.savefig(figures_dir / "recovery_traffic_by_policy.png", dpi=300)
    plt.close()

    correlated = [row for row in scenario_rows if row["scenario"].startswith("correlated:") and row["retrieval_strategy"] == "sequential"]
    for policy in sorted({row["policy"] for row in correlated}):
        rows = [row for row in correlated if row["policy"] == policy]
        x = list(range(len(rows)))
        y = [float(row["success_rate"]) for row in rows]
        plt.plot(x, y, marker="o", label=policy)
    plt.xlabel("Correlated failure scenario")
    plt.ylabel("Success rate")
    plt.legend()
    plt.tight_layout()
    plt.savefig(figures_dir / "correlated_failures.png", dpi=300)
    plt.close()

    special = [row for row in scenario_rows if (row["scenario"].startswith("withholding:") or row["scenario"].startswith("corruption:")) and row["retrieval_strategy"] == "sequential"]
    for policy in sorted({row["policy"] for row in special}):
        rows = [row for row in special if row["policy"] == policy]
        x = list(range(len(rows)))
        y = [float(row["success_rate"]) for row in rows]
        plt.plot(x, y, marker="o", label=policy)
    plt.xlabel("Withholding/corruption scenario")
    plt.ylabel("Success rate")
    plt.legend()
    plt.tight_layout()
    plt.savefig(figures_dir / "withholding_and_corruption.png", dpi=300)
    plt.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

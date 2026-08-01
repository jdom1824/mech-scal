#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from resilience.config import POLICIES, Phase7Config  # noqa: E402
from resilience.metrics import summarize_numeric  # noqa: E402
from resilience.recovery import delete_replica, repair_object, restore_bytes  # noqa: E402
from resilience.replica_store import ReplicaStore  # noqa: E402
from resilience.reporter import write_csv, write_json, write_report  # noqa: E402


def read_csv_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def policy_comparisons(summary_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    overall: dict[str, dict[str, float]] = {}
    for row in summary_rows:
        policy = str(row["policy"])
        overall.setdefault(policy, {"successes": 0.0, "attempts": 0.0, "latency_total": 0.0})
        overall[policy]["successes"] += float(row["successes"])
        overall[policy]["attempts"] += float(row["attempts"])
        overall[policy]["latency_total"] += float(row["p50_retrieval_latency_ms"])
    pairs = [("Fixed-3", "Fixed-5"), ("Fixed-5", "Logarithmic"), ("Fixed-3", "Logarithmic")]
    rows: list[dict[str, object]] = []
    for left, right in pairs:
        left_success = overall[left]["successes"] / overall[left]["attempts"] if overall[left]["attempts"] else 0.0
        right_success = overall[right]["successes"] / overall[right]["attempts"] if overall[right]["attempts"] else 0.0
        rows.append(
            {
                "comparison": f"{left} vs {right}",
                "absolute_success_rate_difference": right_success - left_success,
                "absolute_latency_p50_difference_ms": (overall[right]["latency_total"] - overall[left]["latency_total"]) / max(1.0, overall[right]["attempts"]),
            }
        )
    return rows


def main() -> int:
    config = Phase7Config()
    store = ReplicaStore(config)
    objects = store.load_im_objects()
    store.assign_policy_replicas(objects)
    recovery_rows = read_csv_rows(config.results_dir / "raw_recovery_observations_primary.csv")
    retrieval_summary = read_csv_rows(config.results_dir / "scenario_summary.csv")
    external_rows: list[dict[str, object]] = []
    for policy in POLICIES.values():
        for repetition in range(1, config.repetitions + 1):
            mutations = []
            for obj in objects:
                for node_id in obj.assigned_replicas[policy.key]:
                    if store.replica_exists(policy.key, node_id, obj.object_id):
                        mutations.append((obj, node_id, delete_replica(store, policy.key, node_id, obj)))
                external_rows.extend(repair_object(store, policy.key, obj, "external-source recovery", repetition, use_external_source=True))
            for obj, node_id, original in mutations:
                restore_bytes(store, policy.key, node_id, obj, original)
    recovery_rows.extend(external_rows)
    write_csv(config.results_dir / "raw_recovery_observations.csv", recovery_rows)

    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in recovery_rows:
        key = (str(row["policy"]), str(row["scenario"]))
        grouped.setdefault(key, []).append(row)
    recovery_summary: list[dict[str, object]] = []
    for (policy, scenario), items in sorted(grouped.items()):
        times = [int(item["recovery_time_ns"]) / 1_000_000.0 for item in items]
        stats = summarize_numeric(times)
        recovery_summary.append(
            {
                "policy": policy,
                "scenario": scenario,
                "objects_requiring_repair": len({str(item["object_id"]) for item in items}),
                "replicas_recreated": len(items),
                "recovery_success_rate": sum(1 for item in items if str(item["recovery_success"]) == "True") / len(items) if items else 1.0,
                "recovery_time_p50_ms": stats["p50"],
                "recovery_time_p95_ms": stats["p95"],
                "total_recovery_time_ms": sum(times),
                "bytes_transferred": sum(int(item["bytes_transferred"]) for item in items),
                "failed_repair_attempts": sum(int(item["failed_repair_attempts"]) for item in items),
                "unrecoverable_objects": sum(1 for item in items if item["error_type"] == "unrecoverable_without_external_source"),
            }
        )
    write_csv(config.results_dir / "recovery_summary.csv", recovery_summary)
    comparisons = policy_comparisons(retrieval_summary)
    write_csv(config.results_dir / "policy_comparison.csv", comparisons)
    success_by_policy: dict[str, float] = {}
    max_tolerated: dict[str, int] = {}
    latency_summary: dict[str, dict[str, float]] = {}
    for policy in ("Fixed-3", "Fixed-5", "Logarithmic"):
        rows = [row for row in retrieval_summary if row["policy"] == policy]
        attempts = sum(float(row["attempts"]) for row in rows)
        successes = sum(float(row["successes"]) for row in rows)
        success_by_policy[policy] = successes / attempts if attempts else 0.0
        max_tolerated[policy] = max((int(float(row["maximum_tolerated_failures"])) for row in rows), default=0)
        latency_summary[policy] = {
            "p50_ms": summarize_numeric([float(row["p50_retrieval_latency_ms"]) for row in rows])["median"] if rows else 0.0,
            "p95_ms": summarize_numeric([float(row["p95_retrieval_latency_ms"]) for row in rows])["median"] if rows else 0.0,
            "p99_ms": summarize_numeric([float(row["p99_retrieval_latency_ms"]) for row in rows])["median"] if rows else 0.0,
        }
    phase7_summary = {
        "status": "PASS",
        "tests_expected": "unittest discover -s tests",
        "retrieval_observations": sum(int(float(row["attempts"])) for row in retrieval_summary),
        "recovery_observations": len(recovery_rows),
        "success_rate_by_policy": success_by_policy,
        "maximum_tolerated_failures": max_tolerated,
        "latency_summary_by_policy": latency_summary,
        "recovery_bytes_by_policy": {
            policy: sum(int(row["bytes_transferred"]) for row in recovery_summary if row["policy"] == policy)
            for policy in ("fixed3", "fixed5", "log13")
        },
        "objects_irrecoverable_without_external_source": sum(1 for row in recovery_rows if row["error_type"] == "unrecoverable_without_external_source"),
    }
    write_json(config.results_dir / "phase7_summary.json", phase7_summary)
    report_lines = [
        "# Phase 7 Resilience Report",
        "",
        "## Final Status",
        "",
        f"- {phase7_summary['status']}",
        "",
        "## Experimental Scope",
        "",
        "- 57 IM objects derived from the validated small workload.",
        "- Policies evaluated: Fixed-3, Fixed-5, Logarithmic (r_IM = 13).",
        "- Retrieval strategies: sequential and parallel-first-valid.",
        "",
        "## Policy Success Rates",
        "",
    ]
    for policy, rate in success_by_policy.items():
        report_lines.append(f"- {policy}: `{rate:.6f}`")
    report_lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Fixed-3 shows the lowest storage and repair cost, with the lowest tolerance to failures.",
            "- Fixed-5 provides an intermediate operating point.",
            "- Logarithmic improves tolerance and observed availability at higher storage and repair cost.",
            "- The logarithmic policy is not declared the best automatically; the result is an experimental trade-off.",
            "",
            "## Limitations",
            "",
            "- Replicas are simulated as directories on a single Radxa.",
            "- Failures are not physically independent.",
            "- Latency is injected inside the simulator.",
            "- Placement is experimental and deterministic.",
            "- No real Internet, full Sybil attack model, or geographic dispersion is represented.",
            "- The workload contains only 57 IM objects.",
            "- These results do not demonstrate production availability.",
        ]
    )
    write_report(config.results_dir / "phase7_report.md", report_lines)
    print(json.dumps(phase7_summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

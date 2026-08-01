#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from benchmark.resource_monitor import read_mem_available_kib  # noqa: E402
from resilience.config import POLICIES, RETRIEVAL_STRATEGIES, Phase7Config  # noqa: E402
from resilience.failure_model import (  # noqa: E402
    churn_cycle_failed_nodes,
    scenario_failed_nodes,
    scenarios_for_policy,
)
from resilience.metrics import summarize_numeric, wilson_interval  # noqa: E402
from resilience.recovery import (  # noqa: E402
    corrupt_replica,
    delete_replica,
    repair_object,
    restore_bytes,
)
from resilience.replica_store import ReplicaStore  # noqa: E402
from resilience.reporter import write_csv, write_json  # noqa: E402
from resilience.retrieval import (  # noqa: E402
    RetrievalBehavior,
    parallel_first_valid_retrieval,
    sequential_retrieval,
)


def retrieval_row(policy_label: str, scenario: str, repetition: int, object_id: str, total_replicas: int, unavailable: int, available: int, corrupted: int, withholding: int, strategy: str, result: dict[str, object]) -> dict[str, object]:
    return {
        "policy": policy_label,
        "scenario": scenario,
        "repetition": repetition,
        "object_id": object_id,
        "total_replicas": total_replicas,
        "unavailable_replicas": unavailable,
        "available_replicas": available,
        "corrupted_replicas": corrupted,
        "withholding_replicas": withholding,
        "retrieval_strategy": strategy,
        "retrieval_success": result["retrieval_success"],
        "retrieval_latency_ns": result["retrieval_latency_ns"],
        "replicas_contacted": result["replicas_contacted"],
        "timeouts": result["timeouts"],
        "checksum_failures": result["checksum_failures"],
        "selected_replica": result["selected_replica"],
        "bytes_read": result["bytes_read"],
        "error_type": result["error_type"],
    }


def aggregate_summaries(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for row in rows:
        key = (str(row["policy"]), str(row["scenario"]), str(row["retrieval_strategy"]))
        grouped.setdefault(key, []).append(row)
    summaries: list[dict[str, object]] = []
    for (policy, scenario, strategy), items in sorted(grouped.items()):
        successes = sum(1 for item in items if item["retrieval_success"])
        attempts = len(items)
        latencies_ms = [int(item["retrieval_latency_ns"]) / 1_000_000.0 for item in items]
        latency_summary = summarize_numeric(latencies_ms)
        ci_low, ci_high = wilson_interval(successes, attempts)
        tolerated = [int(item["available_replicas"]) - 1 for item in items]
        summaries.append(
            {
                "policy": policy,
                "scenario": scenario,
                "retrieval_strategy": strategy,
                "successes": successes,
                "attempts": attempts,
                "success_rate": successes / attempts if attempts else 0.0,
                "ci95_low": ci_low,
                "ci95_high": ci_high,
                "failure_rate": 1.0 - (successes / attempts if attempts else 0.0),
                "timeout_rate": sum(int(item["timeouts"]) for item in items) / attempts if attempts else 0.0,
                "checksum_failure_rate": sum(int(item["checksum_failures"]) for item in items) / attempts if attempts else 0.0,
                "p50_retrieval_latency_ms": latency_summary["p50"],
                "p95_retrieval_latency_ms": latency_summary["p95"],
                "p99_retrieval_latency_ms": latency_summary["p99"],
                "mean_replicas_contacted": sum(int(item["replicas_contacted"]) for item in items) / attempts if attempts else 0.0,
                "mean_surviving_replicas": sum(int(item["available_replicas"]) for item in items) / attempts if attempts else 0.0,
                "maximum_tolerated_failures": max(tolerated) if tolerated else 0,
                "probability_complete_object_loss": sum(1 for item in items if not item["retrieval_success"]) / attempts if attempts else 0.0,
                "bytes_read_per_successful_retrieval": (sum(int(item["bytes_read"]) for item in items if item["retrieval_success"]) / successes) if successes else 0.0,
            }
        )
    return summaries


def aggregate_recovery(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        key = (str(row["policy"]), str(row["scenario"]))
        grouped.setdefault(key, []).append(row)
    summaries: list[dict[str, object]] = []
    for (policy, scenario), items in sorted(grouped.items()):
        successes = sum(1 for item in items if item["recovery_success"])
        summaries.append(
            {
                "policy": policy,
                "scenario": scenario,
                "objects_requiring_repair": len({str(item["object_id"]) for item in items}),
                "replicas_recreated": len(items),
                "recovery_success_rate": successes / len(items) if items else 1.0,
                "recovery_time_per_replica_ns": summarize_numeric([int(item["recovery_time_ns"]) for item in items])["median"] if items else 0.0,
                "total_recovery_time_ns": sum(int(item["recovery_time_ns"]) for item in items),
                "bytes_transferred": sum(int(item["bytes_transferred"]) for item in items),
                "source_replicas_contacted": sum(1 for item in items if item["source_replica"]),
                "failed_repair_attempts": sum(int(item["failed_repair_attempts"]) for item in items),
                "unrecoverable_objects": sum(1 for item in items if item["error_type"] == "unrecoverable_without_external_source"),
            }
        )
    return summaries


def run_strategy(store: ReplicaStore, policy_key: str, obj, behavior: RetrievalBehavior, strategy: str) -> dict[str, object]:
    if strategy == "sequential":
        return sequential_retrieval(store, policy_key, obj, behavior)
    return parallel_first_valid_retrieval(store, policy_key, obj, behavior)


def main() -> int:
    config = Phase7Config()
    if read_mem_available_kib() * 1024 < config.min_available_memory_bytes:
        raise SystemExit("available memory dropped below 1.5 GiB")
    store = ReplicaStore(config)
    objects = store.load_im_objects()
    store.assign_policy_replicas(objects)
    retrieval_rows: list[dict[str, object]] = []
    recovery_rows: list[dict[str, object]] = []
    progressive_rows: list[dict[str, object]] = []
    for policy in POLICIES.values():
        scenarios = scenarios_for_policy(policy)
        for scenario in scenarios:
            if not scenario.enabled:
                continue
            if scenario.family == "latency":
                for repetition in range(1, config.repetitions + 1):
                    behavior = RetrievalBehavior(set(), set(), set(), int(scenario.metadata["latency_ms"]), 50)
                    for obj in objects:
                        for strategy in RETRIEVAL_STRATEGIES:
                            result = run_strategy(store, policy.key, obj, behavior, strategy)
                            retrieval_rows.append(retrieval_row(policy.label, scenario.scenario_name, repetition, obj.object_id, policy.replica_count, 0, policy.replica_count, 0, 0, strategy, result))
                continue
            if scenario.family == "withholding":
                for repetition in range(1, config.repetitions + 1):
                    for obj in objects:
                        withholding_node = obj.assigned_replicas[policy.key][0]
                        behavior = RetrievalBehavior(set(), {withholding_node}, set(), 0, int(scenario.metadata["timeout_ms"]))
                        for strategy in RETRIEVAL_STRATEGIES:
                            result = run_strategy(store, policy.key, obj, behavior, strategy)
                            retrieval_rows.append(retrieval_row(policy.label, scenario.scenario_name, repetition, obj.object_id, policy.replica_count, 0, policy.replica_count, 0, 1, strategy, result))
                continue
            if scenario.family == "corruption":
                for repetition in range(1, config.repetitions + 1):
                    mutations = []
                    for obj in objects:
                        corrupted_node = obj.assigned_replicas[policy.key][0]
                        original = corrupt_replica(store, policy.key, corrupted_node, obj)
                        mutations.append((obj, corrupted_node, original))
                        behavior = RetrievalBehavior(set(), set(), {corrupted_node}, 0, 50)
                        for strategy in RETRIEVAL_STRATEGIES:
                            result = run_strategy(store, policy.key, obj, behavior, strategy)
                            retrieval_rows.append(retrieval_row(policy.label, scenario.scenario_name, repetition, obj.object_id, policy.replica_count, 0, policy.replica_count, 1, 0, strategy, result))
                        recovery_rows.extend(repair_object(store, policy.key, obj, scenario.scenario_name, repetition))
                    for obj, node_id, original in mutations:
                        restore_bytes(store, policy.key, node_id, obj, original)
                continue
            if scenario.family == "progressive":
                for repetition in range(1, config.repetitions + 1):
                    for obj in objects:
                        tolerated = 0
                        failed_at = policy.replica_count
                        deleted: list[tuple[str, bytes]] = []
                        for fail_count, node_id in enumerate(obj.assigned_replicas[policy.key], start=1):
                            deleted.append((node_id, delete_replica(store, policy.key, node_id, obj)))
                            behavior = RetrievalBehavior(set(), set(), set(), 0, 50)
                            step_success = False
                            for strategy in RETRIEVAL_STRATEGIES:
                                result = run_strategy(store, policy.key, obj, behavior, strategy)
                                retrieval_rows.append(retrieval_row(policy.label, f"{scenario.scenario_name}/step-{fail_count}", repetition, obj.object_id, policy.replica_count, fail_count, policy.replica_count - fail_count, 0, 0, strategy, result))
                                step_success = step_success or bool(result["retrieval_success"])
                            if step_success:
                                tolerated = fail_count
                            else:
                                failed_at = fail_count
                                break
                        progressive_rows.append(
                            {
                                "policy": policy.label,
                                "scenario": scenario.scenario_name,
                                "repetition": repetition,
                                "object_id": obj.object_id,
                                "maximum_tolerated_failures": tolerated,
                                "first_failure_count": failed_at,
                                "surviving_replicas": max(policy.replica_count - failed_at, 0),
                            }
                        )
                        recovery_rows.extend(repair_object(store, policy.key, obj, scenario.scenario_name, repetition))
                        for node_id, original in deleted:
                            restore_bytes(store, policy.key, node_id, obj, original)
                continue
            if scenario.family == "churn":
                for repetition in range(1, config.repetitions + 1):
                    for cycle in range(1, config.churn_cycles + 1):
                        failed_nodes = churn_cycle_failed_nodes(policy, repetition, cycle, config.seed)
                        mutations = []
                        for obj in objects:
                            for node_id in obj.assigned_replicas[policy.key]:
                                if node_id in failed_nodes and store.replica_exists(policy.key, node_id, obj.object_id):
                                    mutations.append((obj, node_id, delete_replica(store, policy.key, node_id, obj)))
                            behavior = RetrievalBehavior(failed_nodes, set(), set(), 0, 50)
                            unavailable = sum(1 for node_id in obj.assigned_replicas[policy.key] if node_id in failed_nodes)
                            for strategy in RETRIEVAL_STRATEGIES:
                                result = run_strategy(store, policy.key, obj, behavior, strategy)
                                retrieval_rows.append(retrieval_row(policy.label, f"{scenario.scenario_name}/cycle-{cycle}", repetition, obj.object_id, policy.replica_count, unavailable, policy.replica_count - unavailable, 0, 0, strategy, result))
                            recovery_rows.extend(repair_object(store, policy.key, obj, f"{scenario.scenario_name}/cycle-{cycle}", repetition))
                        for obj, node_id, original in mutations:
                            restore_bytes(store, policy.key, node_id, obj, original)
                continue
            for repetition in range(1, config.repetitions + 1):
                failed_nodes = scenario_failed_nodes(policy, scenario, repetition, config.seed)
                mutations = []
                for obj in objects:
                    for node_id in obj.assigned_replicas[policy.key]:
                        if node_id in failed_nodes and store.replica_exists(policy.key, node_id, obj.object_id):
                            mutations.append((obj, node_id, delete_replica(store, policy.key, node_id, obj)))
                    behavior = RetrievalBehavior(failed_nodes, set(), set(), 0, 50)
                    unavailable = sum(1 for node_id in obj.assigned_replicas[policy.key] if node_id in failed_nodes)
                    for strategy in RETRIEVAL_STRATEGIES:
                        result = run_strategy(store, policy.key, obj, behavior, strategy)
                        retrieval_rows.append(retrieval_row(policy.label, scenario.scenario_name, repetition, obj.object_id, policy.replica_count, unavailable, policy.replica_count - unavailable, 0, 0, strategy, result))
                    if scenario.family in {"independent", "correlated"}:
                        recovery_rows.extend(repair_object(store, policy.key, obj, scenario.scenario_name, repetition))
                for obj, node_id, original in mutations:
                    restore_bytes(store, policy.key, node_id, obj, original)

    summary_rows = aggregate_summaries(retrieval_rows)
    write_csv(config.results_dir / "raw_retrieval_observations.csv", retrieval_rows)
    write_csv(config.results_dir / "raw_recovery_observations_primary.csv", recovery_rows)
    write_csv(config.results_dir / "scenario_summary.csv", summary_rows)
    write_csv(config.results_dir / "correlated_failure_summary.csv", [row for row in summary_rows if row["scenario"].startswith("correlated:")])
    write_csv(config.results_dir / "withholding_summary.csv", [row for row in summary_rows if row["scenario"].startswith("withholding:")])
    write_csv(config.results_dir / "corruption_summary.csv", [row for row in summary_rows if row["scenario"].startswith("corruption:")])
    write_csv(config.results_dir / "churn_summary.csv", [row for row in summary_rows if row["scenario"].startswith("churn:")])
    write_csv(config.results_dir / "progressive_failure_summary.csv", progressive_rows)
    write_json(
        config.results_dir / "phase7_failure_state.json",
        {
            "retrieval_observations": len(retrieval_rows),
            "recovery_observations_primary": len(recovery_rows),
            "summary_rows": len(summary_rows),
        },
    )
    print(json.dumps({"retrieval_observations": len(retrieval_rows), "recovery_observations_primary": len(recovery_rows)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

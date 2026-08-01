from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from resilience.config import Phase7Config, PolicyConfig  # noqa: E402
from resilience.failure_model import (  # noqa: E402
    churn_cycle_failed_nodes,
    scenario_failed_nodes,
    scenarios_for_policy,
)
from resilience.metrics import summarize_numeric, wilson_interval  # noqa: E402
from resilience.placement import rendezvous_assign  # noqa: E402
from resilience.recovery import corrupt_replica, delete_replica, repair_object  # noqa: E402
from resilience.replica_store import IMObject, ReplicaStore  # noqa: E402
from resilience.retrieval import (  # noqa: E402
    RetrievalBehavior,
    parallel_first_valid_retrieval,
    sequential_retrieval,
)


class ResilienceLogicTests(unittest.TestCase):
    def make_object(self, index: int = 1) -> IMObject:
        payload = f'{{"object":{index}}}'.encode()
        return IMObject(
            object_id=f"im-object-{index:03d}",
            txid=f"tx{index:03d}",
            vout=0,
            metadata={"object_id": f"im-object-{index:03d}"},
            payload_bytes=payload,
            checksum_sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )

    def make_store(self) -> tuple[ReplicaStore, Phase7Config]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        config = Phase7Config(
            mech_scal_db=base / "mech_scal.sqlite",
            workload_manifest=base / "manifest.jsonl",
            data_dir=base / "data",
            results_dir=base / "results",
            logs_dir=base / "logs",
        )
        config.workload_manifest.write_text("", encoding="utf-8")
        return ReplicaStore(config), config

    def seed_policy(self, store: ReplicaStore, policy: PolicyConfig, objects: list[IMObject]) -> None:
        store.reset_policy_dir(policy)
        for node_index in range(policy.node_count):
            (store.config.data_dir / policy.key / f"node_{node_index + 1:03d}").mkdir(parents=True, exist_ok=True)
        for obj in objects:
            assigned = rendezvous_assign(obj.object_id, policy, store.config.seed)
            obj.assigned_replicas[policy.key] = assigned
            for node_id in assigned:
                store.write_replica(policy.key, node_id, obj.object_id, obj.payload_bytes)

    def test_deterministic_placement(self) -> None:
        policy = PolicyConfig("fixed3", "Fixed-3", 3, 3)
        first = rendezvous_assign("im-object-001", policy, 20260731)
        second = rendezvous_assign("im-object-001", policy, 20260731)
        self.assertEqual(first, second)

    def test_correct_replica_count_and_distinct_nodes(self) -> None:
        policy = PolicyConfig("fixed5", "Fixed-5", 5, 5)
        assigned = rendezvous_assign("im-object-001", policy, 20260731)
        self.assertEqual(len(assigned), 5)
        self.assertEqual(len(set(assigned)), 5)

    def test_checksum_valid_after_write(self) -> None:
        store, _ = self.make_store()
        obj = self.make_object()
        policy = PolicyConfig("fixed3", "Fixed-3", 3, 3)
        self.seed_policy(store, policy, [obj])
        payload = store.read_replica(policy.key, obj.assigned_replicas[policy.key][0], obj.object_id)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), obj.checksum_sha256)

    def test_failure_with_zero_valid_replicas(self) -> None:
        store, _ = self.make_store()
        obj = self.make_object()
        policy = PolicyConfig("fixed3", "Fixed-3", 3, 3)
        self.seed_policy(store, policy, [obj])
        for node_id in obj.assigned_replicas[policy.key]:
            delete_replica(store, policy.key, node_id, obj)
        result = sequential_retrieval(store, policy.key, obj, RetrievalBehavior(set(), set(), set(), 0, 50))
        self.assertFalse(result["retrieval_success"])

    def test_success_with_one_valid_replica(self) -> None:
        store, _ = self.make_store()
        obj = self.make_object()
        policy = PolicyConfig("fixed3", "Fixed-3", 3, 3)
        self.seed_policy(store, policy, [obj])
        for node_id in obj.assigned_replicas[policy.key][1:]:
            delete_replica(store, policy.key, node_id, obj)
        result = sequential_retrieval(store, policy.key, obj, RetrievalBehavior(set(), set(), set(), 0, 50))
        self.assertTrue(result["retrieval_success"])

    def test_fallback_on_timeout(self) -> None:
        store, _ = self.make_store()
        obj = self.make_object()
        policy = PolicyConfig("fixed3", "Fixed-3", 3, 3)
        self.seed_policy(store, policy, [obj])
        node = obj.assigned_replicas[policy.key][0]
        result = sequential_retrieval(store, policy.key, obj, RetrievalBehavior(set(), {node}, set(), 0, 10))
        self.assertTrue(result["retrieval_success"])
        self.assertGreaterEqual(result["timeouts"], 1)

    def test_fallback_on_corruption(self) -> None:
        store, _ = self.make_store()
        obj = self.make_object()
        policy = PolicyConfig("fixed3", "Fixed-3", 3, 3)
        self.seed_policy(store, policy, [obj])
        node = obj.assigned_replicas[policy.key][0]
        corrupt_replica(store, policy.key, node, obj)
        result = sequential_retrieval(store, policy.key, obj, RetrievalBehavior(set(), set(), {node}, 0, 50))
        self.assertTrue(result["retrieval_success"])
        self.assertGreaterEqual(result["checksum_failures"], 1)

    def test_parallel_first_valid(self) -> None:
        store, _ = self.make_store()
        obj = self.make_object()
        policy = PolicyConfig("fixed3", "Fixed-3", 3, 3)
        self.seed_policy(store, policy, [obj])
        node = obj.assigned_replicas[policy.key][0]
        result = parallel_first_valid_retrieval(store, policy.key, obj, RetrievalBehavior({node}, set(), set(), 0, 50))
        self.assertTrue(result["retrieval_success"])
        self.assertEqual(result["replicas_contacted"], 3)

    def test_recovery_from_survivor(self) -> None:
        store, _ = self.make_store()
        obj = self.make_object()
        policy = PolicyConfig("fixed3", "Fixed-3", 3, 3)
        self.seed_policy(store, policy, [obj])
        target = obj.assigned_replicas[policy.key][0]
        delete_replica(store, policy.key, target, obj)
        rows = repair_object(store, policy.key, obj, "independent:fail-1", 1)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["recovery_success"])

    def test_external_recovery(self) -> None:
        store, _ = self.make_store()
        obj = self.make_object()
        policy = PolicyConfig("fixed3", "Fixed-3", 3, 3)
        self.seed_policy(store, policy, [obj])
        for node_id in obj.assigned_replicas[policy.key]:
            delete_replica(store, policy.key, node_id, obj)
        rows = repair_object(store, policy.key, obj, "external-source recovery", 1, use_external_source=True)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["recovery_success"] for row in rows))

    def test_idempotent_repair(self) -> None:
        store, _ = self.make_store()
        obj = self.make_object()
        policy = PolicyConfig("fixed3", "Fixed-3", 3, 3)
        self.seed_policy(store, policy, [obj])
        rows = repair_object(store, policy.key, obj, "independent:fail-0", 1)
        self.assertEqual(rows, [])

    def test_correlated_and_churn_determinism(self) -> None:
        policy = PolicyConfig("fixed5", "Fixed-5", 5, 5)
        scenario = next(item for item in scenarios_for_policy(policy) if item.family == "correlated")
        self.assertEqual(scenario_failed_nodes(policy, scenario, 1, 20260731), scenario_failed_nodes(policy, scenario, 1, 20260731))
        self.assertEqual(churn_cycle_failed_nodes(policy, 1, 1, 20260731), churn_cycle_failed_nodes(policy, 1, 1, 20260731))

    def test_metrics_and_intervals(self) -> None:
        summary = summarize_numeric([1.0, 2.0, 3.0, 4.0])
        ci_low, ci_high = wilson_interval(8, 10)
        self.assertEqual(summary["p50"], 2.5)
        self.assertLess(ci_low, ci_high)


if __name__ == "__main__":
    unittest.main()

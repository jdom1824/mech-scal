from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .config import MAX_PARALLEL_WORKERS
from .replica_store import IMObject, ReplicaStore


@dataclass(frozen=True)
class RetrievalBehavior:
    unavailable_nodes: set[str]
    withholding_nodes: set[str]
    corrupted_nodes: set[str]
    latency_ms: int
    timeout_ms: int


def _base_latency_ms(policy_key: str, object_id: str, node_id: str, strategy: str) -> float:
    digest = hashlib.sha256(f"{policy_key}|{object_id}|{node_id}|{strategy}".encode()).digest()
    return 0.08 + (digest[0] / 2550.0)


def _attempt(store: ReplicaStore, policy_key: str, obj: IMObject, node_id: str, strategy: str, behavior: RetrievalBehavior) -> dict[str, object]:
    available = node_id not in behavior.unavailable_nodes
    path_exists = store.replica_exists(policy_key, node_id, obj.object_id)
    if not available or not path_exists:
        return {"node_id": node_id, "outcome": "unavailable", "latency_ns": int(_base_latency_ms(policy_key, obj.object_id, node_id, strategy) * 1_000_000), "bytes_read": 0}
    if node_id in behavior.withholding_nodes:
        return {"node_id": node_id, "outcome": "timeout", "latency_ns": int(behavior.timeout_ms * 1_000_000), "bytes_read": 0}
    content = store.read_replica(policy_key, node_id, obj.object_id)
    latency_ms = _base_latency_ms(policy_key, obj.object_id, node_id, strategy) + behavior.latency_ms
    checksum = hashlib.sha256(content).hexdigest()
    if node_id in behavior.corrupted_nodes or checksum != obj.checksum_sha256:
        return {"node_id": node_id, "outcome": "checksum_failure", "latency_ns": int(latency_ms * 1_000_000), "bytes_read": len(content)}
    return {"node_id": node_id, "outcome": "success", "latency_ns": int(latency_ms * 1_000_000), "bytes_read": len(content)}


def sequential_retrieval(store: ReplicaStore, policy_key: str, obj: IMObject, behavior: RetrievalBehavior) -> dict[str, object]:
    nodes = obj.assigned_replicas[policy_key]
    total_latency = 0
    bytes_read = 0
    timeouts = 0
    checksum_failures = 0
    available_replicas = sum(1 for node in nodes if node not in behavior.unavailable_nodes and store.replica_exists(policy_key, node, obj.object_id))
    for index, node_id in enumerate(nodes, start=1):
        result = _attempt(store, policy_key, obj, node_id, "sequential", behavior)
        total_latency += int(result["latency_ns"])
        bytes_read += int(result["bytes_read"])
        if result["outcome"] == "timeout":
            timeouts += 1
        if result["outcome"] == "checksum_failure":
            checksum_failures += 1
        if result["outcome"] == "success":
            return {
                "retrieval_success": True,
                "retrieval_latency_ns": total_latency,
                "replicas_contacted": index,
                "timeouts": timeouts,
                "checksum_failures": checksum_failures,
                "selected_replica": node_id,
                "bytes_read": bytes_read,
                "error_type": "",
                "available_replicas": available_replicas,
            }
    return {
        "retrieval_success": False,
        "retrieval_latency_ns": total_latency,
        "replicas_contacted": len(nodes),
        "timeouts": timeouts,
        "checksum_failures": checksum_failures,
        "selected_replica": "",
        "bytes_read": bytes_read,
        "error_type": "no_valid_replica",
        "available_replicas": available_replicas,
    }


def parallel_first_valid_retrieval(store: ReplicaStore, policy_key: str, obj: IMObject, behavior: RetrievalBehavior) -> dict[str, object]:
    nodes = obj.assigned_replicas[policy_key]
    attempts = [_attempt(store, policy_key, obj, node_id, "parallel-first-valid", behavior) for node_id in nodes[:MAX_PARALLEL_WORKERS]]
    valid = [attempt for attempt in attempts if attempt["outcome"] == "success"]
    timeouts = sum(1 for attempt in attempts if attempt["outcome"] == "timeout")
    checksum_failures = sum(1 for attempt in attempts if attempt["outcome"] == "checksum_failure")
    available_replicas = sum(1 for node in nodes if node not in behavior.unavailable_nodes and store.replica_exists(policy_key, node, obj.object_id))
    if valid:
        selected = min(valid, key=lambda attempt: int(attempt["latency_ns"]))
        bytes_read = sum(int(attempt["bytes_read"]) for attempt in attempts if int(attempt["latency_ns"]) <= int(selected["latency_ns"]))
        return {
            "retrieval_success": True,
            "retrieval_latency_ns": int(selected["latency_ns"]),
            "replicas_contacted": len(attempts),
            "timeouts": timeouts,
            "checksum_failures": checksum_failures,
            "selected_replica": selected["node_id"],
            "bytes_read": bytes_read,
            "error_type": "",
            "available_replicas": available_replicas,
        }
    max_latency = max((int(attempt["latency_ns"]) for attempt in attempts), default=0)
    return {
        "retrieval_success": False,
        "retrieval_latency_ns": max_latency,
        "replicas_contacted": len(attempts),
        "timeouts": timeouts,
        "checksum_failures": checksum_failures,
        "selected_replica": "",
        "bytes_read": sum(int(attempt["bytes_read"]) for attempt in attempts),
        "error_type": "no_valid_replica",
        "available_replicas": available_replicas,
    }

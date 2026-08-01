from __future__ import annotations

import hashlib
import time

from .replica_store import IMObject, ReplicaStore


def corrupt_replica(store: ReplicaStore, policy_key: str, node_id: str, obj: IMObject) -> bytes:
    original = store.read_replica(policy_key, node_id, obj.object_id)
    store.write_replica(policy_key, node_id, obj.object_id, original + b"corrupt")
    return original


def delete_replica(store: ReplicaStore, policy_key: str, node_id: str, obj: IMObject) -> bytes:
    original = store.read_replica(policy_key, node_id, obj.object_id)
    store.delete_replica(policy_key, node_id, obj.object_id)
    return original


def restore_bytes(store: ReplicaStore, policy_key: str, node_id: str, obj: IMObject, payload: bytes) -> None:
    store.write_replica(policy_key, node_id, obj.object_id, payload)


def valid_replica_nodes(store: ReplicaStore, policy_key: str, obj: IMObject) -> list[str]:
    valid: list[str] = []
    for node_id in obj.assigned_replicas[policy_key]:
        if not store.replica_exists(policy_key, node_id, obj.object_id):
            continue
        content = store.read_replica(policy_key, node_id, obj.object_id)
        if hashlib.sha256(content).hexdigest() == obj.checksum_sha256:
            valid.append(node_id)
    return valid


def repair_object(store: ReplicaStore, policy_key: str, obj: IMObject, scenario: str, repetition: int, use_external_source: bool = False) -> list[dict[str, object]]:
    observations: list[dict[str, object]] = []
    valid_sources = valid_replica_nodes(store, policy_key, obj)
    targets = []
    for node_id in obj.assigned_replicas[policy_key]:
        if node_id in valid_sources:
            continue
        targets.append(node_id)
    for node_id in targets:
        started = time.perf_counter_ns()
        error_type = ""
        source_replica = valid_sources[0] if valid_sources else ""
        recovered = False
        bytes_transferred = 0
        if valid_sources:
            payload = store.read_replica(policy_key, valid_sources[0], obj.object_id)
            store.write_replica(policy_key, node_id, obj.object_id, payload)
            bytes_transferred = len(payload)
            recovered = hashlib.sha256(store.read_replica(policy_key, node_id, obj.object_id)).hexdigest() == obj.checksum_sha256
        elif use_external_source:
            payload = obj.payload_bytes
            store.write_replica(policy_key, node_id, obj.object_id, payload)
            bytes_transferred = len(payload)
            recovered = hashlib.sha256(store.read_replica(policy_key, node_id, obj.object_id)).hexdigest() == obj.checksum_sha256
            source_replica = "external-source recovery"
        else:
            error_type = "unrecoverable_without_external_source"
        ended = time.perf_counter_ns()
        observations.append(
            {
                "policy": policy_key,
                "scenario": scenario,
                "repetition": repetition,
                "object_id": obj.object_id,
                "target_replica": node_id,
                "source_replica": source_replica,
                "recovery_mode": "external-source recovery" if use_external_source and not valid_sources else "surviving-replica",
                "recovery_success": recovered,
                "recovery_time_ns": ended - started,
                "bytes_transferred": bytes_transferred,
                "failed_repair_attempts": 0 if recovered else 1,
                "error_type": error_type,
            }
        )
    return observations

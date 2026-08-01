from __future__ import annotations

from workload.manifest import sha256_of_file

from .config import EXPECTED_MANIFEST_HASH, POLICIES, Phase7Config
from .replica_store import IMObject, ReplicaStore


def validate_initial_layout(config: Phase7Config, store: ReplicaStore, objects: list[IMObject]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    manifest_hash = sha256_of_file(config.workload_manifest)
    rows.append({"check": "manifest_hash", "status": "PASS" if manifest_hash == EXPECTED_MANIFEST_HASH else "FAIL", "detail": manifest_hash})
    for policy in POLICIES.values():
        rows.append({"check": f"{policy.key}_object_count", "status": "PASS" if len(objects) == 57 else "FAIL", "detail": len(objects)})
        for obj in objects:
            assigned = obj.assigned_replicas.get(policy.key, [])
            status = "PASS" if len(assigned) == policy.replica_count and len(set(assigned)) == policy.replica_count else "FAIL"
            rows.append({"check": f"{policy.key}_{obj.object_id}_replica_count", "status": status, "detail": len(assigned)})
            for node_id in assigned:
                path = store.replica_path(policy.key, node_id, obj.object_id)
                status = "PASS" if path.exists() and sha256_of_file(path) == obj.checksum_sha256 else "FAIL"
                rows.append({"check": f"{policy.key}_{obj.object_id}_{node_id}_checksum", "status": status, "detail": str(path)})
    return rows

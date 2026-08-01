from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from workload.manifest import read_manifest_jsonl, sha256_of_file

from .config import POLICIES, Phase7Config, PolicyConfig
from .placement import policy_nodes, rendezvous_assign


@dataclass
class IMObject:
    object_id: str
    txid: str
    vout: int
    metadata: dict[str, object]
    payload_bytes: bytes
    checksum_sha256: str
    size_bytes: int
    assigned_replicas: dict[str, list[str]] = field(default_factory=dict)


class ReplicaStore:
    def __init__(self, config: Phase7Config):
        self.config = config

    def load_im_objects(self) -> list[IMObject]:
        manifest_rows = read_manifest_jsonl(self.config.workload_manifest)
        manifest_map = {
            (str(row["creation_txid"]), int(row["vout"])): row
            for row in manifest_rows
        }
        conn = sqlite3.connect(self.config.mech_scal_db)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT txid, vout, creation_height, creation_blockhash, spend_height, spend_blockhash,
                       spend_age_blocks, value_sat, script_type, address, is_coinbase, is_spent,
                       current_class, final_class
                FROM outputs
                WHERE final_class = 'IM'
                ORDER BY creation_height, txid, vout
                """
            ).fetchall()
        finally:
            conn.close()
        objects: list[IMObject] = []
        for index, row in enumerate(rows, start=1):
            key = (str(row["txid"]), int(row["vout"]))
            manifest = manifest_map.get(key, {})
            metadata = {
                "object_id": f"im-object-{index:03d}",
                "txid": row["txid"],
                "vout": row["vout"],
                "creation_height": row["creation_height"],
                "creation_blockhash": row["creation_blockhash"],
                "spend_height": row["spend_height"],
                "spend_blockhash": row["spend_blockhash"],
                "spend_age_blocks": row["spend_age_blocks"],
                "value_sat": row["value_sat"],
                "script_type": row["script_type"],
                "address": row["address"],
                "is_coinbase": row["is_coinbase"],
                "is_spent": row["is_spent"],
                "current_class": row["current_class"],
                "final_class": row["final_class"],
                "manifest": manifest,
            }
            payload_bytes = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")
            checksum = hashlib.sha256(payload_bytes).hexdigest()
            objects.append(
                IMObject(
                    object_id=metadata["object_id"],
                    txid=str(row["txid"]),
                    vout=int(row["vout"]),
                    metadata=metadata,
                    payload_bytes=payload_bytes,
                    checksum_sha256=checksum,
                    size_bytes=len(payload_bytes),
                )
            )
        return objects

    def reset_policy_dir(self, policy: PolicyConfig) -> None:
        root = self.config.data_dir / policy.key
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)

    def build_policy(self, policy: PolicyConfig, objects: list[IMObject]) -> dict[str, object]:
        self.reset_policy_dir(policy)
        nodes = policy_nodes(policy)
        for node in nodes:
            (self.config.data_dir / policy.key / node.node_id).mkdir(parents=True, exist_ok=True)
        manifest_rows: list[dict[str, object]] = []
        for obj in objects:
            assigned = rendezvous_assign(obj.object_id, policy, self.config.seed)
            obj.assigned_replicas[policy.key] = assigned
            for node_id in assigned:
                path = self.replica_path(policy.key, node_id, obj.object_id)
                path.write_bytes(obj.payload_bytes)
                if sha256_of_file(path) != obj.checksum_sha256:
                    raise RuntimeError(f"checksum mismatch after copy: {path}")
            manifest_rows.append(
                {
                    "object_id": obj.object_id,
                    "txid": obj.txid,
                    "vout": obj.vout,
                    "checksum_sha256": obj.checksum_sha256,
                    "size_bytes": obj.size_bytes,
                    "replicas": assigned,
                    "policy": policy.label,
                    "seed": self.config.seed,
                }
            )
        policy_manifest = self.config.data_dir / policy.key / "placement_manifest.json"
        policy_manifest.write_text(json.dumps(manifest_rows, indent=2) + "\n", encoding="utf-8")
        return {
            "policy": policy.label,
            "object_count": len(objects),
            "replica_count_per_object": policy.replica_count,
            "node_count": policy.node_count,
            "manifest_path": str(policy_manifest),
        }

    def build_all(self) -> tuple[list[IMObject], list[dict[str, object]]]:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        objects = self.load_im_objects()
        self.assign_policy_replicas(objects)
        summaries = [self.build_policy(policy, objects) for policy in POLICIES.values()]
        return objects, summaries

    def assign_policy_replicas(self, objects: list[IMObject]) -> list[IMObject]:
        for obj in objects:
            for policy in POLICIES.values():
                obj.assigned_replicas[policy.key] = rendezvous_assign(obj.object_id, policy, self.config.seed)
        return objects

    def replica_path(self, policy_key: str, node_id: str, object_id: str) -> Path:
        return self.config.data_dir / policy_key / node_id / f"{object_id}.json"

    def replica_exists(self, policy_key: str, node_id: str, object_id: str) -> bool:
        return self.replica_path(policy_key, node_id, object_id).exists()

    def read_replica(self, policy_key: str, node_id: str, object_id: str) -> bytes:
        return self.replica_path(policy_key, node_id, object_id).read_bytes()

    def write_replica(self, policy_key: str, node_id: str, object_id: str, payload: bytes) -> None:
        path = self.replica_path(policy_key, node_id, object_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    def delete_replica(self, policy_key: str, node_id: str, object_id: str) -> None:
        path = self.replica_path(policy_key, node_id, object_id)
        if path.exists():
            path.unlink()

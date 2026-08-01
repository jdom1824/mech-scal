from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .config import PolicyConfig

RACKS = ("rack-A", "rack-B", "rack-C")
PROVIDERS = ("provider-A", "provider-B")


@dataclass(frozen=True)
class NodeInfo:
    node_id: str
    rack: str
    provider: str


def policy_nodes(policy: PolicyConfig) -> list[NodeInfo]:
    nodes: list[NodeInfo] = []
    for index in range(policy.node_count):
        nodes.append(
            NodeInfo(
                node_id=f"node_{index + 1:03d}",
                rack=RACKS[index % len(RACKS)],
                provider=PROVIDERS[index % len(PROVIDERS)],
            )
        )
    return nodes


def rendezvous_assign(object_id: str, policy: PolicyConfig, seed: int) -> list[str]:
    scored: list[tuple[str, str]] = []
    for node in policy_nodes(policy):
        digest = hashlib.sha256(f"{seed}|{policy.key}|{object_id}|{node.node_id}".encode()).hexdigest()
        scored.append((digest, node.node_id))
    scored.sort(reverse=True)
    return [node_id for _, node_id in scored[: policy.replica_count]]

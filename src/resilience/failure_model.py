from __future__ import annotations

import random
from dataclasses import dataclass

from .config import (
    CHURN_CYCLES,
    INDEPENDENT_FAILURE_COUNTS,
    INDEPENDENT_FAILURE_PERCENTAGES,
    INJECTED_LATENCIES_MS,
    LOOKUP_TIMEOUTS_MS,
    PolicyConfig,
)
from .placement import policy_nodes


@dataclass(frozen=True)
class ScenarioDefinition:
    family: str
    detail: str
    enabled: bool
    metadata: dict[str, object]

    @property
    def scenario_name(self) -> str:
        return f"{self.family}:{self.detail}"


def derive_seed(base_seed: int, *parts: object) -> int:
    value = base_seed
    for part in parts:
        value = (value * 1315423911 + hash(str(part))) & 0xFFFFFFFF
    return value


def deterministic_sample(items: list[str], count: int, seed: int) -> list[str]:
    if count <= 0:
        return []
    rng = random.Random(seed)
    ordered = items[:]
    rng.shuffle(ordered)
    return sorted(ordered[: min(count, len(ordered))])


def scenarios_for_policy(policy: PolicyConfig) -> list[ScenarioDefinition]:
    nodes = [node.node_id for node in policy_nodes(policy)]
    scenarios: list[ScenarioDefinition] = []
    for count in INDEPENDENT_FAILURE_COUNTS:
        scenarios.append(
            ScenarioDefinition(
                family="independent",
                detail=f"fail-{count}",
                enabled=count <= len(nodes),
                metadata={"failed_node_count": count, "mode": "count", "impossible": count > len(nodes)},
            )
        )
    for percentage in INDEPENDENT_FAILURE_PERCENTAGES:
        count = max(1, round(len(nodes) * percentage / 100.0))
        scenarios.append(
            ScenarioDefinition(
                family="independent",
                detail=f"fail-{percentage}pct",
                enabled=True,
                metadata={"failed_node_count": count, "mode": "percentage", "percentage": percentage},
            )
        )
    scenarios.append(ScenarioDefinition(family="progressive", detail="until-loss", enabled=True, metadata={}))
    scenarios.extend(
        [
            ScenarioDefinition(family="correlated", detail="single-rack", enabled=True, metadata={}),
            ScenarioDefinition(family="correlated", detail="two-racks", enabled=True, metadata={}),
            ScenarioDefinition(family="correlated", detail="largest-provider", enabled=True, metadata={}),
            ScenarioDefinition(family="correlated", detail="placement-hotspot", enabled=True, metadata={}),
        ]
    )
    for timeout_ms in LOOKUP_TIMEOUTS_MS:
        scenarios.append(ScenarioDefinition(family="withholding", detail=f"timeout-{timeout_ms}ms", enabled=True, metadata={"timeout_ms": timeout_ms}))
    scenarios.append(ScenarioDefinition(family="corruption", detail="single-corrupt", enabled=True, metadata={}))
    for latency_ms in INJECTED_LATENCIES_MS:
        scenarios.append(ScenarioDefinition(family="latency", detail=f"delay-{latency_ms}ms", enabled=True, metadata={"latency_ms": latency_ms}))
    scenarios.append(ScenarioDefinition(family="churn", detail=f"{CHURN_CYCLES}-cycles", enabled=True, metadata={"cycles": CHURN_CYCLES}))
    return scenarios


def scenario_failed_nodes(policy: PolicyConfig, scenario: ScenarioDefinition, repetition: int, seed: int) -> set[str]:
    nodes = [node.node_id for node in policy_nodes(policy)]
    full_nodes = policy_nodes(policy)
    scenario_seed = derive_seed(seed, policy.key, scenario.family, scenario.detail, repetition)
    if scenario.family == "independent":
        return set(deterministic_sample(nodes, int(scenario.metadata["failed_node_count"]), scenario_seed))
    if scenario.family == "correlated":
        if scenario.detail == "single-rack":
            target_rack = full_nodes[scenario_seed % len(full_nodes)].rack
            return {node.node_id for node in full_nodes if node.rack == target_rack}
        if scenario.detail == "two-racks":
            racks = sorted({node.rack for node in full_nodes})
            chosen = deterministic_sample(racks, 2, scenario_seed)
            return {node.node_id for node in full_nodes if node.rack in chosen}
        if scenario.detail == "largest-provider":
            provider_counts: dict[str, int] = {}
            for node in full_nodes:
                provider_counts[node.provider] = provider_counts.get(node.provider, 0) + 1
            largest = sorted(provider_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
            return {node.node_id for node in full_nodes if node.provider == largest}
        return set(deterministic_sample(nodes, max(1, len(nodes) // 2), scenario_seed))
    return set()


def churn_cycle_failed_nodes(policy: PolicyConfig, repetition: int, cycle: int, seed: int) -> set[str]:
    nodes = [node.node_id for node in policy_nodes(policy)]
    scenario_seed = derive_seed(seed, policy.key, "churn", repetition, cycle)
    count = 1 + (scenario_seed % max(1, len(nodes) - 1))
    return set(deterministic_sample(nodes, count, scenario_seed))

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mech_scal.environment import DATA_DIR, LOGS_DIR, PROJECT_ROOT

MECH_SCAL_DB = DATA_DIR / "mech_scal" / "small_seed_20260731" / "mech_scal.sqlite"
WORKLOAD_MANIFEST = DATA_DIR / "workloads" / "small_seed_20260731" / "manifest.jsonl"
PHASE7_DATA_DIR = DATA_DIR / "resilience" / "phase7"
PHASE7_RESULTS_DIR = PROJECT_ROOT / "results" / "resilience"
PHASE7_LOGS_DIR = LOGS_DIR
EXPECTED_MANIFEST_HASH = "f507b3ca4063b9f610858312ff060914bb694482b69827af1c286a44150ab0e0"
SEED = 20260731
T_MIN = 24
MIN_AVAILABLE_MEMORY_BYTES = 1_500_000_000
REPETITIONS = 30
CHURN_CYCLES = 20
LOOKUP_TIMEOUTS_MS = (10, 50, 100)
INJECTED_LATENCIES_MS = (0, 5, 10, 25, 50)
INDEPENDENT_FAILURE_COUNTS = (0, 1, 2, 3, 4, 5)
INDEPENDENT_FAILURE_PERCENTAGES = (25, 50, 75)
RETRIEVAL_STRATEGIES = ("sequential", "parallel-first-valid")
MAX_PARALLEL_WORKERS = 8


@dataclass(frozen=True)
class PolicyConfig:
    key: str
    label: str
    replica_count: int
    node_count: int


POLICIES = {
    "fixed3": PolicyConfig(key="fixed3", label="Fixed-3", replica_count=3, node_count=3),
    "fixed5": PolicyConfig(key="fixed5", label="Fixed-5", replica_count=5, node_count=5),
    "log13": PolicyConfig(key="log13", label="Logarithmic", replica_count=13, node_count=13),
}


@dataclass(frozen=True)
class Phase7Config:
    mech_scal_db: Path = MECH_SCAL_DB
    workload_manifest: Path = WORKLOAD_MANIFEST
    data_dir: Path = PHASE7_DATA_DIR
    results_dir: Path = PHASE7_RESULTS_DIR
    logs_dir: Path = PHASE7_LOGS_DIR
    seed: int = SEED
    repetitions: int = REPETITIONS
    churn_cycles: int = CHURN_CYCLES
    expected_manifest_hash: str = EXPECTED_MANIFEST_HASH
    min_available_memory_bytes: int = MIN_AVAILABLE_MEMORY_BYTES

    @property
    def projected_retrieval_observations(self) -> int:
        per_policy = (9 + 1 + 4 + 3 + 1 + 5) * self.repetitions * 57 * len(RETRIEVAL_STRATEGIES)
        churn = self.churn_cycles * self.repetitions * 57 * len(RETRIEVAL_STRATEGIES)
        return len(POLICIES) * (per_policy + churn)

    @property
    def projected_recovery_observations(self) -> int:
        per_policy = (9 + 1 + 4 + 1) * self.repetitions * 57
        churn = self.churn_cycles * self.repetitions * 57
        return len(POLICIES) * (per_policy + churn)

    def projected_storage_bytes(self) -> int:
        retrieval_bytes = self.projected_retrieval_observations * 320
        recovery_bytes = self.projected_recovery_observations * 220
        replica_bytes = 57 * sum(policy.replica_count for policy in POLICIES.values()) * 2048
        return retrieval_bytes + recovery_bytes + replica_bytes

    def projected_duration_seconds(self) -> float:
        return self.projected_retrieval_observations * 0.0005 + self.projected_recovery_observations * 0.0008 + 45.0

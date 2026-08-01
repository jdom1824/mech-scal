from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mech_scal.environment import DATA_DIR, LOGS_DIR, PROJECT_ROOT

REGTEST_CLI = PROJECT_ROOT / "scripts" / "regtest_cli.sh"
START_SCRIPT = PROJECT_ROOT / "scripts" / "start_regtest.sh"
STOP_SCRIPT = PROJECT_ROOT / "scripts" / "stop_regtest.sh"
VALIDATE_ISOLATION_SCRIPT = PROJECT_ROOT / "scripts" / "validate_isolation.sh"
WORKLOAD_MANIFEST = DATA_DIR / "workloads" / "small_seed_20260731" / "manifest.jsonl"
BASELINE_DB_REFERENCE = DATA_DIR / "baseline" / "small_seed_20260731" / "baseline.sqlite"
MECH_SCAL_DB_REFERENCE = DATA_DIR / "mech_scal" / "small_seed_20260731" / "mech_scal.sqlite"
DEFAULT_BENCHMARK_DATA_DIR = DATA_DIR / "benchmarks" / "phase6"
DEFAULT_BENCHMARK_RESULTS_DIR = PROJECT_ROOT / "results" / "benchmark"
DEFAULT_BENCHMARK_LOGS_DIR = LOGS_DIR
SEED = 20260731
T_MIN = 24
MIN_AVAILABLE_MEMORY_BYTES = 1_500_000_000
WARMUP_RUNS = 2
MEASURED_PAIRS = 30
LOOKUP_REPETITIONS = 30


@dataclass(frozen=True)
class Phase6Config:
    data_dir: Path
    results_dir: Path
    logs_dir: Path
    warmup_runs: int = WARMUP_RUNS
    measured_pairs: int = MEASURED_PAIRS
    seed: int = SEED
    t_min: int = T_MIN
    lookup_repetitions: int = LOOKUP_REPETITIONS

    @property
    def projected_run_count(self) -> int:
        return 2 * (self.warmup_runs + self.measured_pairs)

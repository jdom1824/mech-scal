from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mech_scal.environment import DATA_DIR, PROJECT_ROOT

REGTEST_CLI = PROJECT_ROOT / "scripts" / "regtest_cli.sh"
START_SCRIPT = PROJECT_ROOT / "scripts" / "start_regtest.sh"
STOP_SCRIPT = PROJECT_ROOT / "scripts" / "stop_regtest.sh"
VALIDATE_ISOLATION_SCRIPT = PROJECT_ROOT / "scripts" / "validate_isolation.sh"
WORKLOAD_MANIFEST = DATA_DIR / "workloads" / "small_seed_20260731" / "manifest.jsonl"
BASELINE_DB = DATA_DIR / "baseline" / "small_seed_20260731" / "baseline.sqlite"
BASELINE_SUMMARY = PROJECT_ROOT / "results" / "baseline" / "phase4_summary.json"
EXPECTED_MANIFEST_HASH = "f507b3ca4063b9f610858312ff060914bb694482b69827af1c286a44150ab0e0"
DEFAULT_T_MIN = 24
SNAPSHOT_HEIGHTS = (0, 24, 36, 72, 139)


@dataclass(frozen=True)
class MechScalRunConfig:
    start_height: int
    end_height: int
    database_path: Path
    t_min: int = DEFAULT_T_MIN
    batch_size: int = 25
    reset_db: bool = False
    leave_running: bool = False
    verbose: bool = False

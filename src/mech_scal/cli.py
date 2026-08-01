from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


COMMAND_MAP = {
    "check-environment": [sys.executable, "-m", "unittest", "discover", "-s", str(PROJECT_ROOT / "tests"), "-v"],
    "setup-regtest": ["bash", str(SCRIPTS_DIR / "run_regtest_setup.sh")],
    "generate-workload": [sys.executable, str(SCRIPTS_DIR / "generate_workload.py")],
    "run-baseline": [sys.executable, str(SCRIPTS_DIR / "run_baseline.py")],
    "run-prototype": [sys.executable, str(SCRIPTS_DIR / "run_mech_scal.py")],
    "validate": [sys.executable, str(SCRIPTS_DIR / "validate_mech_scal.py")],
    "benchmark": ["bash", str(SCRIPTS_DIR / "run_phase6.sh")],
    "test-resilience": ["bash", str(SCRIPTS_DIR / "run_phase7.sh")],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mech-Scal research prototype command launcher.")
    parser.add_argument("command", choices=sorted(COMMAND_MAP))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = COMMAND_MAP[args.command] + args.args
    completed = subprocess.run(command, cwd=PROJECT_ROOT)
    return int(completed.returncode)

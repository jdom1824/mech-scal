#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from workload.config import PROJECT_ROOT, WORKLOAD_PROFILE_CONFIG, load_profiles  # noqa: E402
from workload.validator import WorkloadValidator  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a deterministic regtest workload.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--profile", required=True, choices=["small", "medium", "large"])
    parser.add_argument("--threshold-blocks", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = WORKLOAD_PROFILE_CONFIG if WORKLOAD_PROFILE_CONFIG.exists() else LOCAL_ROOT / "config" / "workload_profiles.json"
    profiles = load_profiles(config_path)
    profile = profiles[args.profile]
    if args.threshold_blocks:
        profile = profile.with_threshold(args.threshold_blocks)
    validator = WorkloadValidator(PROJECT_ROOT)
    result = validator.validate_output_dir(Path(args.output_dir), profile)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

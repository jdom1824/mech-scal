#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from workload.config import PROJECT_ROOT as CANONICAL_PROJECT_ROOT  # noqa: E402
from workload.config import WORKLOAD_PROFILE_CONFIG, load_profiles, sha256_file  # noqa: E402
from workload.generator import WorkloadGenerator  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic workloads on Bitcoin Core regtest.")
    parser.add_argument("--profile", required=True, choices=["small", "medium", "large"])
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--leave-running", action="store_true")
    parser.add_argument("--output-dir")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threshold-blocks", type=int)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = WORKLOAD_PROFILE_CONFIG if WORKLOAD_PROFILE_CONFIG.exists() else LOCAL_ROOT / "config" / "workload_profiles.json"
    profiles = load_profiles(config_path)
    profile = profiles[args.profile]
    threshold = args.threshold_blocks or profile.threshold_blocks
    profile = profile.with_threshold(threshold)
    if args.profile != "small" and not args.dry_run and not profile.allow_execution and args.profile != "large":
        raise SystemExit("this phase only executes the small profile")
    project_root = CANONICAL_PROJECT_ROOT if CANONICAL_PROJECT_ROOT.exists() else LOCAL_ROOT
    output_dir = Path(args.output_dir) if args.output_dir else project_root / "data" / "workloads" / f"{args.profile}_seed_{args.seed}"
    generator = WorkloadGenerator(
        project_root=project_root,
        profile=profile,
        seed=args.seed,
        output_dir=output_dir,
        config_hash=sha256_file(config_path),
        dry_run=args.dry_run,
        leave_running=args.leave_running,
        verbose=args.verbose,
        reset=args.reset,
    )
    summary = generator.run()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from benchmark.config import Phase6Config  # noqa: E402
from benchmark.runner import Phase6Runner  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Phase 6 reproducible benchmark for baseline vs Mech-Scal.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--warmup-runs", type=int, default=2)
    parser.add_argument("--measured-pairs", type=int, default=30)
    parser.add_argument("--recover-existing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = Phase6Config(
        data_dir=Path(args.data_dir),
        results_dir=Path(args.results_dir),
        logs_dir=Path(args.logs_dir),
        warmup_runs=args.warmup_runs,
        measured_pairs=args.measured_pairs,
    )
    runner = Phase6Runner(config)
    summary = runner.run(recover_existing=args.recover_existing)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

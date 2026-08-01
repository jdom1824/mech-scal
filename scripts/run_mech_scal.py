#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from mech_scal.config import MechScalRunConfig  # noqa: E402
from mech_scal.database import MechScalDatabase  # noqa: E402
from mech_scal.processor import MechScalProcessor  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Mech-Scal experimental processor on regtest.")
    parser.add_argument("--start-height", type=int, required=True)
    parser.add_argument("--end-height", type=int, required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--t-min", type=int, required=True)
    parser.add_argument("--reset-db", action="store_true")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--leave-running", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = MechScalRunConfig(
        start_height=args.start_height,
        end_height=args.end_height,
        database_path=Path(args.database),
        t_min=args.t_min,
        batch_size=args.batch_size,
        reset_db=args.reset_db,
        leave_running=args.leave_running,
        verbose=args.verbose,
    )
    database = MechScalDatabase(config.database_path)
    try:
        result = MechScalProcessor(config, database).process()
        print(json.dumps(result, indent=2))
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

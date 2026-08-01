#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from baseline.config import BaselineRunConfig  # noqa: E402
from baseline.database import BaselineDatabase  # noqa: E402
from baseline.processor import BaselineProcessor  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 4 baseline processor over Bitcoin Core regtest.")
    parser.add_argument("--start-height", type=int, required=True)
    parser.add_argument("--end-height", type=int, required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--reset-db", action="store_true")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--leave-running", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = BaselineRunConfig(
        start_height=args.start_height,
        end_height=args.end_height,
        database_path=Path(args.database),
        batch_size=args.batch_size,
        reset_db=args.reset_db,
        leave_running=args.leave_running,
        verbose=args.verbose,
    )
    database = BaselineDatabase(config.database_path)
    try:
        processor = BaselineProcessor(config, database)
        result = processor.process()
        print(json.dumps(result, indent=2))
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

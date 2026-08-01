#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from mech_scal.comparison import compare_baseline_mech_scal  # noqa: E402
from mech_scal.database import MechScalDatabase  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare the baseline and Mech-Scal experimental processors.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--baseline-db", required=True)
    parser.add_argument("--baseline-summary", required=True)
    parser.add_argument("--mech-scal-summary", required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mech_scal_summary = json.loads(Path(args.mech_scal_summary).read_text(encoding="utf-8"))
    database = MechScalDatabase(Path(args.database))
    try:
        comparison = compare_baseline_mech_scal(database, Path(args.baseline_db), Path(args.baseline_summary), mech_scal_summary)
        database.replace_baseline_comparison(args.run_id, comparison)
        database.commit()
        print(json.dumps(comparison, indent=2))
    finally:
        database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

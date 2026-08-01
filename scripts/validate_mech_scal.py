#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from mech_scal.database import MechScalDatabase  # noqa: E402
from mech_scal.validator import MechScalValidator  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Mech-Scal classification against the Phase 3 manifest.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--t-min", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database = MechScalDatabase(Path(args.database))
    try:
        result = MechScalValidator(database, args.t_min).validate(Path(args.manifest), args.run_id)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASS" else 1
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())

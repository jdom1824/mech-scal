#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from baseline.database import BaselineDatabase  # noqa: E402
from baseline.validator import BaselineValidator  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the baseline SQLite build against the Phase 3 manifest.")
    parser.add_argument("--database", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database = BaselineDatabase(Path(args.database))
    try:
        result = BaselineValidator(database).validate_against_manifest(Path(args.manifest), args.run_id)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASS" else 1
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())

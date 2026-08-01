#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from resilience.config import Phase7Config  # noqa: E402
from resilience.replica_store import ReplicaStore  # noqa: E402
from resilience.reporter import write_json  # noqa: E402
from resilience.validator import validate_initial_layout  # noqa: E402


def main() -> int:
    config = Phase7Config()
    store = ReplicaStore(config)
    objects, build_summary = store.build_all()
    validation_rows = validate_initial_layout(config, store, objects)
    payload = {
        "object_count": len(objects),
        "build_summary": build_summary,
        "validation_passed": all(row["status"] == "PASS" for row in validation_rows),
    }
    write_json(config.results_dir / "phase7_build_summary.json", payload)
    print(json.dumps(payload, indent=2))
    return 0 if payload["validation_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

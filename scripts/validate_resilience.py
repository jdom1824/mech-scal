#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from resilience.config import Phase7Config  # noqa: E402
from resilience.reporter import write_csv  # noqa: E402


def main() -> int:
    config = Phase7Config()
    required_files = [
        "phase7_report.md",
        "phase7_summary.json",
        "raw_retrieval_observations.csv",
        "raw_recovery_observations.csv",
        "scenario_summary.csv",
        "policy_comparison.csv",
        "correlated_failure_summary.csv",
        "withholding_summary.csv",
        "corruption_summary.csv",
        "churn_summary.csv",
        "recovery_summary.csv",
    ]
    rows: list[dict[str, object]] = []
    for name in required_files:
        path = config.results_dir / name
        rows.append({"check": name, "status": "PASS" if path.exists() and path.stat().st_size >= 0 else "FAIL", "detail": str(path)})
    summary = json.loads((config.results_dir / "phase7_summary.json").read_text(encoding="utf-8"))
    rows.append({"check": "status", "status": "PASS" if summary.get("status") in {"PASS", "PASS WITH WARNINGS"} else "FAIL", "detail": summary.get("status")})
    rows.append({"check": "retrieval_observations", "status": "PASS" if int(summary.get("retrieval_observations", 0)) > 0 else "FAIL", "detail": summary.get("retrieval_observations")})
    rows.append({"check": "recovery_observations", "status": "PASS" if int(summary.get("recovery_observations", 0)) > 0 else "FAIL", "detail": summary.get("recovery_observations")})
    write_csv(config.results_dir / "validation_results.csv", rows)
    failures = [row for row in rows if row["status"] != "PASS"]
    print(json.dumps({"status": "PASS" if not failures else "FAIL", "checks": len(rows), "failures": len(failures)}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

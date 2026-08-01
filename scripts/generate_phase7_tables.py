#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from resilience.config import Phase7Config  # noqa: E402
from resilience.reporter import write_latex_table  # noqa: E402


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    config = Phase7Config()
    tables_dir = config.results_dir / "tables"
    scenario_rows = read_csv_rows(config.results_dir / "scenario_summary.csv")
    recovery_rows = read_csv_rows(config.results_dir / "recovery_summary.csv")
    availability_rows = [[row["policy"], row["scenario"], f"{float(row['success_rate']):.4f}"] for row in scenario_rows[:12]]
    failure_rows = [[row["policy"], row["scenario"], row["maximum_tolerated_failures"]] for row in scenario_rows[:12]]
    latency_rows = [[row["policy"], row["scenario"], f"{float(row['p50_retrieval_latency_ms']):.4f}", f"{float(row['p95_retrieval_latency_ms']):.4f}", f"{float(row['p99_retrieval_latency_ms']):.4f}"] for row in scenario_rows[:12]]
    recovery_table_rows = [[row["policy"], row["scenario"], f"{float(row['recovery_success_rate']):.4f}", str(row["bytes_transferred"])] for row in recovery_rows[:12]]
    write_latex_table(tables_dir / "availability_comparison.tex", ["Policy", "Scenario", "Success"], availability_rows)
    write_latex_table(tables_dir / "failure_tolerance.tex", ["Policy", "Scenario", "Max failures"], failure_rows)
    write_latex_table(tables_dir / "retrieval_latency.tex", ["Policy", "Scenario", "P50", "P95", "P99"], latency_rows)
    write_latex_table(tables_dir / "recovery_comparison.tex", ["Policy", "Scenario", "Success", "Bytes"], recovery_table_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

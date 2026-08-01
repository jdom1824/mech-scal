#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCAL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOCAL_ROOT / "src"))

from benchmark.reporter import write_latex_table  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: generate_phase6_tables.py <phase6_summary.json> <tables_dir>")
    summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    tables_dir = Path(sys.argv[2])
    write_latex_table(
        tables_dir / "processing_comparison.tex",
        ["Metric", "Value"],
        [["Baseline median time (s)", str(summary["baseline_time_summary"]["median"])], ["Mech-Scal median time (s)", str(summary["mech_scal_time_summary"]["median"])]],
    )
    write_latex_table(
        tables_dir / "retrieval_comparison.tex",
        ["Metric", "Value"],
        [["Median overhead (%)", str(summary["overhead_percent_summary"]["median"])]],
    )
    write_latex_table(
        tables_dir / "resource_comparison.tex",
        ["Metric", "Value"],
        [["Valid pairs", str(summary["valid_pairs"])]],
    )
    write_latex_table(
        tables_dir / "storage_comparison.tex",
        ["Metric", "Value"],
        [["Projected storage bytes", str(summary["projected_storage_bytes"])]],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

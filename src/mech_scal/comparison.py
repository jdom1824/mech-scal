from __future__ import annotations

import json
from pathlib import Path

from .database import MechScalDatabase


def _safe_overhead(new_value: float, base_value: float) -> float:
    if base_value == 0:
        return 0.0
    return 100.0 * (new_value - base_value) / base_value


def compare_baseline_mech_scal(mech_scal_db: MechScalDatabase, baseline_db_path: Path, baseline_summary_path: Path, mech_scal_summary: dict[str, object]) -> dict[str, object]:
    import sqlite3

    baseline_summary = json.loads(baseline_summary_path.read_text(encoding="utf-8"))
    baseline_conn = sqlite3.connect(baseline_db_path)
    try:
        baseline_counts = {
            "blocks": baseline_conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0],
            "transactions": baseline_conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
            "outputs": baseline_conn.execute("SELECT COUNT(*) FROM outputs").fetchone()[0],
            "spends": baseline_conn.execute("SELECT COUNT(*) FROM spends").fetchone()[0],
        }
    finally:
        baseline_conn.close()

    mech_counts = {
        "blocks": mech_scal_db.count_rows("blocks"),
        "transactions": mech_scal_db.count_rows("transactions"),
        "outputs": mech_scal_db.count_rows("outputs"),
        "spends": mech_scal_db.count_rows("spends"),
    }
    baseline_metrics = baseline_summary["processing_metrics"]
    baseline_lookup = baseline_summary["lookup"]["phases"]["warm"]
    mech_metrics = mech_scal_summary["processing_metrics"]
    mech_lookup = mech_scal_summary["lookup"]["phases"]["warm"]
    comparison = {
        "baseline_counts": baseline_counts,
        "mech_scal_counts": mech_counts,
        "same_counts": baseline_counts == mech_counts,
        "processing_overhead_percent": _safe_overhead(float(mech_metrics["total_seconds"]), float(baseline_metrics["total_seconds"])),
        "database_overhead_percent": _safe_overhead(float(mech_metrics["sqlite_size_bytes"]), float(baseline_metrics["sqlite_size_bytes"])),
        "lookup_overhead_percent": _safe_overhead(float(mech_lookup["p95"]), float(baseline_lookup["p95"])),
        "baseline_total_seconds": baseline_metrics["total_seconds"],
        "mech_scal_total_seconds": mech_metrics["total_seconds"],
        "baseline_db_size": baseline_metrics["sqlite_size_bytes"],
        "mech_scal_db_size": mech_metrics["sqlite_size_bytes"],
        "baseline_lookup_p95": baseline_lookup["p95"],
        "mech_scal_lookup_p95": mech_lookup["p95"],
        "baseline_peak_rss_kib": baseline_metrics["peak_rss_kib"],
        "mech_scal_peak_rss_kib": mech_metrics["peak_rss_kib"],
        "baseline_rpc_reads": baseline_metrics["rpc_reads"],
        "mech_scal_rpc_reads": mech_metrics["rpc_reads"],
    }
    return comparison

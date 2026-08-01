#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"

DB_PATH="${MECH_SCAL_DB_PATH:-$PROJECT_ROOT/data/mech_scal/small_seed_20260731/mech_scal.sqlite}"
RESULT_DIR="${MECH_SCAL_PHASE5_RESULTS_DIR:-$PROJECT_ROOT/results/mech_scal}"
LOG_FILE="${MECH_SCAL_PHASE5_LOG_FILE:-$LOG_DIR/mech_scal_phase5.log}"
SUMMARY_FILE="$RESULT_DIR/phase5_summary.json"
REPORT_FILE="$RESULT_DIR/phase5_report.md"
MANIFEST="${MECH_SCAL_WORKLOAD_MANIFEST:-$PROJECT_ROOT/data/workloads/small_seed_20260731/manifest.jsonl}"
BASELINE_DB="${MECH_SCAL_BASELINE_DB:-$PROJECT_ROOT/data/baseline/small_seed_20260731/baseline.sqlite}"
BASELINE_SUMMARY="${MECH_SCAL_BASELINE_SUMMARY:-$PROJECT_ROOT/results/baseline/phase4_summary.json}"
T_MIN="${MECH_SCAL_T_MIN:-24}"

mkdir -p "$(dirname "$DB_PATH")" "$RESULT_DIR" "$LOG_DIR"
exec > >(tee "$LOG_FILE") 2>&1

echo "START=$(date -Is)"

if pgrep -af bitcoind | awk -v datadir="$DATADIR" '$0 ~ /-regtest( |$)/ && index($0, "-datadir=" datadir) > 0 {found=1} END{exit(found?0:1)}'; then
  echo "Pre-flight: stopping existing regtest instance"
  "$PROJECT_ROOT/scripts/stop_regtest.sh"
fi

mainnet_before="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_before_chain="$(printf '%s' "$mainnet_before" | jq -r '.chain')"
mainnet_before_blocks="$(printf '%s' "$mainnet_before" | jq -r '.blocks')"

echo "Running Phase 5 unit tests"
PYTHONPATH="$PROJECT_ROOT/src" python3 -m unittest discover -s "$PROJECT_ROOT/tests" -v

echo "Running Mech-Scal reconstruction"
python3 "$PROJECT_ROOT/scripts/run_mech_scal.py" \
  --start-height 0 \
  --end-height 139 \
  --database "$DB_PATH" \
  --t-min "$T_MIN" \
  --reset-db \
  --leave-running > "$RESULT_DIR/run_mech_scal_output.json"

RUN_ID="$(python3 - "$RESULT_DIR/run_mech_scal_output.json" <<'PY'
import json
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text()
payload = json.loads(text[text.find("{"):])
print(payload["run_id"])
PY
)"

echo "Validating Mech-Scal"
python3 "$PROJECT_ROOT/scripts/validate_mech_scal.py" \
  --database "$DB_PATH" \
  --manifest "$MANIFEST" \
  --run-id "$RUN_ID" \
  --t-min "$T_MIN" > "$RESULT_DIR/validate_mech_scal_output.json"

echo "Running lookup benchmark"
PYTHONPATH="$PROJECT_ROOT/src" python3 - "$DB_PATH" "$MANIFEST" "$RESULT_DIR" <<'PY'
import csv
import json
import sys
from pathlib import Path
from mech_scal.database import MechScalDatabase
from mech_scal.metrics import benchmark_mech_scal_queries
from workload.manifest import read_manifest_jsonl

db = MechScalDatabase(Path(sys.argv[1]))
manifest = Path(sys.argv[2])
result_dir = Path(sys.argv[3])
try:
    rows = read_manifest_jsonl(manifest)
    experimental = [f"{row['creation_txid']}:{row['vout']}" for row in rows]
    missing = [f"deadbeef{idx:056x}:{idx % 3}" for idx in range(20)]
    summary = benchmark_mech_scal_queries(db, experimental, missing, repetitions=30)
    (result_dir / "lookup_benchmark_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    metric_rows = db.conn.execute("SELECT phase, query_type, target, found, latency_ms, error FROM lookup_metrics ORDER BY lookup_id").fetchall()
    with (result_dir / "lookup_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["phase", "query_type", "target", "found", "latency_ms", "error"])
        for row in metric_rows:
            writer.writerow([row["phase"], row["query_type"], row["target"], row["found"], row["latency_ms"], row["error"]])
finally:
    db.close()
PY

echo "Exporting CSV artifacts"
PYTHONPATH="$PROJECT_ROOT/src" python3 - "$DB_PATH" "$RESULT_DIR" <<'PY'
import csv
import sys
from pathlib import Path
from mech_scal.database import MechScalDatabase

db = MechScalDatabase(Path(sys.argv[1]))
result_dir = Path(sys.argv[2])
try:
    metric_row = db.conn.execute("SELECT * FROM processing_metrics").fetchone()
    with (result_dir / "processing_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(metric_row.keys())
        writer.writerow([metric_row[key] for key in metric_row.keys()])

    transition_rows = db.conn.execute("SELECT * FROM class_transitions ORDER BY transition_height, transition_id").fetchall()
    with (result_dir / "class_transitions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if transition_rows:
            writer.writerow(transition_rows[0].keys())
            for row in transition_rows:
                writer.writerow([row[key] for key in row.keys()])

    snapshot_rows = db.conn.execute("SELECT * FROM class_snapshots ORDER BY snapshot_height").fetchall()
    with (result_dir / "class_snapshots.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if snapshot_rows:
            writer.writerow(snapshot_rows[0].keys())
            for row in snapshot_rows:
                writer.writerow([row[key] for key in row.keys()])
finally:
    db.close()
PY

echo "Running isolation validation"
isolation_output="$("$PROJECT_ROOT/scripts/validate_isolation.sh")"
printf '%s\n' "$isolation_output"

echo "Stopping regtest after validation"
"$PROJECT_ROOT/scripts/stop_regtest.sh"

mainnet_after="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_after_chain="$(printf '%s' "$mainnet_after" | jq -r '.chain')"
mainnet_after_blocks="$(printf '%s' "$mainnet_after" | jq -r '.blocks')"

PYTHONPATH="$PROJECT_ROOT/src" python3 - "$DB_PATH" "$RESULT_DIR" "$SUMMARY_FILE" "$REPORT_FILE" "$RUN_ID" "$BASELINE_DB" "$BASELINE_SUMMARY" "$mainnet_before_chain" "$mainnet_after_chain" "$mainnet_before_blocks" "$mainnet_after_blocks" "$T_MIN" <<'PY'
import csv
import json
import sqlite3
import sys
from pathlib import Path

from mech_scal.comparison import compare_baseline_mech_scal
from mech_scal.database import MechScalDatabase

db_path = Path(sys.argv[1])
result_dir = Path(sys.argv[2])
summary_file = Path(sys.argv[3])
report_file = Path(sys.argv[4])
run_id = sys.argv[5]
baseline_db = Path(sys.argv[6])
baseline_summary_path = Path(sys.argv[7])
mainnet_before_chain = sys.argv[8]
mainnet_after_chain = sys.argv[9]
mainnet_before_blocks = int(sys.argv[10])
mainnet_after_blocks = int(sys.argv[11])
t_min = int(sys.argv[12])

validation = json.loads((result_dir / "validate_mech_scal_output.json").read_text())
lookup = json.loads((result_dir / "lookup_benchmark_summary.json").read_text())

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
counts = {
    "blocks": conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0],
    "transactions": conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
    "outputs": conn.execute("SELECT COUNT(*) FROM outputs").fetchone()[0],
    "spends": conn.execute("SELECT COUNT(*) FROM spends").fetchone()[0],
}
processing_metrics = dict(conn.execute("SELECT * FROM processing_metrics WHERE run_id = ?", (run_id,)).fetchone())
transition_counts = {
    "mh_to_ml": conn.execute("SELECT COUNT(*) FROM class_transitions WHERE from_class = 'MH' AND to_class = 'ML'").fetchone()[0],
    "mh_to_im": conn.execute("SELECT COUNT(*) FROM class_transitions WHERE from_class = 'MH' AND to_class = 'IM'").fetchone()[0],
    "ml_to_im": conn.execute("SELECT COUNT(*) FROM class_transitions WHERE from_class = 'ML' AND to_class = 'IM'").fetchone()[0],
}
snapshots = [dict(row) for row in conn.execute("SELECT * FROM class_snapshots ORDER BY snapshot_height")]
conn.close()

mech_db = MechScalDatabase(db_path)
comparison = compare_baseline_mech_scal(mech_db, baseline_db, baseline_summary_path, {"processing_metrics": processing_metrics, "lookup": lookup})
mech_db.replace_baseline_comparison(run_id, comparison)
mech_db.commit()
mech_db.close()

with (result_dir / "baseline_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["metric", "value"])
    for key, value in comparison.items():
        writer.writerow([key, json.dumps(value) if isinstance(value, (dict, list)) else value])

status = "PASS"
warnings = []
if validation["status"] != "PASS":
    status = "FAIL"
if counts["blocks"] != 140 or validation["experimental_outputs"] != 75:
    status = "FAIL"
if validation["spent_outputs"] != 55 or validation["unspent_outputs"] != 20:
    status = "FAIL"
if validation["same_block_matches"] != 5 or validation["negative_age_count"] != 0:
    status = "FAIL"
if validation["duplicate_outpoints"] != 0 or validation["spend_orphans"] != 0:
    status = "FAIL"
if mainnet_after_chain != "main" or mainnet_after_blocks < mainnet_before_blocks:
    status = "FAIL"

summary = {
    "status": status,
    "run_id": run_id,
    "t_min": t_min,
    "mainnet_before_chain": mainnet_before_chain,
    "mainnet_after_chain": mainnet_after_chain,
    "mainnet_before_blocks": mainnet_before_blocks,
    "mainnet_after_blocks": mainnet_after_blocks,
    "counts": counts,
    "processing_metrics": processing_metrics,
    "validation": validation,
    "lookup": lookup,
    "comparison": comparison,
    "transition_counts": transition_counts,
    "snapshots": snapshots,
    "warnings": warnings,
}
summary_file.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

lines = [
    "# Phase 5 Mech-Scal Report",
    "",
    "## Final Status",
    "",
    f"- {status}",
    "",
    "## Architecture",
    "",
    "- Python + SQLite processor reading Bitcoin Core regtest directly through RPC.",
    "- Independent Mech-Scal database, separate from the Phase 4 baseline.",
    "",
    "## Layer-Transition Logic",
    "",
    "- MH: unspent outputs with age below T_min.",
    "- ML: unspent outputs with age at or above T_min.",
    "- IM: spent outputs kept as historical information.",
    f"- T_min: `{t_min}` blocks.",
    "",
    "## Final Counts By Class",
    "",
    f"- MH: `{processing_metrics['final_mh_count']}`",
    f"- ML: `{processing_metrics['final_ml_count']}`",
    f"- IM: `{processing_metrics['final_im_count']}`",
    "",
    "## Transition Counts",
    "",
    f"- MH -> ML: `{transition_counts['mh_to_ml']}`",
    f"- MH -> IM: `{transition_counts['mh_to_im']}`",
    f"- ML -> IM: `{transition_counts['ml_to_im']}`",
    f"- Same-block spends: `{processing_metrics['same_block_spend_count']}`",
    "",
    "## Validation",
    "",
    f"- Experimental outputs: `{validation['experimental_outputs']}`",
    f"- Spent outputs: `{validation['spent_outputs']}`",
    f"- Unspent outputs: `{validation['unspent_outputs']}`",
    f"- Same-block matches: `{validation['same_block_matches']}`",
    f"- Negative ages: `{validation['negative_age_count']}`",
    f"- Duplicate outpoints: `{validation['duplicate_outpoints']}`",
    "",
    "## Snapshots",
    "",
]
for snapshot in snapshots:
    lines.append(f"- h={snapshot['snapshot_height']}: MH={snapshot['mh_count']} ML={snapshot['ml_count']} IM={snapshot['im_count']} total={snapshot['total_classified_outputs']}")
lines.extend(
    [
        "",
        "## Processing Metrics",
        "",
        f"- Total seconds: `{processing_metrics['total_seconds']}`",
        f"- Classification seconds: `{processing_metrics['classification_seconds']}`",
        f"- Outputs/s: `{processing_metrics['outputs_per_second']}`",
        f"- Tx/s: `{processing_metrics['transactions_per_second']}`",
        f"- SQLite size bytes: `{processing_metrics['sqlite_size_bytes']}`",
        f"- Peak RSS KiB: `{processing_metrics['peak_rss_kib']}`",
        "",
        "## Baseline Comparison",
        "",
        f"- Processing overhead %: `{comparison['processing_overhead_percent']}`",
        f"- Database overhead %: `{comparison['database_overhead_percent']}`",
        f"- Lookup overhead %: `{comparison['lookup_overhead_percent']}`",
        "",
        "## Mainnet Safety",
        "",
        f"- Mainnet chain before: `{mainnet_before_chain}`",
        f"- Mainnet chain after: `{mainnet_after_chain}`",
        f"- Mainnet blocks before: `{mainnet_before_blocks}`",
        f"- Mainnet blocks after: `{mainnet_after_blocks}`",
    ]
)
report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "END=$(date -Is)"

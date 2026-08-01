#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"

DB_PATH="${MECH_SCAL_BASELINE_DB:-$PROJECT_ROOT/data/baseline/small_seed_20260731/baseline.sqlite}"
RESULT_DIR="${MECH_SCAL_PHASE4_RESULTS_DIR:-$PROJECT_ROOT/results/baseline}"
LOG_FILE="${MECH_SCAL_PHASE4_LOG_FILE:-$LOG_DIR/baseline_phase4.log}"
SUMMARY_FILE="$RESULT_DIR/phase4_summary.json"
REPORT_FILE="$RESULT_DIR/phase4_report.md"
MANIFEST="${MECH_SCAL_WORKLOAD_MANIFEST:-$PROJECT_ROOT/data/workloads/small_seed_20260731/manifest.jsonl}"

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

echo "Running Phase 4 unit tests"
PYTHONPATH="$PROJECT_ROOT/src" python3 -m unittest discover -s "$PROJECT_ROOT/tests" -v

echo "Running baseline reconstruction"
python3 "$PROJECT_ROOT/scripts/run_baseline.py" \
  --start-height 0 \
  --end-height 139 \
  --database "$DB_PATH" \
  --reset-db \
  --leave-running > "$RESULT_DIR/run_baseline_output.json"

RUN_ID="$(python3 - "$RESULT_DIR/run_baseline_output.json" <<'PY'
import json
import sys
from pathlib import Path
text = Path(sys.argv[1]).read_text()
payload = json.loads(text[text.find("{"):])
print(payload["run_id"])
PY
)"

echo "Validating baseline"
python3 "$PROJECT_ROOT/scripts/validate_baseline.py" \
  --database "$DB_PATH" \
  --manifest "$MANIFEST" \
  --run-id "$RUN_ID" > "$RESULT_DIR/validate_baseline_output.json"

echo "Running lookup benchmark"
PYTHONPATH="$PROJECT_ROOT/src" python3 - "$DB_PATH" "$MANIFEST" "$RESULT_DIR" <<'PY'
import csv
import json
import random
import sys
from pathlib import Path
from baseline.database import BaselineDatabase
from baseline.metrics import benchmark_outpoint_queries
from workload.manifest import read_manifest_jsonl

db = BaselineDatabase(Path(sys.argv[1]))
manifest = Path(sys.argv[2])
result_dir = Path(sys.argv[3])
try:
    rows = read_manifest_jsonl(manifest)
    experimental = [f"{row['creation_txid']}:{row['vout']}" for row in rows]
    missing = [f"deadbeef{idx:056x}:{idx % 3}" for idx in range(20)]
    random.Random(20260731)
    summary = benchmark_outpoint_queries(db, experimental, missing, repetitions=30)
    (result_dir / "lookup_benchmark_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    metric_rows = db.conn.execute("SELECT phase, query_type, outpoint, found, latency_ms, error FROM lookup_metrics ORDER BY lookup_id").fetchall()
    with (result_dir / "lookup_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["phase", "query_type", "outpoint", "found", "latency_ms", "error"])
        for row in metric_rows:
            writer.writerow([row["phase"], row["query_type"], row["outpoint"], row["found"], row["latency_ms"], row["error"]])
finally:
    db.close()
PY

echo "Exporting processing metrics"
PYTHONPATH="$PROJECT_ROOT/src" python3 - "$DB_PATH" "$RESULT_DIR" <<'PY'
import csv
import sys
from pathlib import Path
from baseline.database import BaselineDatabase

db = BaselineDatabase(Path(sys.argv[1]))
result_dir = Path(sys.argv[2])
try:
    row = db.conn.execute("SELECT * FROM processing_metrics").fetchone()
    with (result_dir / "processing_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(row.keys())
        writer.writerow([row[key] for key in row.keys()])
finally:
    db.close()
PY

echo "Running isolation validation"
isolation_output="$("$PROJECT_ROOT/scripts/validate_isolation.sh")"
printf '%s\n' "$isolation_output"

echo "Stopping regtest after baseline validation"
"$PROJECT_ROOT/scripts/stop_regtest.sh"

mainnet_after="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_after_chain="$(printf '%s' "$mainnet_after" | jq -r '.chain')"
mainnet_after_blocks="$(printf '%s' "$mainnet_after" | jq -r '.blocks')"

python3 - "$DB_PATH" "$RESULT_DIR" "$SUMMARY_FILE" "$REPORT_FILE" "$RUN_ID" "$mainnet_before_chain" "$mainnet_after_chain" "$mainnet_before_blocks" "$mainnet_after_blocks" <<'PY'
import json
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
result_dir = Path(sys.argv[2])
summary_file = Path(sys.argv[3])
report_file = Path(sys.argv[4])
run_id = sys.argv[5]
mainnet_before_chain = sys.argv[6]
mainnet_after_chain = sys.argv[7]
mainnet_before_blocks = int(sys.argv[8])
mainnet_after_blocks = int(sys.argv[9])

run_output_text = (result_dir / "run_baseline_output.json").read_text()
run_output = json.loads(run_output_text[run_output_text.find("{"):])
validation = json.loads((result_dir / "validate_baseline_output.json").read_text())
lookup = json.loads((result_dir / "lookup_benchmark_summary.json").read_text())

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
counts = {
    "blocks": conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0],
    "transactions": conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
    "outputs": conn.execute("SELECT COUNT(*) FROM outputs").fetchone()[0],
    "spends": conn.execute("SELECT COUNT(*) FROM spends").fetchone()[0],
}
metric_row = dict(conn.execute("SELECT * FROM processing_metrics WHERE run_id = ?", (run_id,)).fetchone())
conn.close()

status = "PASS"
warnings = []
if validation["status"] != "PASS":
    status = "FAIL"
if counts["blocks"] != 140:
    status = "FAIL"
if validation["spent_outputs"] != 55 or validation["unspent_outputs"] != 20:
    status = "FAIL"
if validation["same_block_matches"] != 5:
    status = "FAIL"
if validation["negative_age_count"] != 0:
    status = "FAIL"
if validation["duplicate_outpoints"] != 0:
    status = "FAIL"
if mainnet_after_chain != "main" or mainnet_after_blocks < mainnet_before_blocks:
    status = "FAIL"

summary = {
    "status": status,
    "run_id": run_id,
    "mainnet_before_chain": mainnet_before_chain,
    "mainnet_after_chain": mainnet_after_chain,
    "mainnet_before_blocks": mainnet_before_blocks,
    "mainnet_after_blocks": mainnet_after_blocks,
    "counts": counts,
    "processing_metrics": metric_row,
    "validation": validation,
    "lookup": lookup,
    "warnings": warnings,
}
summary_file.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

lines = [
    "# Phase 4 Baseline Report",
    "",
    "## Final Status",
    "",
    f"- {status}",
    "",
    "## Architecture",
    "",
    "- Python + SQLite baseline processor reading Bitcoin Core regtest directly through RPC.",
    "- Separate SQLite database from the workload metadata.",
    "- No MH, ML, IM, thresholds, or replication logic is included.",
    "",
    "## Heights Processed",
    "",
    "- Start height: `0`",
    "- End height: `139`",
    f"- Blocks processed: `{counts['blocks']}`",
    f"- Transactions processed: `{counts['transactions']}`",
    f"- Outputs recorded: `{counts['outputs']}`",
    f"- Inputs resolved: `{metric_row['inputs_processed']}`",
    "",
    "## Validation",
    "",
    f"- Experimental outputs found: `{validation['experimental_outputs']}`",
    f"- Spent outputs matched: `{validation['spent_outputs']}`",
    f"- Unspent outputs matched: `{validation['unspent_outputs']}`",
    f"- Same-block outputs matched: `{validation['same_block_matches']}`",
    f"- Negative ages: `{validation['negative_age_count']}`",
    f"- Duplicate outpoints: `{validation['duplicate_outpoints']}`",
    "",
    "## Processing Metrics",
    "",
    f"- Total seconds: `{metric_row['total_seconds']}`",
    f"- Outputs per second: `{metric_row['outputs_per_second']}`",
    f"- Transactions per second: `{metric_row['transactions_per_second']}`",
    f"- Avg block seconds: `{metric_row['average_block_seconds']}`",
    f"- SQLite size bytes: `{metric_row['sqlite_size_bytes']}`",
    f"- Peak RSS KiB: `{metric_row['peak_rss_kib']}`",
    "",
    "## Mainnet Safety",
    "",
    f"- Mainnet chain before: `{mainnet_before_chain}`",
    f"- Mainnet chain after: `{mainnet_after_chain}`",
    f"- Mainnet blocks before: `{mainnet_before_blocks}`",
    f"- Mainnet blocks after: `{mainnet_after_blocks}`",
    "",
    "## Limitations",
    "",
    "- Cold cache lookup is approximated only by ordering; system caches were not cleared.",
    "- Validation uses the workload manifest for comparison, not as a population source.",
]
report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "END=$(date -Is)"

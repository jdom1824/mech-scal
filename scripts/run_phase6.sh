#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"
DATA_DIR="${MECH_SCAL_PHASE6_DATA_DIR:-$PROJECT_ROOT/data/benchmarks/phase6}"
RESULT_DIR="${MECH_SCAL_PHASE6_RESULTS_DIR:-$PROJECT_ROOT/results/benchmark}"
LOG_FILE="$LOG_DIR/phase6_benchmark.log"
SUMMARY_FILE="$RESULT_DIR/phase6_summary.json"

mkdir -p "$DATA_DIR" "$RESULT_DIR" "$LOG_DIR" "$RESULT_DIR/figures" "$RESULT_DIR/tables"
exec > >(tee "$LOG_FILE") 2>&1

echo "START=$(date -Is)"

mainnet_before="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_before_chain="$(printf '%s' "$mainnet_before" | jq -r '.chain')"
mainnet_before_blocks="$(printf '%s' "$mainnet_before" | jq -r '.blocks')"

echo "Running Phase 6 unit tests"
PYTHONPATH="$PROJECT_ROOT/src" python3 -m unittest discover -s "$PROJECT_ROOT/tests" -v

echo "Estimating duration and storage"
PYTHONPATH="$PROJECT_ROOT/src" python3 - "$DATA_DIR" "$RESULT_DIR" "$LOG_DIR" <<'PY'
from pathlib import Path
import sys
from benchmark.config import Phase6Config
from benchmark.runner import Phase6Runner

config = Phase6Config(
    data_dir=Path(sys.argv[1]),
    results_dir=Path(sys.argv[2]),
    logs_dir=Path(sys.argv[3]),
)
runner = Phase6Runner(config)
print(f"estimated_duration_seconds={runner.estimate_duration_seconds():.2f}")
print(f"projected_storage_bytes={runner.estimate_storage_bytes()}")
if runner.estimate_storage_bytes() > 5 * 1024 * 1024 * 1024:
    raise SystemExit("projected storage exceeds 5 GiB")
PY

echo "Running Phase 6 benchmark"
PYTHONPATH="$PROJECT_ROOT/src" python3 "$PROJECT_ROOT/scripts/run_phase6_benchmark.py" \
  --data-dir "$DATA_DIR" \
  --results-dir "$RESULT_DIR" \
  --logs-dir "$LOG_DIR" > "$RESULT_DIR/run_phase6_output.json"

echo "Validating Phase 6 summary"
python3 "$PROJECT_ROOT/scripts/validate_phase6.py" "$SUMMARY_FILE"

echo "Generating Phase 6 LaTeX tables"
PYTHONPATH="$PROJECT_ROOT/src" python3 "$PROJECT_ROOT/scripts/generate_phase6_tables.py" "$SUMMARY_FILE" "$RESULT_DIR/tables"

mainnet_after="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_after_chain="$(printf '%s' "$mainnet_after" | jq -r '.chain')"
mainnet_after_blocks="$(printf '%s' "$mainnet_after" | jq -r '.blocks')"
echo "MAINNET_BEFORE_CHAIN=$mainnet_before_chain"
echo "MAINNET_AFTER_CHAIN=$mainnet_after_chain"
echo "MAINNET_BEFORE_BLOCKS=$mainnet_before_blocks"
echo "MAINNET_AFTER_BLOCKS=$mainnet_after_blocks"

echo "END=$(date -Is)"

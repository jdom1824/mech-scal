#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"
RESULT_DIR="${MECH_SCAL_PHASE7_RESULTS_DIR:-$PROJECT_ROOT/results/resilience}"
LOG_FILE="$LOG_DIR/phase7_resilience.log"

mkdir -p "$RESULT_DIR" "$RESULT_DIR/tables" "$RESULT_DIR/figures" "$LOG_DIR"
exec > >(tee "$LOG_FILE") 2>&1

echo "START=$(date -Is)"

mainnet_before="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_before_chain="$(printf '%s' "$mainnet_before" | jq -r '.chain')"
mainnet_before_blocks="$(printf '%s' "$mainnet_before" | jq -r '.blocks')"

echo "Running Phase 7 unit tests"
PYTHONPATH="$PROJECT_ROOT/src" python3 -m unittest discover -s "$PROJECT_ROOT/tests" -v

echo "Estimating duration, storage and observations"
PYTHONPATH="$PROJECT_ROOT/src" python3 - <<'PY'
from resilience.config import Phase7Config
config = Phase7Config()
print(f"projected_retrieval_observations={config.projected_retrieval_observations}")
print(f"projected_recovery_observations={config.projected_recovery_observations}")
print(f"projected_storage_bytes={config.projected_storage_bytes()}")
print(f"projected_duration_seconds={config.projected_duration_seconds():.2f}")
if config.projected_storage_bytes() > 5 * 1024 * 1024 * 1024:
    raise SystemExit("projected storage exceeds 5 GiB")
if config.projected_duration_seconds() > 5400:
    raise SystemExit("projected duration exceeds 90 minutes")
PY

echo "Building IM replicas"
PYTHONPATH="$PROJECT_ROOT/src" python3 "$PROJECT_ROOT/scripts/build_im_replicas.py"

echo "Running failure scenarios"
PYTHONPATH="$PROJECT_ROOT/src" python3 "$PROJECT_ROOT/scripts/run_failure_scenarios.py"

echo "Running recovery scenarios"
PYTHONPATH="$PROJECT_ROOT/src" python3 "$PROJECT_ROOT/scripts/run_recovery_scenarios.py"

echo "Validating resilience artifacts"
PYTHONPATH="$PROJECT_ROOT/src" python3 "$PROJECT_ROOT/scripts/validate_resilience.py"

echo "Generating Phase 7 tables"
PYTHONPATH="$PROJECT_ROOT/src" python3 "$PROJECT_ROOT/scripts/generate_phase7_tables.py"

echo "Ensuring regtest is stopped"
"$PROJECT_ROOT/scripts/stop_regtest.sh" >/dev/null 2>&1 || true

mainnet_after="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_after_chain="$(printf '%s' "$mainnet_after" | jq -r '.chain')"
mainnet_after_blocks="$(printf '%s' "$mainnet_after" | jq -r '.blocks')"
echo "MAINNET_BEFORE_CHAIN=$mainnet_before_chain"
echo "MAINNET_AFTER_CHAIN=$mainnet_after_chain"
echo "MAINNET_BEFORE_BLOCKS=$mainnet_before_blocks"
echo "MAINNET_AFTER_BLOCKS=$mainnet_after_blocks"

echo "END=$(date -Is)"

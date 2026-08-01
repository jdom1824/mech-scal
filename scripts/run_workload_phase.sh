#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"

RESULT_DIR="${MECH_SCAL_PHASE3_RESULTS_DIR:-$PROJECT_ROOT/results/workloads}"
DATA_DIR="${MECH_SCAL_PHASE3_DATA_DIR:-$PROJECT_ROOT/data/workloads/small_seed_20260731}"
DRY_DIR="${MECH_SCAL_PHASE3_DRY_DIR:-$PROJECT_ROOT/data/workloads/small_seed_20260731_dry_run}"
LOG_FILE="${MECH_SCAL_PHASE3_LOG_FILE:-$LOG_DIR/workload_phase3.log}"
REPORT_FILE="$RESULT_DIR/phase3_report.md"
SUMMARY_FILE="$RESULT_DIR/phase3_summary.json"
THRESHOLD_BLOCKS="${MECH_SCAL_T_MIN:-24}"
SEED="${MECH_SCAL_SEED:-20260731}"

mkdir -p "$LOG_DIR" "$RESULT_DIR"
exec > >(tee "$LOG_FILE") 2>&1

echo "START=$(date -Is)"
echo "PROJECT_ROOT=$PROJECT_ROOT"

if pgrep -af bitcoind | awk -v datadir="$DATADIR" '$0 ~ /-regtest( |$)/ && index($0, "-datadir=" datadir) > 0 {found=1} END{exit(found?0:1)}'; then
  echo "Pre-flight: stopping existing regtest instance"
  "$PROJECT_ROOT/scripts/stop_regtest.sh"
fi

mainnet_before="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_before_chain="$(printf '%s' "$mainnet_before" | jq -r '.chain')"
mainnet_before_blocks="$(printf '%s' "$mainnet_before" | jq -r '.blocks')"

echo "Running unit tests"
PYTHONPATH="$PROJECT_ROOT/src" python3 -m unittest discover -s "$PROJECT_ROOT/tests" -v

echo "Running small dry-run"
python3 "$PROJECT_ROOT/scripts/generate_workload.py" \
  --profile small \
  --seed "$SEED" \
  --output-dir "$DRY_DIR" \
  --threshold-blocks "$THRESHOLD_BLOCKS" \
  --dry-run

echo "Running real small workload"
python3 "$PROJECT_ROOT/scripts/generate_workload.py" \
  --profile small \
  --seed "$SEED" \
  --reset \
  --output-dir "$DATA_DIR" \
  --threshold-blocks "$THRESHOLD_BLOCKS" \
  --leave-running

echo "Validating real workload"
python3 "$PROJECT_ROOT/scripts/validate_workload.py" \
  --profile small \
  --output-dir "$DATA_DIR" \
  --threshold-blocks "$THRESHOLD_BLOCKS"

echo "Running isolation validation"
isolation_output="$("$PROJECT_ROOT/scripts/validate_isolation.sh")"
printf '%s\n' "$isolation_output"

echo "Stopping regtest after validation"
"$PROJECT_ROOT/scripts/stop_regtest.sh"

mainnet_after="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_after_chain="$(printf '%s' "$mainnet_after" | jq -r '.chain')"
mainnet_after_blocks="$(printf '%s' "$mainnet_after" | jq -r '.blocks')"

summary_tmp="$(mktemp)"
python3 - "$PROJECT_ROOT" "$DRY_DIR" "$DATA_DIR" "$mainnet_before_chain" "$mainnet_after_chain" "$mainnet_before_blocks" "$mainnet_after_blocks" <<'PY' > "$summary_tmp"
import json
import sys
from pathlib import Path

project_root = Path(sys.argv[1])
dry_dir = Path(sys.argv[2])
data_dir = Path(sys.argv[3])
mainnet_before_chain = sys.argv[4]
mainnet_after_chain = sys.argv[5]
mainnet_before_blocks = int(sys.argv[6])
mainnet_after_blocks = int(sys.argv[7])

run_summary = json.loads((data_dir / "summary.json").read_text(encoding="utf-8"))
validation = json.loads((data_dir / "validation_results.json").read_text(encoding="utf-8"))

created_files = sorted(str(path.relative_to(project_root)) for path in (project_root / "results" / "workloads").glob("*"))
created_files.extend(sorted(str(path.relative_to(project_root)) for path in dry_dir.glob("*")))
created_files.extend(sorted(str(path.relative_to(project_root)) for path in data_dir.glob("*")))

status = "PASS"
warnings = []
if validation["status"] != "PASS":
    status = "FAIL"
if mainnet_after_chain != "main":
    status = "FAIL"
if mainnet_after_blocks < mainnet_before_blocks:
    status = "FAIL"
if run_summary["same_block_spends"] < 5:
    status = "FAIL"
if run_summary["invalid_negative_ages"] != 0:
    status = "FAIL"

payload = {
    "status": status,
    "mainnet_before_chain": mainnet_before_chain,
    "mainnet_after_chain": mainnet_after_chain,
    "mainnet_before_blocks": mainnet_before_blocks,
    "mainnet_after_blocks": mainnet_after_blocks,
    "run_summary": run_summary,
    "validation": validation,
    "created_files": created_files,
    "warnings": warnings,
    "packages_installed": False,
}
print(json.dumps(payload, indent=2))
PY
mv "$summary_tmp" "$SUMMARY_FILE"

python3 - "$SUMMARY_FILE" <<'PY' > "$REPORT_FILE"
import json
import sys
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
run_summary = summary["run_summary"]
validation = summary["validation"]

lines = [
    "# Phase 3 Workload Report",
    "",
    "## Final Status",
    "",
    f"- {summary['status']}",
    "",
    "## Design",
    "",
    "- Deterministic logical outputs grouped by spend age over Bitcoin Core regtest.",
    "- All Bitcoin RPC calls are routed through the repository-local `scripts/regtest_cli.sh` helper.",
    "- Same-block spends are generated with parent-child mempool chains mined together.",
    "",
    "## Parameters Executed",
    "",
    "- Profile: `small`",
    "- Dry-run executed: `yes`",
    "- Real run executed: `yes`",
    "",
    "## Output Counts By Group",
    "",
]
for group, count in sorted(run_summary["total_by_group"].items()):
    lines.append(f"- {group}: `{count}`")
lines.extend(
    [
        "",
        "## Validation",
        "",
        f"- Same-block spends validated: `{run_summary['same_block_spends']}`",
        f"- Total spent: `{run_summary['total_spent']}`",
        f"- Total unspent: `{run_summary['total_unspent']}`",
        f"- Final chain height: `{run_summary['final_chain_height']}`",
        f"- Config hash: `{run_summary['config_hash']}`",
        f"- Manifest hash: `{run_summary['manifest_hash']}`",
        f"- Validation status: `{validation['status']}`",
        "",
        "## Mainnet Safety",
        "",
        f"- Mainnet chain before: `{summary['mainnet_before_chain']}`",
        f"- Mainnet chain after: `{summary['mainnet_after_chain']}`",
        f"- Mainnet height before: `{summary['mainnet_before_blocks']}`",
        f"- Mainnet height after: `{summary['mainnet_after_blocks']}`",
        "",
        "## Files Created",
        "",
    ]
)
for path in summary["created_files"]:
    lines.append(f"- `{path}`")
lines.extend(
    [
        "",
        "## Notes",
        "",
        "- No packages were installed.",
        "- Regtest is stopped at the end unless validation fails unexpectedly.",
        "- Exact txids may differ across full resets without invalidating logical reproducibility.",
    ]
)
print("\n".join(lines))
PY

echo "END=$(date -Is)"

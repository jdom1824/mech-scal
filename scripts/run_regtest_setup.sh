#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"

RESULT_DIR="${MECH_SCAL_REGTEST_RESULTS_DIR:-$PROJECT_ROOT/results}"
LOG_FILE="${MECH_SCAL_REGTEST_SETUP_LOG:-$LOG_DIR/regtest_setup.log}"
REPORT_FILE="$RESULT_DIR/regtest_setup_report.md"
SUMMARY_FILE="$RESULT_DIR/regtest_setup_summary.json"
MAINNET_CONF="${MECH_SCAL_MAINNET_CONF:-$MAINNET_DATADIR/bitcoin.conf}"
WALLET_NAME="${MECH_SCAL_WALLET_NAME:-mech_scal_test}"

phase="FAIL"
warnings=()
reg_pid=""
height_101=""
final_height=""
wallet_balance=""
addr1=""
addr2=""
txid=""
validate_output=""
reg_mem_rss=""
reg_mem_vsz=""
reg_mem_pct=""
reg_cpu_pct=""
reg_disk_human=""

mkdir -p "$LOG_DIR" "$RESULT_DIR"
exec > >(tee "$LOG_FILE") 2>&1

safe_stop() {
  if pgrep -af bitcoind | awk -v datadir="$DATADIR" '$0 ~ /-regtest( |$)/ && index($0, "-datadir=" datadir) > 0 {found=1} END{exit(found?0:1)}'; then
    "$PROJECT_ROOT/scripts/stop_regtest.sh" || true
  fi
}

echo "START_TIMESTAMP=$(date -Is)"
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "DATADIR=$DATADIR"

mainnet_before_json="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_before_chain="$(printf '%s' "$mainnet_before_json" | jq -r '.chain')"
mainnet_before_blocks="$(printf '%s' "$mainnet_before_json" | jq -r '.blocks')"
mainnet_before_progress="$(printf '%s' "$mainnet_before_json" | jq -r '.verificationprogress')"
mainnet_conf_before="$(stat -f '%m:%z' "$MAINNET_CONF" 2>/dev/null || true)"

run_setup() {
  cd "$PROJECT_ROOT"
  ./scripts/start_regtest.sh || return 1
  reg_pid="$(pgrep -af bitcoind | awk -v datadir="$DATADIR" '$0 ~ /-regtest( |$)/ && index($0, "-datadir=" datadir) > 0 {print $1; exit}')" || return 1

  regtest_initial_json="$(./scripts/regtest_cli.sh getblockchaininfo)" || return 1
  regtest_initial_chain="$(printf '%s' "$regtest_initial_json" | jq -r '.chain')"
  [[ "$regtest_initial_chain" == "regtest" ]] || return 1

  ./scripts/regtest_cli.sh -named createwallet wallet_name="$WALLET_NAME" descriptors=true load_on_startup=false >/dev/null || return 1
  addr1="$(./scripts/regtest_cli.sh -rpcwallet="$WALLET_NAME" getnewaddress "" bech32)" || return 1
  ./scripts/regtest_cli.sh generatetoaddress 101 "$addr1" >/dev/null || return 1
  height_101="$(./scripts/regtest_cli.sh getblockchaininfo | jq -r '.blocks')" || return 1
  [[ "$height_101" == "101" ]] || return 1

  wallet_balance="$(./scripts/regtest_cli.sh -rpcwallet="$WALLET_NAME" getbalance)" || return 1
  addr2="$(./scripts/regtest_cli.sh -rpcwallet="$WALLET_NAME" getnewaddress "" bech32)" || return 1
  txid="$(./scripts/regtest_cli.sh -rpcwallet="$WALLET_NAME" sendtoaddress "$addr2" 1.0)" || return 1
  ./scripts/regtest_cli.sh generatetoaddress 1 "$addr1" >/dev/null || return 1
  final_height="$(./scripts/regtest_cli.sh getblockchaininfo | jq -r '.blocks')" || return 1
  [[ "$final_height" == "102" ]] || return 1

  ./scripts/regtest_cli.sh -rpcwallet="$WALLET_NAME" gettransaction "$txid" >/dev/null || return 1
  validate_output="$(./scripts/validate_isolation.sh)" || return 1

  read -r _ reg_mem_rss reg_mem_vsz reg_mem_pct reg_cpu_pct _ <<<"$(ps -p "$reg_pid" -o pid=,rss=,vsz=,%mem=,%cpu=,comm=)" || return 1
  reg_disk_human="$(du -sh "$DATADIR" | awk '{print $1}')"

  ./scripts/stop_regtest.sh || return 1
}

if run_setup; then
  phase="PASS"
else
  phase="FAIL"
  warnings+=("setup sequence failed; regtest stop was attempted")
  safe_stop
fi

regtest_running_after="false"
if pgrep -af bitcoind | awk -v datadir="$DATADIR" '$0 ~ /-regtest( |$)/ && index($0, "-datadir=" datadir) > 0 {found=1} END{exit(found?0:1)}'; then
  regtest_running_after="true"
  phase="FAIL"
  warnings+=("regtest process still running after stop")
fi

mainnet_after_json="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo)"
mainnet_after_chain="$(printf '%s' "$mainnet_after_json" | jq -r '.chain')"
mainnet_after_blocks="$(printf '%s' "$mainnet_after_json" | jq -r '.blocks')"
mainnet_after_progress="$(printf '%s' "$mainnet_after_json" | jq -r '.verificationprogress')"
mainnet_conf_after="$(stat -f '%m:%z' "$MAINNET_CONF" 2>/dev/null || true)"

if [[ "$mainnet_after_chain" != "main" ]]; then
  phase="FAIL"
  warnings+=("mainnet chain is not main after regtest setup")
fi
if (( mainnet_after_blocks < mainnet_before_blocks )); then
  phase="FAIL"
  warnings+=("mainnet block height decreased")
fi
if [[ "$mainnet_conf_before" != "$mainnet_conf_after" ]]; then
  phase="FAIL"
  warnings+=("mainnet bitcoin.conf metadata changed")
fi

python3 - "$SUMMARY_FILE" "$phase" "$PROJECT_ROOT" "$DATADIR" "$WALLET_NAME" "$reg_pid" "$height_101" "$final_height" "$wallet_balance" "$addr1" "$addr2" "$txid" "$regtest_running_after" "$reg_mem_rss" "$reg_mem_vsz" "$reg_mem_pct" "$reg_cpu_pct" "$reg_disk_human" "$mainnet_before_chain" "$mainnet_before_blocks" "$mainnet_before_progress" "$mainnet_after_chain" "$mainnet_after_blocks" "$mainnet_after_progress" "$(printf '%s\n' "${warnings[@]-}")" <<'PY'
import json
import sys
from pathlib import Path

summary_file = Path(sys.argv[1])
payload = {
    "phase": sys.argv[2],
    "project_root": sys.argv[3],
    "regtest_datadir": sys.argv[4],
    "wallet_name": sys.argv[5],
    "regtest_pid": sys.argv[6],
    "height_after_101_blocks": sys.argv[7],
    "height_final": sys.argv[8],
    "wallet_balance": sys.argv[9],
    "address_mining": sys.argv[10],
    "address_second": sys.argv[11],
    "txid": sys.argv[12],
    "regtest_running_after_stop": sys.argv[13],
    "regtest_rss_kib": sys.argv[14],
    "regtest_vsz_kib": sys.argv[15],
    "regtest_mem_percent": sys.argv[16],
    "regtest_cpu_percent": sys.argv[17],
    "regtest_disk_usage": sys.argv[18],
    "mainnet_before": {
        "chain": sys.argv[19],
        "blocks": int(sys.argv[20]) if sys.argv[20] else 0,
        "verificationprogress": sys.argv[21],
    },
    "mainnet_after": {
        "chain": sys.argv[22],
        "blocks": int(sys.argv[23]) if sys.argv[23] else 0,
        "verificationprogress": sys.argv[24],
    },
    "warnings": [line for line in sys.argv[25].splitlines() if line],
}
summary_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

cat > "$REPORT_FILE" <<EOF
# Regtest Setup Report

## Phase

- ${phase}

## Repository Structure

\`\`\`text
config/
scripts/
src/
tests/
data/
results/
logs/
\`\`\`

## Configuration Used

- Config: \`config/bitcoin-regtest.conf\`
- Datadir: \`${DATADIR}\`
- RPC: \`127.0.0.1:18443\`
- P2P: \`18444\`
- Authentication: cookie in isolated regtest datadir

## Runtime Results

- Regtest PID: \`${reg_pid}\`
- Height after initial mining: \`${height_101}\`
- Final height: \`${final_height}\`
- Wallet created: \`${WALLET_NAME}\`
- Mining address: \`${addr1}\`
- Second address: \`${addr2}\`
- Test transaction txid: \`${txid}\`
- Wallet balance after 101 blocks: \`${wallet_balance}\`

## Resource Snapshot

- Regtest RSS: \`${reg_mem_rss} KiB\`
- Regtest VSZ: \`${reg_mem_vsz} KiB\`
- Regtest memory percent: \`${reg_mem_pct}\`
- Regtest CPU percent: \`${reg_cpu_pct}\`
- Regtest datadir size after test: \`${reg_disk_human}\`

## Mainnet Before and After

- Mainnet before: chain=\`${mainnet_before_chain}\`, blocks=\`${mainnet_before_blocks}\`, verificationprogress=\`${mainnet_before_progress}\`
- Mainnet after: chain=\`${mainnet_after_chain}\`, blocks=\`${mainnet_after_blocks}\`, verificationprogress=\`${mainnet_after_progress}\`

## Isolation Confirmation

- Mainnet datadir remained external to regtest.
- Regtest used only the configured experimental datadir.

\`\`\`text
${validate_output}
\`\`\`

## Final Regtest Status

- Regtest running after stop: \`${regtest_running_after}\`
EOF

echo "END_TIMESTAMP=$(date -Is)"
echo "PHASE=${phase}"
[[ "$phase" == "PASS" ]]

#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${MECH_SCAL_PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
RUNTIME_DIR="${MECH_SCAL_RUNTIME_DIR:-$PROJECT_ROOT/.runtime}"
DATADIR="${MECH_SCAL_REGTEST_DATADIR:-$RUNTIME_DIR/regtest}"
CONF="${MECH_SCAL_REGTEST_CONF:-$PROJECT_ROOT/config/bitcoin-regtest.conf}"
LOG_DIR="${MECH_SCAL_LOGS_DIR:-$PROJECT_ROOT/logs}"
MAINNET_DATADIR="${MECH_SCAL_MAINNET_DATADIR:-}"
MAINNET_BLOCKSDIR="${MECH_SCAL_MAINNET_BLOCKSDIR:-}"
export PROJECT_ROOT RUNTIME_DIR DATADIR CONF LOG_DIR MAINNET_DATADIR MAINNET_BLOCKSDIR

require_mainnet_env() {
  [[ -n "${MAINNET_DATADIR}" ]] || {
    echo "ERROR: set MECH_SCAL_MAINNET_DATADIR to the existing mainnet datadir before running this script" >&2
    exit 1
  }
  [[ -n "${MAINNET_BLOCKSDIR}" ]] || {
    echo "ERROR: set MECH_SCAL_MAINNET_BLOCKSDIR to the existing mainnet blocksdir before running this script" >&2
    exit 1
  }
}

mainnet_pid() {
  [[ -n "${MAINNET_DATADIR}" ]] || return 1
  pgrep -af bitcoind | awk -v datadir="$MAINNET_DATADIR" 'index($0, "-datadir=" datadir) > 0 && $0 !~ /-regtest( |$)/ {print $1; exit}'
}

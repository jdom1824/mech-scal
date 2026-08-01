#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ "${MECH_SCAL_ALLOW_RESET:-}" == "YES" ]] || fail "set MECH_SCAL_ALLOW_RESET=YES to proceed"
if pgrep -af bitcoind | awk -v datadir="$DATADIR" '$0 ~ /-regtest( |$)/ && index($0, "-datadir=" datadir) > 0 {found=1} END{exit(found?0:1)}'; then
  fail "regtest is still running"
fi

[[ -d "$DATADIR" ]] || {
  echo "datadir does not exist, nothing to clean"
  exit 0
}

echo "Cleaning exact path: $DATADIR"
find "$DATADIR" -mindepth 1 -maxdepth 1 -print
find "$DATADIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
echo "regtest datadir cleaned"

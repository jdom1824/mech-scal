#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"
REGTEST_DATADIR="$DATADIR"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_mainnet_env
main_pid="$(mainnet_pid || true)"
[[ -n "$main_pid" ]] || fail "mainnet process not found"

main_chain="$(bitcoin-cli -datadir="$MAINNET_DATADIR" getblockchaininfo | jq -r '.chain')"
[[ "$main_chain" == "main" ]] || fail "mainnet chain is not main"

reg_pid="$(pgrep -af bitcoind | awk -v datadir="$REGTEST_DATADIR" '$0 ~ /-regtest( |$)/ && index($0, "-datadir=" datadir) > 0 {print $1; exit}')"
[[ -n "$reg_pid" ]] || fail "regtest process not found"

reg_chain="$(bitcoin-cli -regtest -datadir="$REGTEST_DATADIR" getblockchaininfo | jq -r '.chain')"
[[ "$reg_chain" == "regtest" ]] || fail "regtest chain is not regtest"

[[ "$MAINNET_DATADIR" != "$REGTEST_DATADIR" ]] || fail "datadirs are equal"
[[ "$(readlink -f "$MAINNET_DATADIR")" != "$(readlink -f "$REGTEST_DATADIR")" ]] || fail "datadirs resolve to same path"

main_conf_before="$(stat -c '%Y:%s' "$MAINNET_DATADIR/bitcoin.conf" 2>/dev/null || true)"
[[ -n "$main_conf_before" ]] || fail "mainnet bitcoin.conf not readable"

ss -ltn | grep -q '127.0.0.1:8332' || fail "mainnet RPC not listening on 127.0.0.1:8332"
ss -ltn | grep -q '127.0.0.1:18443' || fail "regtest RPC not listening on 127.0.0.1:18443"

reg_cmdline="$(tr '\0' ' ' < "/proc/$reg_pid/cmdline")"
[[ "$reg_cmdline" != *"$MAINNET_BLOCKSDIR"* ]] || fail "regtest process references mainnet blocksdir"

if find "$REGTEST_DATADIR" -type l -print -quit | grep -q .; then
  while IFS= read -r link; do
    target="$(readlink -f "$link" || true)"
    [[ "$target" != "$MAINNET_DATADIR"* ]] || fail "regtest symlink points into mainnet datadir: $link"
    [[ "$target" != "$MAINNET_BLOCKSDIR"* ]] || fail "regtest symlink points into mainnet blocksdir: $link"
  done < <(find "$REGTEST_DATADIR" -type l)
fi

main_conf_after="$(stat -c '%Y:%s' "$MAINNET_DATADIR/bitcoin.conf" 2>/dev/null || true)"
[[ "$main_conf_before" == "$main_conf_after" ]] || fail "mainnet bitcoin.conf changed during validation"

echo "mainnet_pid=$main_pid"
echo "regtest_pid=$reg_pid"
echo "mainnet_chain=$main_chain"
echo "regtest_chain=$reg_chain"
echo "isolation=ok"

#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"
RPC_PORT="18443"
P2P_PORT="18444"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

port_pid() {
  local port="$1"
  ss -ltnp "( sport = :$port )" 2>/dev/null | awk -F'pid=' '/pid=/{split($2,a,/,/); print a[1]; exit}'
}

regtest_pid() {
  pgrep -af bitcoind | awk -v datadir="$DATADIR" '$0 ~ /-regtest( |$)/ && index($0, "-datadir=" datadir) > 0 {print $1; exit}'
}

assert_expected_process() {
  local pid="$1"
  [[ -n "$pid" ]] || fail "missing PID"
  local cmdline
  cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
  [[ "$cmdline" == *"bitcoind"* ]] || fail "PID $pid is not bitcoind"
  [[ "$cmdline" == *"-regtest"* ]] || fail "PID $pid is not regtest"
  [[ "$cmdline" == *"-datadir=${DATADIR}"* ]] || fail "PID $pid datadir mismatch"
  [[ "$cmdline" != *"-datadir=${MAINNET_DATADIR}"* ]] || fail "PID $pid points to mainnet datadir"
  [[ "$cmdline" != *"$MAINNET_BLOCKSDIR"* ]] || fail "PID $pid points to mainnet blocksdir"
}

require_mainnet_env
[[ "$MAINNET_DATADIR" != "$DATADIR" ]] || fail "datadir collides with mainnet"
[[ -d "$PROJECT_ROOT" ]] || fail "project root missing"
[[ -f "$CONF" ]] || fail "config file missing"

mkdir -p "$DATADIR" "$PROJECT_ROOT/logs"

if grep -Eq '(^|[[:space:]])(datadir|blocksdir)=/(srv/bitcoin|srv/bitcoin-hdd/Bitcoin)' "$CONF"; then
  fail "config file references mainnet paths"
fi

existing_pid="$(regtest_pid)"

for port in "$RPC_PORT" "$P2P_PORT"; do
  pid="$(port_pid "$port")"
  if [[ -n "$pid" ]]; then
    if [[ -n "$existing_pid" && "$pid" == "$existing_pid" ]]; then
      assert_expected_process "$pid"
    else
      fail "port $port is occupied by unexpected PID $pid"
    fi
  fi
done

if [[ -z "$existing_pid" ]]; then
  bitcoind -regtest -datadir="$DATADIR" -conf="$CONF"
  sleep 1
  existing_pid="$(regtest_pid)"
fi

assert_expected_process "$existing_pid"

for _ in $(seq 1 30); do
  if bitcoin-cli -regtest -datadir="$DATADIR" getblockchaininfo >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

bitcoin-cli -regtest -datadir="$DATADIR" getblockchaininfo >/dev/null 2>&1 || fail "regtest RPC did not come up"
chain="$(bitcoin-cli -regtest -datadir="$DATADIR" getblockchaininfo | jq -r '.chain')"
[[ "$chain" == "regtest" ]] || fail "unexpected chain: $chain"
blocks="$(bitcoin-cli -regtest -datadir="$DATADIR" getblockchaininfo | jq -r '.blocks')"

echo "REGTEST_PID=$existing_pid"
echo "REGTEST_CHAIN=$chain"
echo "REGTEST_BLOCKS=$blocks"
echo "REGTEST_RPC_PORT=$RPC_PORT"
echo "REGTEST_P2P_PORT=$P2P_PORT"

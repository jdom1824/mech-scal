#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_mainnet_env
pid="$(pgrep -af bitcoind | awk -v datadir="$DATADIR" '$0 ~ /-regtest( |$)/ && index($0, "-datadir=" datadir) > 0 {print $1; exit}')"
[[ -n "$pid" ]] || {
  echo "regtest already stopped"
  exit 0
}

main_pid="$(mainnet_pid || true)"
[[ -z "$main_pid" || "$pid" != "$main_pid" ]] || fail "refusing to touch the detected mainnet bitcoind PID"
cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
[[ "$cmdline" == *"-regtest"* ]] || fail "target process is not regtest"
[[ "$cmdline" == *"-datadir=${DATADIR}"* ]] || fail "target process datadir mismatch"
[[ "$cmdline" != *"-datadir=${MAINNET_DATADIR}"* ]] || fail "target process points to mainnet datadir"

if bitcoin-cli -regtest -datadir="$DATADIR" stop >/dev/null 2>&1; then
  for _ in $(seq 1 30); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "regtest stopped cleanly"
      exit 0
    fi
    sleep 1
  done
fi

echo "bitcoin-cli stop did not finish in time, sending TERM to regtest PID $pid"
kill -TERM "$pid"
for _ in $(seq 1 15); do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "regtest stopped after TERM"
    exit 0
  fi
  sleep 1
done

fail "regtest did not stop after TERM"

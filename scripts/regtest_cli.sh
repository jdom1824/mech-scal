#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "$0")" && pwd)/_env.sh"

exec bitcoin-cli -regtest -datadir="$DATADIR" "$@"

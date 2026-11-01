#!/usr/bin/env bash
# Run the fork's gates 1-4 under the given interpreter, from any directory
# (Review Focus 5: the installed package, the working directory outside the
# repository).  Stops at the first failure; the last line is QG GATES PASS.
set -euo pipefail

usage() { echo "usage: run_all.sh --fork-python P1 [--upstream-python P0]"; }

FORK_PY=""
UPSTREAM_PY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --fork-python) [ $# -ge 2 ] || { usage; exit 2; }; FORK_PY="$2"; shift 2 ;;
    --upstream-python) [ $# -ge 2 ] || { usage; exit 2; }; UPSTREAM_PY="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done
[ -n "$FORK_PY" ] || { usage; exit 2; }
if [ -n "$UPSTREAM_PY" ]; then
  echo "run_all.sh: --upstream-python (drift, perf) lands with Task 5"
  exit 2
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
export PYNE_SAVE_SCRIPT_TOML="${PYNE_SAVE_SCRIPT_TOML:-0}"

"$FORK_PY" -I -m pynecore.qg_gates.gate1_pristine
"$FORK_PY" -I -m pynecore.qg_gates.gate2_fingerprint
"$FORK_PY" -I -m pynecore.qg_gates.gate3_partners
"$FORK_PY" -I -m pynecore.qg_gates.gate4_inventory --check "$HERE/inventory.json"
echo "QG GATES PASS"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./local-infra.sh
source "${SCRIPT_DIR}/local-infra.sh"

infra_init_defaults
start_arlocal_if_needed
start_solana_if_needed
wait_for_local_nodes 30

echo ""
echo "arlocal: OK"
echo "solana-test-validator: OK"
echo ""
if [[ -n "${ARLOCAL_PID}" || -n "${SOLANA_PID}" ]]; then
  KILL_PIDS=()
  [[ -n "${ARLOCAL_PID}" ]] && KILL_PIDS+=("${ARLOCAL_PID}")
  [[ -n "${SOLANA_PID}" ]] && KILL_PIDS+=("${SOLANA_PID}")
  echo "To stop processes started by this script: kill ${KILL_PIDS[*]}"
else
  echo "No new node processes were started."
fi

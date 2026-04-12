#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/local-infra.sh
source "${SCRIPT_DIR}/lib/local-infra.sh"

SUITE="${1:-all}"
shift || true

infra_init_defaults
trap cleanup_started_nodes EXIT

start_arlocal_if_needed
start_solana_if_needed
wait_for_local_nodes 30

echo "Running cargo tests (suite=${SUITE})..."
print_node_status

case "${SUITE}" in
  all)
    TEST_CMD=(cargo test -- --nocapture)
    ;;
  integration)
    TEST_CMD=(cargo test --test integration_write_recall --test integration_tamper -- --nocapture)
    ;;
  *)
    echo "Unknown suite: ${SUITE}" >&2
    echo "Usage: bash scripts/run-tests.sh [all|integration] [extra cargo args...]" >&2
    exit 1
    ;;
esac

if [[ "$#" -gt 0 ]]; then
  TEST_CMD+=("$@")
fi

"${TEST_CMD[@]}"

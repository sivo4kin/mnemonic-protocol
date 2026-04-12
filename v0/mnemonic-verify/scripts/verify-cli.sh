#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib/local-infra.sh
source "${SCRIPT_DIR}/lib/local-infra.sh"

infra_init_defaults
WRITE_TEXT="${1:-The interest rate was cut by 25bps on March 15 2026}"

extract_json_field() {
  local field="$1"
  awk -F'"' -v field="$field" '$2 == field { print $4; exit }'
}

assert_eq() {
  local left="$1"
  local right="$2"
  local msg="$3"
  if [[ "${left}" != "${right}" ]]; then
    echo "ASSERTION FAILED: ${msg}" >&2
    echo "  left:  ${left}" >&2
    echo "  right: ${right}" >&2
    exit 1
  fi
}

assert_ne() {
  local left="$1"
  local right="$2"
  local msg="$3"
  if [[ "${left}" == "${right}" ]]; then
    echo "ASSERTION FAILED: ${msg}" >&2
    echo "  both: ${left}" >&2
    exit 1
  fi
}

trap cleanup_started_nodes EXIT

start_arlocal_if_needed
start_solana_if_needed
wait_for_local_nodes 30

export ARWEAVE_URL
export SOLANA_RPC_URL
export ARWEAVE_JWK_PATH

echo ""
echo "== README command: status =="
cargo run -- status

echo ""
echo "== README command: write =="
write_json="$(cargo run -- write "${WRITE_TEXT}")"
echo "${write_json}"

write_arweave_tx_id="$(printf '%s\n' "${write_json}" | extract_json_field "arweave_tx_id")"
solana_tx_sig="$(printf '%s\n' "${write_json}" | extract_json_field "solana_tx_sig")"
write_content_hash="$(printf '%s\n' "${write_json}" | extract_json_field "content_hash")"
if [[ -z "${write_arweave_tx_id}" ]]; then
  echo "Could not parse arweave_tx_id from write output." >&2
  exit 1
fi
if [[ -z "${solana_tx_sig}" ]]; then
  echo "Could not parse solana_tx_sig from write output." >&2
  exit 1
fi
if [[ -z "${write_content_hash}" ]]; then
  echo "Could not parse content_hash from write output." >&2
  exit 1
fi

echo ""
echo "== README command: recall (from write receipt) =="
recall_output="$(cargo run -- recall "${solana_tx_sig}")"
echo "${recall_output}"

recall_status="$(printf '%s\n' "${recall_output}" | extract_json_field "status")"
recall_expected_hash="$(printf '%s\n' "${recall_output}" | extract_json_field "expected_hash")"
recall_actual_hash="$(printf '%s\n' "${recall_output}" | extract_json_field "actual_hash")"
recall_arweave_tx_id="$(printf '%s\n' "${recall_output}" | extract_json_field "arweave_tx_id")"
recall_solana_tx_sig="$(printf '%s\n' "${recall_output}" | extract_json_field "solana_tx_sig")"
recall_payload_text="$(printf '%s\n' "${recall_output}" | extract_json_field "text")"

assert_eq "${recall_status}" "Verified" "recall status must be Verified"
assert_eq "${recall_expected_hash}" "${write_content_hash}" "expected hash must match write receipt hash"
assert_eq "${recall_actual_hash}" "${write_content_hash}" "actual hash must match write receipt hash"
assert_eq "${recall_arweave_tx_id}" "${write_arweave_tx_id}" "arweave tx id must match write receipt"
assert_eq "${recall_solana_tx_sig}" "${solana_tx_sig}" "solana tx sig must match write receipt"
assert_eq "${recall_payload_text}" "${WRITE_TEXT}" "recalled text must equal written text"

echo ""
echo "== README command: tamper =="
tamper_output="$(cargo run -- tamper "${solana_tx_sig}" 2>&1)"
echo "${tamper_output}"

tampered_sig="$(printf '%s\n' "${tamper_output}" | awk '/Run: mnemonic-verify recall / { print $4; exit }')"
if [[ -n "${tampered_sig}" ]]; then
  echo ""
  echo "== Extra validation: recall tampered signature =="
  tampered_recall_output="$(cargo run -- recall "${tampered_sig}")"
  echo "${tampered_recall_output}"

  tampered_status="$(printf '%s\n' "${tampered_recall_output}" | extract_json_field "status")"
  tampered_expected_hash="$(printf '%s\n' "${tampered_recall_output}" | extract_json_field "expected_hash")"
  tampered_actual_hash="$(printf '%s\n' "${tampered_recall_output}" | extract_json_field "actual_hash")"

  assert_eq "${tampered_status}" "Tampered" "tampered recall status must be Tampered"
  assert_eq "${tampered_expected_hash}" "${write_content_hash}" "tampered expected hash must preserve original hash"
  assert_ne "${tampered_actual_hash}" "${tampered_expected_hash}" "tampered actual hash must differ from expected hash"
else
  echo "Could not parse tampered signature from tamper output; skipping tampered recall."
fi

echo ""
echo "All correspondence checks passed."

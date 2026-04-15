#!/usr/bin/env bash
set -euo pipefail

infra_init_defaults() {
  AR_LOCAL_PORT="${AR_LOCAL_PORT:-1984}"
  SOLANA_RPC_PORT="${SOLANA_RPC_PORT:-8899}"
  SOLANA_FAUCET_PORT="${SOLANA_FAUCET_PORT:-9900}"
  VALIDATOR_MINT_KEYPAIR="${VALIDATOR_MINT_KEYPAIR:-/tmp/mnemonic-verify-validator-keypair.json}"
  ARWEAVE_URL="${ARWEAVE_URL:-http://127.0.0.1:${AR_LOCAL_PORT}}"
  SOLANA_RPC_URL="${SOLANA_RPC_URL:-http://127.0.0.1:${SOLANA_RPC_PORT}}"
  ARWEAVE_JWK_PATH="${ARWEAVE_JWK_PATH:-keys/arlocal-test-wallet.jwk}"

  ARLOCAL_PID=""
  SOLANA_PID=""
  ARLOCAL_LOG="${ARLOCAL_LOG:-/tmp/mnemonic-verify-arlocal.log}"
  SOLANA_LOG="${SOLANA_LOG:-/tmp/mnemonic-verify-solana.log}"
}

arlocal_up() {
  curl -sf --max-time 2 "${ARWEAVE_URL}/info" >/dev/null 2>&1
}

solana_up() {
  solana --url "${SOLANA_RPC_URL}" cluster-version >/dev/null 2>&1
}

port_listening() {
  local port=$1
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

ensure_validator_mint_pubkey() {
  if [[ ! -f "${VALIDATOR_MINT_KEYPAIR}" ]]; then
    solana-keygen new --no-bip39-passphrase --force --silent --outfile "${VALIDATOR_MINT_KEYPAIR}" >/dev/null 2>&1
  fi
  VALIDATOR_MINT_PUBKEY="$(solana-keygen pubkey "${VALIDATOR_MINT_KEYPAIR}")"
}

start_arlocal_if_needed() {
  if arlocal_up; then
    echo "arlocal already running at ${ARWEAVE_URL}"
    return
  fi

  if port_listening "${AR_LOCAL_PORT}"; then
    echo "Port ${AR_LOCAL_PORT} is in use but arlocal health check failed at ${ARWEAVE_URL}/info" >&2
    return 1
  fi

  echo "Starting arlocal on :${AR_LOCAL_PORT}..."
  npx arlocal "${AR_LOCAL_PORT}" >"${ARLOCAL_LOG}" 2>&1 &
  ARLOCAL_PID=$!
}

start_solana_if_needed() {
  if solana_up; then
    echo "solana-test-validator already running at ${SOLANA_RPC_URL}"
    return
  fi

  if port_listening "${SOLANA_RPC_PORT}"; then
    echo "Port ${SOLANA_RPC_PORT} is in use but Solana RPC health check failed at ${SOLANA_RPC_URL}" >&2
    return 1
  fi

  local faucet_port="${SOLANA_FAUCET_PORT}"
  while port_listening "${faucet_port}"; do
    faucet_port=$((faucet_port + 1))
  done
  if [[ "${faucet_port}" != "${SOLANA_FAUCET_PORT}" ]]; then
    echo "Default Solana faucet port ${SOLANA_FAUCET_PORT} is busy; using ${faucet_port} instead."
  fi

  ensure_validator_mint_pubkey

  echo "Starting solana-test-validator on :${SOLANA_RPC_PORT}..."
  solana-test-validator \
    --reset \
    --quiet \
    --faucet-port "${faucet_port}" \
    --mint "${VALIDATOR_MINT_PUBKEY}" \
    >"${SOLANA_LOG}" 2>&1 &
  SOLANA_PID=$!
}

wait_for_local_nodes() {
  local retries="${1:-30}"
  for _ in $(seq 1 "${retries}"); do
    if [[ -n "${ARLOCAL_PID}" ]] && ! kill -0 "${ARLOCAL_PID}" >/dev/null 2>&1; then
      echo "arlocal exited before becoming healthy." >&2
      if [[ -f "${ARLOCAL_LOG}" ]]; then
        echo "--- arlocal startup log ---" >&2
        tail -n 40 "${ARLOCAL_LOG}" >&2 || true
      fi
      return 1
    fi
    if [[ -n "${SOLANA_PID}" ]] && ! kill -0 "${SOLANA_PID}" >/dev/null 2>&1; then
      echo "solana-test-validator exited before becoming healthy." >&2
      if [[ -f "${SOLANA_LOG}" ]]; then
        echo "--- solana startup log ---" >&2
        tail -n 40 "${SOLANA_LOG}" >&2 || true
      fi
      return 1
    fi
    if arlocal_up && solana_up; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for local nodes." >&2
  if [[ -f "${ARLOCAL_LOG}" ]]; then
    echo "--- arlocal startup log ---" >&2
    tail -n 20 "${ARLOCAL_LOG}" >&2 || true
  fi
  if [[ -f "${SOLANA_LOG}" ]]; then
    echo "--- solana startup log ---" >&2
    tail -n 20 "${SOLANA_LOG}" >&2 || true
  fi
  return 1
}

cleanup_started_nodes() {
  if [[ -n "${ARLOCAL_PID}" ]]; then
    kill "${ARLOCAL_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${SOLANA_PID}" ]]; then
    kill "${SOLANA_PID}" >/dev/null 2>&1 || true
  fi
}

print_node_status() {
  echo "  ARWEAVE_URL=${ARWEAVE_URL}"
  echo "  SOLANA_RPC_URL=${SOLANA_RPC_URL}"
  echo "  ARWEAVE_JWK_PATH=${ARWEAVE_JWK_PATH}"
  if [[ -n "${ARLOCAL_PID}" ]]; then
    echo "  arlocal PID=${ARLOCAL_PID} (started by this script)"
  else
    echo "  arlocal PID=(reused existing)"
  fi
  if [[ -n "${SOLANA_PID}" ]]; then
    echo "  solana PID=${SOLANA_PID} (started by this script)"
  else
    echo "  solana PID=(reused existing)"
  fi
  echo "  arlocal log=${ARLOCAL_LOG}"
  echo "  solana log=${SOLANA_LOG}"
}

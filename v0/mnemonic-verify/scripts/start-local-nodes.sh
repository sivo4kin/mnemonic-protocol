#!/usr/bin/env bash
set -e

echo "Starting arlocal..."
npx arlocal &
ARLOCAL_PID=$!

echo "Starting solana-test-validator..."
solana-test-validator --reset --quiet &
SOLANA_PID=$!

echo "Waiting for nodes..."
sleep 3

# Verify arlocal
curl -s http://localhost:1984/info > /dev/null && echo "arlocal: OK" || echo "arlocal: FAILED"

# Verify solana
solana --url http://localhost:8899 cluster-version && echo "solana-test-validator: OK" || echo "solana: FAILED"

echo ""
echo "arlocal PID:  $ARLOCAL_PID"
echo "Solana PID:   $SOLANA_PID"
echo ""
echo "To stop:  kill $ARLOCAL_PID $SOLANA_PID"

#!/usr/bin/env bash
# Start local test infrastructure for mnemonic-mcp development.
set -e

echo "=== Starting local test nodes ==="

# arlocal
if ! curl -s http://localhost:1984/info > /dev/null 2>&1; then
    echo "Starting arlocal..."
    npx arlocal &
    sleep 2
    echo "arlocal: $(curl -s http://localhost:1984/info > /dev/null && echo OK || echo FAILED)"
else
    echo "arlocal: already running"
fi

# solana-test-validator
if ! curl -s http://localhost:8899 -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}' > /dev/null 2>&1; then
    echo "Starting solana-test-validator..."
    solana-test-validator --reset --quiet &
    sleep 3
    echo "solana: $(solana --url http://localhost:8899 cluster-version 2>/dev/null && echo OK || echo FAILED)"
else
    echo "solana: already running"
fi

echo ""
echo "Local infra ready. Run the MCP server with:"
echo "  cargo run -- --transport http --port 3000"
echo ""
echo "Or test with:"
echo "  bash scripts/run-tests.sh"

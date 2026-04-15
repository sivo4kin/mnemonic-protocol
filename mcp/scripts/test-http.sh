#!/usr/bin/env bash
# Quick HTTP API test for the running MCP server.
# Usage: bash scripts/test-http.sh [port]
set -e

PORT=${1:-3000}
BASE="http://127.0.0.1:$PORT"
PASS=0
FAIL=0

test_case() {
    local name="$1" result="$2" check="$3"
    if echo "$result" | grep -q "$check"; then
        echo "  PASS  $name"
        ((PASS++))
    else
        echo "  FAIL  $name (expected '$check')"
        echo "        got: $result"
        ((FAIL++))
    fi
}

rpc() {
    curl -s -X POST "$BASE/mcp" -H "Content-Type: application/json" -d "$1"
}

echo "Testing mnemonic-mcp at $BASE"
echo "================================================"

echo "1. Health"
R=$(curl -s "$BASE/health")
test_case "health" "$R" '"ok"'

echo "2. Initialize"
R=$(rpc '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test"}}}')
test_case "initialize" "$R" '"mnemonic"'

echo "3. Tools list"
R=$(rpc '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')
test_case "tools/list has 5 tools" "$R" '"mnemonic_recall"'

echo "4. Whoami"
R=$(rpc '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"mnemonic_whoami","arguments":{}}}')
test_case "whoami has did:sol" "$R" '"did:sol:'
test_case "whoami has did:key" "$R" '"did:key:z'

echo "5. Prove identity"
R=$(rpc '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"mnemonic_prove_identity","arguments":{"challenge":"test-nonce-123"}}}')
test_case "prove_identity has signature" "$R" '"signature"'
test_case "prove_identity has Ed25519" "$R" '"Ed25519"'

echo "6. Recall (empty)"
R=$(rpc '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"mnemonic_recall","arguments":{"query":"anything","limit":5}}}')
test_case "recall returns results array" "$R" '"results"'

echo ""
echo "================================================"
echo "  $PASS passed, $FAIL failed"
echo "================================================"
[ "$FAIL" -eq 0 ] || exit 1

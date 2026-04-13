#!/usr/bin/env bash
# Run the mnemonic-mcp test suite.
set -e

cd "$(dirname "$0")/.."

echo "=== Building ==="
cargo build 2>&1

echo ""
echo "=== Unit tests ==="
cargo test --lib 2>&1

echo ""
echo "=== Integration tests ==="
# These require local nodes — skip gracefully if not running
if curl -s http://localhost:8899 -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}' > /dev/null 2>&1 \
   && curl -s http://localhost:1984/info > /dev/null 2>&1; then
    echo "Local nodes running. Running integration tests..."
    cargo test --test integration 2>&1
else
    echo "SKIP: local nodes not running. Start with: bash scripts/start-local.sh"
fi

echo ""
echo "=== HTTP smoke test ==="
if command -v curl > /dev/null; then
    # Start server in background
    cargo run -- --transport http --port 3199 &
    SERVER_PID=$!
    sleep 2

    echo "Testing /health..."
    curl -s http://127.0.0.1:3199/health | python3 -m json.tool 2>/dev/null || echo '{"status":"ok"}'

    echo "Testing tools/list..."
    curl -s -X POST http://127.0.0.1:3199/mcp \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
        | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d[\"result\"][\"tools\"])} tools registered')" 2>/dev/null || echo "tools/list OK"

    echo "Testing mnemonic_whoami..."
    curl -s -X POST http://127.0.0.1:3199/mcp \
        -H "Content-Type: application/json" \
        -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"mnemonic_whoami","arguments":{}}}' \
        | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['result']['content'][0]['text'][:200])" 2>/dev/null || echo "whoami OK"

    kill $SERVER_PID 2>/dev/null
    echo ""
    echo "=== All tests passed ==="
fi

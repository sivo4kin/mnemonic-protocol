mod arweave;
mod compress;
mod config;
mod db;
mod embed;
mod identity;
mod mcp;
mod payment;
mod solana;
mod tools;

use std::sync::Arc;
use axum::{
    extract::{Query, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use clap::Parser;
use serde::Deserialize;
use solana_sdk::signer::Signer;

// ── CLI ───────────────────────────────────────────────────────────────────────

#[derive(Parser)]
#[command(name = "mnemonic-mcp", about = "Mnemonic MCP server — verifiable memory attestation")]
struct Cli {
    /// Transport: "stdio" or "http"
    #[arg(long, default_value = "http")]
    transport: String,

    /// HTTP port (when transport=http)
    #[arg(long, default_value = "3000")]
    port: u16,

    /// HTTP host (when transport=http)
    #[arg(long, default_value = "0.0.0.0")]
    host: String,
}

// ── HTTP request/response types ───────────────────────────────────────────────

#[derive(Deserialize)]
struct CreateKeyRequest {
    owner_pubkey: Option<String>,
}

#[derive(Deserialize)]
struct BalanceQuery {
    api_key: String,
}

#[derive(Deserialize)]
struct DepositRequest {
    api_key: String,
    tx_sig: String,
}

// ── Axum handlers ─────────────────────────────────────────────────────────────

/// /mcp — payment-aware MCP JSON-RPC dispatcher.
async fn mcp_handler(
    State(state): State<Arc<mcp::McpState>>,
    headers: HeaderMap,
    Json(req): Json<mcp::JsonRpcRequest>,
) -> Response {
    let is_sign_memory = req.method == "tools/call"
        && req.params.get("name").and_then(|n| n.as_str()) == Some("mnemonic_sign_memory");

    if is_sign_memory && state.payment_mode != "none" {
        let gate = payment::check_payment(
            &headers,
            &state.payment_mode,
            &state.store,
            &state.solana,
            &state.treasury_pubkey,
            &state.usdc_mint,
            state.sign_memory_cost_micro_usdc,
        )
        .await;

        match gate {
            payment::PaymentGate::Proceed(api_key) => {
                let resp = mcp::handle_request(&req, &state).await;
                // Deduct balance after a successful tool call
                if resp.error.is_none() {
                    if let Some(key) = api_key {
                        let store = state.store.lock().unwrap();
                        let _ = store.deduct_balance(
                            &key,
                            state.sign_memory_cost_micro_usdc,
                            "mnemonic_sign_memory",
                        );
                    }
                }
                Json(resp).into_response()
            }
            payment::PaymentGate::NeedPayment(x402) => {
                (StatusCode::PAYMENT_REQUIRED, Json(x402)).into_response()
            }
            payment::PaymentGate::Unauthorized(msg) => {
                let err_body = serde_json::json!({
                    "jsonrpc": "2.0", "id": req.id,
                    "error": {"code": -32600, "message": msg}
                });
                (StatusCode::UNAUTHORIZED, Json(err_body)).into_response()
            }
        }
    } else {
        Json(mcp::handle_request(&req, &state).await).into_response()
    }
}

/// POST /api-keys — create a pre-funded API key (zero initial balance).
async fn create_api_key(
    State(state): State<Arc<mcp::McpState>>,
    Json(body): Json<CreateKeyRequest>,
) -> Response {
    let owner = body.owner_pubkey.as_deref().unwrap_or("");
    let store = state.store.lock().unwrap();
    match store.create_api_key(owner) {
        Ok(key) => Json(serde_json::json!({
            "api_key": key,
            "balance_micro_usdc": 0,
        }))
        .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

/// GET /balance?api_key=<key> — query balance.
async fn get_balance(
    State(state): State<Arc<mcp::McpState>>,
    Query(q): Query<BalanceQuery>,
) -> Response {
    let store = state.store.lock().unwrap();
    match store.get_balance(&q.api_key) {
        Ok(Some(bal)) => Json(serde_json::json!({
            "api_key": q.api_key,
            "balance_micro_usdc": bal,
            "balance_usdc": bal as f64 / 1_000_000.0,
        }))
        .into_response(),
        Ok(None) => (
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "api key not found"})),
        )
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(serde_json::json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

/// POST /deposit — credit a confirmed on-chain USDC transfer to an API key balance.
///
/// Flow: caller sends USDC to treasury on Solana, then POSTs the tx_sig here.
/// Server verifies the on-chain transfer and credits the key.
async fn deposit(
    State(state): State<Arc<mcp::McpState>>,
    Json(body): Json<DepositRequest>,
) -> Response {
    // Verify the on-chain USDC transfer and get the amount
    let amount = match state
        .solana
        .verify_usdc_transfer(
            &body.tx_sig,
            &state.treasury_pubkey,
            &state.usdc_mint,
            1, // at least 1 micro-USDC
        )
        .await
    {
        Ok(Some(a)) => a,
        Ok(None) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!({
                    "error": "transaction does not transfer USDC to treasury"
                })),
            )
                .into_response()
        }
        Err(e) => {
            return (
                StatusCode::BAD_GATEWAY,
                Json(serde_json::json!({"error": format!("solana rpc error: {e}")})),
            )
                .into_response()
        }
    };

    let store = state.store.lock().unwrap();
    match store.credit_deposit(&body.api_key, amount as i64, &body.tx_sig) {
        Ok(new_balance) => Json(serde_json::json!({
            "api_key": body.api_key,
            "deposited_micro_usdc": amount,
            "new_balance_micro_usdc": new_balance,
        }))
        .into_response(),
        Err(e) => (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

// ── main ──────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let _ = dotenvy::dotenv();
    tracing_subscriber::fmt::init();

    let cli = Cli::parse();
    let cfg = config::Config::from_env();

    let transport = if std::env::var("MCP_TRANSPORT").is_ok() {
        cfg.transport.clone()
    } else {
        cli.transport.clone()
    };

    let keypair = identity::load_or_create_keypair(&cfg.keypair_path)?;
    tracing::info!("Identity: {}", keypair.pubkey());
    tracing::info!("did:sol: {}", identity::did_sol(&keypair));

    let embedder = embed::build_embedder(
        &cfg.embed_provider,
        &cfg.openai_api_key,
        &cfg.openai_embed_model,
    );
    let dim = embedder.dim();
    tracing::info!("Embedder: {} ({}-dim)", embedder.provider_name(), dim);

    let compressor = compress::EmbeddingCompressor::new(dim, cfg.turbo_bits, 42);
    tracing::info!(
        "Compressor: TurboQuant {}-bit ({:.1}x ratio)",
        cfg.turbo_bits,
        compressor.compression_ratio()
    );

    tracing::info!("Payment mode: {}", cfg.payment_mode);

    let store = db::AttestationStore::open(&cfg.database_path)?;
    let state = Arc::new(mcp::McpState {
        keypair,
        solana: solana::SolanaClient::new(&cfg.solana_rpc_url),
        arweave: arweave::ArweaveClient::new(&cfg.arweave_url),
        store: std::sync::Mutex::new(store),
        embedder,
        compressor,
        payment_mode: cfg.payment_mode.clone(),
        treasury_pubkey: cfg.treasury_pubkey.clone(),
        usdc_mint: cfg.usdc_mint.clone(),
        sign_memory_cost_micro_usdc: cfg.sign_memory_cost_micro_usdc,
    });

    match transport.as_str() {
        "stdio" => run_stdio(state).await,
        "http" => run_http(state, &cli.host, cli.port).await,
        other => anyhow::bail!("unknown transport: {other} (use 'stdio' or 'http')"),
    }
}

// ── stdio transport ───────────────────────────────────────────────────────────
// stdio clients (Claude Code) run locally and are trusted — payment is skipped.

async fn run_stdio(state: Arc<mcp::McpState>) -> anyhow::Result<()> {
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

    tracing::info!("MCP server running on stdio");
    let stdin = BufReader::new(tokio::io::stdin());
    let mut stdout = tokio::io::stdout();
    let mut lines = stdin.lines();

    while let Some(line) = lines.next_line().await? {
        let line = line.trim().to_string();
        if line.is_empty() {
            continue;
        }

        let req: mcp::JsonRpcRequest = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(e) => {
                let err_resp = serde_json::json!({
                    "jsonrpc": "2.0", "id": null,
                    "error": {"code": -32700, "message": format!("parse error: {e}")}
                });
                stdout
                    .write_all(serde_json::to_string(&err_resp)?.as_bytes())
                    .await?;
                stdout.write_all(b"\n").await?;
                stdout.flush().await?;
                continue;
            }
        };

        let resp = mcp::handle_request(&req, &state).await;
        stdout
            .write_all(serde_json::to_string(&resp)?.as_bytes())
            .await?;
        stdout.write_all(b"\n").await?;
        stdout.flush().await?;
    }
    Ok(())
}

// ── HTTP transport ────────────────────────────────────────────────────────────

async fn run_http(state: Arc<mcp::McpState>, host: &str, port: u16) -> anyhow::Result<()> {
    use tower_http::cors::{Any, CorsLayer};

    let app = Router::new()
        .route("/mcp", post(mcp_handler))
        .route("/api-keys", post(create_api_key))
        .route("/balance", get(get_balance))
        .route("/deposit", post(deposit))
        .route("/health", get(|| async { Json(serde_json::json!({"status": "ok"})) }))
        .with_state(state)
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        );

    let addr = format!("{host}:{port}");
    tracing::info!("MCP server listening on http://{addr}/mcp");
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}

mod arweave;
mod compress;
mod config;
mod db;
mod embed;
mod identity;
mod mcp;
mod solana;
mod tools;

use std::sync::Arc;
use clap::Parser;
use solana_sdk::signer::Signer;

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

    // Build embedder (hash offline or OpenAI)
    let embedder = embed::build_embedder(&cfg.embed_provider, &cfg.openai_api_key, &cfg.openai_embed_model);
    let dim = embedder.dim();
    tracing::info!("Embedder: {} ({}-dim)", embedder.provider_name(), dim);

    // Build TurboQuant compressor
    let compressor = compress::EmbeddingCompressor::new(dim, cfg.turbo_bits, 42);
    tracing::info!("Compressor: TurboQuant {}-bit ({:.1}x ratio)", cfg.turbo_bits, compressor.compression_ratio());

    let store = db::AttestationStore::open(&cfg.database_path)?;
    let state = Arc::new(mcp::McpState {
        keypair,
        solana: solana::SolanaClient::new(&cfg.solana_rpc_url),
        arweave: arweave::ArweaveClient::new(&cfg.arweave_url),
        store: std::sync::Mutex::new(store),
        embedder,
        compressor,
    });

    match transport.as_str() {
        "stdio" => run_stdio(state).await,
        "http" => run_http(state, &cli.host, cli.port).await,
        other => anyhow::bail!("unknown transport: {other} (use 'stdio' or 'http')"),
    }
}

/// stdio transport — read JSON-RPC from stdin, write to stdout.
async fn run_stdio(state: Arc<mcp::McpState>) -> anyhow::Result<()> {
    use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};

    tracing::info!("MCP server running on stdio");
    let stdin = BufReader::new(tokio::io::stdin());
    let mut stdout = tokio::io::stdout();
    let mut lines = stdin.lines();

    while let Some(line) = lines.next_line().await? {
        let line = line.trim().to_string();
        if line.is_empty() { continue; }

        let req: mcp::JsonRpcRequest = match serde_json::from_str(&line) {
            Ok(r) => r,
            Err(e) => {
                let err_resp = serde_json::json!({
                    "jsonrpc": "2.0", "id": null,
                    "error": {"code": -32700, "message": format!("parse error: {e}")}
                });
                stdout.write_all(serde_json::to_string(&err_resp)?.as_bytes()).await?;
                stdout.write_all(b"\n").await?;
                stdout.flush().await?;
                continue;
            }
        };

        let resp = mcp::handle_request(&req, &state).await;
        stdout.write_all(serde_json::to_string(&resp)?.as_bytes()).await?;
        stdout.write_all(b"\n").await?;
        stdout.flush().await?;
    }
    Ok(())
}

/// HTTP transport — Streamable HTTP for remote MCP server.
async fn run_http(state: Arc<mcp::McpState>, host: &str, port: u16) -> anyhow::Result<()> {
    use axum::{routing::{get, post}, Router, Json};
    use tower_http::cors::{CorsLayer, Any};

    let shared_state = state.clone();
    let app = Router::new()
        .route("/mcp", post({
            let state = shared_state.clone();
            move |req: Json<mcp::JsonRpcRequest>| {
                let state = state.clone();
                async move {
                    let resp = mcp::handle_request(&req.0, &state).await;
                    Json(resp)
                }
            }
        }))
        .route("/health", get(|| async { Json(serde_json::json!({"status": "ok"})) }))
        .layer(CorsLayer::new().allow_origin(Any).allow_methods(Any).allow_headers(Any));

    let addr = format!("{host}:{port}");
    tracing::info!("MCP server listening on http://{addr}/mcp");
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}

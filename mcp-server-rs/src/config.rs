use std::path::PathBuf;

#[derive(Clone)]
pub struct Config {
    pub transport: String,
    pub http_host: String,
    pub http_port: u16,
    pub solana_rpc_url: String,
    pub arweave_url: String,
    pub keypair_path: PathBuf,
    pub database_path: PathBuf,
    /// "hash" (default, offline) or "openai" (requires OPENAI_API_KEY)
    pub embed_provider: String,
    pub openai_api_key: String,
    pub openai_embed_model: String,
    /// TurboQuant bit width for compression (2, 3, or 4)
    pub turbo_bits: usize,
}

impl Config {
    pub fn from_env() -> Self {
        let home = dirs_home();
        Self {
            transport: env_or("MCP_TRANSPORT", "http"),
            http_host: env_or("MCP_HTTP_HOST", "0.0.0.0"),
            http_port: env_or("MCP_HTTP_PORT", "3000").parse().unwrap_or(3000),
            solana_rpc_url: env_or("SOLANA_RPC_URL", "http://localhost:8899"),
            arweave_url: env_or("ARWEAVE_URL", "http://localhost:1984"),
            keypair_path: expand_path(&env_or(
                "MNEMONIC_KEYPAIR_PATH",
                &format!("{}/.mnemonic/id.json", home),
            )),
            database_path: expand_path(&env_or(
                "DATABASE_PATH",
                &format!("{}/.mnemonic/attestations.db", home),
            )),
            embed_provider: env_or("EMBED_PROVIDER", "hash"),
            openai_api_key: env_or("OPENAI_API_KEY", ""),
            openai_embed_model: env_or("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
            turbo_bits: env_or("TURBO_BITS", "4").parse().unwrap_or(4),
        }
    }
}

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

fn expand_path(p: &str) -> PathBuf {
    if p.starts_with('~') {
        PathBuf::from(p.replacen('~', &dirs_home(), 1))
    } else {
        PathBuf::from(p)
    }
}

fn dirs_home() -> String {
    std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string())
}

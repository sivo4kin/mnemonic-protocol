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

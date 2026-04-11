use mnemonic_verify::arweave::ArweaveClient;
use mnemonic_verify::solana::SolanaClient;

fn arweave_url() -> String {
    std::env::var("ARWEAVE_URL").unwrap_or_else(|_| "http://localhost:1984".into())
}

fn solana_url() -> String {
    std::env::var("SOLANA_RPC_URL").unwrap_or_else(|_| "http://localhost:8899".into())
}

/// Check that arlocal and solana-test-validator are reachable.
/// If not, prints a skip message and returns None.
pub async fn require_local_nodes() -> Option<(ArweaveClient, SolanaClient)> {
    let arweave = arweave_client();
    let solana = match funded_solana_client().await {
        Some(s) => s,
        None => return None,
    };

    if arweave.health_check().await.is_err() {
        eprintln!("SKIP: arlocal not running at {}", arweave_url());
        return None;
    }

    if solana.health_check().await.is_err() {
        eprintln!("SKIP: solana-test-validator not running at {}", solana_url());
        return None;
    }

    Some((arweave, solana))
}

pub fn arweave_client() -> ArweaveClient {
    ArweaveClient::new(&arweave_url())
}

pub async fn funded_solana_client() -> Option<SolanaClient> {
    let client = SolanaClient::new_with_random_payer(&solana_url());
    match client.airdrop(2_000_000_000).await {
        Ok(_) => Some(client),
        Err(e) => {
            eprintln!("SKIP: solana airdrop failed: {e}");
            None
        }
    }
}

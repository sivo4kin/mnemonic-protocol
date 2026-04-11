use std::path::PathBuf;

use anyhow::Context;
use chrono::Utc;
use clap::{Parser, Subcommand};

use mnemonic_verify::{
    arweave::ArweaveClient,
    embed,
    hash,
    receipt::{AnchorRecord, MemoryPayload, MemoryReceipt, VerificationStatus},
    solana::SolanaClient,
    verify,
};

/// Safely truncate a string to at most `n` characters, appending "..." if truncated.
fn truncate(s: &str, n: usize) -> String {
    if s.len() > n {
        format!("{}...", &s[..n])
    } else {
        s.to_string()
    }
}

#[derive(Parser)]
#[command(name = "mnemonic-verify")]
#[command(about = "Minimal verifiable memory round-trip (local nodes)")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Write memory and return receipt
    Write {
        /// The text to store as a memory
        text: String,
    },
    /// Recall and verify memory
    Recall {
        /// Solana transaction signature from a previous write
        solana_tx_sig: String,
    },
    /// Create a tampered copy for demo/testing
    Tamper {
        /// Solana transaction signature of the original write
        solana_tx_sig: String,
    },
    /// Check local node connectivity
    Status,
}

fn load_env() {
    let _ = dotenvy::dotenv();
}

fn arweave_url() -> String {
    std::env::var("ARWEAVE_URL").unwrap_or_else(|_| "http://localhost:1984".into())
}

fn solana_url() -> String {
    std::env::var("SOLANA_RPC_URL").unwrap_or_else(|_| "http://localhost:8899".into())
}

fn receipts_dir() -> PathBuf {
    PathBuf::from("receipts")
}

async fn setup_solana() -> anyhow::Result<SolanaClient> {
    let client = SolanaClient::new_with_random_payer(&solana_url());
    // Airdrop 2 SOL for transactions
    client.airdrop(2_000_000_000).await.context("airdrop")?;
    Ok(client)
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    load_env();
    let cli = Cli::parse();

    match cli.command {
        Commands::Write { text } => cmd_write(&text).await,
        Commands::Recall { solana_tx_sig } => cmd_recall(&solana_tx_sig).await,
        Commands::Tamper { solana_tx_sig } => cmd_tamper(&solana_tx_sig).await,
        Commands::Status => cmd_status().await,
    }
}

async fn cmd_write(text: &str) -> anyhow::Result<()> {
    let arweave = ArweaveClient::new(&arweave_url());
    let solana = setup_solana().await?;

    // 1. Embed
    let model = embed::init_model()?;
    let embedding = embed::embed_text(&model, text)?;
    let quantized = embed::quantize(&embedding);
    eprintln!(
        "  Embedded  ({}-dim -> {} bytes quantized)",
        quantized.dims,
        quantized.bytes.len()
    );

    // 2. Construct payload (content_hash placeholder)
    let now = Utc::now();
    let mut payload = MemoryPayload {
        text: text.to_string(),
        embedding: quantized,
        content_hash: String::new(),
        written_at: now,
    };

    // 3. Hash (excludes content_hash field)
    let content_hash = hash::hash_payload(&payload);
    payload.content_hash = content_hash.clone();
    eprintln!("  Hashed    {}", truncate(&content_hash, 16));

    // 4. Serialize and write to Arweave
    let payload_json = serde_json::to_string(&payload)?;
    let arweave_tx_id = arweave.write(&payload_json).await?;
    eprintln!("  Written   arweave_tx: {}", truncate(&arweave_tx_id, 20));

    // 5. Mine block on arlocal
    arweave.mine().await?;
    eprintln!("  Mined     block confirmed (arlocal)");

    // 6. Anchor on Solana
    let anchor = AnchorRecord {
        arweave_tx_id: arweave_tx_id.clone(),
        content_hash: content_hash.clone(),
        timestamp_unix: now.timestamp(),
    };
    let solana_tx_sig = solana.write_anchor(&anchor).await?;
    eprintln!("  Anchored  solana_tx: {}", truncate(&solana_tx_sig, 20));

    // 7. Save receipt
    let receipt = MemoryReceipt {
        arweave_tx_id,
        solana_tx_sig: solana_tx_sig.clone(),
        content_hash,
        written_at: now,
    };
    let dir = receipts_dir();
    std::fs::create_dir_all(&dir)?;
    let sig_prefix = if solana_tx_sig.len() >= 16 { &solana_tx_sig[..16] } else { &solana_tx_sig };
    let receipt_path = dir.join(format!("{}.json", sig_prefix));
    std::fs::write(
        &receipt_path,
        serde_json::to_string_pretty(&receipt)?,
    )?;
    eprintln!("\nReceipt saved to: {}", receipt_path.display());

    // Print receipt JSON to stdout
    println!("{}", serde_json::to_string_pretty(&receipt)?);
    Ok(())
}

async fn cmd_recall(solana_tx_sig: &str) -> anyhow::Result<()> {
    let arweave = ArweaveClient::new(&arweave_url());
    let solana = SolanaClient::new_with_random_payer(&solana_url());

    eprintln!("Fetching anchor from Solana...");
    eprintln!("Fetching content from Arweave...");
    eprintln!("Verifying hash...\n");

    let result = verify::recall_and_verify(solana_tx_sig, &solana, &arweave).await?;

    match result.status {
        VerificationStatus::Verified => {
            let text_preview = result
                .payload
                .as_ref()
                .map(|p| truncate(&p.text, 60))
                .unwrap_or_else(|| "<deserialization failed>".into());

            println!("+-------------------------------------------------+");
            println!("|  STATUS:   VERIFIED                             |");
            println!("|  Expected: {:35} |", truncate(&result.expected_hash, 32));
            println!("|  Actual:   {:35} |", truncate(&result.actual_hash, 32));
            println!("|  Text:     {:38} |", format!("\"{}\"", text_preview));
            println!("+-------------------------------------------------+");
        }
        VerificationStatus::Tampered => {
            println!("+-------------------------------------------------+");
            println!("|  STATUS:   TAMPERED                             |");
            println!("|  Expected: {:35} |", truncate(&result.expected_hash, 32));
            println!("|  Actual:   {:35} |", truncate(&result.actual_hash, 32));
            println!("+-------------------------------------------------+");
        }
        VerificationStatus::AnchorNotFound => {
            println!("+-------------------------------------------------+");
            println!("|  STATUS:   ANCHOR NOT FOUND                     |");
            println!("|  Solana transaction not found or has no memo    |");
            println!("+-------------------------------------------------+");
        }
        VerificationStatus::ArweaveNotFound => {
            println!("+-------------------------------------------------+");
            println!("|  STATUS:   ARWEAVE NOT FOUND                    |");
            println!("|  Arweave tx: {:35} |", truncate(&result.arweave_tx_id, 32));
            println!("+-------------------------------------------------+");
        }
    }

    // Also print machine-readable JSON
    println!("\n{}", serde_json::to_string_pretty(&result)?);
    Ok(())
}

async fn cmd_tamper(solana_tx_sig: &str) -> anyhow::Result<()> {
    let arweave = ArweaveClient::new(&arweave_url());
    let solana = setup_solana().await?;

    // 1. Read the original anchor from Solana
    eprintln!("Reading original anchor from Solana...");
    let original_anchor = solana.read_anchor(solana_tx_sig).await?;

    // 2. Read original content from Arweave
    eprintln!("Reading original content from Arweave...");
    let original_bytes = arweave.read(&original_anchor.arweave_tx_id).await?;

    // 3. Corrupt the content (flip bytes)
    let mut corrupted = original_bytes.clone();
    if corrupted.len() > 10 {
        for i in 0..std::cmp::min(10, corrupted.len()) {
            corrupted[i] = corrupted[i].wrapping_add(1);
        }
    } else {
        corrupted.push(b'X');
    }
    eprintln!("  Corrupted {} bytes", corrupted.len());

    // 4. Write corrupted data to new Arweave tx
    let corrupted_str = String::from_utf8_lossy(&corrupted).into_owned();
    let corrupted_tx_id = arweave.write(&corrupted_str).await?;
    arweave.mine().await?;
    eprintln!("  Written corrupted data to arweave_tx: {}", truncate(&corrupted_tx_id, 20));

    // 5. Create new anchor with ORIGINAL hash but CORRUPTED arweave tx
    let tampered_anchor = AnchorRecord {
        arweave_tx_id: corrupted_tx_id,
        content_hash: original_anchor.content_hash.clone(), // original hash
        timestamp_unix: Utc::now().timestamp(),
    };
    let tampered_sig = solana.write_anchor(&tampered_anchor).await?;
    eprintln!("  Mismatched anchor written to Solana: {}", truncate(&tampered_sig, 20));

    eprintln!(
        "\nRun: mnemonic-verify recall {}  to observe tamper detection",
        tampered_sig
    );
    Ok(())
}

async fn cmd_status() -> anyhow::Result<()> {
    let arweave = ArweaveClient::new(&arweave_url());
    let solana_client = SolanaClient::new_with_random_payer(&solana_url());

    // Arweave check
    let ar_status = match arweave.health_check().await {
        Ok(_) => "reachable",
        Err(_) => "UNREACHABLE",
    };
    println!(
        "Arweave (arlocal)    {}  {}",
        arweave_url(),
        ar_status
    );

    // Solana check
    let sol_status = match solana_client.health_check().await {
        Ok(_) => "reachable",
        Err(_) => "UNREACHABLE",
    };
    println!(
        "Solana (local)       {}  {}",
        solana_url(),
        sol_status
    );

    // Balance (best-effort)
    if let Ok(bal) = solana_client.balance_sol().await {
        println!("Payer balance        {:.2} SOL", bal);
    }

    // Embedding model check
    match embed::init_model() {
        Ok(_) => println!("Embedding model      all-MiniLM-L6-v2      cached"),
        Err(e) => println!("Embedding model      ERROR: {}", e),
    };

    Ok(())
}

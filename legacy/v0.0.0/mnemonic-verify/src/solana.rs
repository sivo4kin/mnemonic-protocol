use anyhow::Context;
use solana_client::nonblocking::rpc_client::RpcClient;
use solana_sdk::{
    commitment_config::CommitmentConfig,
    signature::{Keypair, Signature},
    signer::Signer,
    transaction::Transaction,
};
use solana_client::rpc_config::RpcTransactionConfig;
use solana_transaction_status::{
    EncodedTransaction, UiMessage, UiTransactionEncoding,
};
use std::str::FromStr;

use crate::errors::MnemonicError;
use crate::receipt::AnchorRecord;

pub struct SolanaClient {
    pub rpc_client: RpcClient,
    pub payer: Keypair,
}

impl SolanaClient {
    pub fn new(rpc_url: &str, payer: Keypair) -> Self {
        let rpc_client = RpcClient::new_with_commitment(
            rpc_url.to_string(),
            CommitmentConfig::confirmed(),
        );
        Self { rpc_client, payer }
    }

    /// Create a new client with a fresh keypair.
    pub fn new_with_random_payer(rpc_url: &str) -> Self {
        Self::new(rpc_url, Keypair::new())
    }

    /// Write AnchorRecord as SPL Memo transaction.
    ///
    /// 1. Serialize AnchorRecord to compact JSON string
    /// 2. Build transaction with spl_memo::build_memo instruction
    /// 3. Sign with payer keypair
    /// 4. Send + confirm with commitment: Confirmed
    /// 5. Return transaction signature as base58 string
    pub async fn write_anchor(&self, record: &AnchorRecord) -> anyhow::Result<String> {
        let memo_json =
            serde_json::to_string(record).context("serializing AnchorRecord")?;
        let memo_bytes = memo_json.as_bytes();

        // SPL Memo instruction
        let memo_ix =
            spl_memo::build_memo(memo_bytes, &[&self.payer.pubkey()]);

        let recent_blockhash = self
            .rpc_client
            .get_latest_blockhash()
            .await
            .context("get latest blockhash")?;

        let tx = Transaction::new_signed_with_payer(
            &[memo_ix],
            Some(&self.payer.pubkey()),
            &[&self.payer],
            recent_blockhash,
        );

        let sig = self
            .rpc_client
            .send_and_confirm_transaction(&tx)
            .await
            .map_err(|e| MnemonicError::SolanaWrite(e.to_string()))?;

        Ok(sig.to_string())
    }

    /// Read and parse AnchorRecord from a transaction signature.
    ///
    /// 1. Fetch transaction by signature
    /// 2. Extract the Memo instruction data from the message
    /// 3. Deserialize JSON → AnchorRecord
    pub async fn read_anchor(&self, tx_sig: &str) -> anyhow::Result<AnchorRecord> {
        let sig = Signature::from_str(tx_sig)
            .map_err(|e| MnemonicError::AnchorNotFound(format!("invalid sig: {e}")))?;

        let config = RpcTransactionConfig {
            encoding: Some(UiTransactionEncoding::Json),
            commitment: Some(CommitmentConfig::confirmed()),
            max_supported_transaction_version: Some(0),
        };

        let tx_result = self
            .rpc_client
            .get_transaction_with_config(&sig, config)
            .await
            .map_err(|e| MnemonicError::AnchorNotFound(e.to_string()))?;

        // Extract memo data from the transaction
        let memo_data = extract_memo_from_transaction(&tx_result.transaction.transaction)?;

        let anchor: AnchorRecord = serde_json::from_str(&memo_data)
            .map_err(|e| MnemonicError::DeserializeError(e.to_string()))?;

        Ok(anchor)
    }

    /// Airdrop SOL to payer (local validator only).
    pub async fn airdrop(&self, lamports: u64) -> anyhow::Result<()> {
        let sig = self
            .rpc_client
            .request_airdrop(&self.payer.pubkey(), lamports)
            .await
            .context("airdrop request failed")?;

        // Wait for airdrop confirmation
        loop {
            let confirmed = self
                .rpc_client
                .confirm_transaction(&sig)
                .await
                .unwrap_or(false);
            if confirmed {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        }

        Ok(())
    }

    /// Health check: verify RPC is reachable.
    pub async fn health_check(&self) -> anyhow::Result<()> {
        self.rpc_client
            .get_health()
            .await
            .map_err(|e| {
                MnemonicError::NodeUnreachable {
                    url: self.rpc_client.url(),
                    reason: e.to_string(),
                }
            })?;
        Ok(())
    }

    /// Get payer balance in SOL.
    pub async fn balance_sol(&self) -> anyhow::Result<f64> {
        let lamports = self
            .rpc_client
            .get_balance(&self.payer.pubkey())
            .await
            .context("get balance")?;
        Ok(lamports as f64 / 1_000_000_000.0)
    }
}

/// Extract memo text from an encoded transaction.
///
/// Looks for the SPL Memo program instruction and decodes its data.
fn extract_memo_from_transaction(
    encoded_tx: &EncodedTransaction,
) -> anyhow::Result<String> {
    let memo_program_id = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr";

    match encoded_tx {
        EncodedTransaction::Json(ui_tx) => {
            match &ui_tx.message {
                UiMessage::Raw(raw_msg) => {
                    // Compiled instructions with account keys
                    for inst in &raw_msg.instructions {
                        let program_id =
                            &raw_msg.account_keys[inst.program_id_index as usize];
                        if program_id == memo_program_id {
                            let data_bytes = bs58::decode(&inst.data)
                                .into_vec()
                                .context("decoding memo instruction data")?;
                            return String::from_utf8(data_bytes)
                                .context("memo data is not valid UTF-8");
                        }
                    }
                }
                UiMessage::Parsed(parsed_msg) => {
                    // Try parsed instructions
                    for inst in &parsed_msg.instructions {
                        match inst {
                            solana_transaction_status::UiInstruction::Parsed(
                                ui_parsed,
                            ) => {
                                match ui_parsed {
                                    solana_transaction_status::UiParsedInstruction::PartiallyDecoded(partial) => {
                                        if partial.program_id == memo_program_id {
                                            let data_bytes = bs58::decode(&partial.data)
                                                .into_vec()
                                                .context("decoding memo data")?;
                                            return String::from_utf8(data_bytes)
                                                .context("memo data is not valid UTF-8");
                                        }
                                    }
                                    solana_transaction_status::UiParsedInstruction::Parsed(parsed) => {
                                        if parsed.program_id == memo_program_id {
                                            // The memo text is in the `parsed` field as a string
                                            if let Some(s) = parsed.parsed.as_str() {
                                                return Ok(s.to_string());
                                            }
                                            return Ok(parsed.parsed.to_string());
                                        }
                                    }
                                }
                            }
                            solana_transaction_status::UiInstruction::Compiled(comp) => {
                                let program_id =
                                    &parsed_msg.account_keys[comp.program_id_index as usize].pubkey;
                                if program_id == memo_program_id {
                                    let data_bytes = bs58::decode(&comp.data)
                                        .into_vec()
                                        .context("decoding memo data")?;
                                    return String::from_utf8(data_bytes)
                                        .context("memo data not valid UTF-8");
                                }
                            }
                        }
                    }
                }
            }
        }
        EncodedTransaction::LegacyBinary(raw) | EncodedTransaction::Binary(raw, _) => {
            // Decode the raw transaction and extract memo
            let tx_bytes = bs58::decode(raw)
                .into_vec()
                .context("decoding binary tx")?;
            let tx: Transaction = bincode::deserialize(&tx_bytes)
                .context("deserializing binary transaction")?;
            for inst in &tx.message.instructions {
                let program_id = tx.message.account_keys[inst.program_id_index as usize];
                if program_id.to_string() == memo_program_id {
                    return String::from_utf8(inst.data.clone())
                        .context("memo data not valid UTF-8");
                }
            }
        }
        EncodedTransaction::Accounts(_) => {
            return Err(anyhow::anyhow!(
                "Accounts-only encoding not supported for memo extraction"
            ));
        }
    }

    Err(MnemonicError::AnchorNotFound("no memo instruction found in transaction".into()).into())
}

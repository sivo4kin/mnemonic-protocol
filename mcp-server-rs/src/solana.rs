//! Solana client — SPL Memo write/read via JSON-RPC.

use anyhow::Context;
use solana_sdk::{
    instruction::{AccountMeta, Instruction},
    message::Message,
    pubkey::Pubkey,
    signature::{Keypair, Signer},
    transaction::Transaction,
    hash::Hash,
};
use std::str::FromStr;

const MEMO_PROGRAM_ID: &str = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr";

pub struct SolanaClient {
    rpc_url: String,
    client: reqwest::Client,
}

impl SolanaClient {
    pub fn new(rpc_url: &str) -> Self {
        Self {
            rpc_url: rpc_url.to_string(),
            client: reqwest::Client::new(),
        }
    }

    async fn rpc(&self, method: &str, params: serde_json::Value) -> anyhow::Result<serde_json::Value> {
        let body = serde_json::json!({
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params
        });
        let resp = self.client.post(&self.rpc_url).json(&body).send().await?;
        let result: serde_json::Value = resp.json().await?;
        if let Some(err) = result.get("error") {
            anyhow::bail!("Solana RPC error: {err}");
        }
        Ok(result["result"].clone())
    }

    pub async fn write_memo(&self, keypair: &Keypair, memo: &str) -> anyhow::Result<String> {
        let memo_pid = Pubkey::from_str(MEMO_PROGRAM_ID)?;
        let ix = Instruction {
            program_id: memo_pid,
            accounts: vec![AccountMeta::new(keypair.pubkey(), true)],
            data: memo.as_bytes().to_vec(),
        };

        let blockhash_result = self.rpc("getLatestBlockhash",
            serde_json::json!([{"commitment": "confirmed"}])).await?;
        let blockhash_str = blockhash_result["value"]["blockhash"].as_str()
            .context("no blockhash")?;
        let blockhash = Hash::from_str(blockhash_str)?;

        let msg = Message::new_with_blockhash(&[ix], Some(&keypair.pubkey()), &blockhash);
        let mut tx = Transaction::new_unsigned(msg);
        tx.sign(&[keypair], blockhash);

        let tx_bytes = bincode::serialize(&tx)?;
        let tx_b64 = base64::Engine::encode(&base64::engine::general_purpose::STANDARD, &tx_bytes);

        let result = self.rpc("sendTransaction",
            serde_json::json!([tx_b64, {"encoding": "base64"}])).await?;
        let sig = result.as_str().context("no tx signature")?.to_string();

        self.confirm_tx(&sig).await?;
        Ok(sig)
    }

    pub async fn read_memo(&self, tx_sig: &str) -> anyhow::Result<Option<serde_json::Value>> {
        let result = self.rpc("getTransaction", serde_json::json!([
            tx_sig,
            {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}
        ])).await?;

        if result.is_null() {
            return Ok(None);
        }

        // Extract memo from log messages
        if let Some(logs) = result["meta"]["logMessages"].as_array() {
            for log in logs {
                if let Some(s) = log.as_str() {
                    if s.contains("Memo") && s.contains("len") {
                        if let (Some(start), Some(end)) = (s.find('"'), s.rfind('"')) {
                            if end > start {
                                let memo_str = &s[start + 1..end];
                                if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(memo_str) {
                                    return Ok(Some(parsed));
                                }
                                return Ok(Some(serde_json::json!({"raw": memo_str})));
                            }
                        }
                    }
                }
            }
        }
        Ok(None)
    }

    pub async fn airdrop(&self, pubkey: &Pubkey, lamports: u64) -> anyhow::Result<String> {
        let result = self.rpc("requestAirdrop",
            serde_json::json!([pubkey.to_string(), lamports])).await?;
        let sig = result.as_str().context("no airdrop sig")?.to_string();
        self.confirm_tx(&sig).await?;
        Ok(sig)
    }

    pub async fn health_check(&self) -> bool {
        self.rpc("getHealth", serde_json::json!([])).await.is_ok()
    }

    async fn confirm_tx(&self, sig: &str) -> anyhow::Result<()> {
        for _ in 0..30 {
            let result = self.rpc("getSignatureStatuses",
                serde_json::json!([[sig]])).await?;
            if let Some(statuses) = result["value"].as_array() {
                if let Some(status) = statuses.first().and_then(|s| s.as_object()) {
                    if let Some(conf) = status.get("confirmationStatus").and_then(|c| c.as_str()) {
                        if conf == "confirmed" || conf == "finalized" {
                            if status.get("err").map_or(true, |e| e.is_null()) {
                                return Ok(());
                            }
                            anyhow::bail!("tx failed: {:?}", status.get("err"));
                        }
                    }
                }
            }
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        }
        anyhow::bail!("tx {sig} not confirmed")
    }
}

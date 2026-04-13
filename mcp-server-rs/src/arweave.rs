//! Arweave client — arlocal (local) + Irys (production) via HTTP.

use anyhow::Context;
use base64::Engine;
use sha2::{Sha256, Digest};

pub struct ArweaveClient {
    base_url: String,
    client: reqwest::Client,
}

impl ArweaveClient {
    pub fn new(base_url: &str) -> Self {
        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            client: reqwest::Client::new(),
        }
    }

    pub async fn write(&self, payload: &str) -> anyhow::Result<String> {
        let data = payload.as_bytes();
        if self.is_local() {
            self.write_arlocal(data).await
        } else {
            self.write_irys(data).await
        }
    }

    pub async fn read(&self, tx_id: &str) -> anyhow::Result<Vec<u8>> {
        let url = format!("{}/{tx_id}", self.base_url);
        let resp = self.client.get(&url).send().await.context("arweave read")?;
        if resp.status() == reqwest::StatusCode::NOT_FOUND {
            anyhow::bail!("arweave tx not found: {tx_id}");
        }
        resp.error_for_status_ref().context("arweave read status")?;
        Ok(resp.bytes().await?.to_vec())
    }

    pub async fn mine(&self) -> anyhow::Result<()> {
        if self.is_local() {
            self.client.get(&format!("{}/mine", self.base_url)).send().await?;
        }
        Ok(())
    }

    pub async fn health_check(&self) -> bool {
        self.client.get(&format!("{}/info", self.base_url))
            .send().await
            .map(|r| r.status().is_success())
            .unwrap_or(false)
    }

    fn is_local(&self) -> bool {
        self.base_url.contains("localhost") || self.base_url.contains("127.0.0.1")
    }

    async fn write_arlocal(&self, data: &[u8]) -> anyhow::Result<String> {
        let b64url = base64::engine::general_purpose::URL_SAFE_NO_PAD;
        let mut sig_bytes = vec![0u8; 512];
        getrandom(&mut sig_bytes);
        let id_hash = Sha256::digest(&sig_bytes);
        let id = b64url.encode(id_hash);

        let mut owner = vec![0u8; 256];
        getrandom(&mut owner);

        let data_root = Sha256::digest(data);

        let tx = serde_json::json!({
            "format": 2,
            "id": id,
            "last_tx": "",
            "owner": b64url.encode(&owner),
            "tags": [
                {"name": b64url.encode(b"Content-Type"), "value": b64url.encode(b"application/json")},
                {"name": b64url.encode(b"App-Name"), "value": b64url.encode(b"mnemonic-protocol")},
            ],
            "target": "",
            "quantity": "0",
            "data_size": data.len().to_string(),
            "data": b64url.encode(data),
            "data_root": b64url.encode(data_root),
            "reward": "0",
            "signature": b64url.encode(&sig_bytes),
        });

        let resp = self.client.post(&format!("{}/tx", self.base_url))
            .json(&tx).send().await.context("arweave POST")?;
        if !resp.status().is_success() {
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("arweave write failed: {body}");
        }
        Ok(id)
    }

    async fn write_irys(&self, data: &[u8]) -> anyhow::Result<String> {
        let resp = self.client.post("https://uploader.irys.xyz/upload")
            .header("Content-Type", "application/octet-stream")
            .header("x-network", "arweave")
            .body(data.to_vec())
            .send().await.context("irys upload")?;
        if !resp.status().is_success() {
            anyhow::bail!("irys upload failed: {}", resp.status());
        }
        let result: serde_json::Value = resp.json().await?;
        result["id"].as_str().map(|s| s.to_string())
            .context("no id in irys response")
    }
}

fn getrandom(buf: &mut [u8]) {
    use std::time::{SystemTime, UNIX_EPOCH};
    // Simple PRNG for arlocal dummy fields (not crypto-sensitive)
    let seed = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos() as u64;
    let mut state = seed;
    for byte in buf.iter_mut() {
        state = state.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        *byte = (state >> 33) as u8;
    }
}

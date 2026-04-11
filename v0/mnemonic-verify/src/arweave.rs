use anyhow::Context;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use rand::Rng;
use sha2::{Digest, Sha256};

use crate::errors::MnemonicError;

pub struct ArweaveClient {
    base_url: String,
    client: reqwest::Client,
}

/// Arweave transaction structure for arlocal submissions.
#[derive(serde::Serialize)]
struct ArweaveTx {
    format: u32,
    id: String,
    last_tx: String,
    owner: String,
    tags: Vec<ArweaveTag>,
    target: String,
    quantity: String,
    data_size: String,
    data: String,
    data_root: String,
    reward: String,
    signature: String,
}

#[derive(serde::Serialize)]
struct ArweaveTag {
    name: String,
    value: String,
}

impl ArweaveClient {
    pub fn new(base_url: &str) -> Self {
        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            client: reqwest::Client::new(),
        }
    }

    /// POST data to arlocal. Returns the Arweave transaction ID.
    ///
    /// Constructs a minimal Arweave format-2 transaction with dummy
    /// cryptographic fields (arlocal does not validate signatures).
    pub async fn write(&self, payload_json: &str) -> anyhow::Result<String> {
        let data_bytes = payload_json.as_bytes();
        let mut rng = rand::thread_rng();

        // Generate dummy signature (512 bytes) — arlocal doesn't validate
        let sig_bytes: Vec<u8> = (0..512).map(|_| rng.gen()).collect();
        let id_hash = Sha256::digest(&sig_bytes);
        let id = URL_SAFE_NO_PAD.encode(id_hash);
        let signature = URL_SAFE_NO_PAD.encode(&sig_bytes);

        // Dummy owner (256 bytes)
        let owner_bytes: Vec<u8> = (0..256).map(|_| rng.gen()).collect();
        let owner = URL_SAFE_NO_PAD.encode(&owner_bytes);

        // Data encoding
        let data_b64 = URL_SAFE_NO_PAD.encode(data_bytes);
        let data_root_hash = Sha256::digest(data_bytes);
        let data_root = URL_SAFE_NO_PAD.encode(data_root_hash);

        // Tags
        let tags = vec![
            ArweaveTag {
                name: URL_SAFE_NO_PAD.encode(b"Content-Type"),
                value: URL_SAFE_NO_PAD.encode(b"application/json"),
            },
            ArweaveTag {
                name: URL_SAFE_NO_PAD.encode(b"App-Name"),
                value: URL_SAFE_NO_PAD.encode(b"mnemonic-verify"),
            },
            ArweaveTag {
                name: URL_SAFE_NO_PAD.encode(b"Version"),
                value: URL_SAFE_NO_PAD.encode(b"0.1.0"),
            },
        ];

        let tx = ArweaveTx {
            format: 2,
            id: id.clone(),
            last_tx: String::new(),
            owner,
            tags,
            target: String::new(),
            quantity: "0".into(),
            data_size: data_bytes.len().to_string(),
            data: data_b64,
            data_root,
            reward: "0".into(),
            signature,
        };

        let url = format!("{}/tx", self.base_url);
        let resp = self
            .client
            .post(&url)
            .json(&tx)
            .send()
            .await
            .context("arweave POST /tx failed")?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(MnemonicError::ArweaveWrite(format!(
                "HTTP {status}: {body}"
            ))
            .into());
        }

        Ok(id)
    }

    /// GET /<tx_id> from arlocal. Returns raw bytes of the stored content.
    pub async fn read(&self, tx_id: &str) -> anyhow::Result<Vec<u8>> {
        let url = format!("{}/{}", self.base_url, tx_id);
        let resp = self
            .client
            .get(&url)
            .send()
            .await
            .context("arweave GET failed")?;

        if resp.status() == reqwest::StatusCode::NOT_FOUND {
            return Err(MnemonicError::ArweaveNotFound(tx_id.to_string()).into());
        }
        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("arweave read HTTP {status}: {body}"));
        }

        let bytes = resp.bytes().await.context("reading arweave body")?;
        Ok(bytes.to_vec())
    }

    /// Mine pending transactions (arlocal only).
    ///
    /// Transactions are not readable on arlocal until a block is mined.
    /// POST /mine commits pending transactions to a new block.
    pub async fn mine(&self) -> anyhow::Result<()> {
        let url = format!("{}/mine", self.base_url);
        let resp = self
            .client
            .get(&url)
            .send()
            .await
            .context("arweave POST /mine failed")?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("arweave mine HTTP {status}: {body}"));
        }
        Ok(())
    }

    /// Health check: GET /info — returns Ok if node is reachable.
    pub async fn health_check(&self) -> anyhow::Result<()> {
        let url = format!("{}/info", self.base_url);
        self.client
            .get(&url)
            .send()
            .await
            .map_err(|e| {
                MnemonicError::NodeUnreachable {
                    url: url.clone(),
                    reason: e.to_string(),
                }
            })?
            .error_for_status()
            .map_err(|e| MnemonicError::NodeUnreachable {
                url,
                reason: e.to_string(),
            })?;
        Ok(())
    }
}

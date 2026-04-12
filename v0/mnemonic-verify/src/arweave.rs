use anyhow::Context;
use arweave_rs::{
    crypto::base64::Base64,
    transaction::tags::{FromUtf8Strs, Tag},
    Arweave,
};
use reqwest::Url;
use std::path::PathBuf;

use crate::errors::MnemonicError;

pub struct ArweaveClient {
    base_url: String,
    jwk_path: PathBuf,
    client: reqwest::Client,
}

impl ArweaveClient {
    pub fn new(base_url: &str) -> Self {
        let jwk_path = std::env::var("ARWEAVE_JWK_PATH")
            .unwrap_or_else(|_| "keys/arlocal-test-wallet.jwk".to_string());
        Self {
            base_url: base_url.trim_end_matches('/').to_string(),
            jwk_path: PathBuf::from(jwk_path),
            client: reqwest::Client::new(),
        }
    }

    /// POST data to arlocal. Returns the Arweave transaction ID.
    ///
    /// Builds and signs a valid Arweave v2 transaction using a JWK wallet.
    /// This is accepted by strict arlocal versions that reject dummy tx fields.
    pub async fn write(&self, payload_json: &str) -> anyhow::Result<String> {
        let data_bytes = payload_json.as_bytes();
        let base_url = Url::parse(&self.base_url).context("invalid ARWEAVE_URL")?;
        let arweave = Arweave::from_keypair_path(self.jwk_path.clone(), base_url)
            .context("initializing arweave signer from ARWEAVE_JWK_PATH")?;
        let wallet_address = arweave
            .get_wallet_address()
            .context("reading wallet address from JWK")?;

        let tags = vec![
            Tag::<Base64>::from_utf8_strs("Content-Type", "application/json")
                .context("creating Content-Type tag")?,
            Tag::<Base64>::from_utf8_strs("App-Name", "mnemonic-verify")
                .context("creating App-Name tag")?,
            Tag::<Base64>::from_utf8_strs("Version", "0.1.0")
                .context("creating Version tag")?,
        ];

        let tx = arweave
            .create_transaction(Base64::empty(), tags, data_bytes.to_vec(), 0, 0, false)
            .await
            .context("creating arweave transaction")?;
        let signed_tx = arweave
            .sign_transaction(tx)
            .context("signing arweave transaction")?;

        let (status, body) = self.post_signed_tx(&signed_tx).await?;
        if status.is_success() {
            return Ok(signed_tx.id.to_string());
        }

        // arlocal can reject with 410 if the test wallet has no balance yet.
        // Top up locally and retry once.
        if status == reqwest::StatusCode::GONE
            && body.contains("enough tokens")
            && self.is_local_gateway()
        {
            self.mint_local_wallet(&wallet_address, "1000000000000000")
                .await
                .context("funding local arweave wallet")?;

            let (retry_status, retry_body) = self.post_signed_tx(&signed_tx).await?;
            if retry_status.is_success() {
                return Ok(signed_tx.id.to_string());
            }

            return Err(MnemonicError::ArweaveWrite(format!(
                "HTTP {retry_status}: {retry_body}"
            ))
            .into());
        }

        Err(MnemonicError::ArweaveWrite(format!("HTTP {status}: {body}")).into())
    }

    async fn post_signed_tx(
        &self,
        signed_tx: &arweave_rs::transaction::Tx,
    ) -> anyhow::Result<(reqwest::StatusCode, String)> {
        let url = format!("{}/tx", self.base_url);
        let resp = self
            .client
            .post(&url)
            .json(signed_tx)
            .send()
            .await
            .context("arweave POST /tx failed")?;
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        Ok((status, body))
    }

    async fn mint_local_wallet(&self, address: &str, balance: &str) -> anyhow::Result<()> {
        let url = format!("{}/mint/{address}/{balance}", self.base_url);
        let resp = self
            .client
            .get(&url)
            .send()
            .await
            .context("arweave GET /mint/:address/:balance failed")?;
        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "arweave wallet fund HTTP {status}: {body}"
            ));
        }
        Ok(())
    }

    fn is_local_gateway(&self) -> bool {
        match Url::parse(&self.base_url) {
            Ok(url) => matches!(url.host_str(), Some("localhost" | "127.0.0.1")),
            Err(_) => false,
        }
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

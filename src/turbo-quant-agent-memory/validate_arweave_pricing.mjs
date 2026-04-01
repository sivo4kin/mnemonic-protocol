/**
 * Arweave Pricing Validation — Option A (API price query, zero cost)
 *
 * Queries Irys (formerly Bundlr) price API and CoinGecko AR/USD rate
 * to derive current $/GB for Arweave permanent storage.
 *
 * Usage: node validate_arweave_pricing.mjs
 *
 * Future validation options (not implemented here):
 *   Option B: Real micro-upload (10KB–1MB via commit.mjs, ~$0.001)
 *   Option C: Upload actual snapshot files (data/snapshot_*.bin, ~$0.05–0.40)
 * See ARWEAVE_PRICING_VALIDATION.md for full plan.
 */

const IRYS_PRICE_URL = "https://node1.irys.xyz/price";
const COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids=arweave&vs_currencies=usd";
const WINSTON_PER_AR = 1e12;

const SIZES = [
  { label: "10 KB",  bytes: 10_000 },
  { label: "100 KB", bytes: 100_000 },
  { label: "1 MB",   bytes: 1_000_000 },
  { label: "10 MB",  bytes: 10_000_000 },
  { label: "100 MB", bytes: 100_000_000 },
  { label: "1 GB",   bytes: 1_000_000_000 },
];

// Typical Mnemonic snapshot sizes (from measured data)
const SNAPSHOTS = [
  { label: "1k memories (8-bit, 384-dim)",   bytes: 2_000_000 },
  { label: "1k memories (8-bit, 1536-dim)",  bytes: 8_000_000 },
  { label: "10k memories (8-bit, 384-dim)",  bytes: 15_000_000 },
  { label: "10k memories (8-bit, 1536-dim)", bytes: 100_000_000 },
];

async function getIrysPrice(bytes) {
  const resp = await fetch(`${IRYS_PRICE_URL}/${bytes}`);
  if (!resp.ok) throw new Error(`Irys price API failed: ${resp.status}`);
  const text = await resp.text();
  return BigInt(text.trim());
}

async function getArUsdPrice() {
  const resp = await fetch(COINGECKO_URL);
  if (!resp.ok) throw new Error(`CoinGecko API failed: ${resp.status}`);
  const data = await resp.json();
  return data.arweave.usd;
}

function winstonToUsd(winston, arPrice) {
  return (Number(winston) / WINSTON_PER_AR) * arPrice;
}

async function main() {
  console.log("Arweave Pricing Validation (via Irys bundler)\n");
  console.log("Fetching AR/USD price...");
  const arPrice = await getArUsdPrice();
  console.log(`AR/USD: $${arPrice}\n`);

  // General price table
  console.log("=== General Pricing ===\n");
  console.log("Size        | Winston          | AR           | USD         | $/GB");
  console.log("------------|------------------|--------------|-------------|--------");

  for (const { label, bytes } of SIZES) {
    const winston = await getIrysPrice(bytes);
    const ar = Number(winston) / WINSTON_PER_AR;
    const usd = winstonToUsd(winston, arPrice);
    const perGb = usd * (1_000_000_000 / bytes);
    console.log(
      `${label.padEnd(12)}| ${String(winston).padEnd(17)}| ${ar.toFixed(6).padEnd(13)}| $${usd.toFixed(6).padEnd(10)}| $${perGb.toFixed(2)}/GB`
    );
  }

  // Snapshot-specific pricing
  console.log("\n=== Mnemonic Snapshot Pricing ===\n");
  console.log("Scenario                          | Size     | Cost/snapshot | Cost/day | Cost/month");
  console.log("----------------------------------|----------|--------------|----------|----------");

  for (const { label, bytes } of SNAPSHOTS) {
    const winston = await getIrysPrice(bytes);
    const usd = winstonToUsd(winston, arPrice);
    const sizeLabel = bytes >= 1_000_000
      ? `${(bytes / 1_000_000).toFixed(0)} MB`
      : `${(bytes / 1_000).toFixed(0)} KB`;
    console.log(
      `${label.padEnd(34)}| ${sizeLabel.padEnd(9)}| $${usd.toFixed(4).padEnd(11)}| $${usd.toFixed(4).padEnd(7)}| $${(usd * 30).toFixed(2)}`
    );
  }

  // Compare against whitepaper claims
  const gbWinston = await getIrysPrice(1_000_000_000);
  const gbUsd = winstonToUsd(gbWinston, arPrice);

  console.log("\n=== Whitepaper Claim Validation ===\n");
  console.log(`Whitepaper v0.1 claimed:  ~$5.00/GB`);
  console.log(`Whitepaper v0.2 claimed:  ~$5.00/GB (carried over)`);
  console.log(`Measured (Irys bundler):  $${gbUsd.toFixed(2)}/GB`);
  console.log(`AR/USD at measurement:    $${arPrice}`);
  console.log(`Ratio (measured/claimed): ${(gbUsd / 5.0).toFixed(1)}x`);
  console.log(`\nVerdict: ${gbUsd > 10 ? "WHITEPAPER COST IS UNDERSTATED — must fix" : gbUsd > 7 ? "WHITEPAPER COST IS SOMEWHAT UNDERSTATED" : "WHITEPAPER COST IS APPROXIMATELY CORRECT"}`);

  // Output machine-readable JSON
  const result = {
    timestamp: new Date().toISOString(),
    ar_usd: arPrice,
    irys_price_per_gb_winston: String(gbWinston),
    irys_price_per_gb_ar: Number(gbWinston) / WINSTON_PER_AR,
    irys_price_per_gb_usd: gbUsd,
    whitepaper_claimed_per_gb_usd: 5.0,
    ratio: gbUsd / 5.0,
    snapshot_costs: {},
  };
  for (const { label, bytes } of SNAPSHOTS) {
    const w = await getIrysPrice(bytes);
    result.snapshot_costs[label] = {
      bytes,
      winston: String(w),
      usd: winstonToUsd(w, arPrice),
    };
  }

  const outPath = new URL("./arweave_pricing_validation.json", import.meta.url).pathname;
  const { writeFileSync } = await import("fs");
  writeFileSync(outPath, JSON.stringify(result, null, 2));
  console.log(`\nResults saved to: ${outPath}`);
}

main().catch(err => {
  console.error("Validation failed:", err.message);
  process.exit(1);
});

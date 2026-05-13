/**
 * Bootstrap Polymarket CLOB API credentials from a Polygon EOA private key.
 *
 * The CLOB API requires three credentials: key, secret, passphrase. These
 * are derived from the funder wallet's signature over a standard
 * authentication challenge. `@polymarket/clob-client-v2` exposes
 * `createOrDeriveApiKey()` which is idempotent — if a key already exists
 * for this wallet, it returns the existing one; otherwise it creates a
 * fresh one. Both paths require only an off-chain signature; no on-chain
 * transaction, no USDC spent.
 *
 * Usage
 * =====
 *
 *     POLY_FUNDER_SECRET=0x<private_key> \
 *       pnpm --filter=prism-polymarket-gateway exec \
 *         tsx scripts/bootstrap-clob-creds.ts
 *
 * Prints the three credentials in a format ready to paste into Railway.
 * **Do NOT commit the output anywhere.**
 *
 * Prerequisites
 * =============
 *
 * 1. A Polygon EOA private key (the wallet you intend to use as
 *    POLY_FUNDER_SECRET). 0x-prefixed hex, 32 bytes.
 * 2. The wallet must already be KYC'd on polymarket.com and have made
 *    at least one deposit to its Polymarket proxy. Otherwise the auth
 *    call returns a 403 with "user not registered".
 * 3. Locale during KYC must not be in Polymarket's restricted
 *    jurisdictions (Estonia is allowed per AGENTS.md hard rule #10).
 *
 * What this does NOT do
 * =====================
 *
 * - No on-chain transaction. Only signs an off-chain message.
 * - No USDC or gas cost. Pure auth handshake.
 * - Does NOT modify any Railway env vars — prints to stdout so you can
 *   review + paste manually.
 */
import { ClobClient, Chain } from "@polymarket/clob-client-v2";
import { createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { polygon } from "viem/chains";

const CLOB_HOST = process.env.POLY_CLOB_HOST ?? "https://clob.polymarket.com";
const CHAIN_ID = Chain.POLYGON;

async function main() {
  const pk = process.env.POLY_FUNDER_SECRET;
  if (!pk || !pk.startsWith("0x") || pk.length !== 66) {
    console.error(
      "FATAL: POLY_FUNDER_SECRET must be a 0x-prefixed 32-byte hex string."
    );
    console.error(
      "Got:",
      pk ? `${pk.slice(0, 6)}…${pk.slice(-4)} (len ${pk.length})` : "(unset)"
    );
    process.exit(1);
  }

  const account = privateKeyToAccount(pk as `0x${string}`);
  const signer = createWalletClient({
    account,
    chain: polygon,
    transport: http(),
  });

  console.log("");
  console.log("┌─────────────────────────────────────────────────────────────┐");
  console.log("│ Polymarket CLOB API key bootstrap                            │");
  console.log("├─────────────────────────────────────────────────────────────┤");
  console.log(`│ CLOB host:    ${CLOB_HOST}`);
  console.log(`│ Chain:        Polygon (${CHAIN_ID})`);
  console.log(`│ Funder addr:  ${account.address}`);
  console.log("└─────────────────────────────────────────────────────────────┘");
  console.log("");

  // ClobClient constructor in v2 takes a config object.
  // For credential bootstrapping we don't pass `creds` (we're trying to
  // generate them). The signer + chain + host are enough.
  const client = new ClobClient({
    host: CLOB_HOST,
    chain: CHAIN_ID,
    signer: signer as unknown as ClobClient["signer"],
    funderAddress: account.address,
    throwOnError: true,
  });

  console.log("→ Calling createOrDeriveApiKey() …");
  let creds;
  try {
    creds = await client.createOrDeriveApiKey();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("");
    console.error("✗ createOrDeriveApiKey failed.");
    console.error(`  Underlying: ${msg}`);
    console.error("");
    if (
      msg.includes("403") ||
      msg.toLowerCase().includes("not register") ||
      msg.toLowerCase().includes("unauthorized")
    ) {
      console.error("  This wallet likely hasn't completed Polymarket onboarding yet.");
      console.error("  Steps to fix:");
      console.error("    1. Go to https://polymarket.com");
      console.error(`    2. Connect this wallet (${account.address}).`);
      console.error(
        "    3. Complete KYC + at least one deposit (any amount of USDC on Polygon)."
      );
      console.error("    4. Re-run this script.");
    }
    process.exit(2);
  }

  if (!creds.key || !creds.secret || !creds.passphrase) {
    console.error("✗ CLOB returned an incomplete credentials object:", creds);
    process.exit(3);
  }

  console.log("");
  console.log(
    "✓ Credentials derived. Paste these into Railway → prism-polymarket-gateway → Variables:"
  );
  console.log("");
  console.log(`POLY_CLOB_API_KEY=${creds.key}`);
  console.log(`POLY_CLOB_SECRET=${creds.secret}`);
  console.log(`POLY_CLOB_PASSPHRASE=${creds.passphrase}`);
  console.log(`POLY_FUNDER_ADDRESS=${account.address}`);
  console.log("");
  console.log("Plus the funder secret you already have:");
  console.log("");
  console.log("  POLY_FUNDER_SECRET=<the 0x… private key you passed in>");
  console.log("");
  console.log("Then flip the trade mode:");
  console.log("");
  console.log(
    "  railway variables --set PRISM_TRADE_MODE=live --service prism-trader"
  );
  console.log(
    "  railway variables --set PRISM_TRADE_MODE=live --service prism-polymarket-gateway"
  );
  console.log("");
  console.log("Both services will redeploy automatically.");
}

main().catch((err) => {
  console.error("Unhandled error:", err);
  process.exit(99);
});

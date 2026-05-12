/** Thin wrapper around @polymarket/clob-client-v2.

Provides a lazy singleton ClobClient initialized with a viem WalletClient
funded by POLY_FUNDER_SECRET. Exposes:

- `submitLiveOrder(params)` — sign + post a real CLOB order with builderCode
- `fetchBuilderTrades(builderCode)` — list trades attributed to a builderCode

This module is the only place that touches the real Polymarket V2 SDK so it
can be mocked in tests via `vi.mock("../src/clob.js", ...)`.
*/

import {
  ApiKeyCreds,
  ClobClient,
  OrderType,
  Side,
} from "@polymarket/clob-client-v2";
import type { BuilderTrade } from "@polymarket/clob-client-v2";
import pino from "pino";
import { createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import type { Account, Chain, WalletClient } from "viem";

import { getEnv } from "./env.js";
import type { TradeSide } from "./trade.js";

const logger = pino({ name: "prism.clob" });

/** Live order parameters. The market price is resolved by the CLOB client. */
export interface LiveOrderParams {
  tokenId: string;
  marketId: string;
  side: TradeSide;
  /** Notional size in USDC for BUY; share count for SELL (V2 SDK semantics). */
  sizeUsdc: number;
  /** Limit price (0 < price < 1). Default 0.5 means mid. */
  price: number;
  builderCode: string;
}

/** Response from the V2 SDK's createAndPostOrder (lightly typed). */
export interface LiveOrderResponse {
  success: boolean;
  orderID: string;
  status: string;
  errorMsg?: string;
  transactionsHashes?: string[];
}

let _client: ClobClient | null = null;

/** Build a viem WalletClient from POLY_FUNDER_SECRET on the configured chain. */
function buildSigner(secret: string, chainId: number): WalletClient {
  if (!secret.startsWith("0x")) {
    throw new Error(
      "POLY_FUNDER_SECRET must be a 0x-prefixed hex string (account secret for EIP-712 signing)",
    );
  }
  const account: Account = privateKeyToAccount(secret as `0x${string}`);
  const chain: Chain = {
    id: chainId,
    name: chainId === 137 ? "Polygon" : `Chain-${chainId}`,
    nativeCurrency: { name: "MATIC", symbol: "MATIC", decimals: 18 },
    rpcUrls: { default: { http: ["https://polygon-rpc.com"] } },
  };
  return createWalletClient({ account, chain, transport: http() });
}

/** Lazily create the singleton ClobClient. Throws if live credentials missing. */
export function getClobClient(): ClobClient {
  if (_client) return _client;
  const env = getEnv();
  if (
    !env.POLY_FUNDER_SECRET ||
    !env.POLY_CLOB_API_KEY ||
    !env.POLY_CLOB_SECRET ||
    !env.POLY_CLOB_PASSPHRASE
  ) {
    throw new Error(
      "live trade misconfigured: POLY_FUNDER_SECRET, POLY_CLOB_API_KEY, POLY_CLOB_SECRET, POLY_CLOB_PASSPHRASE all required for PRISM_TRADE_MODE=live",
    );
  }
  const signer = buildSigner(env.POLY_FUNDER_SECRET, env.POLY_CHAIN_ID);
  const creds: ApiKeyCreds = {
    key: env.POLY_CLOB_API_KEY,
    secret: env.POLY_CLOB_SECRET,
    passphrase: env.POLY_CLOB_PASSPHRASE,
  };
  _client = new ClobClient({
    host: env.POLY_CLOB_HOST,
    chain: env.POLY_CHAIN_ID,
    signer: signer as unknown as ClobClient["signer"],
    creds,
    funderAddress: env.POLY_FUNDER_ADDRESS,
    builderConfig: { builderCode: env.POLY_BUILDER_CODE },
    throwOnError: false,
  });
  logger.info(
    { host: env.POLY_CLOB_HOST, chain: env.POLY_CHAIN_ID, funder: env.POLY_FUNDER_ADDRESS },
    "ClobClient initialized",
  );
  return _client;
}

/** Reset the cached CLOB client (test helper). */
export function resetClobClient(): void {
  _client = null;
}

/** Submit a real Polymarket CLOB order with the given builderCode.

Wraps `createAndPostOrder` with structured error handling. Returns the
SDK response (including the real Polymarket `orderID`).
*/
export async function submitLiveOrder(
  params: LiveOrderParams,
): Promise<LiveOrderResponse> {
  const client = getClobClient();
  const side = params.side === "BUY" ? Side.BUY : Side.SELL;
  const response = (await client.createAndPostOrder(
    {
      tokenID: params.tokenId,
      price: params.price,
      size: params.sizeUsdc,
      side,
      builderCode: params.builderCode,
    },
    undefined,
    OrderType.GTC,
  )) as LiveOrderResponse;
  return response;
}

/** Query Polymarket for trades attributed to a builderCode.

Returns the raw `BuilderTrade[]` from the V2 SDK so callers can pick out
the fields they care about (e.g., `transactionHash` for `polymarket_tx`).
*/
export async function fetchBuilderTrades(builderCode: string): Promise<BuilderTrade[]> {
  const client = getClobClient();
  const resp = await client.getBuilderTrades({ builder_code: builderCode });
  return resp.trades;
}

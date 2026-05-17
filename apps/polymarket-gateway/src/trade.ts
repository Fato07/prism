/** Trade execution: paper (simulated) or live (real Polymarket V2 CLOB).

PRISM_TRADE_MODE controls dispatch:
- `paper` → simulated receipt with status:`paper_filled` and `orderId` UUID
- `live`  → real createAndPostOrder via @polymarket/clob-client-v2 with builderCode,
            real `orderId` from Polymarket, `status:'open'` until fill polling
            updates it to `filled` with a real polymarket_tx hash

Size guards:
- Both modes: ≤ 25% of capped wallet balance (Phase 0 invariant)
- Live mode also: LIVE_TRADE_MIN_USDC (0.5) ≤ size ≤ LIVE_TRADE_MAX_USDC (25)

Builder code is deterministically derived from agentId via HMAC.
*/

import { randomUUID } from "node:crypto";

import pino from "pino";

import { mapAgentIdToBuilderCode } from "./builder.js";
import { submitLiveOrder } from "./clob.js";
import type { LiveOrderResponse } from "./clob.js";
import { getEnv } from "./env.js";
import { checkGeofence } from "./geofence.js";

const logger = pino({ name: "prism.trade" });

const DEFAULT_WALLET_CAP_USDC = 100;
const DEFAULT_LIVE_PRICE = 0.5;

// Price clamping bounds — Polymarket CLOB rejects prices outside [0.001, 0.999];
// we use [0.01, 0.99] as a safety net to leave margin and avoid edge-case rejections.
const PRICE_MIN = 0.01;
const PRICE_MAX = 0.99;

export type TradeSide = "BUY" | "SELL";

export type TradeStatus =
  | "paper_filled"
  | "open"
  | "filled"
  | "failed"
  | "expired";

export interface PrismOrderParams {
  agentId: number;
  traceId: string;
  marketId: string;
  side: TradeSide;
  sizeUsdc: number;
  priceLimit?: number;
  /** Polymarket conditional token ID. Required for live mode; defaults to marketId in paper mode. */
  tokenId?: string;
}

export interface TradeReceipt {
  orderId: string;
  traceId: string;
  marketId: string;
  side: TradeSide;
  size: number;
  builderCode: string;
  status: TradeStatus;
  timestamp: string;
  polymarketTx?: string | null;
  /** Fill or assumed paper-fill price. Null until a live order fills. */
  fillPrice?: number | null;
  errorMsg?: string;
}

export interface SizeValidation {
  allowed: boolean;
  maxSize: number;
  requestedSize: number;
  reason?: string;
}

/** Validate that a trade size is within the balance-percentage cap.

Rules:
- Max trade size = 25% of effective wallet balance
- Wallet balance is capped at WALLET_BALANCE_CAP_USDC (default 100 USDC)

@param sizeUsdc - Requested trade size in USDC
@param walletBalanceUsdc - Current wallet balance in USDC (defaults to cap)
*/
export function validateTradeSize(
  sizeUsdc: number,
  walletBalanceUsdc: number = DEFAULT_WALLET_CAP_USDC,
): SizeValidation {
  const env = getEnv();
  const cap = env.WALLET_BALANCE_CAP_USDC;

  if (walletBalanceUsdc > cap) {
    logger.warn(
      { balance: walletBalanceUsdc, cap },
      "Wallet balance exceeds cap, using cap for max calculation",
    );
  }

  const effectiveBalance = Math.min(walletBalanceUsdc, cap);
  const maxSize = effectiveBalance * 0.25;

  if (sizeUsdc <= 0) {
    return {
      allowed: false,
      maxSize,
      requestedSize: sizeUsdc,
      reason: "Trade size must be positive",
    };
  }

  if (sizeUsdc > maxSize) {
    return {
      allowed: false,
      maxSize,
      requestedSize: sizeUsdc,
      reason: `Trade size ${sizeUsdc} USDC exceeds max allowed ${maxSize} USDC (25% of effective balance ${effectiveBalance} USDC)`,
    };
  }

  return {
    allowed: true,
    maxSize,
    requestedSize: sizeUsdc,
  };
}

/** Extra live-mode constraint: size must be within [LIVE_TRADE_MIN_USDC, LIVE_TRADE_MAX_USDC]. */
export function validateLiveTradeSize(sizeUsdc: number): SizeValidation {
  const env = getEnv();
  if (sizeUsdc < env.LIVE_TRADE_MIN_USDC) {
    return {
      allowed: false,
      maxSize: env.LIVE_TRADE_MAX_USDC,
      requestedSize: sizeUsdc,
      reason: `Live trade size ${sizeUsdc} USDC below minimum ${env.LIVE_TRADE_MIN_USDC} USDC`,
    };
  }
  if (sizeUsdc > env.LIVE_TRADE_MAX_USDC) {
    return {
      allowed: false,
      maxSize: env.LIVE_TRADE_MAX_USDC,
      requestedSize: sizeUsdc,
      reason: `Live trade size ${sizeUsdc} USDC exceeds live cap ${env.LIVE_TRADE_MAX_USDC} USDC`,
    };
  }
  return { allowed: true, maxSize: env.LIVE_TRADE_MAX_USDC, requestedSize: sizeUsdc };
}

function buildPaperReceipt(
  params: PrismOrderParams,
  builderCode: string,
): TradeReceipt {
  const rawPrice = params.priceLimit ?? DEFAULT_LIVE_PRICE;
  const fillPrice = Math.max(PRICE_MIN, Math.min(PRICE_MAX, rawPrice));

  const receipt: TradeReceipt = {
    orderId: randomUUID(),
    traceId: params.traceId,
    marketId: params.marketId,
    side: params.side,
    size: params.sizeUsdc,
    builderCode,
    status: "paper_filled",
    timestamp: new Date().toISOString(),
    polymarketTx: null,
    fillPrice,
  };
  logger.info(
    {
      orderId: receipt.orderId,
      marketId: params.marketId,
      side: params.side,
      size: params.sizeUsdc,
      builderCode,
    },
    "Paper trade executed",
  );
  return receipt;
}

async function buildLiveReceipt(
  params: PrismOrderParams,
  builderCode: string,
): Promise<TradeReceipt> {
  const env = getEnv();
  const geo = checkGeofence(env.LOCALE);
  if (!geo.allowed) {
    throw new Error(geo.reason ?? "geofence_restricted");
  }

  const sizeCheck = validateLiveTradeSize(params.sizeUsdc);
  if (!sizeCheck.allowed) {
    throw new Error(sizeCheck.reason ?? "live size invalid");
  }

  const tokenId = params.tokenId;
  if (!tokenId) {
    throw new Error("tokenId is required for live orders; resolve it before calling /trade");
  }

  let response: LiveOrderResponse;
  // Safety-net clamping: ensure price is within [0.01, 0.99] even if
  // upstream layers fail to clamp. Polymarket CLOB rejects prices
  // outside [0.001, 0.999]; we use [0.01, 0.99] for extra margin.
  const rawPrice = params.priceLimit ?? DEFAULT_LIVE_PRICE;
  const price = Math.max(PRICE_MIN, Math.min(PRICE_MAX, rawPrice));

  try {
    response = await submitLiveOrder({
      tokenId,
      marketId: params.marketId,
      side: params.side,
      sizeUsdc: params.sizeUsdc,
      price,
      builderCode,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "polymarket order submission failed";
    logger.error({ err: message, marketId: params.marketId }, "Live order threw");
    return {
      orderId: randomUUID(),
      traceId: params.traceId,
      marketId: params.marketId,
      side: params.side,
      size: params.sizeUsdc,
      builderCode,
      status: "failed",
      timestamp: new Date().toISOString(),
      polymarketTx: null,
      fillPrice: null,
      errorMsg: message,
    };
  }

  if (!response.success || !response.orderID) {
    const errorMsg = response.errorMsg ?? "polymarket order rejected";
    logger.warn(
      {
        errorMsg,
        marketId: params.marketId,
        status: response.status,
        // Dump the full raw response so we can see what Polymarket actually
        // returned (the SDK sometimes drops detail in errorMsg). This makes
        // 403/400 debugging tractable without redeploys.
        raw_response: JSON.stringify(response).slice(0, 800),
      },
      "Live order rejected",
    );
    return {
      orderId: response.orderID || randomUUID(),
      traceId: params.traceId,
      marketId: params.marketId,
      side: params.side,
      size: params.sizeUsdc,
      builderCode,
      status: "failed",
      timestamp: new Date().toISOString(),
      polymarketTx: null,
      fillPrice: null,
      errorMsg,
    };
  }

  const firstTx = response.transactionsHashes?.[0] ?? null;
  const status: TradeStatus = firstTx ? "filled" : "open";

  const receipt: TradeReceipt = {
    orderId: response.orderID,
    traceId: params.traceId,
    marketId: params.marketId,
    side: params.side,
    size: params.sizeUsdc,
    builderCode,
    status,
    timestamp: new Date().toISOString(),
    polymarketTx: firstTx,
    fillPrice: firstTx ? price : null,
  };

  logger.info(
    {
      orderId: receipt.orderId,
      marketId: params.marketId,
      side: params.side,
      size: params.sizeUsdc,
      builderCode,
      polymarketTx: firstTx,
      status,
    },
    "Live order submitted to Polymarket CLOB",
  );

  return receipt;
}

/** Execute a Prism order. Dispatches to paper or live based on PRISM_TRADE_MODE. */
export async function placePrismOrder(
  params: PrismOrderParams,
  walletBalanceUsdc: number = DEFAULT_WALLET_CAP_USDC,
): Promise<TradeReceipt> {
  const env = getEnv();

  const sizeCheck = validateTradeSize(params.sizeUsdc, walletBalanceUsdc);
  if (!sizeCheck.allowed) {
    throw new Error(sizeCheck.reason ?? "Trade size exceeds limit");
  }

  const builderCode = mapAgentIdToBuilderCode(params.agentId);

  if (env.PRISM_TRADE_MODE === "paper") {
    return buildPaperReceipt(params, builderCode);
  }

  if (env.PRISM_TRADE_MODE === "live") {
    return buildLiveReceipt(params, builderCode);
  }

  throw new Error(
    `Unsupported trade mode: ${env.PRISM_TRADE_MODE}. Expected 'paper' or 'live'.`,
  );
}

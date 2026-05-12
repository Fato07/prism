/** Paper trade execution with size enforcement and simulated receipts.

Phase 0: No real Polymarket orders. Returns simulated receipt.
Trade size enforced at 25% of capped wallet balance (100 USDC cap).
Builder code deterministically derived from agentId via HMAC.
*/

import { randomUUID } from "node:crypto";

import pino from "pino";

import { mapAgentIdToBuilderCode } from "./builder.js";
import { getEnv } from "./env.js";

const logger = pino({ name: "prism.trade" });

/** Wallet balance cap in USDC. Never allow trades exceeding 25% of this. */
const DEFAULT_WALLET_CAP_USDC = 100;

/** Side of a trade order. */
export type TradeSide = "BUY" | "SELL";

/** Parameters for placing a Prism order. */
export interface PrismOrderParams {
  agentId: number;
  traceId: string;
  marketId: string;
  side: TradeSide;
  sizeUsdc: number;
  priceLimit?: number;
}

/** Simulated paper trade receipt. */
export interface TradeReceipt {
  orderId: string;
  traceId: string;
  marketId: string;
  side: TradeSide;
  size: number;
  builderCode: string;
  status: "paper_filled";
  timestamp: string;
}

/** Trade size validation result. */
export interface SizeValidation {
  allowed: boolean;
  maxSize: number;
  requestedSize: number;
  reason?: string;
}

/** Validate that a trade size is within allowed bounds.

Rules:
- Max trade size = 25% of wallet balance
- Wallet balance is capped at WALLET_BALANCE_CAP_USDC (default 100 USDC)
- So max trade size = min(25, 0.25 * actualBalance)
- If balance > cap, still max 25 USDC and a warning is logged

@param sizeUsdc - Requested trade size in USDC
@param walletBalanceUsdc - Current wallet balance in USDC (defaults to cap)
@returns Validation result with allowed flag and max size
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

/** Execute a paper trade (simulated, no real Polymarket orders).

In PRISM_TRADE_MODE=paper:
- No HTTP requests to Polymarket CLOB
- Returns a simulated receipt with all required fields
- Builder code derived from agentId via HMAC

@param params - Order parameters
@param walletBalanceUsdc - Current wallet balance (for size validation)
@returns Simulated trade receipt
@throws Error if agentId is not configured or trade size exceeds limit
*/
export function placePrismOrder(
  params: PrismOrderParams,
  walletBalanceUsdc: number = DEFAULT_WALLET_CAP_USDC,
): TradeReceipt {
  const env = getEnv();

  if (env.PRISM_TRADE_MODE !== "paper") {
    throw new Error(
      `Unsupported trade mode: ${env.PRISM_TRADE_MODE}. Only 'paper' is supported in Phase 0.`,
    );
  }

  // Validate trade size
  const sizeCheck = validateTradeSize(params.sizeUsdc, walletBalanceUsdc);
  if (!sizeCheck.allowed) {
    throw new Error(sizeCheck.reason ?? "Trade size exceeds limit");
  }

  // Derive builder code from agentId
  const builderCode = mapAgentIdToBuilderCode(params.agentId);

  const receipt: TradeReceipt = {
    orderId: randomUUID(),
    traceId: params.traceId,
    marketId: params.marketId,
    side: params.side,
    size: params.sizeUsdc,
    builderCode,
    status: "paper_filled",
    timestamp: new Date().toISOString(),
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

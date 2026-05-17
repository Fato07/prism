/** Neon Postgres persistence for trades.

Uses @neondatabase/serverless for HTTP-based queries over the
pooled DATABASE_URL connection.

Phase 1 additions:
- `polymarket_tx` may be non-null for live trades
- `updateTradeStatus` for the builder-trades poller to land fill data
*/

import { neon } from "@neondatabase/serverless";
import pino from "pino";

import { getEnv } from "./env.js";
import type { TradeReceipt, TradeSide } from "./trade.js";

const logger = pino({ name: "prism.db" });

/** Row shape from the trades table. */
export interface TradeRow {
  order_id: string;
  trace_id: string;
  market_id: string;
  side: string;
  size: string;
  builder_code: string;
  status: string;
  polymarket_tx: string | null;
  fill_price: string | null;
  created_at: string;
}

/** Persist a trade receipt to the trades table.

Stores `polymarket_tx` if the receipt already carries one (live fills),
otherwise NULL (paper, or live order still resting).

@param receipt - The trade receipt to persist
@returns True on success
*/
export async function persistTrade(receipt: TradeReceipt): Promise<boolean> {
  const env = getEnv();
  const sql = neon(env.DATABASE_URL);

  try {
    const polymarketTx = receipt.polymarketTx ?? null;
    const fillPrice = receipt.fillPrice ?? null;
    await sql`
      INSERT INTO trades (order_id, trace_id, market_id, side, size, builder_code, status, polymarket_tx, fill_price)
      VALUES (
        ${receipt.orderId},
        ${receipt.traceId},
        ${receipt.marketId},
        ${receipt.side},
        ${receipt.size.toString()},
        ${receipt.builderCode},
        ${receipt.status},
        ${polymarketTx},
        ${fillPrice}
      )
    `;
    logger.info(
      { orderId: receipt.orderId, status: receipt.status, polymarketTx },
      "Trade persisted to Neon",
    );
    return true;
  } catch (err) {
    logger.error({ err, orderId: receipt.orderId }, "Failed to persist trade");
    return false;
  }
}

/** Update an existing trade row's status and (optionally) polymarket_tx.

Used by the builder-trades poller when a live order fills, expires, or fails.

@returns True on success
*/
export async function updateTradeStatus(
  orderId: string,
  status: string,
  polymarketTx: string | null,
  fillPrice: number | string | null = null,
): Promise<boolean> {
  const env = getEnv();
  const sql = neon(env.DATABASE_URL);

  try {
    await sql`
      UPDATE trades
         SET status = ${status},
             polymarket_tx = COALESCE(${polymarketTx}, polymarket_tx),
             fill_price = COALESCE(${fillPrice}, fill_price)
       WHERE order_id = ${orderId}
    `;
    logger.info({ orderId, status, polymarketTx, fillPrice }, "Trade status updated");
    return true;
  } catch (err) {
    logger.error({ err, orderId }, "Failed to update trade status");
    return false;
  }
}

/** Return all open live trades (status='open', polymarket_tx IS NULL).

Used by the builder-trades poller.
*/
export async function listOpenLiveTrades(): Promise<TradeRow[]> {
  const env = getEnv();
  const sql = neon(env.DATABASE_URL);
  try {
    const rows = await sql`
      SELECT order_id, trace_id, market_id, side, size, builder_code, status, polymarket_tx, fill_price::text AS fill_price, created_at
        FROM trades
       WHERE status = 'open'
         AND polymarket_tx IS NULL
    `;
    return rows as TradeRow[];
  } catch (err) {
    logger.error({ err }, "Failed to list open live trades");
    return [];
  }
}

/** Look up a trade by order_id.

@param orderId - The order ID to query
@returns The trade row, or null if not found
*/
export async function getTrade(
  orderId: string,
): Promise<TradeRow | null> {
  const env = getEnv();
  const sql = neon(env.DATABASE_URL);

  try {
    const rows = await sql`
      SELECT order_id, trace_id, market_id, side, size, builder_code, status, polymarket_tx, fill_price::text AS fill_price, created_at
      FROM trades
      WHERE order_id = ${orderId}
    `;
    if (rows.length === 0) return null;
    return rows[0] as TradeRow;
  } catch (err) {
    logger.error({ err, orderId }, "Failed to query trade");
    return null;
  }
}

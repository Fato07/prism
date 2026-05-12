/** Neon Postgres persistence for trades.

Uses @neondatabase/serverless for HTTP-based queries over the
pooled DATABASE_URL connection.
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
  size: string; // NUMERIC comes as string
  builder_code: string;
  status: string;
  polymarket_tx: string | null;
  created_at: string;
}

/** Persist a paper trade receipt to the trades table.

@param receipt - The trade receipt to persist
@returns True on success
*/
export async function persistTrade(receipt: TradeReceipt): Promise<boolean> {
  const env = getEnv();
  const sql = neon(env.DATABASE_URL);

  try {
    await sql`
      INSERT INTO trades (order_id, trace_id, market_id, side, size, builder_code, status, polymarket_tx)
      VALUES (
        ${receipt.orderId},
        ${receipt.traceId},
        ${receipt.marketId},
        ${receipt.side},
        ${receipt.size.toString()},
        ${receipt.builderCode},
        ${receipt.status},
        NULL
      )
    `;
    logger.info({ orderId: receipt.orderId }, "Trade persisted to Neon");
    return true;
  } catch (err) {
    logger.error({ err, orderId: receipt.orderId }, "Failed to persist trade");
    return false;
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
      SELECT order_id, trace_id, market_id, side, size, builder_code, status, polymarket_tx, created_at
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

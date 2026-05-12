/** Background poller: getBuilderTrades → fill status into Neon.

In live mode, orders return immediately with `status: "open"` (resting on the
book). When a trade fills, we have to learn about it asynchronously by polling
`getBuilderTrades({ builder_code })`. When we find a match, we update the row:

- `status: "open"` → `"filled"`
- `polymarket_tx`: null → real Polygon transaction hash

The poller is stateless: it queries open live trades on each tick and reconciles.
*/

import type { BuilderTrade } from "@polymarket/clob-client-v2";
import pino from "pino";

import { mapAgentIdToBuilderCode } from "./builder.js";
import { fetchBuilderTrades } from "./clob.js";
import { getEnv } from "./env.js";
import { listOpenLiveTrades, updateTradeStatus } from "./db.js";
import type { TradeRow } from "./db.js";

const logger = pino({ name: "prism.poller" });

export interface PollResult {
  checked: number;
  filled: number;
  unchanged: number;
}

/** Compute the set of distinct builder codes from a list of trade rows.

A single Prism deployment may have multiple agentIds; each maps to its own
builderCode via HMAC. The poller queries Polymarket once per distinct code.
*/
function distinctBuilderCodes(rows: TradeRow[]): string[] {
  const codes = new Set<string>();
  for (const row of rows) {
    if (row.builder_code) codes.add(row.builder_code);
  }
  return [...codes];
}

/** Build an index of orderID → BuilderTrade for fast lookup. */
function indexTradesByOrderId(trades: BuilderTrade[]): Map<string, BuilderTrade> {
  const idx = new Map<string, BuilderTrade>();
  for (const trade of trades) {
    if (trade.id) idx.set(trade.id, trade);
    if (trade.takerOrderHash) idx.set(trade.takerOrderHash, trade);
  }
  return idx;
}

/** Reconcile open live trades against the latest builder trades from Polymarket.

For every open trade whose `order_id` appears in the fetched builder-trade list:
- If `transactionHash` present → mark `filled` with that hash as polymarket_tx
- If trade is older than `POLY_BUILDER_POLL_SECONDS * 10` and still missing → leave
  for the next tick (callers can mark expired separately)

@returns counts of trades checked / filled / unchanged
*/
export async function reconcileOpenLiveTrades(): Promise<PollResult> {
  const open = await listOpenLiveTrades();
  if (open.length === 0) {
    return { checked: 0, filled: 0, unchanged: 0 };
  }

  const codes = distinctBuilderCodes(open);
  const allTrades: BuilderTrade[] = [];
  for (const code of codes) {
    try {
      const trades = await fetchBuilderTrades(code);
      allTrades.push(...trades);
    } catch (err) {
      logger.warn(
        { err: err instanceof Error ? err.message : String(err), builderCode: code },
        "fetchBuilderTrades failed; will retry next tick",
      );
    }
  }

  const idx = indexTradesByOrderId(allTrades);
  let filled = 0;
  for (const row of open) {
    const match = idx.get(row.order_id);
    if (!match) continue;
    if (match.transactionHash) {
      const ok = await updateTradeStatus(row.order_id, "filled", match.transactionHash);
      if (ok) filled += 1;
    }
  }

  return {
    checked: open.length,
    filled,
    unchanged: open.length - filled,
  };
}

/** Convenience wrapper used by tests to verify the polling shape end-to-end. */
export function deriveBuilderCodeForAgent(agentId: number | string): string {
  return mapAgentIdToBuilderCode(agentId);
}

let _interval: NodeJS.Timeout | null = null;

/** Start the periodic poller. Idempotent. */
export function startBuilderTradesPoller(): void {
  if (_interval) return;
  const env = getEnv();
  if (!env.POLY_BUILDER_POLL_ENABLED) {
    logger.info({}, "Builder trades poller disabled via POLY_BUILDER_POLL_ENABLED=false");
    return;
  }
  if (env.PRISM_TRADE_MODE !== "live") {
    logger.info({ mode: env.PRISM_TRADE_MODE }, "Poller only runs in live mode; skipping");
    return;
  }
  const periodMs = env.POLY_BUILDER_POLL_SECONDS * 1000;
  _interval = setInterval(() => {
    void reconcileOpenLiveTrades().then(
      (res) => logger.debug(res, "Poll tick"),
      (err) => logger.warn({ err: err instanceof Error ? err.message : String(err) }, "Poll tick failed"),
    );
  }, periodMs);
  logger.info({ periodMs }, "Builder trades poller started");
}

/** Stop the poller (test helper). */
export function stopBuilderTradesPoller(): void {
  if (_interval) {
    clearInterval(_interval);
    _interval = null;
  }
}

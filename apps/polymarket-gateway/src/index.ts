/** Polymarket Gateway — Hono server on port 3203.

Entry point that creates the Hono app and starts the server.
App logic is in app.ts for testability.

In live mode:
- Geofencing gate runs at startup; restricted locale → process exits with code 1.
- Builder-trades poller starts in the background to reconcile fills.
*/

import pino from "pino";

import { createApp } from "./app.js";
import { getEnv } from "./env.js";
import { assertGeoEligibleForLive } from "./geofence.js";
import { startBuilderTradesPoller } from "./polling.js";

const logger = pino({ name: "prism.gateway" });

const app = createApp();
const env = getEnv();
const port = env.PORT;

if (env.PRISM_TRADE_MODE === "live") {
  try {
    assertGeoEligibleForLive(env.LOCALE);
    logger.info({ locale: env.LOCALE }, "Live mode geofence gate passed");
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    logger.error({ err: message, locale: env.LOCALE }, "Live mode geofence gate failed");
    if (
      process.argv[1]?.endsWith("src/index.ts") ||
      process.argv[1]?.endsWith("src/index.js")
    ) {
      process.exit(1);
    } else {
      throw err;
    }
  }
}

logger.info({ port, mode: env.PRISM_TRADE_MODE, locale: env.LOCALE }, "Starting Polymarket Gateway");

export default {
  port,
  fetch: app.fetch,
};

const _entryFile = process.argv[1] ?? "";
const _isDirectRun =
  _entryFile.endsWith("src/index.ts") ||
  _entryFile.endsWith("src/index.js") ||
  _entryFile.endsWith("dist/index.js");

if (_isDirectRun) {
  const { serve } = await import("@hono/node-server");
  serve({ fetch: app.fetch, port });
  logger.info({ port }, `Polymarket Gateway listening on http://localhost:${port}`);
  if (env.PRISM_TRADE_MODE === "live") {
    startBuilderTradesPoller();
  }
}

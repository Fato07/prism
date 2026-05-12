/** Polymarket Gateway — Hono server on port 3203.

Entry point that creates the Hono app and starts the server.
App logic is in app.ts for testability.
*/

import pino from "pino";

import { createApp } from "./app.js";
import { getEnv } from "./env.js";

const logger = pino({ name: "prism.gateway" });

const app = createApp();
const env = getEnv();
const port = env.PORT;

logger.info({ port, mode: env.PRISM_TRADE_MODE }, "Starting Polymarket Gateway");

export default {
  port,
  fetch: app.fetch,
};

// Only start listening when run directly (not imported for testing)
if (
  process.argv[1]?.endsWith("src/index.ts") ||
  process.argv[1]?.endsWith("src/index.js")
) {
  const { serve } = await import("@hono/node-server");
  serve({ fetch: app.fetch, port });
  logger.info({ port }, `Polymarket Gateway listening on http://localhost:${port}`);
}

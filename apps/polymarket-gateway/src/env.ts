/** Environment variable validation and configuration. */

import { z } from "zod";

const envSchema = z.object({
  PORT: z.coerce.number().default(3203),
  PRISM_TRADE_MODE: z
    .enum(["paper", "live"])
    .default("paper"),
  POLY_BUILDER_CODE: z.string().min(1, "POLY_BUILDER_CODE is required"),
  DATABASE_URL: z.string().min(1, "DATABASE_URL is required"),
  BUILDER_HMAC_SECRET: z.string().default("prism-default-hmac-secret"),
  WALLET_BALANCE_CAP_USDC: z.coerce.number().default(100),
  MARKET_CACHE_TTL_SECONDS: z.coerce.number().default(45),

  LOCALE: z.string().default("EE"),

  LIVE_TRADE_MIN_USDC: z.coerce.number().default(5),
  LIVE_TRADE_MAX_USDC: z.coerce.number().default(10),

  POLY_CLOB_HOST: z.string().default("https://clob.polymarket.com"),
  POLY_FUNDER_SECRET: z.string().optional(),
  POLY_FUNDER_ADDRESS: z.string().optional(),
  POLY_CLOB_API_KEY: z.string().optional(),
  POLY_CLOB_SECRET: z.string().optional(),
  POLY_CLOB_PASSPHRASE: z.string().optional(),
  POLY_CHAIN_ID: z.coerce.number().default(137),
  POLY_BUILDER_POLL_SECONDS: z.coerce.number().default(60),
  POLY_BUILDER_POLL_ENABLED: z
    .enum(["true", "false"])
    .default("true")
    .transform((v) => v === "true"),
});

export type Env = z.infer<typeof envSchema>;

let _env: Env | null = null;

/** Validate and return parsed environment variables. Throws on invalid config. */
export function getEnv(): Env {
  if (_env) return _env;
  const result = envSchema.safeParse(process.env);
  if (!result.success) {
    const errors = result.error.issues
      .map((i) => `${i.path.join(".")}: ${i.message}`)
      .join("; ");
    throw new Error(`Environment validation failed: ${errors}`);
  }
  _env = result.data;
  return _env;
}

/** Reset cached env (for testing). */
export function resetEnv(): void {
  _env = null;
}

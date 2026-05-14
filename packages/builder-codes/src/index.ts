/** Deterministic builder code mapping from agentId via HMAC.

Uses HMAC-SHA256 to derive a builder code from an agentId.
Same agentId always produces the same code (deterministic).
Different agentIds produce different codes (no collisions).

This links ERC-8004 on-chain identity to Polymarket builder attribution
without requiring a cross-chain bridge.

Pure functions: no env reads, no side effects. The HMAC secret is an
explicit parameter so callers control how it's sourced (env var, config
file, etc.). Zero runtime dependencies beyond Node's built-in crypto.
*/

import * as crypto from "node:crypto";

/** Derive a deterministic builder code from an agentId using HMAC-SHA256.

@param agentId - The ERC-8004 agentId (NFT tokenId)
@param hmacSecret - The HMAC secret key used for derivation
@returns A hex string suitable for use as a Polymarket builder code
*/
export function mapAgentIdToBuilderCode(
  agentId: number | string,
  hmacSecret: string,
): string {
  const hmac = crypto.createHmac("sha256", hmacSecret);
  hmac.update(String(agentId));
  return `0x${hmac.digest("hex")}`;
}

/** Verify that a builder code was derived from a given agentId.

@param agentId - The ERC-8004 agentId
@param builderCode - The claimed builder code
@param hmacSecret - The HMAC secret key used for derivation
@returns True if the builder code matches the HMAC derivation
*/
export function verifyBuilderCode(
  agentId: number | string,
  builderCode: string,
  hmacSecret: string,
): boolean {
  return mapAgentIdToBuilderCode(agentId, hmacSecret) === builderCode;
}

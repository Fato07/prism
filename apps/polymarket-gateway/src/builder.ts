/** Gateway wrapper: injects BUILDER_HMAC_SECRET from env into the pure
HMAC functions from @prism/builder-codes.

The pure package takes the secret as an explicit parameter so it has
zero runtime deps beyond Node crypto. This wrapper preserves the
gateway's existing API (secret read from env) with no behavior change.
*/

import {
  mapAgentIdToBuilderCode as _mapAgentIdToBuilderCode,
  verifyBuilderCode as _verifyBuilderCode,
} from "@prism/builder-codes";

import { getEnv } from "./env.js";

/** Derive a deterministic builder code from an agentId using HMAC-SHA256.

@param agentId - The ERC-8004 agentId (NFT tokenId)
@returns A hex string suitable for use as a Polymarket builder code
*/
export function mapAgentIdToBuilderCode(agentId: number | string): string {
  return _mapAgentIdToBuilderCode(agentId, getEnv().BUILDER_HMAC_SECRET);
}

/** Verify that a builder code was derived from a given agentId.

@param agentId - The ERC-8004 agentId
@param builderCode - The claimed builder code
@returns True if the builder code matches the HMAC derivation
*/
export function verifyBuilderCode(
  agentId: number | string,
  builderCode: string,
): boolean {
  return _verifyBuilderCode(agentId, builderCode, getEnv().BUILDER_HMAC_SECRET);
}

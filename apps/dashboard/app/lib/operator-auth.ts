import { timingSafeEqual } from "crypto";

/**
 * Check whether a request carries a valid OPERATOR_ADMIN_TOKEN.
 *
 * Uses constant-time comparison (`timingSafeEqual`) to prevent timing attacks.
 * Accepts both `Authorization: Bearer <token>` and `X-Prism-Admin-Token: <token>`
 * headers.  Completely independent of CONNECTOR_ADMIN_TOKEN — connector tokens
 * do NOT grant operator access and vice versa.
 */
export function isOperatorAdminRequest(request: Request): boolean {
  const configured = process.env.OPERATOR_ADMIN_TOKEN?.trim();
  if (!configured) return false;

  const supplied = operatorAdminTokenFromRequest(request);
  if (!supplied) return false;
  return constantTimeEquals(supplied, configured);
}

/**
 * Extract the operator admin token from either the Authorization (Bearer) header
 * or the X-Prism-Admin-Token header.  Returns `null` when neither header carries
 * a usable value.
 */
export function operatorAdminTokenFromRequest(request: Request): string | null {
  const authorization = request.headers.get("authorization") ?? "";
  if (authorization.toLowerCase().startsWith("bearer ")) {
    return authorization.slice(7).trim() || null;
  }
  return request.headers.get("x-prism-admin-token")?.trim() || null;
}

function constantTimeEquals(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

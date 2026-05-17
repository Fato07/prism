import { timingSafeEqual } from "crypto";

export function isConnectorAdminRequest(request: Request): boolean {
  const configured = process.env.CONNECTOR_ADMIN_TOKEN?.trim();
  if (!configured) return false;

  const supplied = connectorAdminTokenFromRequest(request);
  if (!supplied) return false;
  return constantTimeEquals(supplied, configured);
}

export function connectorAdminTokenFromRequest(request: Request): string | null {
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

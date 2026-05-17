const PRIVATE_IPV4_PATTERNS = [
  /^127\./,
  /^10\./,
  /^192\.168\./,
  /^169\.254\./,
  /^172\.(1[6-9]|2\d|3[0-1])\./,
  /^0\./,
] as const;

export function isSafeConnectorUrl(rawUrl: string): boolean {
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    return false;
  }

  if (url.username || url.password) return false;
  if (!["https:", "http:"].includes(url.protocol)) return false;
  if (url.protocol === "http:" && process.env.CONNECTOR_ALLOW_HTTP_CONNECTORS !== "1") return false;

  const hostname = url.hostname.toLowerCase();
  if (process.env.CONNECTOR_ALLOW_PRIVATE_URLS === "1") return true;
  if (hostname === "localhost" || hostname === "0.0.0.0" || hostname === "::1") return false;
  if (hostname.endsWith(".local") || hostname.endsWith(".internal")) return false;
  if (hostname.startsWith("[") || hostname.includes(":")) return false;
  if (PRIVATE_IPV4_PATTERNS.some((pattern) => pattern.test(hostname))) return false;

  return true;
}

export function redactConnectorUrl(rawUrl: string | null): string | null {
  if (!rawUrl) return null;
  try {
    const url = new URL(rawUrl);
    return `${url.protocol}//configured-host`;
  } catch {
    return "configured";
  }
}

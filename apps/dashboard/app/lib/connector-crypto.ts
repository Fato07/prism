import { createCipheriv, createDecipheriv, randomBytes, timingSafeEqual } from "crypto";

const ENVELOPE_VERSION = "v1";
const IV_BYTES = 12;
const TAG_BYTES = 16;
const KEY_BYTES = 32;

export class ConnectorCryptoError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConnectorCryptoError";
  }
}

export function decodeConnectorEncryptionKey(rawKey: string | undefined): Buffer {
  if (!rawKey?.trim()) {
    throw new ConnectorCryptoError("CONNECTOR_SECRETS_KEY is not set");
  }

  const trimmed = rawKey.trim();
  if (/^[0-9a-fA-F]{64}$/.test(trimmed)) {
    return Buffer.from(trimmed, "hex");
  }

  for (const encoding of ["base64", "base64url"] as const) {
    try {
      const decoded = Buffer.from(trimmed, encoding);
      if (decoded.length === KEY_BYTES) return decoded;
    } catch {
      // Try the next supported encoding.
    }
  }

  const utf8 = Buffer.from(trimmed, "utf8");
  if (utf8.length === KEY_BYTES) return utf8;

  throw new ConnectorCryptoError(
    "CONNECTOR_SECRETS_KEY must decode to exactly 32 bytes; use `openssl rand -base64 32`"
  );
}

export function getConnectorEncryptionKey(env: NodeJS.ProcessEnv = process.env): Buffer {
  return decodeConnectorEncryptionKey(env.CONNECTOR_SECRETS_KEY);
}

export function encryptConnectorToken(secret: string, key = getConnectorEncryptionKey()): string {
  if (!secret) {
    throw new ConnectorCryptoError("connector token must not be empty");
  }
  if (key.length !== KEY_BYTES) {
    throw new ConnectorCryptoError("connector token key must be 32 bytes");
  }

  const iv = randomBytes(IV_BYTES);
  const cipher = createCipheriv("aes-256-gcm", key, iv, { authTagLength: TAG_BYTES });
  const ciphertext = Buffer.concat([cipher.update(secret, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();

  return [
    ENVELOPE_VERSION,
    iv.toString("base64url"),
    tag.toString("base64url"),
    ciphertext.toString("base64url"),
  ].join(":");
}

export function decryptConnectorToken(envelope: string, key = getConnectorEncryptionKey()): string {
  if (key.length !== KEY_BYTES) {
    throw new ConnectorCryptoError("connector token key must be 32 bytes");
  }

  const [version, ivBase64, tagBase64, ciphertextBase64, ...extra] = envelope.split(":");
  if (version !== ENVELOPE_VERSION || !ivBase64 || !tagBase64 || !ciphertextBase64 || extra.length > 0) {
    throw new ConnectorCryptoError("invalid connector token envelope");
  }

  const iv = Buffer.from(ivBase64, "base64url");
  const tag = Buffer.from(tagBase64, "base64url");
  const ciphertext = Buffer.from(ciphertextBase64, "base64url");
  if (iv.length !== IV_BYTES || tag.length !== TAG_BYTES || ciphertext.length === 0) {
    throw new ConnectorCryptoError("invalid connector token envelope lengths");
  }

  const decipher = createDecipheriv("aes-256-gcm", key, iv, { authTagLength: TAG_BYTES });
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");
}

export function connectorTokenHint(secret: string): string {
  const normalized = secret.trim();
  if (normalized.length <= 4) return "configured";
  return `…${normalized.slice(-4)}`;
}

export function constantTimeTokenEquals(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}

import { describe, expect, it } from "vitest";

import {
  ConnectorCryptoError,
  connectorTokenHint,
  decodeConnectorEncryptionKey,
  decryptConnectorToken,
  encryptConnectorToken,
} from "@/lib/connector-crypto";

const key = Buffer.from("0123456789abcdef0123456789abcdef", "utf8");

describe("connector token encryption", () => {
  it("round-trips bearer tokens without embedding plaintext in the envelope", () => {
    const token = "prism_test_token_123456";
    const encrypted = encryptConnectorToken(token, key);

    expect(encrypted).toMatch(/^v1:/);
    expect(encrypted).not.toContain(token);
    expect(decryptConnectorToken(encrypted, key)).toBe(token);
  });

  it("rejects missing or badly sized keys", () => {
    expect(() => decodeConnectorEncryptionKey(undefined)).toThrow(ConnectorCryptoError);
    expect(() => decodeConnectorEncryptionKey("too-short")).toThrow(/32 bytes/);
  });

  it("accepts base64, hex, and raw 32-byte keys", () => {
    expect(decodeConnectorEncryptionKey(key.toString("base64"))).toHaveLength(32);
    expect(decodeConnectorEncryptionKey(key.toString("hex"))).toHaveLength(32);
    expect(decodeConnectorEncryptionKey(key.toString("utf8"))).toHaveLength(32);
  });

  it("returns a non-secret auth hint only", () => {
    expect(connectorTokenHint("prism_test_token_123456")).toBe("…3456");
    expect(connectorTokenHint("abc")).toBe("configured");
  });
});

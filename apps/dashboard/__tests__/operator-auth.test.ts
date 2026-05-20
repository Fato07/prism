import { describe, expect, it, beforeEach } from "vitest";

import { isOperatorAdminRequest, operatorAdminTokenFromRequest } from "@/lib/operator-auth";

const VALID_TOKEN = "op-secret-token-123";
const WRONG_TOKEN = "wrong-token-456";
const CONNECTOR_TOKEN = "connector-token-789";

function buildRequest(headers: Record<string, string> = {}): Request {
  return new Request("http://localhost/api/admin/runtime", { headers });
}

describe("operatorAdminTokenFromRequest", () => {
  it("extracts token from Authorization: Bearer header", () => {
    const req = buildRequest({ authorization: `Bearer ${VALID_TOKEN}` });
    expect(operatorAdminTokenFromRequest(req)).toBe(VALID_TOKEN);
  });

  it("extracts token from X-Prism-Admin-Token header", () => {
    const req = buildRequest({ "x-prism-admin-token": VALID_TOKEN });
    expect(operatorAdminTokenFromRequest(req)).toBe(VALID_TOKEN);
  });

  it("favors Bearer over X-Prism-Admin-Token when both are present", () => {
    const req = buildRequest({
      authorization: `Bearer ${VALID_TOKEN}`,
      "x-prism-admin-token": WRONG_TOKEN,
    });
    expect(operatorAdminTokenFromRequest(req)).toBe(VALID_TOKEN);
  });

  it("returns null when no auth header is present", () => {
    const req = buildRequest({});
    expect(operatorAdminTokenFromRequest(req)).toBeNull();
  });

  it("returns null for empty Bearer token", () => {
    const req = buildRequest({ authorization: "Bearer " });
    expect(operatorAdminTokenFromRequest(req)).toBeNull();
  });

  it("returns null for empty X-Prism-Admin-Token header", () => {
    const req = buildRequest({ "x-prism-admin-token": "  " });
    expect(operatorAdminTokenFromRequest(req)).toBeNull();
  });

  it("ignores Authorization header that is not Bearer", () => {
    const req = buildRequest({ authorization: `Basic ${VALID_TOKEN}` });
    // Falls through to X-Prism-Admin-Token check — Basic is not Bearer
    expect(operatorAdminTokenFromRequest(req)).toBeNull();
  });
});

describe("isOperatorAdminRequest", () => {
  beforeEach(() => {
    // Ensure env is clean before each test
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    delete (process.env as Record<string, string | undefined>).CONNECTOR_ADMIN_TOKEN;
  });

  it("returns true for valid token via Bearer header (VAL-ADMIN-001)", () => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    const req = buildRequest({ authorization: `Bearer ${VALID_TOKEN}` });
    expect(isOperatorAdminRequest(req)).toBe(true);
  });

  it("returns true for valid token via X-Prism-Admin-Token header (VAL-ADMIN-002)", () => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    const req = buildRequest({ "x-prism-admin-token": VALID_TOKEN });
    expect(isOperatorAdminRequest(req)).toBe(true);
  });

  it("returns false for missing token (VAL-ADMIN-003)", () => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    const req = buildRequest({});
    expect(isOperatorAdminRequest(req)).toBe(false);
  });

  it("returns false for incorrect token (VAL-ADMIN-004)", () => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    const req = buildRequest({ authorization: `Bearer ${WRONG_TOKEN}` });
    expect(isOperatorAdminRequest(req)).toBe(false);
  });

  it("returns false when CONNECTOR_ADMIN_TOKEN is used (VAL-ADMIN-005)", () => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.CONNECTOR_ADMIN_TOKEN = CONNECTOR_TOKEN;
    const req = buildRequest({ authorization: `Bearer ${CONNECTOR_TOKEN}` });
    expect(isOperatorAdminRequest(req)).toBe(false);
  });

  it("returns false when CONNECTOR_ADMIN_TOKEN is used via X-Prism-Admin-Token header", () => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.CONNECTOR_ADMIN_TOKEN = CONNECTOR_TOKEN;
    const req = buildRequest({ "x-prism-admin-token": CONNECTOR_TOKEN });
    expect(isOperatorAdminRequest(req)).toBe(false);
  });

  it("returns false when OPERATOR_ADMIN_TOKEN is unset (VAL-ADMIN-006)", () => {
    delete (process.env as Record<string, string | undefined>).OPERATOR_ADMIN_TOKEN;
    const req = buildRequest({ authorization: `Bearer ${VALID_TOKEN}` });
    expect(isOperatorAdminRequest(req)).toBe(false);
  });

  it("returns false when OPERATOR_ADMIN_TOKEN is empty string", () => {
    process.env.OPERATOR_ADMIN_TOKEN = "   ";
    const req = buildRequest({ authorization: `Bearer ${VALID_TOKEN}` });
    expect(isOperatorAdminRequest(req)).toBe(false);
  });

  it("returns false when both OPERATOR_ADMIN_TOKEN and CONNECTOR_ADMIN_TOKEN are set but bearer token is empty", () => {
    process.env.OPERATOR_ADMIN_TOKEN = VALID_TOKEN;
    process.env.CONNECTOR_ADMIN_TOKEN = CONNECTOR_TOKEN;
    const req = buildRequest({ authorization: "Bearer " });
    expect(isOperatorAdminRequest(req)).toBe(false);
  });
});

import { isSafeConnectorUrl } from "@/lib/connector-url-policy";
import type { ToolConnectorRow, ToolConnectorSmokeReceipt } from "@/lib/schemas";

const SMOKE_QUERY = "Prism connector smoke test: latest public evidence for a prediction market claim";
const MCP_PROTOCOL_VERSION = "2025-03-26";

type JsonRpcResponse = {
  jsonrpc?: string;
  id?: string | number | null;
  result?: unknown;
  error?: { code?: number; message?: string };
};

type McpCallResponse = {
  payload: JsonRpcResponse;
  sessionId: string | null;
};

type SmokeFetch = typeof fetch;

export type ConnectorSmokeInput = {
  row: ToolConnectorRow;
  bearerToken?: string | null;
  fetchImpl?: SmokeFetch;
  now?: () => Date;
};

export function buildSmokeToolArguments(row: Pick<ToolConnectorRow, "input_mapper" | "max_results">): Record<string, unknown> {
  switch (row.input_mapper) {
    case "query_limit":
      return { query: SMOKE_QUERY, limit: row.max_results };
    case "query_max_results":
      return { query: SMOKE_QUERY, max_results: row.max_results };
    case "q_count":
      return { q: SMOKE_QUERY, count: row.max_results };
    case "prism_evidence_request":
      return {
        query: SMOKE_QUERY,
        max_results: row.max_results,
        market_question: "Will the connector return current external evidence?",
        challenge: {
          id: "smoke-temporal-001",
          type: "temporal",
          severity: "material",
          question: "Can this tool return recent evidence for sentinel issue resolution?",
          required_resolution: "Return at least one parseable evidence result.",
          blocking_pass: false,
          claim_ref: null,
          resolution_status: "open",
        },
      };
    case "query":
    default:
      return { query: SMOKE_QUERY };
  }
}

export async function runMcpConnectorSmoke({
  row,
  bearerToken,
  fetchImpl = fetch,
  now = () => new Date(),
}: ConnectorSmokeInput): Promise<ToolConnectorSmokeReceipt> {
  const checkedAt = now().toISOString();
  let transportOk = false;
  let toolReachable = false;
  let schemaOk = false;
  let mapperOk = false;
  const failClosedOk = row.fail_closed;
  const costCapOk = row.max_usdc === null || Number(row.max_usdc) >= 0;

  if (row.transport === "custom_webhook") {
    return runCustomWebhookConnectorSmoke({
      row,
      bearerToken,
      fetchImpl,
      checkedAt,
      failClosedOk,
      costCapOk,
    });
  }

  if (row.transport !== "mcp_http") {
    return failedConnectorSmokeReceipt({
      checkedAt,
      transportOk,
      toolReachable,
      schemaOk,
      mapperOk,
      failClosedOk,
      costCapOk,
      errorCode: "unsupported_transport",
    });
  }

  if (!row.server_url || !row.tool_name) {
    return failedConnectorSmokeReceipt({
      checkedAt,
      transportOk,
      toolReachable,
      schemaOk,
      mapperOk,
      failClosedOk,
      costCapOk,
      errorCode: "connector_unconfigured",
    });
  }

  if (!isSafeConnectorUrl(row.server_url)) {
    return failedConnectorSmokeReceipt({
      checkedAt,
      transportOk,
      toolReachable,
      schemaOk,
      mapperOk,
      failClosedOk,
      costCapOk,
      errorCode: "unsafe_connector_url",
    });
  }

  try {
    const initializeResponse = await callMcp(row.server_url, "initialize", {
      protocolVersion: MCP_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: { name: "prism-dashboard", version: "0.1.0" },
    }, bearerToken, fetchImpl, "prism-smoke-init").catch(() => null);
    const sessionId = initializeResponse?.sessionId ?? null;
    if (sessionId) {
      await callMcp(row.server_url, "notifications/initialized", {}, bearerToken, fetchImpl, "prism-smoke-initialized", sessionId).catch(() => null);
    }

    const listResponse = await callMcp(row.server_url, "tools/list", {}, bearerToken, fetchImpl, "prism-smoke-list", sessionId);
    transportOk = true;
    const tools = extractMcpTools(listResponse.payload.result);
    toolReachable = tools.some((tool) => tool.name === row.tool_name);
    schemaOk = toolReachable;
    if (!toolReachable) {
      return failedConnectorSmokeReceipt({
        checkedAt,
        transportOk,
        toolReachable,
        schemaOk,
        mapperOk,
        failClosedOk,
        costCapOk,
        errorCode: "tool_not_listed",
      });
    }

    const callResponse = await callMcp(
      row.server_url,
      "tools/call",
      { name: row.tool_name, arguments: buildSmokeToolArguments(row) },
      bearerToken,
      fetchImpl,
      "prism-smoke-call",
      sessionId
    );
    const body = extractMcpResultBody(callResponse.payload.result);
    const evidenceCount = countMappedEvidenceItems(row.result_mapper, body);
    mapperOk = evidenceCount > 0;

    if (!mapperOk) {
      return failedConnectorSmokeReceipt({
        checkedAt,
        transportOk,
        toolReachable,
        schemaOk,
        mapperOk,
        failClosedOk,
        costCapOk,
        errorCode: "mapper_no_results",
      });
    }

    return {
      status: "passed",
      checked_at: checkedAt,
      transport_ok: true,
      tool_reachable: true,
      schema_ok: true,
      mapper_ok: true,
      fail_closed_ok: failClosedOk,
      cost_cap_ok: costCapOk,
      evidence_count: evidenceCount,
    };
  } catch {
    return failedConnectorSmokeReceipt({
      checkedAt,
      transportOk,
      toolReachable,
      schemaOk,
      mapperOk,
      failClosedOk,
      costCapOk,
      errorCode: transportOk ? "mcp_call_failed" : "transport_error",
    });
  }
}

async function runCustomWebhookConnectorSmoke({
  row,
  bearerToken,
  fetchImpl,
  checkedAt,
  failClosedOk,
  costCapOk,
}: {
  row: ToolConnectorRow;
  bearerToken?: string | null;
  fetchImpl: SmokeFetch;
  checkedAt: string;
  failClosedOk: boolean;
  costCapOk: boolean;
}): Promise<ToolConnectorSmokeReceipt> {
  let transportOk = false;
  let toolReachable = false;
  let schemaOk = false;
  let mapperOk = false;

  if (!row.server_url) {
    return failedConnectorSmokeReceipt({
      checkedAt,
      transportOk,
      toolReachable,
      schemaOk,
      mapperOk,
      failClosedOk,
      costCapOk,
      errorCode: "connector_unconfigured",
    });
  }

  if (!isSafeConnectorUrl(row.server_url)) {
    return failedConnectorSmokeReceipt({
      checkedAt,
      transportOk,
      toolReachable,
      schemaOk,
      mapperOk,
      failClosedOk,
      costCapOk,
      errorCode: "unsafe_connector_url",
    });
  }

  const headers: Record<string, string> = { "content-type": "application/json" };
  if (bearerToken) headers.authorization = `Bearer ${bearerToken}`;

  try {
    const response = await fetchImpl(row.server_url, {
      method: "POST",
      headers,
      body: JSON.stringify(buildWebhookSmokeRequest(row)),
    });
    transportOk = true;
    toolReachable = response.ok;
    if (!response.ok) {
      return failedConnectorSmokeReceipt({
        checkedAt,
        transportOk,
        toolReachable,
        schemaOk,
        mapperOk,
        failClosedOk,
        costCapOk,
        errorCode: response.status === 402 ? "x402_payment_required" : "webhook_http_error",
      });
    }

    const body = (await response.json()) as unknown;
    schemaOk = true;
    const evidenceCount = countMappedEvidenceItems(row.result_mapper, body);
    mapperOk = evidenceCount > 0;
    if (!mapperOk) {
      return failedConnectorSmokeReceipt({
        checkedAt,
        transportOk,
        toolReachable,
        schemaOk,
        mapperOk,
        failClosedOk,
        costCapOk,
        errorCode: "mapper_no_results",
      });
    }

    return {
      status: "passed",
      checked_at: checkedAt,
      transport_ok: true,
      tool_reachable: true,
      schema_ok: true,
      mapper_ok: true,
      fail_closed_ok: failClosedOk,
      cost_cap_ok: costCapOk,
      evidence_count: evidenceCount,
    };
  } catch {
    return failedConnectorSmokeReceipt({
      checkedAt,
      transportOk,
      toolReachable,
      schemaOk,
      mapperOk,
      failClosedOk,
      costCapOk,
      errorCode: transportOk ? "webhook_parse_error" : "transport_error",
    });
  }
}

function buildWebhookSmokeRequest(row: Pick<ToolConnectorRow, "max_results">): Record<string, unknown> {
  return {
    query: SMOKE_QUERY,
    max_results: row.max_results,
    market_question: "Will the connector return current external evidence?",
    challenge: {
      id: "smoke-temporal-001",
      type: "temporal",
      severity: "material",
      question: "Can this tool return recent evidence for sentinel issue resolution?",
      required_resolution: "Return at least one parseable evidence result.",
      blocking_pass: false,
      claim_ref: null,
      resolution_status: "open",
    },
  };
}

async function callMcp(
  serverUrl: string,
  method: string,
  params: Record<string, unknown>,
  bearerToken: string | null | undefined,
  fetchImpl: SmokeFetch,
  id: string,
  sessionId: string | null = null
): Promise<McpCallResponse> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    accept: "application/json, text/event-stream",
  };
  if (bearerToken) headers.authorization = `Bearer ${bearerToken}`;
  if (sessionId) headers["mcp-session-id"] = sessionId;

  const response = await fetchImpl(serverUrl, {
    method: "POST",
    headers,
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
  });
  if (!response.ok) {
    throw new Error("mcp_http_error");
  }

  const payload = await readMcpPayload(response);
  if (payload.error) {
    throw new Error("mcp_jsonrpc_error");
  }
  return { payload, sessionId: response.headers.get("mcp-session-id") };
}

async function readMcpPayload(response: Response): Promise<JsonRpcResponse> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/event-stream")) {
    return (await response.json()) as JsonRpcResponse;
  }

  const text = await response.text();
  const dataLine = text
    .split("\n")
    .map((line) => line.trim())
    .find((line) => line.startsWith("data:"));
  if (!dataLine) throw new Error("mcp_sse_missing_data");
  return JSON.parse(dataLine.slice(5).trim()) as JsonRpcResponse;
}

function extractMcpTools(result: unknown): Array<{ name: string }> {
  if (!isRecord(result)) return [];
  const tools = result.tools;
  if (!Array.isArray(tools)) return [];
  return tools
    .filter((tool): tool is { name: string } => isRecord(tool) && typeof tool.name === "string")
    .map((tool) => ({ name: tool.name }));
}

export function extractMcpResultBody(result: unknown): unknown {
  if (!isRecord(result)) return result;
  if ("structuredContent" in result) return result.structuredContent;
  if ("structured_content" in result) return result.structured_content;
  if ("data" in result) return result.data;

  const content = result.content;
  if (Array.isArray(content) && isRecord(content[0]) && typeof content[0].text === "string") {
    try {
      return JSON.parse(content[0].text);
    } catch {
      return content[0].text;
    }
  }
  return result;
}

export function countMappedEvidenceItems(resultMapper: string, body: unknown): number {
  if (resultMapper.trim().toLowerCase() === "exa_mcp_text") {
    return countExaMcpTextItems(body);
  }
  return countEvidenceItems(body);
}

export function countEvidenceItems(body: unknown): number {
  if (Array.isArray(body)) return body.length;
  if (!isRecord(body)) return 0;

  for (const key of ["results", "items", "data", "evidence"] as const) {
    const value = body[key];
    if (Array.isArray(value)) return value.length;
  }

  return hasEvidenceLikeFields(body) ? 1 : 0;
}

function countExaMcpTextItems(body: unknown): number {
  const text = typeof body === "string" ? body : isRecord(body) && typeof body.text === "string" ? body.text : "";
  if (!text.trim()) return 0;
  return text
    .split(/^[\t ]*Title:[\t ]*/m)
    .map((block) => block.trim())
    .filter((block) => /^URL:\s*https?:\/\//m.test(block) && /^Highlights:\s*[\s\S]+/m.test(block)).length;
}

function hasEvidenceLikeFields(value: Record<string, unknown>): boolean {
  return (
    typeof value.title === "string" ||
    typeof value.url === "string" ||
    typeof value.snippet === "string" ||
    typeof value.claim === "string"
  );
}

export function failedConnectorSmokeReceipt(input: {
  checkedAt: string;
  transportOk: boolean;
  toolReachable: boolean;
  schemaOk: boolean;
  mapperOk: boolean;
  failClosedOk: boolean;
  costCapOk: boolean;
  errorCode: string;
}): ToolConnectorSmokeReceipt {
  return {
    status: "failed",
    checked_at: input.checkedAt,
    transport_ok: input.transportOk,
    tool_reachable: input.toolReachable,
    schema_ok: input.schemaOk,
    mapper_ok: input.mapperOk,
    fail_closed_ok: input.failClosedOk,
    cost_cap_ok: input.costCapOk,
    error_code: input.errorCode,
    error_message: "Connector smoke test failed; Prism will fail closed and leave issues unresolved.",
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

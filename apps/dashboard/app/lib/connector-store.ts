import { randomUUID } from "crypto";

import { getPool } from "@/lib/db";
import {
  CreateMcpConnectorRequestSchema,
  EMPTY_CONNECTOR_MANIFEST,
  buildConnectorManifest,
  canArmConnector,
  toConnectorPassport,
  type ConnectorManifest,
  type ConnectorPassport,
  type CreateMcpConnectorRequest,
} from "@/lib/connectors";
import {
  ConnectorCryptoError,
  connectorTokenHint,
  decryptConnectorToken,
  encryptConnectorToken,
} from "@/lib/connector-crypto";
import { failedConnectorSmokeReceipt, runMcpConnectorSmoke } from "@/lib/connector-smoke";
import { ToolConnectorRowSchema, type ToolConnectorRow, type ToolConnectorSmokeReceipt } from "@/lib/schemas";

export class ConnectorStoreError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "ConnectorStoreError";
    this.code = code;
  }
}

const SELECT_CONNECTOR_COLUMNS = `
  id::text AS id,
  owner_scope,
  connector_kind,
  name,
  transport,
  provider,
  server_url,
  tool_name,
  input_mapper,
  result_mapper,
  allowed_tools,
  timeout_seconds::text AS timeout_seconds,
  max_results,
  max_usdc::text AS max_usdc,
  auth_secret_ciphertext,
  auth_secret_hint,
  smoke_status,
  smoke_receipt,
  armed,
  fail_closed,
  created_at::text AS created_at,
  updated_at::text AS updated_at
`;

export async function listConnectorRows(): Promise<ToolConnectorRow[]> {
  const result = await getPool().query(
    `SELECT ${SELECT_CONNECTOR_COLUMNS}
     FROM tool_connectors
     WHERE connector_kind = 'evidence'
     ORDER BY armed DESC, updated_at DESC, created_at DESC`
  );
  return result.rows.map(parseConnectorRow);
}

export async function getConnectorManifest(): Promise<ConnectorManifest> {
  return buildConnectorManifest(await listConnectorRows());
}

export async function getConnectorManifestForDashboard(): Promise<ConnectorManifest> {
  try {
    return await getConnectorManifest();
  } catch {
    return EMPTY_CONNECTOR_MANIFEST;
  }
}

export async function getConnectorRow(id: string): Promise<ToolConnectorRow | null> {
  const result = await getPool().query(
    `SELECT ${SELECT_CONNECTOR_COLUMNS}
     FROM tool_connectors
     WHERE id = $1
     LIMIT 1`,
    [id]
  );
  if (result.rows.length === 0) return null;
  return parseConnectorRow(result.rows[0]);
}

export async function upsertMcpConnector(input: CreateMcpConnectorRequest): Promise<ConnectorPassport> {
  const parsed = CreateMcpConnectorRequestSchema.parse(input);
  const id = parsed.id ?? randomUUID();
  const encryptedToken = parsed.bearer_token ? encryptConnectorToken(parsed.bearer_token) : null;
  const tokenHint = parsed.bearer_token ? connectorTokenHint(parsed.bearer_token) : null;
  const allowedTools = uniqueStrings([parsed.tool_name, ...parsed.allowed_tools]);

  const result = await getPool().query(
    `INSERT INTO tool_connectors (
        id,
        name,
        transport,
        provider,
        server_url,
        tool_name,
        input_mapper,
        result_mapper,
        allowed_tools,
        timeout_seconds,
        max_results,
        max_usdc,
        auth_secret_ciphertext,
        auth_secret_hint,
        fail_closed,
        smoke_status,
        smoke_receipt,
        armed,
        updated_at
      ) VALUES (
        $1, $2, 'mcp_http', 'mcp', $3, $4, $5, $6, $7::text[], $8, $9, $10, $11, $12, $13, 'not_run', NULL, FALSE, NOW()
      )
      ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        transport = EXCLUDED.transport,
        provider = EXCLUDED.provider,
        server_url = EXCLUDED.server_url,
        tool_name = EXCLUDED.tool_name,
        input_mapper = EXCLUDED.input_mapper,
        result_mapper = EXCLUDED.result_mapper,
        allowed_tools = EXCLUDED.allowed_tools,
        timeout_seconds = EXCLUDED.timeout_seconds,
        max_results = EXCLUDED.max_results,
        max_usdc = EXCLUDED.max_usdc,
        auth_secret_ciphertext = COALESCE(EXCLUDED.auth_secret_ciphertext, tool_connectors.auth_secret_ciphertext),
        auth_secret_hint = COALESCE(EXCLUDED.auth_secret_hint, tool_connectors.auth_secret_hint),
        fail_closed = EXCLUDED.fail_closed,
        smoke_status = 'not_run',
        smoke_receipt = NULL,
        armed = FALSE,
        updated_at = NOW()
      RETURNING ${SELECT_CONNECTOR_COLUMNS}`,
    [
      id,
      parsed.name,
      parsed.server_url,
      parsed.tool_name,
      parsed.input_mapper,
      parsed.result_mapper,
      allowedTools,
      parsed.timeout_seconds,
      parsed.max_results,
      parsed.max_usdc ?? null,
      encryptedToken,
      tokenHint,
      parsed.fail_closed,
    ]
  );

  return toConnectorPassport(parseConnectorRow(result.rows[0]));
}

export async function smokeConnector(id: string): Promise<ConnectorPassport> {
  const row = await getConnectorRow(id);
  if (!row) {
    throw new ConnectorStoreError("connector_not_found", "Connector not found");
  }

  const bearerToken = decryptTokenForSmoke(row);
  const receipt = bearerToken === undefined
    ? failedCryptoSmokeReceipt(row)
    : await runMcpConnectorSmoke({ row, bearerToken });
  const updated = await updateConnectorSmoke(row.id, receipt);
  return toConnectorPassport(updated);
}

export async function armConnector(id: string): Promise<ConnectorPassport> {
  const row = await getConnectorRow(id);
  if (!row) {
    throw new ConnectorStoreError("connector_not_found", "Connector not found");
  }
  if (!canArmConnector(row)) {
    throw new ConnectorStoreError("connector_smoke_required", "Connector must pass smoke before arming");
  }

  const pool = getPool();
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query(
      "UPDATE tool_connectors SET armed = FALSE, updated_at = NOW() WHERE connector_kind = $1 AND armed = TRUE",
      [row.connector_kind]
    );
    const result = await client.query(
      `UPDATE tool_connectors
       SET armed = TRUE, updated_at = NOW()
       WHERE id = $1
       RETURNING ${SELECT_CONNECTOR_COLUMNS}`,
      [id]
    );
    await client.query("COMMIT");
    return toConnectorPassport(parseConnectorRow(result.rows[0]));
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

async function updateConnectorSmoke(id: string, receipt: ToolConnectorSmokeReceipt): Promise<ToolConnectorRow> {
  const result = await getPool().query(
    `UPDATE tool_connectors
     SET smoke_status = $2,
         smoke_receipt = $3::jsonb,
         armed = CASE WHEN $2 = 'passed' THEN armed ELSE FALSE END,
         updated_at = NOW()
     WHERE id = $1
     RETURNING ${SELECT_CONNECTOR_COLUMNS}`,
    [id, receipt.status, JSON.stringify(receipt)]
  );
  return parseConnectorRow(result.rows[0]);
}

function decryptTokenForSmoke(row: ToolConnectorRow): string | null | undefined {
  if (!row.auth_secret_ciphertext) return null;
  try {
    return decryptConnectorToken(row.auth_secret_ciphertext);
  } catch (error) {
    if (error instanceof ConnectorCryptoError) {
      return undefined;
    }
    throw error;
  }
}

export function failedCryptoSmokeReceipt(row: ToolConnectorRow, now = () => new Date()): ToolConnectorSmokeReceipt {
  return failedConnectorSmokeReceipt({
    checkedAt: now().toISOString(),
    transportOk: false,
    toolReachable: false,
    schemaOk: false,
    mapperOk: false,
    failClosedOk: row.fail_closed,
    costCapOk: row.max_usdc === null || Number(row.max_usdc) >= 0,
    errorCode: "connector_token_unavailable",
  });
}

function parseConnectorRow(row: Record<string, unknown>): ToolConnectorRow {
  return ToolConnectorRowSchema.parse({
    ...row,
    allowed_tools: Array.isArray(row.allowed_tools) ? row.allowed_tools : [],
    max_results: Number(row.max_results),
  });
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

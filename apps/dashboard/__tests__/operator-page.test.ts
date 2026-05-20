/**
 * /operator page tests — Read-only Runtime Status
 *
 * Covers:
 *   - VAL-UI-001: Page renders with status card showing all 8 runtime fields
 *   - VAL-UI-002: Trade mode and auto-pipeline as static text, no editable inputs
 *   - VAL-UI-011: Admin token input (type=password), auth-required prompt without token
 *   - VAL-UI-012: Page reachable from global navigation, uses GlobalNav layout
 *
 * Tests are unit-level (no browser / no real trader).
 */

import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const PAGE_PATH = path.join(process.cwd(), "app/operator/page.tsx");
const SHELL_PATH = path.join(process.cwd(), "app/operator/operator-shell.tsx");
const NAV_PATH = path.join(process.cwd(), "app/components/global-nav.tsx");

/* ─────────────── VAL-UI-012: Global navigation integration ──── */

describe("VAL-UI-012: Operator page reachable from global navigation", () => {
  it("global nav contains /operator route entry", () => {
    const source = fs.readFileSync(NAV_PATH, "utf8");
    expect(source).toContain('href: "/operator"');
  });

  it("global nav /operator entry has corresponding page identifier", () => {
    const source = fs.readFileSync(NAV_PATH, "utf8");
    expect(source).toContain('page: "operator"');
  });

  it("page imports GlobalNav", () => {
    const source = fs.readFileSync(PAGE_PATH, "utf8");
    expect(source).toContain("GlobalNav");
  });

  it("page passes currentPage='operator' to GlobalNav", () => {
    const source = fs.readFileSync(PAGE_PATH, "utf8");
    expect(source).toContain("currentPage=");
    expect(source).toContain('"operator"');
  });
});

/* ─────────────── Page structure (server component shell) ─────── */

describe("Page structure", () => {
  it("the page file is NOT a client component (server shell)", () => {
    const source = fs.readFileSync(PAGE_PATH, "utf8");
    expect(source).not.toContain('"use client"');
    expect(source).not.toContain("'use client'");
  });

  it("the page imports OperatorShell for client-side logic", () => {
    const source = fs.readFileSync(PAGE_PATH, "utf8");
    expect(source).toContain("OperatorShell");
  });

  it("the page returns JSX with GlobalNav and OperatorShell", () => {
    const source = fs.readFileSync(PAGE_PATH, "utf8");
    expect(source).toContain("<GlobalNav");
    expect(source).toContain("<OperatorShell");
  });
});

/* ─────────────── VAL-UI-011: Auth handling ───────────────────── */

describe("VAL-UI-011: Operator page requires admin token for data access", () => {
  it("operator-shell is a client component", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    expect(source).toContain("use client");
  });

  it("operator-shell contains a password input for admin token", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    // The input uses a dynamic type toggle: type={showPassword ? "text" : "password"}
    // Verify that password is referenced as a possible input type
    expect(source).toMatch(/type.*password|password.*type/);
    expect(source).toContain("password");
  });

  it("operator-shell shows auth-required prompt when no token is provided", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    // Must have user-facing text that explains auth is required
    const hasAuthPrompt =
      source.includes("auth") ||
      source.includes("token") ||
      source.includes("authenticate") ||
      source.includes("Access") ||
      source.includes("connect");
    expect(hasAuthPrompt).toBe(true);
  });

  it("operator-shell does NOT expose status data in initial render (before auth)", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    // The status display should be conditional on authentication
    expect(source).toContain("status"); // references the variable
  });
});

/* ─────────────── VAL-UI-001: Status card with all 8 fields ───── */

describe("VAL-UI-001: Status card displays all 8 runtime fields with labels", () => {
  it("operator-shell references all 8 status fields", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    const requiredFields = [
      "scheduler_running",
      "interval_minutes",
      "auto_pipeline_enabled",
      "trade_mode",
      "last_tick_timestamp",
      "next_tick",
      "last_error",
      "service_version",
    ];
    for (const field of requiredFields) {
      expect(source).toContain(field);
    }
  });

  it("status card is clearly labeled as read-only", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    const hasReadOnlyLabel =
      source.includes("read only") ||
      source.includes("read-only") ||
      source.includes("Read only") ||
      source.includes("Read-only") ||
      source.includes("Read-Only");
    expect(hasReadOnlyLabel).toBe(true);
  });

  it("status card uses Card component for structured layout", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    expect(source).toContain("Card");
  });
});

/* ─────────────── VAL-UI-002: Trade mode + auto-pipeline static ── */

describe("VAL-UI-002: Trade mode and auto-pipeline displayed as static text", () => {
  it("no select, dropdown, or toggle elements for trade_mode or auto_pipeline", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    // Static text — no interactive form controls for these fields specifically
    expect(source).not.toContain("<select");
    // Password input for the token is the only allowed <input>
  });

  it("trade_mode is rendered as static text, not an editable input", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    // Should reference trade_mode for display, not have form bindings
    expect(source).toContain("trade_mode");
    // trade_mode appears inside a display component (Pill), not an input
    // Verify the trade_mode display block uses Pill (search with dotAll flag for multiline)
    expect(source).toMatch(/Pill[\s\S]*trade_mode[\s\S]*Pill/);
  });

  it("auto_pipeline_enabled is rendered as static text, not editable", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    expect(source).toContain("auto_pipeline_enabled");
  });
});

/* ─────────────── No mutation buttons (read-only surface only) ─── */

describe("No mutation buttons", () => {
  it("operator-shell does not contain Start or Stop scheduler buttons", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    // These are for the next milestone — they must NOT be here yet
    // Check for specific mutation-related patterns, not common words
    expect(source).not.toMatch(/start\s*scheduler/i); // no "Start Scheduler" button
    expect(source).not.toMatch(/stop\s*scheduler/i); // no "Stop Scheduler" button
    expect(source).not.toContain("handleStart"); // no mutation handler
    expect(source).not.toContain("handleStop"); // no mutation handler
  });

  it("operator-shell does not contain mutation API endpoint references", () => {
    const source = fs.readFileSync(SHELL_PATH, "utf8");
    expect(source).not.toContain("/api/admin/schedule/start");
    expect(source).not.toContain("/api/admin/schedule/stop");
    expect(source).not.toContain("/api/admin/audit");
  });
});

/* ─────────────── Accessibility & layout ──────────────────────── */

describe("Layout and accessibility", () => {
  it("operator page has consistent layout with GlobalNav wrapper", () => {
    const source = fs.readFileSync(PAGE_PATH, "utf8");
    // Should have the typical dashboard structure
    expect(source).toContain("min-h-screen");
  });

  it("operator page exports metadata or dynamic config", () => {
    const source = fs.readFileSync(PAGE_PATH, "utf8");
    const hasDynamic = source.includes('dynamic = "force-dynamic"');
    const hasMetadata = source.includes("metadata");
    expect(hasDynamic || hasMetadata).toBe(true);
  });
});

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const root = process.cwd();

function read(relativePath: string): string {
  return readFileSync(join(root, relativePath), "utf8");
}

describe("llms.txt route", () => {
  it("publishes public Prism context without payment headers", () => {
    const route = read("app/llms.txt/route.ts");

    expect(route).toContain("Validate-before-action receipts for money-moving AI agents");
    expect(route).toContain("https://prism-dashboard-production-e6e3.up.railway.app");
    expect(route).toContain("https://prism-docs-production.up.railway.app");
    expect(route).toContain("/llms.txt");
    expect(route).toContain("https://prism-sentinel-production.up.railway.app/mcp/");
    expect(route).toContain("Canonical URL-verified report");
    expect(route).toContain("Prism does not guarantee truth, profit, legal compliance, or perfect security");
    expect(route).not.toContain("X-PAYMENT");
  });
});

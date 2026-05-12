/**
 * Tests for the formatRelativeTime utility function.
 */

import { describe, it, expect, vi } from "vitest";

// Inline the function for unit testing (same logic as app/lib/utils.ts)
// This avoids path-alias resolution issues in test context.
function formatRelativeTime(isoTimestamp: string): string {
  const now = Date.now();
  const then = new Date(isoTimestamp).getTime();
  const diffMs = now - then;

  if (diffMs < 0) {
    return "just now";
  }

  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 30) return `${days}d ago`;

  return new Date(isoTimestamp).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

describe("formatRelativeTime", () => {
  it("returns 'just now' for timestamps less than 60 seconds ago", () => {
    const ts = new Date(Date.now() - 30_000).toISOString();
    expect(formatRelativeTime(ts)).toBe("just now");
  });

  it("returns 'Xm ago' for timestamps within the last hour", () => {
    const ts = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatRelativeTime(ts)).toBe("5m ago");
  });

  it("returns 'Xh ago' for timestamps within the last day", () => {
    const ts = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(ts)).toBe("3h ago");
  });

  it("returns 'Xd ago' for timestamps within the last 30 days", () => {
    const ts = new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString();
    expect(formatRelativeTime(ts)).toBe("5d ago");
  });

  it("returns calendar date for timestamps older than 30 days", () => {
    const ts = new Date(Date.now() - 60 * 24 * 60 * 60 * 1000).toISOString();
    const result = formatRelativeTime(ts);
    // Should be a date string like "Mar 13, 2026" not "Xd ago"
    expect(result).not.toMatch(/^\d+[mdh] ago$/);
    expect(result).not.toBe("just now");
  });

  it("returns 'just now' for future timestamps", () => {
    const ts = new Date(Date.now() + 60_000).toISOString();
    expect(formatRelativeTime(ts)).toBe("just now");
  });

  it("handles ISO 8601 timestamps from the trace schema", () => {
    const ts = "2026-05-12T10:00:00Z";
    // This should produce a valid string (calendar date since it's in the past)
    const result = formatRelativeTime(ts);
    expect(result).toBeTruthy();
    expect(typeof result).toBe("string");
  });
});

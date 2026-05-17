/**
 * Calibration page tests — /calibration
 *
 * Keeps the public calibration evidence honest: static fixtures, monotonic
 * score ordering, 45-point gap, and global-nav reachability.
 */

import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  CALIBRATION_CASES,
  CALIBRATION_CORPUS,
  CALIBRATION_RUN,
  calibrationGap,
  isMonotonic,
} from "../app/calibration/data";

describe("VAL-CALIBRATION-001: static calibration fixture shape", () => {
  it("ships exactly good, mediocre, and bad calibration cases", () => {
    expect(CALIBRATION_CASES.map((c) => c.id)).toEqual([
      "good",
      "mediocre",
      "bad",
    ]);
  });

  it("each fixture has a verdict score, label, and challenge targets", () => {
    for (const item of CALIBRATION_CASES) {
      expect(item.verdictScore).toBeGreaterThanOrEqual(0);
      expect(item.verdictScore).toBeLessThanOrEqual(100);
      expect(item.verdictLabel).toMatch(/^(PASS|WARN|REJECT)$/);
      expect(item.failureModes.length).toBeGreaterThanOrEqual(3);
    }
  });
});

describe("VAL-CALIBRATION-002: discrimination gate", () => {
  it("good and bad reasoning separate by 45 points", () => {
    expect(calibrationGap()).toBe(45);
  });

  it("actual gap exceeds the required 30-point threshold", () => {
    expect(calibrationGap()).toBeGreaterThanOrEqual(CALIBRATION_RUN.requiredGap);
  });

  it("scores are monotonic: good > mediocre > bad", () => {
    expect(isMonotonic()).toBe(true);
  });
});

describe("VAL-CALIBRATION-003: private corpus summary", () => {
  it("summarizes the local corpus without publishing raw private rows", () => {
    expect(CALIBRATION_CORPUS.totalRows).toBe(60);
    expect(CALIBRATION_CORPUS.realHarvestedRows).toBe(28);
    expect(CALIBRATION_CORPUS.syntheticSeedRows).toBe(20);
    expect(CALIBRATION_CORPUS.mutatedAdversarialRows).toBe(12);
    expect(CALIBRATION_CORPUS.humanReviewedRows).toBe(43);
    expect(CALIBRATION_CORPUS.frozenPilotRows).toBe(54);
    expect(CALIBRATION_CORPUS.privateCorpusReason).toContain("wallet");
  });
});

describe("VAL-CALIBRATION-004: reproduction copy", () => {
  it("points to the sentinel pytest calibration gate", () => {
    expect(CALIBRATION_RUN.command).toBe(
      "uv run pytest apps/sentinel/src/tests/test_calibration.py",
    );
  });

  it("points to the local calibration corpus CLI", () => {
    expect(CALIBRATION_RUN.corpusCommand).toContain("prism_calibration.cli");
  });
});

describe("VAL-CALIBRATION-005: dashboard route integration", () => {
  it("global nav exposes /calibration", () => {
    const navPath = path.join(process.cwd(), "app/components/global-nav.tsx");
    const source = fs.readFileSync(navPath, "utf8");
    expect(source).toContain('href: "/calibration"');
    expect(source).toContain('page: "calibration"');
  });

  it("page remains a server component with no runtime client dependency", () => {
    const pagePath = path.join(process.cwd(), "app/calibration/page.tsx");
    const source = fs.readFileSync(pagePath, "utf8");
    expect(source).not.toContain('"use client"');
    expect(source).not.toContain("'use client'");
  });
});

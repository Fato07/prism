export type CalibrationLabel = "good" | "mediocre" | "bad";
export type VerdictLabel = "PASS" | "WARN" | "REJECT";

export interface CalibrationCase {
  id: CalibrationLabel;
  title: string;
  qualityBand: string;
  traderPattern: string;
  expectedSentinelBehavior: string;
  verdictScore: number;
  verdictLabel: VerdictLabel;
  failureModes: readonly string[];
}

export const CALIBRATION_RUN = {
  evaluatedAt: "2026-05-13",
  command: "uv run pytest apps/sentinel/src/tests/test_calibration.py",
  requiredGap: 30,
  actualGap: 45,
  corpusCommand: "uv run python -m prism_calibration.cli --help",
} as const;

export const CALIBRATION_CASES = [
  {
    id: "good",
    title: "Good reasoning trace",
    qualityBand: "Coherent thesis, evidence-linked risks, calibrated uncertainty",
    traderPattern:
      "The trader states a bounded market thesis, cites evidence, names risk factors, and sizes the paper trade conservatively.",
    expectedSentinelBehavior:
      "Challenge residual uncertainty without inventing fatal flaws; allow capital to continue in paper mode.",
    verdictScore: 65,
    verdictLabel: "PASS",
    failureModes: [
      "Minor evidence freshness concerns",
      "Some volatility assumptions still need monitoring",
      "No thesis-breaking contradiction found",
    ],
  },
  {
    id: "mediocre",
    title: "Mediocre reasoning trace",
    qualityBand: "Partially supported but overconfident",
    traderPattern:
      "The trader uses plausible evidence but overweights one signal and under-specifies what would falsify the thesis.",
    expectedSentinelBehavior:
      "Warn on calibration and evidence sufficiency; require tighter uncertainty before capital scales.",
    verdictScore: 42,
    verdictLabel: "WARN",
    failureModes: [
      "Single-source evidence dependence",
      "Probability too high for the stated support",
      "Risk factors listed but not connected to sizing",
    ],
  },
  {
    id: "bad",
    title: "Bad reasoning trace",
    qualityBand: "Unsupported conclusion and broken calibration",
    traderPattern:
      "The trader jumps from vague market movement to a high-confidence action without a falsifiable thesis or evidence chain.",
    expectedSentinelBehavior:
      "Reject the trace; block capital movement and surface concrete reasoning failures.",
    verdictScore: 20,
    verdictLabel: "REJECT",
    failureModes: [
      "No reliable evidence chain",
      "Conclusion does not follow from premise",
      "Position sizing ignores downside risk",
    ],
  },
] as const satisfies readonly CalibrationCase[];

export function calibrationGap(cases: readonly CalibrationCase[] = CALIBRATION_CASES): number {
  const good = cases.find((c) => c.id === "good");
  const bad = cases.find((c) => c.id === "bad");
  if (!good || !bad) return 0;
  return good.verdictScore - bad.verdictScore;
}

export function isMonotonic(cases: readonly CalibrationCase[] = CALIBRATION_CASES): boolean {
  const byId = new Map(cases.map((c) => [c.id, c.verdictScore]));
  const good = byId.get("good");
  const mediocre = byId.get("mediocre");
  const bad = byId.get("bad");
  if (good === undefined || mediocre === undefined || bad === undefined) return false;
  return good > mediocre && mediocre > bad;
}

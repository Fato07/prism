import type { Metadata } from "next";
import { GlobalNav } from "@/components/global-nav";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { ScoreDonut } from "@/components/ui/score-donut";
import { Separator } from "@/components/ui/separator";
import {
  CALIBRATION_CASES,
  CALIBRATION_RUN,
  calibrationGap,
  isMonotonic,
  type CalibrationCase,
} from "./data";
import { Activity, ArrowDown, CheckCircle2, FlaskConical, GitBranch, ShieldCheck, Terminal } from "lucide-react";

export const metadata: Metadata = {
  title: "Calibration",
  description:
    "Calibration evidence for Prism's adversarial sentinel: good, mediocre, and bad reasoning traces separate by 45 points.",
};

const GAP = calibrationGap();
const MONOTONIC = isMonotonic();

export default function CalibrationPage() {
  return (
    <div className="min-h-screen bg-canvas text-fg">
      <GlobalNav currentPage="calibration" />

      <main className="mx-auto max-w-6xl px-6 pb-16 pt-10">
        <section className="mb-8 grid grid-cols-1 gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div>
            <Pill tone="sentinel" emphasis="glass" size="sm">
              <FlaskConical className="h-3.5 w-3.5" strokeWidth={2} />
              Sentinel calibration evidence
            </Pill>
            <h1 className="mt-4 max-w-3xl text-balance text-3xl font-semibold tracking-[var(--tracking-tight)] text-fg sm:text-5xl">
              Prism is not just two agents roleplaying disagreement.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-fg-muted sm:text-base">
              The sentinel has to separate sound reasoning from broken reasoning.
              This page shows the startup calibration gate: three synthetic traces,
              three expected quality bands, and a monotonic verdict spread.
            </p>
          </div>

          <Card tone="sentinel" className="self-start">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-[var(--color-sentinel)]" strokeWidth={2} />
                Gate result
              </CardTitle>
              <Pill tone={GAP >= CALIBRATION_RUN.requiredGap ? "good" : "warn"} emphasis="solid" size="xs">
                {GAP >= CALIBRATION_RUN.requiredGap ? "PASS" : "WARN"}
              </Pill>
            </CardHeader>
            <CardContent>
              <div className="flex items-end gap-3">
                <span className="text-mono text-6xl font-semibold leading-none text-fg">
                  {GAP}
                </span>
                <span className="pb-2 text-sm text-fg-muted">point gap</span>
              </div>
              <p className="mt-3 text-sm leading-6 text-fg-muted">
                Required: at least {CALIBRATION_RUN.requiredGap} points between
                good and bad reasoning. Actual: good=65, mediocre=42, bad=20.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Pill tone="good" emphasis="soft" size="xs">
                  <CheckCircle2 className="h-3 w-3" strokeWidth={2} />
                  monotonic: {MONOTONIC ? "yes" : "no"}
                </Pill>
                <Pill tone="neutral" emphasis="outline" size="xs">
                  evaluated {CALIBRATION_RUN.evaluatedAt}
                </Pill>
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-3">
          {CALIBRATION_CASES.map((item) => (
            <CalibrationCaseCard key={item.id} item={item} />
          ))}
        </section>

        <section className="mb-8">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-[var(--color-verdict-good)]" strokeWidth={2} />
                Separation proof
              </CardTitle>
              <Pill tone="neutral" emphasis="outline" size="xs">
                good &gt; mediocre &gt; bad
              </Pill>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 items-center gap-4 md:grid-cols-[1fr_auto_1fr_auto_1fr]">
                <ScoreBox label="good" score={65} verdict="PASS" tone="good" />
                <ArrowDown className="hidden h-5 w-5 -rotate-90 text-fg-faint md:block" strokeWidth={2} />
                <ScoreBox label="mediocre" score={42} verdict="WARN" tone="warn" />
                <ArrowDown className="hidden h-5 w-5 -rotate-90 text-fg-faint md:block" strokeWidth={2} />
                <ScoreBox label="bad" score={20} verdict="REJECT" tone="bad" />
              </div>
              <Separator className="my-5" />
              <p className="text-sm leading-6 text-fg-muted">
                The page is static by design: no live LLM call, no runtime MCP
                dependency, and no database dependency. It documents the calibration
                contract Prism uses before trusting the sentinel as a capital gate.
              </p>
            </CardContent>
          </Card>
        </section>

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Terminal className="h-4 w-4 text-fg-muted" strokeWidth={2} />
                Reproduce locally
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <CodeBlock>{CALIBRATION_RUN.command}</CodeBlock>
              <p className="text-sm leading-6 text-fg-muted">
                The broader corpus pipeline lives in `packages/calibration-python`:
                build, harvest, label, freeze, sync, eval, inspect, and validate.
              </p>
              <CodeBlock>{CALIBRATION_RUN.corpusCommand}</CodeBlock>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <GitBranch className="h-4 w-4 text-fg-muted" strokeWidth={2} />
                Why this matters
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-6 text-fg-muted">
                A same-family critic can share the trader's blind spots. Prism's
                sentinel is a different model family and must prove it can reject
                weak traces, warn on overconfident traces, and pass only traces
                with a coherent evidence chain. The 45-point spread is the
                minimum evidence that the validator is discriminating instead of
                rubber-stamping.
              </p>
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}

function CalibrationCaseCard({ item }: { item: CalibrationCase }) {
  const tone = item.id === "good" ? "good" : item.id === "mediocre" ? "warn" : "bad";
  const cardTone = item.id === "good" ? "verdict" : item.id === "mediocre" ? "default" : "sentinel";

  return (
    <Card tone={cardTone} className="h-full">
      <CardHeader className="items-start">
        <div>
          <CardTitle>{item.title}</CardTitle>
          <p className="mt-1 text-xs leading-5 text-fg-faint">{item.qualityBand}</p>
        </div>
        <Pill tone={tone} emphasis="solid" size="xs">
          {item.verdictLabel}
        </Pill>
      </CardHeader>
      <CardContent>
        <div className="mb-5 flex justify-center">
          <ScoreDonut score={item.verdictScore} label={item.verdictLabel} size="md" />
        </div>
        <div className="space-y-4 text-sm leading-6 text-fg-muted">
          <p>{item.traderPattern}</p>
          <p className="text-fg">{item.expectedSentinelBehavior}</p>
          <div>
            <p className="mb-2 text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-faint">
              Sentinel challenge targets
            </p>
            <ul className="space-y-1.5">
              {item.failureModes.map((mode) => (
                <li key={mode} className="flex gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-fg-faint" aria-hidden="true" />
                  <span>{mode}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ScoreBox({
  label,
  score,
  verdict,
  tone,
}: {
  label: string;
  score: number;
  verdict: string;
  tone: "good" | "warn" | "bad";
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)] p-4 text-center">
      <p className="text-mono text-[10px] uppercase tracking-[var(--tracking-wide)] text-fg-faint">
        {label}
      </p>
      <p className="mt-2 text-mono text-4xl font-semibold text-fg">{score}</p>
      <Pill tone={tone} emphasis="soft" size="xs" className="mt-2">
        {verdict}
      </Pill>
    </div>
  );
}

function CodeBlock({ children }: { children: string }) {
  return (
    <pre className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-canvas-sunken)] px-3 py-3 text-mono text-xs text-fg-muted">
      <code>{children}</code>
    </pre>
  );
}

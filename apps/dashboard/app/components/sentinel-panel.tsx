/**
 * Sentinel panel — displays the most recent adversarial verdict.
 * Server component — fetches verdict from DB and IPFS.
 */

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import type { SentinelVerdict } from "@/lib/schemas";

interface SentinelPanelProps {
  verdict: SentinelVerdict | null;
  responseUri: string | null;
  pendingMessage?: string;
}

function labelVariant(label: string): "reject" | "warn" | "pass" | "endorse" {
  const map: Record<string, "reject" | "warn" | "pass" | "endorse"> = {
    REJECT: "reject",
    WARN: "warn",
    PASS: "pass",
    ENDORSE: "endorse",
  };
  return map[label] ?? "warn";
}

/** Extract CID from an ipfs:// URI. */
function cidFromUri(uri: string): string | null {
  if (uri.startsWith("ipfs://")) return uri.slice(7);
  return null;
}

export function SentinelPanel({ verdict, responseUri, pendingMessage }: SentinelPanelProps) {
  if (!verdict) {
    return (
      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className="text-red-400">◆</span> Sentinel Challenges
          </CardTitle>
        </CardHeader>
        <CardContent>
          {pendingMessage ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="mb-3 animate-pulse text-2xl text-amber-400">⏳</div>
              <p className="text-sm text-amber-300">{pendingMessage}</p>
            </div>
          ) : (
            <EmptyState
              title="No verdicts yet"
              description="The sentinel has not reviewed any traces. Run the validation pipeline to populate this panel."
            />
          )}
        </CardContent>
      </Card>
    );
  }

  const verdictCid = responseUri ? cidFromUri(responseUri) : null;

  return (
    <Card className="h-full overflow-auto">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span className="text-red-400">◆</span> Sentinel Challenges
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Verdict Score + Label */}
        <div className="flex items-center gap-3">
          <Badge variant={labelVariant(verdict.verdict_label)}>
            {verdict.verdict_label}
          </Badge>
          <span className="font-mono text-2xl font-bold text-gray-100">
            {verdict.verdict_score}
          </span>
          <span className="text-xs text-gray-500">/100</span>
        </div>

        {/* Score bar */}
        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-800">
          <div
            className={`h-full rounded-full transition-all ${
              verdict.verdict_score >= 76
                ? "bg-emerald-500"
                : verdict.verdict_score >= 51
                  ? "bg-green-500"
                  : verdict.verdict_score >= 26
                    ? "bg-amber-500"
                    : "bg-red-500"
            }`}
            style={{ width: `${verdict.verdict_score}%` }}
          />
        </div>

        {/* Evidence Challenges */}
        <div>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
            Evidence Challenges ({verdict.evidence_challenges.length})
          </h4>
          <div className="space-y-2">
            {verdict.evidence_challenges.map((challenge, i) => (
              <div key={i} className="rounded border border-red-900/40 bg-red-950/20 p-3">
                <p className="text-sm text-red-200">
                  <span className="mr-1 font-mono text-xs text-red-400">#{i + 1}</span>
                  {challenge}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Thesis Challenges */}
        <div>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
            Thesis Challenges ({verdict.thesis_challenges.length})
          </h4>
          <div className="space-y-2">
            {verdict.thesis_challenges.map((challenge, i) => (
              <div key={i} className="rounded border border-amber-900/40 bg-amber-950/20 p-3">
                <p className="text-sm text-amber-200">
                  <span className="mr-1 font-mono text-xs text-amber-400">#{i + 1}</span>
                  {challenge}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Calibration Critique */}
        <div>
          <h4 className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-500">
            Calibration Critique
          </h4>
          <p className="text-sm text-gray-300">{verdict.calibration_critique}</p>
        </div>

        {/* Dialogue */}
        {verdict.dialogue_messages.length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
              Adversarial Dialogue
            </h4>
            <div className="space-y-2">
              {verdict.dialogue_messages.map((msg, i) => (
                <div key={i} className="rounded bg-gray-800/30 p-3">
                  <span className="mb-1 block text-xs font-medium uppercase text-gray-500">
                    {msg.role}
                  </span>
                  <p className="text-sm text-gray-300">{msg.content}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* IPFS link */}
        {verdictCid && (
          <div className="border-t border-gray-800 pt-3">
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-gray-500">
              On-Chain & IPFS
            </h4>
            <div className="text-xs">
              <span className="text-gray-500">Verdict CID: </span>
              <a
                href={`https://gateway.pinata.cloud/ipfs/${verdictCid}`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-blue-400 underline decoration-blue-400/30 hover:text-blue-300"
              >
                {verdictCid.slice(0, 20)}…
              </a>
            </div>
          </div>
        )}

        {/* Meta */}
        <div className="border-t border-gray-800 pt-3 text-xs text-gray-500">
          <div>Model: {verdict.model_name} ({verdict.model_family})</div>
          <div>Request Hash: <code className="font-mono">{verdict.request_hash.slice(0, 24)}…</code></div>
          <div>Created: {new Date(verdict.created_at).toLocaleString()}</div>
        </div>
      </CardContent>
    </Card>
  );
}

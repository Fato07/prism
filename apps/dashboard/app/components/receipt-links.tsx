/**
 * On-chain receipt links — clickable explorer links for the three
 * ERC-8004 transactions in the trader → sentinel → anchor pipeline.
 *
 * Uses HashChip for each tx hash so they're click-to-copy and open in
 * Arc explorer. Pending state shows a muted hash placeholder.
 */

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { HashChip } from "@/components/ui/hash-chip";
import { Hexagon, ChevronRight } from "lucide-react";

const ARC_EXPLORER = "https://testnet.arcscan.app";

interface ReceiptLinksProps {
  registrationTxHash: string | null;
  validationRequestTxHash: string | null;
  validationResponseTxHash: string | null;
}

interface ReceiptRowProps {
  step: string;
  label: string;
  contract: string;
  txHash: string | null;
}

function ReceiptRow({ step, label, contract, txHash }: ReceiptRowProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
      <div className="flex min-w-0 items-center gap-3">
        <span className="text-mono text-[10px] font-semibold uppercase tracking-[var(--tracking-wide)] text-fg-faint">
          {step}
        </span>
        <ChevronRight
          className="h-3 w-3 shrink-0 text-fg-faint"
          strokeWidth={2}
        />
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-fg">{label}</div>
          <div className="text-mono text-[10px] text-fg-faint">{contract}</div>
        </div>
      </div>

      {txHash ? (
        <HashChip
          value={txHash}
          href={`${ARC_EXPLORER}/tx/${txHash}`}
          truncate={6}
          size="sm"
        />
      ) : (
        <Pill tone="warn" emphasis="outline" size="xs">
          pending
        </Pill>
      )}
    </div>
  );
}

export function ReceiptLinks({
  registrationTxHash,
  validationRequestTxHash,
  validationResponseTxHash,
}: ReceiptLinksProps) {
  const total = [
    registrationTxHash,
    validationRequestTxHash,
    validationResponseTxHash,
  ].filter(Boolean).length;

  return (
    <Card tone="verdict">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Hexagon
            className="h-4 w-4 text-[var(--color-verdict-good)]"
            strokeWidth={1.8}
          />
          On-chain receipts
        </CardTitle>
        <Pill tone="good" emphasis="soft" size="xs">
          <span className="text-mono">{total}/3 anchored</span>
        </Pill>
      </CardHeader>
      <CardContent>
        <div className="divide-y divide-[var(--color-border)]">
          <ReceiptRow
            step="01"
            label="Agent registration"
            contract="IdentityRegistry"
            txHash={registrationTxHash}
          />
          <ReceiptRow
            step="02"
            label="Validation request"
            contract="ValidationRegistry"
            txHash={validationRequestTxHash}
          />
          <ReceiptRow
            step="03"
            label="Validation response"
            contract="ValidationRegistry"
            txHash={validationResponseTxHash}
          />
        </div>
      </CardContent>
    </Card>
  );
}

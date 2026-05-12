/**
 * On-chain receipt links — clickable links to Arc testnet explorer
 * for registration, validationRequest, and validationResponse transactions.
 */

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

const ARC_EXPLORER = "https://testnet.arcscan.app";

interface ReceiptLinksProps {
  registrationTxHash: string | null;
  validationRequestTxHash: string | null;
  validationResponseTxHash: string | null;
}

function ReceiptLink({ label, txHash, contractLabel }: {
  label: string;
  txHash: string | null;
  contractLabel: string;
}) {
  if (!txHash) {
    return (
      <div className="flex items-center justify-between py-2 text-sm">
        <span className="text-gray-400">{label}</span>
        <span className="text-xs text-gray-600">{contractLabel} — pending</span>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-between py-2 text-sm">
      <span className="text-gray-300">{label}</span>
      <a
        href={`${ARC_EXPLORER}/tx/${txHash}`}
        target="_blank"
        rel="noopener noreferrer"
        className="font-mono text-xs text-blue-400 underline decoration-blue-400/30 hover:text-blue-300"
      >
        {txHash.slice(0, 10)}…{txHash.slice(-8)}
      </a>
    </div>
  );
}

export function ReceiptLinks({
  registrationTxHash,
  validationRequestTxHash,
  validationResponseTxHash,
}: ReceiptLinksProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="text-purple-400">⬡</span> On-Chain Receipts
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="divide-y divide-gray-800">
          <ReceiptLink
            label="Agent Registration"
            txHash={registrationTxHash}
            contractLabel="IdentityRegistry"
          />
          <ReceiptLink
            label="Validation Request"
            txHash={validationRequestTxHash}
            contractLabel="ValidationRegistry"
          />
          <ReceiptLink
            label="Validation Response"
            txHash={validationResponseTxHash}
            contractLabel="ValidationRegistry"
          />
        </div>
      </CardContent>
    </Card>
  );
}

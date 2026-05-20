/**
 * Operator Control Plane — /operator
 *
 * Read-only runtime status page.  Displays the trader's 8‑field status via
 * the authenticated GET /api/admin/runtime proxy.  An admin token (password
 * input) gates data access — without a valid token the page shows only an
 * auth‑required prompt.
 *
 * This is a server component shell.  Auth handling and data fetching are
 * client‑side in <OperatorShell>.
 *
 * No mutation buttons yet — read‑only surface only.
 */

import type { Metadata } from "next";
import { GlobalNav } from "@/components/global-nav";
import { OperatorShell } from "./operator-shell";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Operator",
};

export default function OperatorPage() {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-canvas text-fg">
      <GlobalNav currentPage="operator" />

      <main className="mx-auto max-w-3xl px-6 pb-16 pt-8">
        <OperatorShell />
      </main>
    </div>
  );
}

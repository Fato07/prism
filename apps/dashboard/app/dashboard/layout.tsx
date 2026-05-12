/**
 * Dashboard layout — sets metadata for /dashboard route.
 */

import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Dashboard",
  description: "Prism dashboard — live adversarial validation on Arc testnet",
};

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(
    process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3200"
  ),
  title: {
    default: "Prism — The First Adversarial AI Validator on ERC-8004",
    template: "%s | Prism",
  },
  description:
    "Prism is the first adversarial AI validator on ERC-8004. Two agents — a trader and a sentinel — challenge each other's reasoning with on-chain proof on Arc. Join the waitlist.",
  openGraph: {
    title: "Prism — Adversarial AI Validator on ERC-8004",
    description:
      "Two agents challenge each other's reasoning. On-chain proof on Arc. Join the waitlist for early access.",
    type: "website",
    siteName: "Prism",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "Prism — Adversarial AI Validator on ERC-8004",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Prism — Adversarial AI Validator on ERC-8004",
    description:
      "Two agents challenge each other's reasoning. On-chain proof on Arc.",
    images: ["/og-image.png"],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 antialiased">{children}</body>
    </html>
  );
}

import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import Web3ProviderDynamic from "@/context/web3-provider-ssr";
import "./globals.css";

export const viewport: Viewport = {
  themeColor: "#0F1018",
  colorScheme: "dark",
};

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
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
    apple: [
      { url: "/apple-icon.svg", type: "image/svg+xml", sizes: "180x180" },
    ],
  },
  manifest: "/manifest.json",
  applicationName: "Prism",
  appleWebApp: {
    title: "Prism",
    statusBarStyle: "black-translucent",
  },
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

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const headersList = await headers();
  const cookies = headersList.get("cookie");

  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
      suppressHydrationWarning
    >
      <body className="bg-canvas text-fg antialiased font-sans selection:bg-trader/30 selection:text-trader-fg">
        <Web3ProviderDynamic cookies={cookies}>{children}</Web3ProviderDynamic>
      </body>
    </html>
  );
}

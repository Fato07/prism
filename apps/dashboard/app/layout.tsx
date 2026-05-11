import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Prism — See Through the Reasoning",
  description: "Adversarial AI validator on ERC-8004",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 antialiased">{children}</body>
    </html>
  );
}

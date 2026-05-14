import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: [
    "pg",
    // Wagmi / Reown ecosystem — these are client-only packages with
    // optional dynamic imports (e.g. `accounts`) that Next.js server
    // bundling cannot resolve. Marking them as external avoids the
    // "Module not found: Can't resolve 'accounts'" build error.
    "wagmi",
    "@wagmi/core",
    "@wagmi/connectors",
    "@reown/appkit",
    "@reown/appkit-adapter-wagmi",
    "@reown/appkit-utils",
    "@tanstack/react-query",
    "viem",
    "abitype",
    "accounts",
  ],
  // Set to monorepo root so standalone output traces workspace packages correctly
  outputFileTracingRoot: path.join(__dirname, "../../"),
};

export default nextConfig;

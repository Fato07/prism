import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  output: "standalone",
  serverExternalPackages: ["pg"],
  // Set to monorepo root so standalone output traces workspace packages correctly
  outputFileTracingRoot: path.join(__dirname, "../../"),
};

export default nextConfig;

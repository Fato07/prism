import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "node",
    include: ["__tests__/**/*.test.{ts,tsx}"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./app"),
      "@prism/schemas": path.resolve(__dirname, "../../packages/schemas-typescript/src"),
      "@prism/arc-contracts": path.resolve(__dirname, "../../packages/arc-contracts/src"),
    },
  },
});

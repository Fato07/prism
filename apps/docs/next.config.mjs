import path from 'node:path';

import { createMDX } from 'fumadocs-mdx/next';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  outputFileTracingRoot: path.join(process.cwd(), '../..'),
};

const withMDX = createMDX();

export default withMDX(nextConfig);

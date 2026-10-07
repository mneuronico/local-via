import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "export",
  // The hub serves /admin/ as admin/index.html.
  trailingSlash: true,
  turbopack: { root: process.cwd() },
};

export default nextConfig;

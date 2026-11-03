import type { NextConfig } from "next";

const repoName = "examgen-ai";
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath: process.env.NODE_ENV === "production" ? `/${repoName}` : "",
  images: { unoptimized: true },
  poweredByHeader: false,
};

export default nextConfig;

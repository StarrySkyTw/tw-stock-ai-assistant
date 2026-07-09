import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const appDir = dirname(fileURLToPath(import.meta.url));

const nextConfig = {
  reactStrictMode: true,
  output: process.env.NEXT_OUTPUT_MODE === "export" ? "export" : "standalone",
  outputFileTracingRoot: appDir,
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || ""
  }
};

export default nextConfig;
